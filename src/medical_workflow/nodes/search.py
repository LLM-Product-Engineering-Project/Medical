"""RAG 검색 파이프라인 노드 (구 Tavily)"""

from medical_workflow.state import WFState
from medical_workflow.stores import safe_llm_invoke


def n_rag_query_sanitize(s: WFState, llm) -> WFState:
    """RAG 검색 쿼리 생성"""
    diagnosis = (s.get("diagnosis_key") or "").strip()
    query = f"{diagnosis} 관리 방법"
    return {**s, "rag_query": query}


def n_rag_to_guidelines(s: WFState, llm) -> WFState:
    """RAG 검색 결과를 가이드라인으로 변환"""
    prompt = f"""
아래 검색 결과를 바탕으로
안전한 질병 관리 지침을 JSON 배열로 생성.

각 원소:
{{"category":"lifestyle|medication|diet|exercise|followup|warning|other",
  "text":"string",
  "source":"rag"}}

검색결과:
{s.get("rag_raw")}
"""

    fallback = []
    guidelines, error = safe_llm_invoke(
        llm, prompt,
        node_name="rag_to_guidelines",
        fallback_value=fallback,
        parse_json=True,
        severity="high"  # 가이드라인이므로 high
    )

    if not isinstance(guidelines, list):
        guidelines = []

    new_state = {**s, "rag_guidelines": guidelines}
    if error:
        errors = s.get("errors", [])
        errors.append(error)
        new_state["errors"] = errors

        warnings = s.get("warnings", [])
        warnings.append("⚠️ 검색 결과에서 가이드라인을 생성할 수 없습니다. 의료진과 상담하세요.")
        new_state["warnings"] = warnings

    return new_state
