"""
test_rag_to_guidelines.py

RAG 가이드라인 생성 노드 (n_rag_to_guidelines) 단독 테스트

실행 방법:
    cd C:\Users\yebin\Desktop\Medical
    python tests/test_rag_to_guidelines.py
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
from medical_workflow.nodes.search import n_rag_to_guidelines


def test_rag_to_guidelines():
    """RAG 가이드라인 생성 노드 테스트"""
    print("=" * 70)
    print("테스트: n_rag_to_guidelines (RAG → 가이드라인 변환)")
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

    # 테스트 케이스 1: 당뇨병 RAG 결과
    print("\n[테스트 케이스 1] 당뇨병 RAG 결과")
    print("-" * 70)

    sample_state1: WFState = {
        "patient_id": "test_p1",
        "visit_id": "test_v1",
        "diagnosis_key": "당뇨병",
        "rag_raw": {
            "results": [
                {
                    "content": """
당뇨병 환자는 규칙적인 식사가 중요합니다.
하루 세 끼를 거르지 말고, 단순당(설탕, 꿀, 사탕 등)은 피해야 합니다.
복합 탄수화물(현미, 통밀빵)을 선택하고, 식이섬유가 풍부한 채소를 충분히 섭취하세요.
                    """,
                    "metadata": {"source": "서울대병원 의학정보"}
                },
                {
                    "content": """
운동은 혈당 조절에 매우 효과적입니다.
식후 30분 후에 가벼운 산책을 하면 혈당 상승을 억제할 수 있습니다.
일주일에 최소 150분(하루 30분 × 5일) 이상의 유산소 운동을 권장합니다.
                    """,
                    "metadata": {"source": "서울대병원 의학정보"}
                },
                {
                    "content": """
당뇨병 환자는 발 관리에 각별히 주의해야 합니다.
매일 발을 씻고 건조하게 유지하며, 상처나 물집이 있는지 확인하세요.
신발은 편안한 것을 선택하고, 맨발로 걷지 마세요.
                    """,
                    "metadata": {"source": "서울대병원 의학정보"}
                }
            ]
        },
        "errors": [],
        "warnings": [],
    }

    result1 = n_rag_to_guidelines(sample_state1, llm)

    print("\n[입력]")
    print(f"diagnosis_key: {sample_state1['diagnosis_key']}")
    print(f"rag_raw 결과 개수: {len(sample_state1['rag_raw']['results'])}")
    print(f"첫 번째 결과: {sample_state1['rag_raw']['results'][0]['content'][:80]}...")

    print("\n[출력]")
    print(json.dumps(result1.get("rag_guidelines"), ensure_ascii=False, indent=2))

    print("\n[에러/경고]")
    print(f"Errors: {len(result1.get('errors', []))}")
    print(f"Warnings: {len(result1.get('warnings', []))}")

    # 테스트 케이스 2: 고혈압 RAG 결과
    print("\n\n[테스트 케이스 2] 고혈압 RAG 결과")
    print("-" * 70)

    sample_state2: WFState = {
        "patient_id": "test_p2",
        "visit_id": "test_v2",
        "diagnosis_key": "고혈압",
        "rag_raw": {
            "results": [
                {
                    "content": """
고혈압 환자는 저염식이 필수입니다.
하루 염분 섭취량을 5g 이하로 제한하고, 가공식품과 패스트푸드를 피하세요.
국물 음식은 건더기만 드시고, 김치는 싱겁게 담가 드세요.
                    """,
                    "metadata": {"source": "서울대병원 의학정보"}
                },
                {
                    "content": """
적정 체중 유지가 중요합니다. 비만은 혈압을 상승시키는 주요 원인입니다.
규칙적인 운동을 통해 체중을 줄이고, 과식을 피하세요.
                    """,
                    "metadata": {"source": "서울대병원 의학정보"}
                }
            ]
        },
        "errors": [],
        "warnings": [],
    }

    result2 = n_rag_to_guidelines(sample_state2, llm)

    print("\n[입력]")
    print(f"diagnosis_key: {sample_state2['diagnosis_key']}")
    print(f"rag_raw 결과 개수: {len(sample_state2['rag_raw']['results'])}")

    print("\n[출력]")
    print(json.dumps(result2.get("rag_guidelines"), ensure_ascii=False, indent=2))

    print("\n[에러/경고]")
    print(f"Errors: {len(result2.get('errors', []))}")
    print(f"Warnings: {len(result2.get('warnings', []))}")

    # 테스트 케이스 3: 빈 RAG 결과 (에러 핸들링 테스트)
    print("\n\n[테스트 케이스 3] 빈 RAG 결과 (에러 핸들링)")
    print("-" * 70)

    sample_state3: WFState = {
        "patient_id": "test_p3",
        "visit_id": "test_v3",
        "diagnosis_key": "희귀질환",
        "rag_raw": {
            "results": []
        },
        "errors": [],
        "warnings": [],
    }

    result3 = n_rag_to_guidelines(sample_state3, llm)

    print("\n[입력]")
    print(f"diagnosis_key: {sample_state3['diagnosis_key']}")
    print(f"rag_raw 결과 개수: {len(sample_state3['rag_raw']['results'])}")

    print("\n[출력]")
    print(json.dumps(result3.get("rag_guidelines"), ensure_ascii=False, indent=2))

    print("\n[에러/경고]")
    print(f"Errors: {len(result3.get('errors', []))}")
    print(f"Warnings: {len(result3.get('warnings', []))}")
    if result3.get("warnings"):
        print("Warning details:", result3.get("warnings"))

    # 테스트 케이스 4: 복잡한 RAG 결과 (약물 + 식이 + 운동)
    print("\n\n[테스트 케이스 4] 복잡한 RAG 결과 - 고지혈증")
    print("-" * 70)

    sample_state4: WFState = {
        "patient_id": "test_p4",
        "visit_id": "test_v4",
        "diagnosis_key": "고지혈증",
        "rag_raw": {
            "results": [
                {
                    "content": "고지혈증 환자는 포화지방과 트랜스지방 섭취를 줄여야 합니다. 버터, 마가린, 튀긴 음식을 피하세요.",
                    "metadata": {"source": "서울대병원"}
                },
                {
                    "content": "등푸른 생선(고등어, 삼치)에는 오메가-3가 풍부하여 콜레스테롤 수치를 낮추는 데 도움이 됩니다.",
                    "metadata": {"source": "서울대병원"}
                },
                {
                    "content": "규칙적인 유산소 운동은 좋은 콜레스테롤(HDL)을 높이고 나쁜 콜레스테롤(LDL)을 낮춥니다.",
                    "metadata": {"source": "서울대병원"}
                },
                {
                    "content": "스타틴 계열 약물 복용 시 자몽 주스는 피해야 합니다. 약물 대사를 방해할 수 있습니다.",
                    "metadata": {"source": "서울대병원"}
                }
            ]
        },
        "errors": [],
        "warnings": [],
    }

    result4 = n_rag_to_guidelines(sample_state4, llm)

    print("\n[입력]")
    print(f"diagnosis_key: {sample_state4['diagnosis_key']}")
    print(f"rag_raw 결과 개수: {len(sample_state4['rag_raw']['results'])}")

    print("\n[출력]")
    print(json.dumps(result4.get("rag_guidelines"), ensure_ascii=False, indent=2))

    print("\n[에러/경고]")
    print(f"Errors: {len(result4.get('errors', []))}")
    print(f"Warnings: {len(result4.get('warnings', []))}")

    print("\n" + "=" * 70)
    print("테스트 완료")
    print("=" * 70)


if __name__ == "__main__":
    test_rag_to_guidelines()
