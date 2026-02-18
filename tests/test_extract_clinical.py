"""
test_extract_clinical.py

임상 정보 추출 노드 (n_extract_clinical) 단독 테스트

실행 방법:
    cd C:\Users\yebin\Desktop\Medical
    python tests/test_extract_clinical.py
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
from medical_workflow.nodes.extraction import n_extract_clinical


def test_extract_clinical():
    """임상 정보 추출 노드 테스트"""
    print("=" * 70)
    print("테스트: n_extract_clinical (임상 정보 추출)")
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

    # 테스트 케이스 1: 정상적인 진료 기록
    print("\n[테스트 케이스 1] 정상적인 진료 기록 - 당뇨병 진단")
    print("-" * 70)

    sample_state1: WFState = {
        "patient_id": "test_p1",
        "visit_id": "test_v1",
        "doctor_text": """
안녕하세요 환자분. 오늘 검사 결과를 보니 혈당이 많이 높습니다.
당뇨병으로 진단됩니다. 앞으로 식이요법과 운동이 매우 중요합니다.
단 음식을 피하시고, 매일 30분 이상 걷기를 실천하세요.
메트포르민 처방해드리겠습니다. 하루 두 번 식후에 드세요.
3개월 후에 다시 검사하러 오세요.
        """.strip(),
        "errors": [],
        "warnings": [],
    }

    result1 = n_extract_clinical(sample_state1, llm)

    print("\n[입력]")
    print(f"doctor_text: {sample_state1['doctor_text'][:100]}...")

    print("\n[출력]")
    print(json.dumps(result1.get("extracted"), ensure_ascii=False, indent=2))

    print("\n[에러/경고]")
    print(f"Errors: {len(result1.get('errors', []))}")
    print(f"Warnings: {len(result1.get('warnings', []))}")
    if result1.get("errors"):
        print("Error details:", json.dumps(result1.get("errors"), ensure_ascii=False, indent=2))
    if result1.get("warnings"):
        print("Warning details:", result1.get("warnings"))

    # 테스트 케이스 2: 진단명 없는 일반 상담
    print("\n\n[테스트 케이스 2] 진단명 없는 일반 상담")
    print("-" * 70)

    sample_state2: WFState = {
        "patient_id": "test_p2",
        "visit_id": "test_v2",
        "doctor_text": """
안녕하세요. 오늘 감기 증상으로 오셨네요.
약 처방해드릴게요. 충분히 쉬시고 물 많이 드세요.
        """.strip(),
        "errors": [],
        "warnings": [],
    }

    result2 = n_extract_clinical(sample_state2, llm)

    print("\n[입력]")
    print(f"doctor_text: {sample_state2['doctor_text']}")

    print("\n[출력]")
    print(json.dumps(result2.get("extracted"), ensure_ascii=False, indent=2))

    print("\n[에러/경고]")
    print(f"Errors: {len(result2.get('errors', []))}")
    print(f"Warnings: {len(result2.get('warnings', []))}")

    # 테스트 케이스 3: 복잡한 진료 (다중 진단 + 상세 가이드라인)
    print("\n\n[테스트 케이스 3] 복잡한 진료 - 고혈압 + 고지혈증")
    print("-" * 70)

    sample_state3: WFState = {
        "patient_id": "test_p3",
        "visit_id": "test_v3",
        "doctor_text": """
혈압이 150/95로 높고, 콜레스테롤 수치도 높습니다.
고혈압과 고지혈증으로 진단됩니다.
지금부터 저염식, 저지방식을 시작하셔야 합니다.
염분은 하루 5g 이하로 제한하세요.
운동은 매일 30분 이상 유산소 운동을 하세요.
혈압약은 아침에, 콜레스테롤약은 저녁에 드세요.
술과 담배는 반드시 끊으세요.
2주 후에 혈압 체크하러 오세요.
        """.strip(),
        "errors": [],
        "warnings": [],
    }

    result3 = n_extract_clinical(sample_state3, llm)

    print("\n[입력]")
    print(f"doctor_text: {sample_state3['doctor_text'][:100]}...")

    print("\n[출력]")
    print(json.dumps(result3.get("extracted"), ensure_ascii=False, indent=2))

    print("\n[에러/경고]")
    print(f"Errors: {len(result3.get('errors', []))}")
    print(f"Warnings: {len(result3.get('warnings', []))}")

    print("\n" + "=" * 70)
    print("테스트 완료")
    print("=" * 70)


if __name__ == "__main__":
    test_extract_clinical()
