"""워크플로우 실행 (멀티 파일 러너)"""

import os
import re
import json
import glob
import argparse

from langchain_openai import ChatOpenAI

from medical_workflow.config import load_env_keys
from medical_workflow.state import WFState
from medical_workflow.stores import THREAD_STORE, VISIT_STORE
from medical_workflow.graph import build_graph
from medical_workflow.nodes.rag import build_medical_vector_db
from medical_workflow.pii_middleware import redact_pii


def _setup_workflow(project_root: str, reset_stores: bool = False):
    """LLM, RAG, 그래프 초기화 (txt/xlsx 공통)"""
    if reset_stores:
        THREAD_STORE.clear()
        VISIT_STORE.clear()

    llm = ChatOpenAI(
        model="solar-pro2",
        base_url="https://api.upstage.ai/v1",
        api_key=os.environ.get("UPSTAGE_API_KEY"),
        temperature=0.1,
    )

    data_path = os.path.join(project_root, "data", "medical_2.csv")
    if not os.path.isfile(data_path):
        raise FileNotFoundError(f"의료 RAG용 데이터 파일이 없습니다: {data_path}")

    print("[STEP] building vector db...", flush=True)
    persist_path = os.path.join(project_root, "data", "chroma_db")
    vector_db = build_medical_vector_db(file_path=data_path, persist_dir=persist_path)
    print("[STEP] vector db ready", flush=True)

    retriever = vector_db.as_retriever(search_kwargs={"k": 1})

    print("[STEP] building graph...", flush=True)
    graph = build_graph(llm, retriever)
    print("[STEP] graph ready", flush=True)

    return graph


def _process_single(graph, base_state: WFState, label: str) -> None:
    """단일 케이스 처리 (1차 호출 + HITL 2차 호출)"""
    print(f"\n===== {label} =====")

    # PII Middleware: graph.invoke() 전에 이름 비식별화 적용
    base_state = {**base_state, "redacted_transcript": redact_pii(base_state.get("transcript", ""))}

    result1 = graph.invoke(base_state)
    print(json.dumps(result1.get("final_answer", {}), ensure_ascii=False, indent=2))

    hitl = result1.get("hitl_payload")
    if hitl:
        print("\n" + "=" * 50)
        print(json.dumps(hitl, ensure_ascii=False, indent=2))
        ans = input("\n알람/일정표 생성? (yes/no): ").strip().lower()
        alarm_opt_in = ans in ("y", "yes")

        state2: WFState = {
            **result1,
            "alarm_opt_in": alarm_opt_in,
            "hitl_payload": None,
        }
        result2 = graph.invoke(state2)

        print("\n최종 결과:")
        print(json.dumps(result2.get("final_answer", {}), ensure_ascii=False, indent=2))


def run_many(input_dir: str, default_patient_id: str = "p1", reset_stores: bool = False):
    """
    지정된 디렉토리에서 Recording_*.txt 파일들을 읽어서 처리

    Args:
        input_dir: 입력 파일이 있는 디렉토리
        default_patient_id: 기본 환자 ID
        reset_stores: True면 기존 스레드/방문 저장소 초기화
    """
    project_root = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )
    graph = _setup_workflow(project_root, reset_stores)

    paths = sorted(glob.glob(os.path.join(input_dir, "Recording_*.txt")))
    if not paths:
        print(f"Recording_*.txt 파일을 찾을 수 없습니다: {input_dir}")
        return

    print(f"\n총 {len(paths)}개의 파일을 처리합니다.\n")

    for i, path in enumerate(paths, 1):
        fn = os.path.basename(path)
        m = re.search(r"Recording_(\d{8})\.txt$", fn)
        visit_id = f"v_{m.group(1)}" if m else f"v_{i}"

        with open(path, "r", encoding="utf-8") as f:
            transcript = f.read()

        base_state: WFState = {
            "patient_id": default_patient_id,
            "visit_id": visit_id,
            "input_filename": fn,
            "transcript": transcript,
            "alarm_opt_in": None,
            "hitl_payload": None,
        }

        _process_single(graph, base_state, f"[{i}/{len(paths)}] {fn}")


