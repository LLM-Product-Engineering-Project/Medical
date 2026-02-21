"""
test_reflect_patient_state.py

환자 상태 리플렉션 노드 (n_reflect_patient_state) 단독 테스트

실행 방법:
    cd C:/Users/yebin/Desktop/Medical
    python tests/test_reflect_patient_state.py
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
from medical_workflow.nodes.memory import n_reflect_patient_state
from medical_workflow.stores import THREAD_STORE, thread_key


def test_reflect_patient_state():
    """환자 상태 리플렉션 노드 테스트"""
    print("=" * 70)
    print("테스트: n_reflect_patient_state (환자 상태 리플렉션)")
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

    # 테스트 케이스 1: 첫 방문 (메모리 없음)
    print("\n[테스트 케이스 1] 첫 방문 - 메모리 없음")
    print("-" * 70)

    # 스레드 생성
    patient_id_1 = "test_p1"
    diagnosis_key_1 = "당뇨병"
    key1 = thread_key(patient_id_1, diagnosis_key_1)
    THREAD_STORE[key1] = {
        "thread_id": f"thread_{patient_id_1}_{diagnosis_key_1}",
        "patient_id": patient_id_1,
        "diagnosis_key": diagnosis_key_1,
        "status": "active",
        "events": [],
        "memories": [],
        "reflections": [],
    }

    sample_state1: WFState = {
        "patient_id": patient_id_1,
        "visit_id": "test_v1",
        "visit_date": "2026-02-18",
        "diagnosis_key": diagnosis_key_1,
        "retrieved_memories": [],
        "safe_guidelines": [
            {"category": "diet", "text": "단 음식을 피하고, 규칙적으로 식사하세요.", "source": "doctor"},
            {"category": "exercise", "text": "매일 30분 이상 걷기를 실천하세요.", "source": "doctor"},
            {"category": "medication", "text": "메트포르민을 하루 두 번 식후에 드세요.", "source": "doctor"}
        ],
        "thread": THREAD_STORE[key1],
        "errors": [],
        "warnings": [],
    }

    result1 = n_reflect_patient_state(sample_state1, llm)

    print("\n[입력]")
    print(f"diagnosis_key: {sample_state1['diagnosis_key']}")
    print(f"retrieved_memories 개수: {len(sample_state1['retrieved_memories'])}")
    print(f"safe_guidelines 개수: {len(sample_state1['safe_guidelines'])}")

    print("\n[출력]")
    print(f"patient_reflection: {result1.get('patient_reflection')}")

    print("\n[스레드에 저장된 리플렉션]")
    print(json.dumps(THREAD_STORE[key1].get("reflections", []), ensure_ascii=False, indent=2))

    print("\n[에러/경고]")
    print(f"Errors: {len(result1.get('errors', []))}")
    print(f"Warnings: {len(result1.get('warnings', []))}")

    # 테스트 케이스 2: 누적 방문 (메모리 있음)
    print("\n\n[테스트 케이스 2] 누적 방문 - 메모리 있음 (3회차)")
    print("-" * 70)

    # 스레드 생성
    patient_id_2 = "test_p2"
    diagnosis_key_2 = "고혈압"
    key2 = thread_key(patient_id_2, diagnosis_key_2)
    THREAD_STORE[key2] = {
        "thread_id": f"thread_{patient_id_2}_{diagnosis_key_2}",
        "patient_id": patient_id_2,
        "diagnosis_key": diagnosis_key_2,
        "status": "active",
        "events": [
            {"visit_id": "v1", "visit_date": "2026-01-10", "guidelines": [{"text": "저염식"}], "should_close": False},
            {"visit_id": "v2", "visit_date": "2026-02-01", "guidelines": [{"text": "운동 시작"}], "should_close": False}
        ],
        "memories": [
            {"ts": "2026-01-10", "type": "visit", "text": "고혈압 진단, 저염식 시작", "importance": 0.9},
            {"ts": "2026-02-01", "type": "visit", "text": "혈압 약간 감소, 운동 권장", "importance": 0.7}
        ],
        "reflections": [],
    }

    sample_state2: WFState = {
        "patient_id": patient_id_2,
        "visit_id": "test_v3",
        "visit_date": "2026-02-18",
        "diagnosis_key": diagnosis_key_2,
        "retrieved_memories": [
            {"ts": "2026-01-10", "type": "visit", "text": "고혈압 진단, 저염식 시작", "importance": 0.9},
            {"ts": "2026-02-01", "type": "visit", "text": "혈압 약간 감소, 운동 권장", "importance": 0.7},
            {"ts": "2026-02-01", "type": "event", "text": "visit=v2 guidelines=1 close=False", "importance": 0.4}
        ],
        "safe_guidelines": [
            {"category": "diet", "text": "저염식을 계속 유지하세요.", "source": "doctor"},
            {"category": "exercise", "text": "걷기를 하루 40분으로 늘려보세요.", "source": "doctor"},
            {"category": "medication", "text": "혈압약을 빠뜨리지 말고 드세요.", "source": "doctor"},
            {"category": "followup", "text": "한 달 후 재방문하세요.", "source": "doctor"}
        ],
        "thread": THREAD_STORE[key2],
        "errors": [],
        "warnings": [],
    }

    result2 = n_reflect_patient_state(sample_state2, llm)

    print("\n[입력]")
    print(f"diagnosis_key: {sample_state2['diagnosis_key']}")
    print(f"retrieved_memories 개수: {len(sample_state2['retrieved_memories'])}")
    print(f"safe_guidelines 개수: {len(sample_state2['safe_guidelines'])}")
    print("\n[누적 메모리 샘플]")
    print(json.dumps(sample_state2['retrieved_memories'][:2], ensure_ascii=False, indent=2))

    print("\n[출력]")
    print(f"patient_reflection: {result2.get('patient_reflection')}")

    print("\n[스레드에 저장된 리플렉션]")
    print(json.dumps(THREAD_STORE[key2].get("reflections", []), ensure_ascii=False, indent=2))

    print("\n[에러/경고]")
    print(f"Errors: {len(result2.get('errors', []))}")
    print(f"Warnings: {len(result2.get('warnings', []))}")

    # 테스트 케이스 3: 복잡한 케이스 (가이드라인 많음)
    print("\n\n[테스트 케이스 3] 복잡한 케이스 - 가이드라인 5개 이상")
    print("-" * 70)

    # 스레드 생성
    patient_id_3 = "test_p3"
    diagnosis_key_3 = "당뇨병"
    key3 = thread_key(patient_id_3, diagnosis_key_3)
    THREAD_STORE[key3] = {
        "thread_id": f"thread_{patient_id_3}_{diagnosis_key_3}",
        "patient_id": patient_id_3,
        "diagnosis_key": diagnosis_key_3,
        "status": "active",
        "events": [],
        "memories": [
            {"ts": "2026-01-15", "type": "visit", "text": "당뇨병 진단, 혈당 200", "importance": 0.9},
            {"ts": "2026-02-01", "type": "visit", "text": "혈당 170으로 감소", "importance": 0.8},
            {"ts": "2026-02-10", "type": "reflection", "text": "식이요법 잘 지키고 있음", "importance": 0.6}
        ],
        "reflections": [],
    }

    sample_state3: WFState = {
        "patient_id": patient_id_3,
        "visit_id": "test_v3",
        "visit_date": "2026-02-18",
        "diagnosis_key": diagnosis_key_3,
        "retrieved_memories": [
            {"ts": "2026-01-15", "type": "visit", "text": "당뇨병 진단, 혈당 200", "importance": 0.9},
            {"ts": "2026-02-01", "type": "visit", "text": "혈당 170으로 감소", "importance": 0.8},
            {"ts": "2026-02-10", "type": "reflection", "text": "식이요법 잘 지키고 있음", "importance": 0.6}
        ],
        "safe_guidelines": [
            {"category": "diet", "text": "단순당 피하고 복합 탄수화물 섭취", "source": "rag"},
            {"category": "diet", "text": "하루 세 끼 규칙적으로 식사", "source": "rag"},
            {"category": "exercise", "text": "식후 30분 후 가벼운 산책", "source": "rag"},
            {"category": "exercise", "text": "일주일에 150분 이상 유산소 운동", "source": "rag"},
            {"category": "medication", "text": "메트포르민 하루 2회 식후", "source": "doctor"},
            {"category": "followup", "text": "매일 아침 공복 혈당 측정", "source": "rag"},
            {"category": "warning", "text": "발 관리 주의, 매일 확인", "source": "rag"}
        ],
        "thread": THREAD_STORE[key3],
        "errors": [],
        "warnings": [],
    }

    result3 = n_reflect_patient_state(sample_state3, llm)

    print("\n[입력]")
    print(f"diagnosis_key: {sample_state3['diagnosis_key']}")
    print(f"retrieved_memories 개수: {len(sample_state3['retrieved_memories'])}")
    print(f"safe_guidelines 개수: {len(sample_state3['safe_guidelines'])}")

    print("\n[출력]")
    print(f"patient_reflection: {result3.get('patient_reflection')}")

    print("\n[스레드에 저장된 리플렉션]")
    print(json.dumps(THREAD_STORE[key3].get("reflections", []), ensure_ascii=False, indent=2))

    print("\n[에러/경고]")
    print(f"Errors: {len(result3.get('errors', []))}")
    print(f"Warnings: {len(result3.get('warnings', []))}")

    # 스레드 저장소 초기화 (다음 테스트를 위해)
    THREAD_STORE.clear()

    print("\n" + "=" * 70)
    print("테스트 완료")
    print("=" * 70)


if __name__ == "__main__":
    test_reflect_patient_state()
