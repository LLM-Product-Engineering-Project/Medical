"""
test_finalize_user_message.py

최종 안내 메시지 생성 노드 (n_finalize — user_message LLM 전환) 단독 테스트

실행 방법:
    cd C:\\Users\\yebin\\Desktop\\Medical
    python tests/test_finalize_user_message.py
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
from medical_workflow.nodes.finalize import n_finalize
from medical_workflow.stores.thread import THREAD_STORE
from medical_workflow.utils.helpers import thread_key


def _setup_thread(patient_id: str, diagnosis_key: str) -> None:
    """테스트용 THREAD_STORE 초기화 헬퍼."""
    key = thread_key(patient_id, diagnosis_key)
    THREAD_STORE[key] = {
        "thread_id": f"thread_{patient_id}",
        "patient_id": patient_id,
        "diagnosis_key": diagnosis_key,
        "status": "active",
        "events": [],
        "memories": [],
        "alarm_opt_in": True,
    }


def _base_state(
    patient_id: str,
    diagnosis_key: str,
    guardrail_route: str = "allow",
    safe_guidelines: list | None = None,
    errors: list | None = None,
    warnings: list | None = None,
) -> WFState:
    """공통 state 생성 헬퍼."""
    return {
        "patient_id": patient_id,
        "visit_id": f"visit_{patient_id}",
        "visit_date": "2026-02-20",
        "diagnosis_key": diagnosis_key,
        "has_diagnosis": True,
        "thread_id": f"thread_{patient_id}",
        "doctor_text": "",
        "doctor_summary": None,
        "safe_guidelines": safe_guidelines or [],
        "should_close": False,
        "plan_action": "finalize",
        "alarm_opt_in": True,
        "alarm_plan": None,
        "patient_reflection": None,
        "guardrail_route": guardrail_route,
        "guardrail_risk_score": 0.0,
        "guardrail_conflict_score": 0.0,
        "guardrail_evidence_score": 1.0,
        "guardrail_decision_log": [],
        "errors": errors or [],
        "warnings": warnings or [],
    }


def test_finalize_user_message():
    """n_finalize user_message LLM 생성 테스트"""
    print("=" * 70)
    print("테스트: n_finalize — user_message LLM 기반 환자 맞춤 안내 메시지")
    print("=" * 70)

    load_env_keys()

    llm = ChatOpenAI(
        model="solar-pro2",
        base_url="https://api.upstage.ai/v1",
        api_key=os.environ.get("UPSTAGE_API_KEY"),
        temperature=0.1,
    )

    # ── 테스트 케이스 1: 정상 allow — 맞춤 가이드라인 메시지 ─────────────────
    print("\n[테스트 케이스 1] guardrail=allow, 가이드라인 있음")
    print("-" * 70)

    _setup_thread("test_p1", "당뇨병")
    state1 = _base_state(
        "test_p1", "당뇨병",
        guardrail_route="allow",
        safe_guidelines=[
            {"category": "medication", "text": "메트포르민 하루 2회 식후 복용", "source": "doctor"},
            {"category": "diet",       "text": "단순당 섭취 줄이고 복합 탄수화물 선택", "source": "doctor"},
            {"category": "exercise",   "text": "식후 30분 걷기 실천", "source": "rag"},
        ],
    )

    result1 = n_finalize(state1, llm)
    msg1 = result1.get("final_answer", {}).get("user_message", "")

    print(f"[입력] guardrail_route: allow | 가이드라인: {len(state1['safe_guidelines'])}개")
    print(f"[출력] user_message:\n  {msg1}")
    print(f"[에러] {len(result1.get('errors', []))}건")
    print(f"[검증] 메시지 길이: {len(msg1)}자  {'✅ (충분)' if len(msg1) > 20 else '❌ (너무 짧음)'}")

    # ── 테스트 케이스 2: caution — 주의 필요 메시지 ──────────────────────────
    print("\n\n[테스트 케이스 2] guardrail=caution, 증거 부족 경고 포함")
    print("-" * 70)

    _setup_thread("test_p2", "고혈압")
    state2 = _base_state(
        "test_p2", "고혈압",
        guardrail_route="caution",
        safe_guidelines=[
            {"category": "diet", "text": "저염식 실천 (나트륨 하루 2g 이하)", "source": "rag"},
        ],
        warnings=["⚠️ 일부 권고 사항의 근거가 부족합니다. 의료진에게 확인하세요."],
    )

    result2 = n_finalize(state2, llm)
    msg2 = result2.get("final_answer", {}).get("user_message", "")

    print(f"[입력] guardrail_route: caution | 경고: {state2['warnings']}")
    print(f"[출력] user_message:\n  {msg2}")
    print(f"[에러] {len(result2.get('errors', []))}건")
    # caution 시 주의/확인 키워드 포함 여부 (참고용)
    caution_kw = any(kw in msg2 for kw in ["주의", "확인", "상담", "조심", "꼭"])
    print(f"[검증] 주의 관련 키워드 포함: {'✅' if caution_kw else '❌ (참고용, 필수 아님)'}")

    # ── 테스트 케이스 3: block — 의료진 상담 강조 메시지 ─────────────────────
    print("\n\n[테스트 케이스 3] guardrail=block, 위험 가이드라인 차단")
    print("-" * 70)

    _setup_thread("test_p3", "당뇨병")
    state3 = _base_state(
        "test_p3", "당뇨병",
        guardrail_route="block",
        safe_guidelines=[],
        guardrail_risk_score=1.0,
    )
    # guardrail_risk_score를 직접 덮어쓰기
    state3["guardrail_risk_score"] = 1.0

    result3 = n_finalize(state3, llm)
    msg3 = result3.get("final_answer", {}).get("user_message", "")

    print(f"[입력] guardrail_route: block | risk_score: 1.0")
    print(f"[출력] user_message:\n  {msg3}")
    print(f"[에러] {len(result3.get('errors', []))}건")
    # block 시 의료진/상담 키워드 포함 여부
    block_kw = any(kw in msg3 for kw in ["의료진", "상담", "병원", "의사"])
    print(f"[검증] 의료진 상담 안내 포함: {'✅' if block_kw else '❌'}")

    # ── 테스트 케이스 4: critical error — 오류 상황 안내 메시지 ──────────────
    print("\n\n[테스트 케이스 4] severity=high 에러 발생, 가이드라인 생성 실패")
    print("-" * 70)

    _setup_thread("test_p4", "고지혈증")
    state4 = _base_state(
        "test_p4", "고지혈증",
        guardrail_route="allow",
        safe_guidelines=[],
        errors=[{
            "node": "rag_to_guidelines",
            "timestamp": "2026-02-20T00:00:00Z",
            "error_type": "ValueError",
            "message": "LLM returned empty JSON",
            "fallback_used": True,
            "severity": "high",
        }],
    )

    result4 = n_finalize(state4, llm)
    msg4 = result4.get("final_answer", {}).get("user_message", "")

    print(f"[입력] critical_errors: 1건 (rag_to_guidelines 실패)")
    print(f"[출력] user_message:\n  {msg4}")
    print(f"[에러] {len(result4.get('errors', []))}건")

    # ── 테스트 케이스 5: 진단 없음 (general_visit) — user_message 미생성 ─────
    print("\n\n[테스트 케이스 5] 진단 없음 (general_visit) — LLM 미호출")
    print("-" * 70)

    state5: WFState = {
        "patient_id": "test_p5",
        "visit_id": "visit_test_p5",
        "visit_date": "2026-02-20",
        "has_diagnosis": False,
        "errors": [],
        "warnings": [],
    }

    result5 = n_finalize(state5, llm)
    fa5 = result5.get("final_answer", {})

    print(f"[입력] has_diagnosis: False")
    print(f"[출력] final_answer.type: {fa5.get('type')}")
    print(f"[검증] user_message 없음: {'✅' if 'user_message' not in fa5 else '❌'}")
    print(f"[에러] {len(result5.get('errors', []))}건")

    # ── 종합 결과 ─────────────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("📊 종합 결과")
    print("=" * 70)
    cases = [
        ("케이스 1 (allow)",        msg1),
        ("케이스 2 (caution)",      msg2),
        ("케이스 3 (block)",        msg3),
        ("케이스 4 (critical err)", msg4),
    ]
    for label, msg in cases:
        preview = msg[:60].replace("\n", " ") if msg else "(없음)"
        print(f"  {label}: {preview}...")

    # user_message 존재 여부 검증
    all_have_msg = all(msg for _, msg in cases)
    print(f"\n[검증] 4개 케이스 모두 user_message 존재: {'✅' if all_have_msg else '❌'}")

    print("\n테스트 완료")
    print("=" * 70)


if __name__ == "__main__":
    test_finalize_user_message()
