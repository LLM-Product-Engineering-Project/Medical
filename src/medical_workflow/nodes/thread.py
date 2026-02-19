"""스레드 관리 및 종료 감지 노드"""

from typing import Dict, Any

from medical_workflow.state import WFState
from medical_workflow.stores import THREAD_STORE, thread_key, safe_llm_invoke


def _ensure_thread_defaults(t: Dict[str, Any]) -> Dict[str, Any]:
    t.setdefault("events", [])
    t.setdefault("memories", [])
    t.setdefault("reflections", [])
    t.setdefault("alarm_opt_in", None)
    return t


def n_is_existing(s: WFState, llm) -> WFState:
    key = thread_key(s["patient_id"], s["diagnosis_key"])
    return {**s, "is_existing": key in THREAD_STORE}


def n_create_thread(s: WFState, llm) -> WFState:
    key = thread_key(s["patient_id"], s["diagnosis_key"])
    THREAD_STORE[key] = _ensure_thread_defaults(
        {
            "thread_id": f"thread_{s['patient_id']}_{s['diagnosis_key']}",
            "patient_id": s["patient_id"],
            "diagnosis_key": s["diagnosis_key"],
            "status": "active",
        }
    )
    t = THREAD_STORE[key]
    return {**s, "thread_id": t["thread_id"], "thread": t, "alarm_opt_in": t.get("alarm_opt_in")}


def n_load_thread(s: WFState, llm) -> WFState:
    key = thread_key(s["patient_id"], s["diagnosis_key"])
    t = THREAD_STORE[key]
    _ensure_thread_defaults(t)
    # state에 명시적인 값(True/False)이 있으면 유지, 없으면 thread 캐시 사용
    state_opt = s.get("alarm_opt_in")
    alarm_opt_in = state_opt if state_opt in (True, False) else t.get("alarm_opt_in")
    return {**s, "thread_id": t["thread_id"], "thread": t, "alarm_opt_in": alarm_opt_in}


def n_detect_closure(s: WFState, llm) -> WFState:
    prompt = f"""
이 진료에서 "{s.get("diagnosis_key","")}" 질병 관리(스레드)를 종료한다는 의미인가?
JSON만 출력.
{{"should_close": true/false}}

전사:
{s["doctor_text"]}
"""
    # 기본값: 종료하지 않음 (보수적 접근)
    fallback = {"should_close": False}
    out, error = safe_llm_invoke(
        llm, prompt,
        node_name="detect_closure",
        fallback_value=fallback,
        parse_json=True,
        severity="medium"
    )

    should_close = bool(out.get("should_close", False)) if isinstance(out, dict) else False

    new_state = {**s, "should_close": should_close}
    if error:
        errors = s.get("errors", [])
        errors.append(error)
        new_state["errors"] = errors

        warnings = s.get("warnings", [])
        warnings.append("ℹ️ 치료 종료 여부를 판단할 수 없어 진료를 계속합니다.")
        new_state["warnings"] = warnings

    return new_state


def n_close_thread(s: WFState, llm) -> WFState:
    key = thread_key(s["patient_id"], s["diagnosis_key"])
    if key in THREAD_STORE:
        THREAD_STORE[key]["status"] = "closed"
    return s
