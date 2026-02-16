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
    errors = s.get("errors", [])
    warnings = s.get("warnings", [])

    # severity high 에러 개수 확인
    critical_errors = [e for e in errors if e.get("severity") == "high"]

    if not s.get("has_diagnosis", False):
        final_answer = {"type": "general_visit"}

        # 진단 없는 경우에도 에러 정보 포함
        if errors or warnings:
            final_answer["has_errors"] = len(errors) > 0
            final_answer["has_critical_errors"] = len(critical_errors) > 0
            final_answer["errors"] = errors if errors else None
            final_answer["warnings"] = warnings if warnings else None
            final_answer["data_completeness"] = "incomplete" if critical_errors else "complete"

        s2 = {**s, "final_answer": final_answer}
        upsert_visit_record(s2)
        return s2

    _append_memory_and_event(s)

    key = thread_key(s["patient_id"], s["diagnosis_key"])
    thread = THREAD_STORE.get(key)

    final_answer = {
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

        # 에러/경고 정보 추가
        "has_errors": len(errors) > 0,
        "has_critical_errors": len(critical_errors) > 0,
        "errors": errors if errors else None,
        "warnings": warnings if warnings else None,

        # 의료 정보 신뢰성 플래그
        "data_completeness": "incomplete" if critical_errors else "complete"
    }

    # 치명적 에러가 있으면 사용자에게 명확히 알림
    if critical_errors:
        final_answer["user_message"] = (
            "⚠️ 일부 의료 정보 처리에 실패했습니다. "
            "정확한 정보는 의료진과 직접 상담하시기 바랍니다."
        )
    elif warnings:
        final_answer["user_message"] = "\n".join(warnings)

    s2 = {**s, "final_answer": final_answer}
    upsert_visit_record(s2)
    return s2
