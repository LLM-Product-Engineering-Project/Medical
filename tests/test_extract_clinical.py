"""
test_extract_clinical.py

n_extract_clinical 단독 테스트 — xlsx에서 특정 환자의 인터뷰를 읽어
임상 정보 추출 결과(diagnoses, doctor_guidelines)를 확인한다.

실행 방법:
    cd C:/Users/yebin/Desktop/Medical
    python tests/test_extract_clinical.py --patient p01
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


def run_case(llm, transcript: str, label: str = "") -> None:
    print(f"\n{'=' * 70}")
    if label:
        print(f"케이스: {label}")
    print("=" * 70)

    s: WFState = {"transcript": transcript, "errors": [], "warnings": []}
    s = n_deidentify_redact(s)
    result = n_extract_clinical(s, llm)

    print("\n[원본 transcript]")
    print(transcript)

    print("\n[추출된 임상 정보]")
    print(json.dumps(result.get("extracted"), ensure_ascii=False, indent=2))

    if result.get("errors"):
        print("\n[에러]")
        print(json.dumps(result["errors"], ensure_ascii=False, indent=2))
    if result.get("warnings"):
        print("\n[경고]")
        print(result["warnings"])


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

    for _, row in rows.iterrows():
        label = f"patient={row['patient']}  diagnosis={row['diagnosis']}  index={row['index']}"
        run_case(llm, str(row["interview"]), label=label)


if __name__ == "__main__":
    main()
