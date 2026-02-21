"""알람 계획 생성 노드"""

from typing import Dict, Any, List

from medical_workflow.state import WFState
from medical_workflow.stores import THREAD_STORE, thread_key, safe_llm_invoke


def _rule_based_alarm_items(guidelines: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """LLM 실패 시 사용하는 규칙 기반 fallback 알람 생성."""
    plan_items = []
    for g in guidelines:
        text = (g.get("text") or "").strip()
        cat = g.get("category") or "general"
        if not text:
            continue
        if cat == "medication":
            plan_items.append({"time": "09:00", "action": text, "priority": 1})
            plan_items.append({"time": "21:00", "action": text, "priority": 1})
        elif cat in ("lifestyle", "diet", "exercise"):
            plan_items.append({"time": "10:00", "action": text, "priority": 3})
            plan_items.append({"time": "19:00", "action": text, "priority": 3})
        else:
            plan_items.append({"time": "12:00", "action": text, "priority": 5})
    return plan_items[:12]


def n_build_alarm_plan(s: WFState, llm) -> WFState:
    if s.get("diagnosis_key"):
        key = thread_key(s["patient_id"], s["diagnosis_key"])
        thread = THREAD_STORE.get(key, {})
    else:
        # 증상 스레드: diagnosis_key가 없으므로 state에 저장된 thread 객체 사용
        thread = s.get("thread") or {}
    events = thread.get("events", [])

    guidelines: List[Dict[str, Any]] = []
    for ev in events:
        guidelines.extend(ev.get("guidelines", []))
    guidelines.extend(s.get("safe_guidelines") or [])

    visit_date = s.get("visit_date")
    retrieved_memories = s.get("retrieved_memories") or []

    fallback_items = _rule_based_alarm_items(guidelines)

    prompt = f"""환자 메모리 (생활 패턴 파악용):
{retrieved_memories}

가이드라인 (이행해야 할 의료 권고):
{guidelines}

위 정보를 바탕으로 환자에게 맞는 하루 알람 일정표를 JSON 배열로 생성하라.
각 항목 형식: {{"time": "HH:MM", "action": "알람 내용", "priority": 1~5}}
- priority: 1=복약(최우선), 2=검사/처치, 3=식이, 4=운동/생활습관, 5=기타
- 최대 12개, 중복 제거, 의학적으로 안전한 시간대 배정
- 복약 알람은 반드시 포함하고, 식사 시간과 연동하라
- 노인/직장인/어린이 등 생활 패턴이 파악되면 반영하라

JSON 배열만 출력하라 (설명 없이).
"""

    llm_items, error = safe_llm_invoke(
        llm, prompt,
        node_name="build_alarm_plan",
        fallback_value=fallback_items,
        parse_json=True,
        severity="medium"
    )

    # 유효한 리스트 여부 검증
    if isinstance(llm_items, list) and llm_items:
        valid_items = []
        for item in llm_items:
            if isinstance(item, dict) and item.get("time") and item.get("action"):
                valid_items.append(item)
        plan_items = valid_items[:12] if valid_items else fallback_items
    else:
        plan_items = fallback_items

    new_state = {
        **s,
        "alarm_plan": {
            "patient_id": s["patient_id"],
            "start_date": visit_date,
            "timezone": "Asia/Seoul",
            "items": plan_items,
        },
        "plan_action": "finalize",  # 알람 생성 완료 → 다음 단계는 finalize
    }

    if error:
        errors = list(s.get("errors", []))
        errors.append(error)
        new_state["errors"] = errors
        new_state["has_errors"] = True

    return new_state
