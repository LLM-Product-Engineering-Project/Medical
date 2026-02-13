"""스레드 관리 및 종료 감지 노드"""

from typing import Dict, Any

from medical_workflow.state import WFState
from medical_workflow.stores import THREAD_STORE, thread_key, parse_json_safely


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
    return {**s, "thread_id": t["thread_id"], "thread": t, "alarm_opt_in": t.get("alarm_opt_in")}


def n_detect_closure(s: WFState, llm) -> WFState:
    prompt = f"""
이 진료에서 "{s.get("diagnosis_key","")}" 질병 관리(스레드)를 종료한다는 의미인가?
JSON만 출력.
{{"should_close": true/false}}

전사:
{s["doctor_text"]}
"""
    resp = llm.invoke(prompt)
    out = parse_json_safely(resp.content)
    should_close = False
    if isinstance(out, dict):
        should_close = bool(out.get("should_close", False))
    return {**s, "should_close": should_close}


def n_close_thread(s: WFState, llm) -> WFState:
    key = thread_key(s["patient_id"], s["diagnosis_key"])
    if key in THREAD_STORE:
        THREAD_STORE[key]["status"] = "closed"
    return s