def run_from_xlsx(patient_filter: str, xlsx_path: str, reset_stores: bool = False):
    """
    testcase xlsx 파일에서 특정 환자의 인터뷰를 읽어 처리

    Args:
        patient_filter: 처리할 환자 ID (예: "p01")
        xlsx_path: testcase xlsx 파일 경로
        reset_stores: True면 기존 스레드/방문 저장소 초기화
    """
    import pandas as pd

    if not os.path.isfile(xlsx_path):
        raise FileNotFoundError(f"testcase 파일을 찾을 수 없습니다: {xlsx_path}")

    df = pd.read_excel(xlsx_path)

    # B열(patient) 기준 필터링
    patient_rows = df[df["patient"] == patient_filter].reset_index(drop=True)

    if patient_rows.empty:
        print(f"환자 ID '{patient_filter}'에 해당하는 데이터가 없습니다.")
        print(f"사용 가능한 환자 ID: {sorted(df['patient'].unique().tolist())}")
        return

    print(f"환자 '{patient_filter}': {len(patient_rows)}건 발견\n")

    project_root = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )
    graph = _setup_workflow(project_root, reset_stores)

    for i, row in patient_rows.iterrows():
        case_idx = int(row["index"])
        base_state: WFState = {
            "patient_id": str(row["patient"]),
            "visit_id": f"v_{case_idx:04d}",
            "input_filename": f"xlsx_case_{case_idx:04d}.txt",
            "transcript": str(row["interview"]),
            "visit_date": f"case_{case_idx:04d}",
            "alarm_opt_in": None,
            "hitl_payload": None,
        }

        label = f"[{i + 1}/{len(patient_rows)}] patient={row['patient']}  diagnosis={row['diagnosis']}  case={case_idx}"
        _process_single(graph, base_state, label)


def main():
    """메인 함수 (root main.py에서 import 해서 호출되는 진입점)"""
    load_env_keys()

    runner_dir = os.path.dirname(os.path.abspath(__file__))     # .../src/medical_workflow
    project_root = os.path.dirname(os.path.dirname(runner_dir)) # project root

    default_recordings_dir = os.path.join(project_root, "data", "recordings")
    default_xlsx_path = os.path.join(project_root, "data", "testcase(50).xlsx")

    parser = argparse.ArgumentParser(
        description="의료 진료 전사 분석 워크플로우",
        add_help=True,
    )
    # 위치 인수: 환자 ID를 주면 xlsx 모드, 생략하면 txt 모드
    parser.add_argument(
        "patient_id",
        nargs="?",
        default=None,
        help="환자 ID (예: p01). 지정 시 xlsx 모드로 실행됩니다.",
    )
    parser.add_argument("--input_dir", default=default_recordings_dir)
    parser.add_argument("--xlsx", default=default_xlsx_path, help="testcase xlsx 경로")
    parser.add_argument("--reset_stores", action="store_true")
    args = parser.parse_args()

    print("=" * 60)
    print("의료 진료 전사 분석 워크플로우")
    print("=" * 60)

    if args.patient_id:
        # ── xlsx 모드: 특정 환자 케이스 처리 ─────────────────────
        print(f"\n[xlsx 모드] 환자: {args.patient_id}  파일: {args.xlsx}\n")
        run_from_xlsx(
            patient_filter=args.patient_id,
            xlsx_path=args.xlsx,
            reset_stores=args.reset_stores,
        )
    else:
        # ── txt 모드: Recording_*.txt 파일 처리 ──────────────────
        print(f"\n[txt 모드] 입력 디렉토리: {args.input_dir}\n")
        run_many(
            args.input_dir,
            reset_stores=args.reset_stores,
        )

    print("\n" + "=" * 60)
    print("처리 완료")
    print("=" * 60)
