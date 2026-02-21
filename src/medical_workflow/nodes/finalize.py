"""최종 응답 및 메모리/이벤트 저장 노드"""

from medical_workflow.state import WFState
from medical_workflow.stores import (
    THREAD_STORE,
    thread_key,
    now_iso,
    upsert_visit_record,
    safe_llm_invoke,
)
from medical_workflow.nodes.thread import _ensure_thread_defaults


def _append_memory_and_event(s: WFState) -> None:
    """Memory stream + event append를 finalize에서 한 번에 처리."""
    if s.get("has_diagnosis", False):
        key = thread_key(s["patient_id"], s["diagnosis_key"])
        thread = THREAD_STORE.get(key)
    elif s.get("has_symptom", False):
        # 증상 스레드: state에 저장된 thread 객체(THREAD_STORE 참조) 사용
        thread = s.get("thread")
    else:
        return

    if thread is None:
        return

    _ensure_thread_defaults(thread)

    # 동일 visit_id 이벤트/메모리 중복 적재 방지 (2차 호출 시 재진입 방지)
    visit_id = s.get("visit_id")
    if any(ev.get("visit_id") == visit_id for ev in thread["events"]):
        # 이미 적재된 경우 alarm_opt_in 동기화만 수행
        if thread.get("alarm_opt_in") not in (True, False) and s.get("alarm_opt_in") in (True, False):
            thread["alarm_opt_in"] = s["alarm_opt_in"]
        return

    thread["events"].append(
        {
            "visit_id": visit_id,
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

    # alarm_opt_in 동기화 (미설정 시에만)
    if thread.get("alarm_opt_in") not in (True, False) and s.get("alarm_opt_in") in (True, False):
        thread["alarm_opt_in"] = s["alarm_opt_in"]


def n_finalize(s: WFState, llm) -> WFState:
    errors = s.get("errors", [])
    warnings = s.get("warnings", [])

    # severity high 에러 개수 확인
    critical_errors = [e for e in errors if e.get("severity") == "high"]

    if not s.get("has_diagnosis", False):
        if s.get("has_symptom", False):
            # 증상 스레드 방문 — 진단 미확정이지만 의미 있는 결과 출력
            _append_memory_and_event(s)
            thread = s.get("thread") or {}
            symptom_summary = s.get("symptom_summary") or "증상"
            safe_guidelines = s.get("safe_guidelines") or []
            guardrail_route = s.get("guardrail_route") or "allow"

            final_answer = {
                "type": "symptom_thread_visit",
                "patient_id": s["patient_id"],
                "visit_id": s.get("visit_id"),
                "visit_date": s.get("visit_date"),
                "thread_id": s.get("thread_id"),
                "symptom_keys": s.get("symptom_keys"),
                "symptom_summary": symptom_summary,
                "guidelines": safe_guidelines,
                "alarm_opt_in": (thread.get("alarm_opt_in") if thread else s.get("alarm_opt_in")),
                "alarm_plan": s.get("alarm_plan"),
                "plan_action": s.get("plan_action"),
                "has_errors": len(errors) > 0,
                "has_critical_errors": len(critical_errors) > 0,
                "errors": errors if errors else None,
                "warnings": warnings if warnings else None,
                "data_completeness": "incomplete" if critical_errors else "complete",
                "guardrail_route":          guardrail_route,
                "guardrail_risk_score":     s.get("guardrail_risk_score"),
                "guardrail_conflict_score": s.get("guardrail_conflict_score"),
                "guardrail_evidence_score": s.get("guardrail_evidence_score"),
                "guardrail_decision_log":   s.get("guardrail_decision_log"),
            }

            if guardrail_route == "block":
                fallback_msg = (
                    "안전 검증에서 위험한 내용이 감지되었습니다. "
                    "반드시 담당 의료진과 직접 상담하시기 바랍니다."
                )
            elif critical_errors:
                fallback_msg = (
                    "일부 의료 정보 처리에 실패했습니다. "
                    "정확한 정보는 의료진과 직접 상담하시기 바랍니다."
                )
            elif warnings:
                fallback_msg = "\n".join(warnings)
            else:
                fallback_msg = (
                    f"증상({symptom_summary})에 대한 안내를 확인하였습니다. "
                    "아직 진단이 확정되지 않았으니 증상이 지속되면 의료진과 상담하세요."
                )

            guideline_texts = [g.get("text", "") for g in safe_guidelines if g.get("text")][:5]
            warning_summary = "; ".join(warnings[:3]) if warnings else "없음"

            prompt = f"""증상: {symptom_summary}
주요 가이드라인 (최대 5개):
{chr(10).join(f"- {t}" for t in guideline_texts) if guideline_texts else "없음"}
안전 검증 결과: {guardrail_route}
경고 사항: {warning_summary}

위 내용을 바탕으로 환자가 이해하기 쉬운 2~3문장 안내 메시지를 작성하라.
- 아직 진단이 확정되지 않은 상태임을 부드럽게 안내하라
- 의료 용어를 최소화하고 쉬운 말로 설명하라
- 메시지만 출력하라 (설명 없이).
"""
            llm_msg, error = safe_llm_invoke(
                llm, prompt,
                node_name="finalize_user_message",
                fallback_value=fallback_msg,
                parse_json=False,
                severity="low"
            )
            user_message = (llm_msg or "").strip() or fallback_msg
            final_answer["user_message"] = user_message

            if error:
                errors.append(error)
                final_answer["errors"] = errors
                final_answer["has_errors"] = True

            s2 = {**s, "final_answer": final_answer, "errors": errors}
            upsert_visit_record(s2)
            return s2

        else:
            # 진단도 증상도 없는 순수 일반 방문
            final_answer = {"type": "general_visit"}

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
        "data_completeness": "incomplete" if critical_errors else "complete",

        # guardrail 결과 (score 기반)
        "guardrail_route":          s.get("guardrail_route"),
        "guardrail_risk_score":     s.get("guardrail_risk_score"),
        "guardrail_conflict_score": s.get("guardrail_conflict_score"),
        "guardrail_evidence_score": s.get("guardrail_evidence_score"),
        "guardrail_decision_log":   s.get("guardrail_decision_log"),
    }

    # user_message: LLM으로 환자 맞춤형 안내 메시지 생성
    guardrail_route = s.get("guardrail_route") or "allow"
    safe_guidelines = s.get("safe_guidelines") or []
    diagnosis_key = s.get("diagnosis_key", "")

    # block / critical error 상황별 fallback 메시지 (LLM 실패 시 사용)
    if guardrail_route == "block":
        fallback_msg = (
            "안전 검증에서 위험한 내용이 감지되어 가이드라인을 제공할 수 없습니다. "
            "반드시 담당 의료진과 직접 상담하시기 바랍니다."
        )
    elif critical_errors:
        fallback_msg = (
            "일부 의료 정보 처리에 실패했습니다. "
            "정확한 정보는 의료진과 직접 상담하시기 바랍니다."
        )
    elif warnings:
        fallback_msg = "\n".join(warnings)
    else:
        fallback_msg = f"{diagnosis_key} 관련 가이드라인을 확인하였습니다. 의료진의 지도에 따라 건강 관리를 이어가세요."

    guideline_texts = [g.get("text", "") for g in safe_guidelines if g.get("text")][:5]
    warning_summary = "; ".join(warnings[:3]) if warnings else "없음"

    prompt = f"""환자 진단: {diagnosis_key}
주요 가이드라인 (최대 5개):
{chr(10).join(f"- {t}" for t in guideline_texts) if guideline_texts else "없음"}
안전 검증 결과: {guardrail_route}
경고 사항: {warning_summary}
심각한 처리 오류 여부: {"있음" if critical_errors else "없음"}

위 내용을 바탕으로 환자가 이해하기 쉬운 2~3문장 안내 메시지를 작성하라.
- 의료 용어를 최소화하고 쉬운 말로 설명하라
- 다음에 해야 할 행동을 명확히 안내하라
- guardrail이 block이면 의료진 상담 필요성을 강조하라
- caution이면 주의가 필요함을 부드럽게 안내하라
- 메시지만 출력하라 (설명 없이).
"""

    llm_msg, error = safe_llm_invoke(
        llm, prompt,
        node_name="finalize_user_message",
        fallback_value=fallback_msg,
        parse_json=False,
        severity="low"
    )

    user_message = (llm_msg or "").strip() or fallback_msg
    final_answer["user_message"] = user_message

    if error:
        errors.append(error)
        final_answer["errors"] = errors
        final_answer["has_errors"] = True

    s2 = {**s, "final_answer": final_answer, "errors": errors}
    upsert_visit_record(s2)
    return s2
