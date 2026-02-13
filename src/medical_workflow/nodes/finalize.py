"""최종 응답 및 메모리/이벤트 저장 노드"""

from medical_workflow.state import WFState
from medical_workflow.stores import (
    THREAD_STORE,
    thread_key,
    now_iso,
    upsert_visit_record,
)
from medical_workflow.nodes.thread import _ensure_thread_defaults


def _append_memory_and_event(s: WFState) -> None:
    """Memory stream + event append를 finalize에서 한 번에 처리."""
    if not s.get("has_diagnosis", False):
        return

    key = thread_key(s["patient_id"], s["diagnosis_key"])
    thread = THREAD_STORE.get(key)
    if thread is None:
        return

    _ensure_thread_defaults(thread)

    thread["events"].append(
        {
            "visit_id": s.get("visit_id"),
            "visit_date": s.get("visit_date"),
            "guidelines": s.get("safe_guidelines", []),
            "should_close": s.get("should_close", False),
        }
    )

    mem_text_parts = []
    if s.get("doctor_summary"):
        mem_text_parts.append(f"summary: {s.get('doctor_summary')}")
    gs = s.get("safe_guidelines") or []
    if gs:
        mem_text_parts.append(f"guidelines: {len(gs)} items")
    if s.get("should_close"):
        mem_text_parts.append("closure: suggested")

    mem_text = " | ".join(mem_text_parts).strip()
    if mem_text:
        thread["memories"].append(
            {
                "ts": now_iso(),
                "visit_id": s.get("visit_id"),
                "visit_date": s.get("visit_date"),
                "type": "visit_memory",
                "text": mem_text,
                "importance": 0.6,
            }
        )

    if thread.get("alarm_opt_in") not in (True, False) and s.get("alarm_opt_in") in (True, False):
        thread["alarm_opt_in"] = s["alarm_opt_in"]


def n_finalize(s: WFState, llm) -> WFState:
    if not s.get("has_diagnosis", False):
        s2 = {**s, "final_answer": {"type": "general_visit"}}
        upsert_visit_record(s2)
        return s2

    _append_memory_and_event(s)

    key = thread_key(s["patient_id"], s["diagnosis_key"])
    thread = THREAD_STORE.get(key)

    s2 = {
        **s,
        "final_answer": {
            "type": "disease_thread_update",
            "patient_id": s["patient_id"],
            "visit_id": s.get("visit_id"),
            "visit_date": s.get("visit_date"),
            "diagnosis_key": s["diagnosis_key"],
            "thread_id": s.get("thread_id"),
            "guidelines": s.get("safe_guidelines") or [],
            "should_close": s.get("should_close", False),
            "alarm_opt_in": (thread.get("alarm_opt_in") if thread else s.get("alarm_opt_in")),
            "alarm_plan": s.get("alarm_plan"),
            "patient_reflection": s.get("patient_reflection"),
            "plan_action": s.get("plan_action"),
        },
    }
    upsert_visit_record(s2)
    return s2
