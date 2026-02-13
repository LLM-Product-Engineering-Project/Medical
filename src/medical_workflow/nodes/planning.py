"""계획 수립 및 HITL 동의 노드"""

from medical_workflow.state import WFState


def n_plan_next_actions(s: WFState, llm) -> WFState:
    """
    계획 노드:
    - should_close면 finalize
    - alarm_opt_in이 True면 build_alarm (HITL 스킵)
    - alarm_opt_in이 None이고 안전 가이드라인이 있으면 ask_hitl
    - alarm_opt_in이 False면 finalize
    """
    thread = s.get("thread") or {}
    cached_opt = thread.get("alarm_opt_in")
    if cached_opt in (True, False):
        alarm_opt_in = cached_opt
    else:
        alarm_opt_in = s.get("alarm_opt_in")

    if s.get("should_close"):
        return {**s, "plan_action": "finalize", "should_ask_hitl": False, "alarm_opt_in": alarm_opt_in}

    if alarm_opt_in is True:
        return {**s, "plan_action": "build_alarm", "should_ask_hitl": False, "alarm_opt_in": True}

    if alarm_opt_in is False:
        return {**s, "plan_action": "finalize", "should_ask_hitl": False, "alarm_opt_in": False}

    has_any_guideline = bool(s.get("safe_guidelines"))
    if has_any_guideline:
        return {**s, "plan_action": "ask_hitl", "should_ask_hitl": True, "alarm_opt_in": None}

    return {**s, "plan_action": "finalize", "should_ask_hitl": False, "alarm_opt_in": None}


def n_hitl_alarm_opt_in(s: WFState, llm) -> WFState:
    thread = s.get("thread") or {}
    cached = thread.get("alarm_opt_in")

    if cached in (True, False):
        return {**s, "alarm_opt_in": cached, "hitl_payload": None}

    if s.get("alarm_opt_in") in (True, False):
        return {**s, "hitl_payload": None}

    return {
        **s,
        "hitl_payload": {
            "type": "hitl",
            "question": "치료를 위한 생활습관 알람과 일정표를 만들어드릴까요?",
            "choices": ["yes", "no"],
            "visit_date": s.get("visit_date"),
            "diagnosis_key": s.get("diagnosis_key"),
        },
    }
