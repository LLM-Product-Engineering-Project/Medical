"""
test_rag_integration.py

RAG 통합 테스트 — xlsx에서 특정 환자 데이터를 읽어
extract_clinical 결과를 그대로 이어받아 RAG 파이프라인을 검증한다.

파이프라인:
  transcript → n_extract_clinical
    → has_guideline 분기
        True (가이드라인 ≤ 2)  : n_rag_query_sanitize → n_rag_search → n_rag_supplement
        False                  : n_rag_query_sanitize → n_rag_search → n_rag_to_guidelines → n_rag_supplement

실행 방법:
    cd C:/Users/yebin/Desktop/Medical
    python tests/test_rag_integration.py --patient p01
"""

import os
import sys
import json
import argparse

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(project_root, "src"))

from langchain_openai import ChatOpenAI
from medical_workflow.config import load_env_keys
from medical_workflow.state import WFState
from medical_workflow.nodes.input import n_deidentify_redact
from medical_workflow.nodes.extraction import n_extract_clinical
from medical_workflow.nodes.rag import build_medical_vector_db, n_rag_search
from medical_workflow.nodes.search import n_rag_query_sanitize, n_rag_to_guidelines, n_rag_supplement


def run_case(llm, retriever, transcript: str, label: str = "") -> None:
    print(f"\n{'=' * 70}")
    if label:
        print(f"케이스: {label}")
    print("=" * 70)

    # ── 1. 전처리 + 임상 추출 ─────────────────────────────────────────────
    s: WFState = {"transcript": transcript, "errors": [], "warnings": []}
    s = n_deidentify_redact(s)
    s = n_extract_clinical(s, llm)

    extracted = s.get("extracted", {})
    diagnosis = (extracted.get("diagnoses") or [{}])[0].get("name", "")
    doctor_guidelines = extracted.get("doctor_guidelines", [])
    has_guideline = bool(doctor_guidelines)

    s["diagnosis_key"] = diagnosis
    s["has_guideline"] = has_guideline

    print(f"\n[추출 결과]")
    print(f"  진단명        : {diagnosis}")
    print(f"  doctor_guidelines ({len(doctor_guidelines)}개): "
          + json.dumps(doctor_guidelines, ensure_ascii=False))

    # ── 2. RAG 쿼리 생성 ─────────────────────────────────────────────────
    print(f"\n[STEP 1] RAG 쿼리 생성")
    s = n_rag_query_sanitize(s, llm)
    print(f"  rag_query: {s.get('rag_query')}")

    # ── 3. RAG 검색 ──────────────────────────────────────────────────────
    print(f"\n[STEP 2] RAG 검색")
    s = n_rag_search(s, retriever)
    rag_raw = s.get("rag_raw", "")
    print(f"  검색 결과 ({len(rag_raw)}자):")
    print("  " + rag_raw[:400].replace("\n", "\n  "))

    # ── 4. 분기: has_guideline 여부에 따라 경로 다름 ────────────────────
    if not has_guideline:
        print(f"\n[STEP 3] rag_to_guidelines (has_guideline=False 경로)")
        s = n_rag_to_guidelines(s, llm)
        print(json.dumps(s.get("rag_guidelines"), ensure_ascii=False, indent=2))

    # ── 5. rag_supplement (공통) ─────────────────────────────────────────
    print(f"\n[STEP {'4' if not has_guideline else '3'}] rag_supplement")
    before_all = doctor_guidelines if has_guideline else (s.get("rag_guidelines") or [])
    before_actionable = [g for g in before_all if g.get("category") != "other"]
    s = n_rag_supplement(s, llm, retriever)

    if has_guideline:
        after = (s.get("extracted") or {}).get("doctor_guidelines", [])
    else:
        after = s.get("rag_guidelines") or []
    after_actionable = [g for g in after if g.get("category") != "other"]

    print(f"  보완 전: 전체 {len(before_all)}개 (actionable {len(before_actionable)}개, other 제외)")
    print(f"  보완 후: 전체 {len(after)}개 (actionable {len(after_actionable)}개)")
    print(json.dumps(after, ensure_ascii=False, indent=2))

    if s.get("errors"):
        print("\n[에러]")
        print(json.dumps(s["errors"], ensure_ascii=False, indent=2))


def main():
    load_env_keys()

    parser = argparse.ArgumentParser()
    parser.add_argument("--patient", required=True, help="환자 ID (예: p01)")
    parser.add_argument(
        "--xlsx",
        default=os.path.join(project_root, "data", "testcase(50).xlsx"),
    )
    args = parser.parse_args()

    import pandas as pd

    if not os.path.isfile(args.xlsx):
        print(f"xlsx 파일을 찾을 수 없습니다: {args.xlsx}")
        sys.exit(1)

    df = pd.read_excel(args.xlsx)
    rows = df[df["patient"] == args.patient].reset_index(drop=True)

    if rows.empty:
        print(f"환자 ID '{args.patient}'에 해당하는 데이터가 없습니다.")
        print(f"사용 가능한 환자 ID: {sorted(df['patient'].unique().tolist())}")
        sys.exit(1)

    print(f"환자 '{args.patient}': {len(rows)}건 발견")

    llm = ChatOpenAI(
        model="solar-pro2",
        base_url="https://api.upstage.ai/v1",
        api_key=os.environ.get("UPSTAGE_API_KEY"),
        temperature=0.1,
    )

    data_path = os.path.join(project_root, "data", "medical_2.csv")
    persist_path = os.path.join(project_root, "data", "chroma_db")
    print("\n[VectorDB 로드 중...]")
    vector_db = build_medical_vector_db(file_path=data_path, persist_dir=persist_path)
    retriever = vector_db.as_retriever(search_kwargs={"k": 1})
    print("[VectorDB 준비 완료]")

    for _, row in rows.iterrows():
        label = f"patient={row['patient']}  diagnosis={row['diagnosis']}  index={row['index']}"
        run_case(llm, retriever, str(row["interview"]), label=label)


if __name__ == "__main__":
    main()
