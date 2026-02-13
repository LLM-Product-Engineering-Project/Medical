"""가이드라인 판단, 요약, 안전성 체크 노드"""

from medical_workflow.state import WFState


def n_has_guideline(s: WFState, llm) -> WFState:
    return {**s, "has_guideline": bool((s.get("extracted") or {}).get("doctor_guidelines"))}


def n_summarize_guidelines(s: WFState, llm) -> WFState:
    resp = llm.invoke(f"환자에게 전달 가능한 2문장 요약:\n{s['doctor_text']}")
    return {**s, "doctor_summary": resp.content.strip()}


def n_safety_check(s: WFState, llm) -> WFState:
    if s.get("has_guideline"):
        return {**s, "safe_guidelines": (s.get("extracted") or {}).get("doctor_guidelines", [])}
    return {**s, "safe_guidelines": s.get("rag_guidelines") or []}
