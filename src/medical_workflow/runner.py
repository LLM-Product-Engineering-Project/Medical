"""워크플로우 실행 (멀티 파일 러너)"""

import os
import re
import json
import glob

from langchain_openai import ChatOpenAI
from langchain_tavily import TavilySearch

from medical_workflow.config import load_env_keys
from medical_workflow.state import WFState
from medical_workflow.stores import THREAD_STORE, VISIT_STORE
from medical_workflow.graph import build_graph


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
    tavily = TavilySearch(api_key=os.environ.get("TAVILY_API_KEY"))
    graph = build_graph(llm, tavily)

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
    """메인 함수"""
    load_env_keys()

    input_dir = os.path.dirname(os.path.abspath(__file__))
    # runner.py는 src/medical_workflow/ 안에 있으므로 프로젝트 루트 계산
    project_root = os.path.dirname(os.path.dirname(input_dir))

    print("=" * 60)
    print("의료 진료 전사 분석 워크플로우")
    print("=" * 60)
    print(f"\n입력 디렉토리: {project_root}")

    run_many(project_root, reset_stores=False)

    print("\n" + "=" * 60)
    print("처리 완료")
    print("=" * 60)
