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


def run_many(input_dir: str, default_patient_id: str = "p1", reset_stores: bool = False):
    """
    지정된 디렉토리에서 Recording_*.txt 파일들을 읽어서 처리

    Args:
        input_dir: 입력 파일이 있는 디렉토리
        default_patient_id: 기본 환자 ID
        reset_stores: True면 기존 스레드/방문 저장소 초기화
    """
    if reset_stores:
        THREAD_STORE.clear()
        VISIT_STORE.clear()

    llm = ChatOpenAI(
        model="solar-pro2",
        base_url="https://api.upstage.ai/v1",
        api_key=os.environ.get("UPSTAGE_API_KEY"),
        temperature=0.1,
    )

    # 의료 정보 신뢰성을 위해 RAG(벡터 DB) 사용, Tavily 검색 미사용
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    data_path = os.path.join(project_root, "data", "medical_2.csv")
    if not os.path.isfile(data_path):
        raise FileNotFoundError(f"의료 RAG용 데이터 파일이 없습니다: {data_path}")

    # 여기가 멈추는지 확인하고 싶으면 이 2줄을 남겨둬도 됨
    print("[STEP] building vector db...", flush=True)
    persist_path = os.path.join(project_root, "data", "chroma_db")

    vector_db = build_medical_vector_db(
        file_path=data_path,
        persist_dir=persist_path,
    )
    
    print("[STEP] vector db ready", flush=True)

    retriever = vector_db.as_retriever(search_kwargs={"k": 3})

    print("[STEP] building graph...", flush=True)
    graph = build_graph(llm, retriever)
    print("[STEP] graph ready", flush=True)

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

        print(f"\n===== [{i}/{len(paths)}] {fn} =====")

        # 1차 호출
        result1 = graph.invoke(base_state)

        # 방문 처리 결과 출력
        print(json.dumps(result1.get("final_answer", {}), ensure_ascii=False, indent=2))

        # HITL 질문이 있으면 질문 출력 후 2차 호출
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


def main():
    """메인 함수 (root main.py에서 import 해서 호출되는 진입점)"""
    load_env_keys()

    # runner.py는 src/medical_workflow/ 안에 있으므로 프로젝트 루트 계산
    input_dir = os.path.dirname(os.path.abspath(__file__))          # .../src/medical_workflow
    project_root = os.path.dirname(os.path.dirname(input_dir))      # project root

    default_recordings_dir = os.path.join(project_root, "data", "recordings")

    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--input_dir", default=default_recordings_dir)
    parser.add_argument("--patient_id", default="p1")
    parser.add_argument("--reset_stores", action="store_true")
    args, _ = parser.parse_known_args()

    print("=" * 60)
    print("의료 진료 전사 분석 워크플로우")
    print("=" * 60)
    print(f"\n입력 디렉토리: {args.input_dir}")

    run_many(args.input_dir, default_patient_id=args.patient_id, reset_stores=args.reset_stores)

    print("\n" + "=" * 60)
    print("처리 완료")
    print("=" * 60)