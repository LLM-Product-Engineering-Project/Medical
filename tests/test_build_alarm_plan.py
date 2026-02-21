"""
test_build_alarm_plan.py

알람 계획 생성 노드 (n_build_alarm_plan) 단독 테스트

실행 방법:
    cd C:\\Users\\yebin\\Desktop\\Medical
    python tests/test_build_alarm_plan.py
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
from medical_workflow.nodes.alarm import n_build_alarm_plan
from medical_workflow.stores.thread import THREAD_STORE
from medical_workflow.utils.helpers import thread_key


def _setup_thread(patient_id: str, diagnosis_key: str, events: list | None = None) -> None:
    """테스트용 THREAD_STORE 초기화 헬퍼."""
    key = thread_key(patient_id, diagnosis_key)
    THREAD_STORE[key] = {
        "thread_id": f"thread_{patient_id}_{diagnosis_key}",
        "patient_id": patient_id,
        "diagnosis_key": diagnosis_key,
        "status": "active",
        "events": events or [],
        "memories": [],
    }


def _print_alarm_plan(plan: dict | None) -> None:
    """알람 플랜 출력 헬퍼."""
    if not plan:
        print("  (없음)")
        return
    items = plan.get("items", [])
    print(f"  start_date : {plan.get('start_date')}")
    print(f"  timezone   : {plan.get('timezone')}")
    print(f"  항목 수    : {len(items)}")
    for item in items:
        priority = item.get("priority", "-")
        print(f"    [{item.get('time')}] (priority={priority}) {item.get('action')}")


def test_build_alarm_plan():
    """알람 계획 생성 노드 LLM 테스트"""
    print("=" * 70)
    print("테스트: n_build_alarm_plan (LLM 기반 환자 맞춤 알람 생성)")
    print("=" * 70)

    load_env_keys()

    llm = ChatOpenAI(
        model="solar-pro2",
        base_url="https://api.upstage.ai/v1",
        api_key=os.environ.get("UPSTAGE_API_KEY"),
        temperature=0.1,
    )

    # ── 테스트 케이스 1: 복약 + 식이 + 운동 가이드라인 ──────────────────────
    print("\n[테스트 케이스 1] 당뇨병 — 복약/식이/운동 혼합 가이드라인")
    print("-" * 70)

    _setup_thread("test_p1", "당뇨병")

    state1: WFState = {
        "patient_id": "test_p1",
        "visit_id": "test_v1",
        "visit_date": "2026-02-20",
        "diagnosis_key": "당뇨병",
        "retrieved_memories": [
            {"type": "visit_memory", "text": "직장인, 오전 9시 출근, 저녁 6시 퇴근"},
        ],
        "safe_guidelines": [
            {"category": "medication", "text": "메트포르민 하루 2회 식후 복용", "source": "doctor"},
            {"category": "diet",       "text": "단순당(흰쌀, 설탕) 섭취 제한", "source": "doctor"},
            {"category": "exercise",   "text": "식후 30분 걷기 10~15분", "source": "rag"},
            {"category": "followup",   "text": "3개월 후 혈당 재검사", "source": "doctor"},
        ],
        "errors": [],
        "warnings": [],
    }

    result1 = n_build_alarm_plan(state1, llm)
    plan1 = result1.get("alarm_plan")

    print(f"[입력] 가이드라인 {len(state1['safe_guidelines'])}개, 메모리: {state1['retrieved_memories'][0]['text']}")
    print("[출력]")
    _print_alarm_plan(plan1)
    print(f"[에러] {len(result1.get('errors', []))}건")

    # 복약 알람 포함 여부 검증
    has_medication = any(
        "메트포르민" in (item.get("action") or "")
        for item in (plan1.get("items") if plan1 else [])
    )
    print(f"[검증] 복약 알람 포함: {'✅' if has_medication else '❌'}")

    # ── 테스트 케이스 2: 노인 환자 — 생활 패턴 반영 ─────────────────────────
    print("\n\n[테스트 케이스 2] 고혈압 — 노인 환자 (오전 활동 패턴)")
    print("-" * 70)

    _setup_thread("test_p2", "고혈압")

    state2: WFState = {
        "patient_id": "test_p2",
        "visit_id": "test_v2",
        "visit_date": "2026-02-20",
        "diagnosis_key": "고혈압",
        "retrieved_memories": [
            {"type": "visit_memory", "text": "75세 노인, 오전에 주로 활동, 낮잠 1~2시간, 저녁 9시 취침"},
        ],
        "safe_guidelines": [
            {"category": "medication", "text": "혈압약 아침 기상 후 복용", "source": "doctor"},
            {"category": "diet",       "text": "저염식, 하루 나트륨 2g 이하", "source": "doctor"},
            {"category": "lifestyle",  "text": "혈압 측정 하루 2회 (아침/저녁)", "source": "doctor"},
            {"category": "exercise",   "text": "오전 산책 20분 (무리하지 않게)", "source": "rag"},
        ],
        "errors": [],
        "warnings": [],
    }

    result2 = n_build_alarm_plan(state2, llm)
    plan2 = result2.get("alarm_plan")

    print(f"[입력] 가이드라인 {len(state2['safe_guidelines'])}개, 메모리: {state2['retrieved_memories'][0]['text']}")
    print("[출력]")
    _print_alarm_plan(plan2)
    print(f"[에러] {len(result2.get('errors', []))}건")

    # ── 테스트 케이스 3: 이전 방문 가이드라인이 누적된 경우 ──────────────────
    print("\n\n[테스트 케이스 3] 고지혈증 — 이전 방문 가이드라인 누적")
    print("-" * 70)

    _setup_thread("test_p3", "고지혈증", events=[
        {
            "visit_id": "test_v3_prev",
            "visit_date": "2025-12-01",
            "guidelines": [
                {"category": "medication", "text": "스타틴 저녁 식후 복용 (자몽 금지)", "source": "doctor"},
                {"category": "diet",       "text": "포화지방 섭취 하루 15g 이하", "source": "rag"},
            ],
            "should_close": False,
        }
    ])

    state3: WFState = {
        "patient_id": "test_p3",
        "visit_id": "test_v3",
        "visit_date": "2026-02-20",
        "diagnosis_key": "고지혈증",
        "retrieved_memories": [
            {"type": "visit_memory", "text": "40대 직장인, 야근 잦음, 외식 빈번"},
        ],
        "safe_guidelines": [
            {"category": "diet",      "text": "등푸른 생선 주 2회 이상 섭취", "source": "rag"},
            {"category": "exercise",  "text": "유산소 운동 주 3회 이상", "source": "rag"},
        ],
        "errors": [],
        "warnings": [],
    }

    result3 = n_build_alarm_plan(state3, llm)
    plan3 = result3.get("alarm_plan")

    print(f"[입력] 이전 방문 가이드라인 2개 + 금번 방문 가이드라인 {len(state3['safe_guidelines'])}개")
    print(f"       메모리: {state3['retrieved_memories'][0]['text']}")
    print("[출력]")
    _print_alarm_plan(plan3)
    print(f"[에러] {len(result3.get('errors', []))}건")

    # 이전 방문 복약 알람 포함 확인
    has_statin = any(
        "스타틴" in (item.get("action") or "")
        for item in (plan3.get("items") if plan3 else [])
    )
    print(f"[검증] 이전 방문 복약(스타틴) 알람 포함: {'✅' if has_statin else '❌'}")

    # ── 테스트 케이스 4: 가이드라인 없음 (빈 상태) ───────────────────────────
    print("\n\n[테스트 케이스 4] 가이드라인 없음 — 빈 알람 플랜")
    print("-" * 70)

    _setup_thread("test_p4", "기타")

    state4: WFState = {
        "patient_id": "test_p4",
        "visit_id": "test_v4",
        "visit_date": "2026-02-20",
        "diagnosis_key": "기타",
        "retrieved_memories": [],
        "safe_guidelines": [],
        "errors": [],
        "warnings": [],
    }

    result4 = n_build_alarm_plan(state4, llm)
    plan4 = result4.get("alarm_plan")

    print("[입력] 가이드라인 없음, 메모리 없음")
    print("[출력]")
    _print_alarm_plan(plan4)
    print(f"[에러] {len(result4.get('errors', []))}건")

    # ── 종합 결과 ─────────────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("📊 종합 결과")
    print("=" * 70)
    cases = [
        ("케이스 1 (당뇨, 직장인)",   plan1),
        ("케이스 2 (고혈압, 노인)",    plan2),
        ("케이스 3 (고지혈증, 누적)",  plan3),
        ("케이스 4 (빈 가이드라인)",   plan4),
    ]
    for label, plan in cases:
        cnt = len(plan.get("items", [])) if plan else 0
        print(f"  {label}: 알람 {cnt}개")

    # 유효성 검증: 모든 항목에 time, action 필드가 있는지
    all_items = []
    for _, plan in cases:
        if plan:
            all_items.extend(plan.get("items", []))
    invalid = [i for i in all_items if not i.get("time") or not i.get("action")]
    print(f"\n[검증] 전체 알람 항목 수 : {len(all_items)}")
    print(f"[검증] 필드 누락 항목 수  : {len(invalid)} {'✅' if not invalid else '❌'}")

    print("\n테스트 완료")
    print("=" * 70)


if __name__ == "__main__":
    test_build_alarm_plan()
