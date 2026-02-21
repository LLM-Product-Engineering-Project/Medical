"""
test_detect_closure.py

치료 종료 감지 노드 (n_detect_closure) 단독 테스트

실행 방법:
    cd C:/Users/yebin/Desktop/Medical
    python tests/test_detect_closure.py
"""

import os
import sys
import json

# 프로젝트 루트를 경로에 추가
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(project_root, "src"))

from langchain_openai import ChatOpenAI
from medical_workflow.config import load_env_keys
from medical_workflow.state import WFState
from medical_workflow.nodes.thread import n_detect_closure


def test_detect_closure():
    """치료 종료 감지 노드 테스트"""
    print("=" * 70)
    print("테스트: n_detect_closure (치료 종료 감지)")
    print("=" * 70)

    # 환경 변수 로드
    load_env_keys()

    # LLM 초기화
    llm = ChatOpenAI(
        model="solar-pro2",
        base_url="https://api.upstage.ai/v1",
        api_key=os.environ.get("UPSTAGE_API_KEY"),
        temperature=0.1,
    )

    # 테스트 케이스 1: 치료 종료 (완치)
    print("\n[테스트 케이스 1] 치료 종료 - 완치 선언")
    print("-" * 70)

    sample_state1: WFState = {
        "patient_id": "test_p1",
        "visit_id": "test_v1",
        "diagnosis_key": "급성폐렴",
        "doctor_text": """
오늘 검사 결과 폐렴이 완전히 나았습니다.
더 이상 약을 드실 필요가 없습니다.
급성폐렴 치료를 종료하겠습니다. 건강하세요!
        """.strip(),
        "errors": [],
        "warnings": [],
    }

    result1 = n_detect_closure(sample_state1, llm)

    print("\n[입력]")
    print(f"diagnosis_key: {sample_state1['diagnosis_key']}")
    print(f"doctor_text: {sample_state1['doctor_text']}")

    print("\n[출력]")
    print(f"should_close: {result1.get('should_close')}")

    print("\n[에러/경고]")
    print(f"Errors: {len(result1.get('errors', []))}")
    print(f"Warnings: {len(result1.get('warnings', []))}")

    # 테스트 케이스 2: 치료 계속 (경과 관찰)
    print("\n\n[테스트 케이스 2] 치료 계속 - 경과 관찰")
    print("-" * 70)

    sample_state2: WFState = {
        "patient_id": "test_p2",
        "visit_id": "test_v2",
        "diagnosis_key": "당뇨병",
        "doctor_text": """
오늘 혈당 수치가 조금 좋아졌습니다.
계속 약을 드시고, 식이요법을 유지하세요.
3개월 후에 다시 검사하러 오세요.
        """.strip(),
        "errors": [],
        "warnings": [],
    }

    result2 = n_detect_closure(sample_state2, llm)

    print("\n[입력]")
    print(f"diagnosis_key: {sample_state2['diagnosis_key']}")
    print(f"doctor_text: {sample_state2['doctor_text']}")

    print("\n[출력]")
    print(f"should_close: {result2.get('should_close')}")

    print("\n[에러/경고]")
    print(f"Errors: {len(result2.get('errors', []))}")
    print(f"Warnings: {len(result2.get('warnings', []))}")

    # 테스트 케이스 3: 애매한 상황
    print("\n\n[테스트 케이스 3] 애매한 상황 - 경과는 좋지만 추적 필요")
    print("-" * 70)

    sample_state3: WFState = {
        "patient_id": "test_p3",
        "visit_id": "test_v3",
        "diagnosis_key": "골절",
        "doctor_text": """
뼈가 많이 붙었습니다. 회복이 잘 되고 있어요.
깁스는 풀어도 되지만, 아직 무리하면 안 됩니다.
2주 후에 마지막으로 엑스레이 찍으러 오세요.
        """.strip(),
        "errors": [],
        "warnings": [],
    }

    result3 = n_detect_closure(sample_state3, llm)

    print("\n[입력]")
    print(f"diagnosis_key: {sample_state3['diagnosis_key']}")
    print(f"doctor_text: {sample_state3['doctor_text']}")

    print("\n[출력]")
    print(f"should_close: {result3.get('should_close')}")

    print("\n[에러/경고]")
    print(f"Errors: {len(result3.get('errors', []))}")
    print(f"Warnings: {len(result3.get('warnings', []))}")

    # 테스트 케이스 4: 치료 종료 (전원/이송)
    print("\n\n[테스트 케이스 4] 치료 종료 - 다른 병원으로 전원")
    print("-" * 70)

    sample_state4: WFState = {
        "patient_id": "test_p4",
        "visit_id": "test_v4",
        "diagnosis_key": "암",
        "doctor_text": """
더 정밀한 치료가 필요합니다.
대학병원으로 전원하시는 것이 좋겠습니다.
여기서의 치료는 이것으로 종료하고, 소견서를 작성해드리겠습니다.
        """.strip(),
        "errors": [],
        "warnings": [],
    }

    result4 = n_detect_closure(sample_state4, llm)

    print("\n[입력]")
    print(f"diagnosis_key: {sample_state4['diagnosis_key']}")
    print(f"doctor_text: {sample_state4['doctor_text']}")

    print("\n[출력]")
    print(f"should_close: {result4.get('should_close')}")

    print("\n[에러/경고]")
    print(f"Errors: {len(result4.get('errors', []))}")
    print(f"Warnings: {len(result4.get('warnings', []))}")

    print("\n" + "=" * 70)
    print("테스트 완료")
    print("=" * 70)


if __name__ == "__main__":
    test_detect_closure()
