"""LangGraph 워크플로우 그래프 빌드"""

from langgraph.graph import StateGraph, END
from langchain_openai import ChatOpenAI
from langchain_tavily import TavilySearch

from medical_workflow.state import WFState
from medical_workflow.nodes.input import n_parse_input_meta, n_deidentify_redact
from medical_workflow.nodes.extraction import n_extract_doctor, n_extract_clinical, n_has_diagnosis
from medical_workflow.nodes.thread import n_is_existing, n_create_thread, n_load_thread, n_detect_closure, n_close_thread
from medical_workflow.nodes.memory import n_retrieve_memories, n_should_reflect, n_reflect_patient_state
from medical_workflow.nodes.guidelines import n_has_guideline, n_summarize_guidelines, n_safety_check
from medical_workflow.nodes.search import n_tavily_query_sanitize, n_tavily_search, n_tavily_to_guidelines
from medical_workflow.nodes.planning import n_plan_next_actions, n_hitl_alarm_opt_in
from medical_workflow.nodes.alarm import n_build_alarm_plan
from medical_workflow.nodes.finalize import n_finalize


def build_graph(llm: ChatOpenAI, tavily: TavilySearch):
    g = StateGraph(WFState)

    g.add_node("parse_input_meta", n_parse_input_meta)
    g.add_node("deidentify_redact", n_deidentify_redact)

    g.add_node("extract_doctor", lambda s: n_extract_doctor(s, llm))
    g.add_node("extract_clinical", lambda s: n_extract_clinical(s, llm))
    g.add_node("has_diag", lambda s: n_has_diagnosis(s, llm))

    g.add_node("is_existing", lambda s: n_is_existing(s, llm))
    g.add_node("create_thread", lambda s: n_create_thread(s, llm))
    g.add_node("load_thread", lambda s: n_load_thread(s, llm))

    g.add_node("retrieve_memories", n_retrieve_memories)

    g.add_node("detect_closure", lambda s: n_detect_closure(s, llm))
    g.add_node("close_thread", lambda s: n_close_thread(s, llm))

    g.add_node("has_guideline", lambda s: n_has_guideline(s, llm))
    g.add_node("summarize_guidelines", lambda s: n_summarize_guidelines(s, llm))

    g.add_node("tavily_query_sanitize", lambda s: n_tavily_query_sanitize(s, llm))
    g.add_node("tavily_search", lambda s: n_tavily_search(s, tavily))
    g.add_node("tavily_to_guidelines", lambda s: n_tavily_to_guidelines(s, llm))

    g.add_node("safety_check", lambda s: n_safety_check(s, llm))

    g.add_node("should_reflect", n_should_reflect)
    g.add_node("reflect_patient_state", lambda s: n_reflect_patient_state(s, llm))

    g.add_node("plan_next_actions", lambda s: n_plan_next_actions(s, llm))

    g.add_node("hitl_alarm_opt_in", lambda s: n_hitl_alarm_opt_in(s, llm))
    g.add_node("build_alarm_plan", lambda s: n_build_alarm_plan(s, llm))

    g.add_node("finalize", lambda s: n_finalize(s, llm))

    g.set_entry_point("parse_input_meta")

    # START -> privacy -> extract -> has_diag
    g.add_edge("parse_input_meta", "deidentify_redact")
    g.add_edge("deidentify_redact", "extract_doctor")
    g.add_edge("extract_doctor", "extract_clinical")
    g.add_edge("extract_clinical", "has_diag")

    # has_diag
    g.add_conditional_edges(
        "has_diag",
        lambda s: "yes" if s.get("has_diagnosis") else "no",
        {"yes": "is_existing", "no": "finalize"},
    )

    # is_existing -> load/create
    g.add_conditional_edges(
        "is_existing",
        lambda s: "load" if s.get("is_existing") else "create",
        {"load": "load_thread", "create": "create_thread"},
    )

    # load/create -> retrieve_memories -> detect_closure
    g.add_edge("load_thread", "retrieve_memories")
    g.add_edge("create_thread", "retrieve_memories")
    g.add_edge("retrieve_memories", "detect_closure")

    # detect_closure -> close or keep
    g.add_conditional_edges(
        "detect_closure",
        lambda s: "close" if s.get("should_close") else "keep",
        {"close": "close_thread", "keep": "has_guideline"},
    )

    # close_thread -> finalize -> END
    g.add_edge("close_thread", "finalize")
    g.add_edge("finalize", END)

    # keep path: has_guideline -> summarize or tavily
    g.add_conditional_edges(
        "has_guideline",
        lambda s: "yes" if s.get("has_guideline") else "no",
        {"yes": "summarize_guidelines", "no": "tavily_query_sanitize"},
    )

    g.add_edge("summarize_guidelines", "safety_check")

    g.add_edge("tavily_query_sanitize", "tavily_search")
    g.add_edge("tavily_search", "tavily_to_guidelines")
    g.add_edge("tavily_to_guidelines", "safety_check")

    # safety_check -> should_reflect? -> (reflect or skip) -> plan
    g.add_edge("safety_check", "should_reflect")
    g.add_conditional_edges(
        "should_reflect",
        lambda s: "yes" if s.get("should_reflect") else "no",
        {"yes": "reflect_patient_state", "no": "plan_next_actions"},
    )
    g.add_edge("reflect_patient_state", "plan_next_actions")

    # plan -> ask_hitl or build_alarm or finalize
    g.add_conditional_edges(
        "plan_next_actions",
        lambda s: s.get("plan_action", "finalize"),
        {"ask_hitl": "hitl_alarm_opt_in", "build_alarm": "build_alarm_plan", "finalize": "finalize"},
    )

    # hitl -> build_alarm or finalize
    g.add_conditional_edges(
        "hitl_alarm_opt_in",
        lambda s: "yes" if s.get("alarm_opt_in") is True else "no",
        {"yes": "build_alarm_plan", "no": "finalize"},
    )

    # build_alarm_plan -> finalize -> END
    g.add_edge("build_alarm_plan", "finalize")
    g.add_edge("finalize", END)

    return g.compile()
