"""가이드라인 판단, 요약, 안전성 체크 노드"""

from medical_workflow.state import WFState
from medical_workflow.stores import safe_llm_invoke


def n_has_guideline(s: WFState, llm) -> WFState:
    return {**s, "has_guideline": bool((s.get("extracted") or {}).get("doctor_guidelines"))}


def n_summarize_guidelines(s: WFState, llm) -> WFState:
    prompt = f"환자에게 전달 가능한 2문장 요약:\n{s['doctor_text']}"

    fallback = "의사 선생님의 조언을 확인하세요."
    summary, error = safe_llm_invoke(
        llm, prompt,
        node_name="summarize_guidelines",
        fallback_value=fallback,
        parse_json=False,
        severity="medium"
    )

    new_state = {**s, "doctor_summary": summary.strip() if isinstance(summary, str) else fallback}
    if error:
        errors = s.get("errors", [])
        errors.append(error)
        new_state["errors"] = errors

    return new_state


def n_safety_check(s: WFState, llm) -> WFState:
    if s.get("has_guideline"):
        return {**s, "safe_guidelines": (s.get("extracted") or {}).get("doctor_guidelines", [])}
    return {**s, "safe_guidelines": s.get("rag_guidelines") or []}
