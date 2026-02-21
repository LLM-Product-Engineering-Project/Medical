"""
test_summarize_guidelines.py

가이드라인 요약 노드 (n_summarize_guidelines) 단독 테스트

실행 방법:
    cd C:/Users/yebin/Desktop/Medical
    python tests/test_summarize_guidelines.py
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
from medical_workflow.nodes.guidelines import n_summarize_guidelines


def test_summarize_guidelines():
    """가이드라인 요약 노드 테스트"""
    print("=" * 70)
    print("테스트: n_summarize_guidelines (가이드라인 요약)")
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

    # 테스트 케이스 1: 간단한 진료 내용
    print("\n[테스트 케이스 1] 간단한 진료 내용 - 감기")
    print("-" * 70)

    sample_state1: WFState = {
        "patient_id": "test_p1",
        "visit_id": "test_v1",
        "doctor_text": """
감기 증상이 있으시네요.
약 처방해드릴게요. 따뜻한 물 많이 드시고 충분히 쉬세요.
3일 후에도 증상이 지속되면 다시 오세요.
        """.strip(),
        "errors": [],
        "warnings": [],
    }

    result1 = n_summarize_guidelines(sample_state1, llm)

    print("\n[입력]")
    print(f"doctor_text: {sample_state1['doctor_text']}")

    print("\n[출력]")
    print(f"doctor_summary: {result1.get('doctor_summary')}")

    print("\n[에러/경고]")
    print(f"Errors: {len(result1.get('errors', []))}")
    print(f"Warnings: {len(result1.get('warnings', []))}")

    # 테스트 케이스 2: 복잡한 당뇨병 관리 지침
    print("\n\n[테스트 케이스 2] 복잡한 당뇨병 관리 지침")
    print("-" * 70)

    sample_state2: WFState = {
        "patient_id": "test_p2",
        "visit_id": "test_v2",
        "doctor_text": """
당뇨병 관리를 위해서는 여러 가지를 지켜야 합니다.
첫째, 식이요법입니다. 단순당이 들어간 음식을 피하고, 복합 탄수화물 위주로 드세요.
하루 세 끼를 규칙적으로 먹되, 과식하지 마세요.
둘째, 운동입니다. 매일 30분 이상 걷기를 하시고, 식후에 가벼운 산책을 하세요.
셋째, 약물 복용입니다. 메트포르민을 하루 두 번 식후에 드세요. 절대 빠뜨리지 마세요.
넷째, 혈당 측정입니다. 아침 공복과 식후 2시간에 혈당을 체크하세요.
다섯째, 정기 검진입니다. 3개월마다 병원에 오셔서 당화혈색소를 체크하세요.
발 관리도 중요합니다. 매일 발을 씻고 상처가 있는지 확인하세요.
        """.strip(),
        "errors": [],
        "warnings": [],
    }

    result2 = n_summarize_guidelines(sample_state2, llm)

    print("\n[입력]")
    print(f"doctor_text: {sample_state2['doctor_text'][:100]}...")

    print("\n[출력]")
    print(f"doctor_summary: {result2.get('doctor_summary')}")

    print("\n[에러/경고]")
    print(f"Errors: {len(result2.get('errors', []))}")
    print(f"Warnings: {len(result2.get('warnings', []))}")

    # 테스트 케이스 3: 고혈압 + 운동 제한
    print("\n\n[테스트 케이스 3] 고혈압 + 운동 제한")
    print("-" * 70)

    sample_state3: WFState = {
        "patient_id": "test_p3",
        "visit_id": "test_v3",
        "doctor_text": """
혈압이 높습니다. 지금부터 저염식을 하셔야 합니다.
염분은 하루 5g 이하로 제한하고, 가공식품을 피하세요.
운동은 중요하지만, 갑자기 무리하면 안 됩니다.
천천히 시작해서 점진적으로 강도를 높이세요.
혈압약은 아침에 한 알씩 드시고, 혈압을 매일 체크하세요.
술과 담배는 반드시 끊으셔야 합니다.
        """.strip(),
        "errors": [],
        "warnings": [],
    }

    result3 = n_summarize_guidelines(sample_state3, llm)

    print("\n[입력]")
    print(f"doctor_text: {sample_state3['doctor_text'][:100]}...")

    print("\n[출력]")
    print(f"doctor_summary: {result3.get('doctor_summary')}")

    print("\n[에러/경고]")
    print(f"Errors: {len(result3.get('errors', []))}")
    print(f"Warnings: {len(result3.get('warnings', []))}")

    print("\n" + "=" * 70)
    print("테스트 완료")
    print("=" * 70)


if __name__ == "__main__":
    test_summarize_guidelines()
