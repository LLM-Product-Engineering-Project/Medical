"""Tavily 검색 파이프라인 노드"""

from langchain_tavily import TavilySearch

from medical_workflow.state import WFState
from medical_workflow.stores import parse_json_safely


def n_tavily_query_sanitize(s: WFState, llm) -> WFState:
    diagnosis = (s.get("diagnosis_key") or "").strip()
    query = f"{diagnosis} 관리 방법"
    return {**s, "tavily_query": query}


def n_tavily_search(s: WFState, tavily: TavilySearch) -> WFState:
    query = s.get("tavily_query") or f"{s['diagnosis_key']} 관리 방법"
    results = tavily.invoke({"query": query})
    return {**s, "tavily_query": query, "tavily_raw": results}


def n_tavily_to_guidelines(s: WFState, llm) -> WFState:
    prompt = f"""
아래 검색 결과를 바탕으로
안전한 질병 관리 지침을 JSON 배열로 생성.

각 원소:
{{"category":"lifestyle|medication|diet|exercise|followup|warning|other",
  "text":"string",
  "source":"rag"}}

검색결과:
{s.get("tavily_raw")}
"""
    resp = llm.invoke(prompt)
    guidelines = parse_json_safely(resp.content)
    if not isinstance(guidelines, list):
        guidelines = []
    return {**s, "rag_guidelines": guidelines}
