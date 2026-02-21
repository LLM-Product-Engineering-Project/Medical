"""LangGraph 워크플로우 그래프 빌드"""

from langgraph.graph import StateGraph, END
from langchain_openai import ChatOpenAI

from medical_workflow.state import WFState
from medical_workflow.nodes.input import n_parse_input_meta
from medical_workflow.nodes.extraction import n_extract_doctor, n_extract_clinical, n_has_diagnosis
from medical_workflow.nodes.thread import n_is_existing, n_create_thread, n_load_thread, n_detect_closure, n_close_thread, n_create_symptom_thread
from medical_workflow.nodes.memory import n_retrieve_memories, n_should_reflect, n_reflect_patient_state
from medical_workflow.nodes.guidelines import n_has_guideline, n_summarize_guidelines, n_safety_guardrail
from medical_workflow.nodes.search import n_rag_query_sanitize, n_rag_to_guidelines, n_rag_supplement
from medical_workflow.nodes.rag import n_rag_search
from medical_workflow.nodes.planning import n_plan_next_actions, n_hitl_alarm_opt_in
from medical_workflow.nodes.alarm import n_build_alarm_plan
from medical_workflow.nodes.finalize import n_finalize


def build_graph(llm: ChatOpenAI, retriever):
    """
    llm: LLM 객체 (ChatOpenAI)
    retriever: RAG용 retriever (예: vector_db.as_retriever(search_kwargs={"k": 1}))

    의료 정보 신뢰성을 위해 외부 실시간 검색 대신
    내부 검증된 문서 기반 RAG 검색을 사용합니다.
    """

    # 상태 기반 워크플로우 그래프 생성
    g = StateGraph(WFState)

    # ---------------------------
    # 1️⃣ 노드 등록 (각 처리 단계 정의)
    # ---------------------------

    # 입력 전처리 (비식별화는 runner에서 graph.invoke() 전에 PII Middleware로 처리)
    g.add_node("parse_input_meta", n_parse_input_meta)

    # 임상 정보 추출 (LLM 사용)
    g.add_node("extract_doctor", lambda s: n_extract_doctor(s, llm))
    g.add_node("extract_clinical", lambda s: n_extract_clinical(s, llm))
    g.add_node("has_diag", lambda s: n_has_diagnosis(s, llm))

    # 스레드 관리
    g.add_node("is_existing", lambda s: n_is_existing(s, llm))
    g.add_node("create_thread", lambda s: n_create_thread(s, llm))
    g.add_node("load_thread", lambda s: n_load_thread(s, llm))
    g.add_node("create_symptom_thread", lambda s: n_create_symptom_thread(s, llm))

    # 메모리 조회
    g.add_node("retrieve_memories", n_retrieve_memories)

    # 종료 판단
    g.add_node("detect_closure", lambda s: n_detect_closure(s, llm))
    g.add_node("close_thread", lambda s: n_close_thread(s, llm))

    # 가이드라인 처리
    g.add_node("has_guideline", lambda s: n_has_guideline(s, llm))
    g.add_node("summarize_guidelines", lambda s: n_summarize_guidelines(s, llm))

    # RAG 검색 흐름
    g.add_node("rag_query_sanitize", lambda s: n_rag_query_sanitize(s, llm))
    g.add_node("rag_search", lambda s: n_rag_search(s, retriever))
    g.add_node("rag_to_guidelines", lambda s: n_rag_to_guidelines(s, llm))
    g.add_node("rag_supplement", lambda s: n_rag_supplement(s, llm, retriever))

    # 안전성 검증 (4단 Guardrail)
    g.add_node("safety_guardrail", lambda s: n_safety_guardrail(s, llm))

    # 환자 상태 반영
    g.add_node("should_reflect", n_should_reflect)
    g.add_node("reflect_patient_state", lambda s: n_reflect_patient_state(s, llm))

    # 행동 계획 수립
    g.add_node("plan_next_actions", lambda s: n_plan_next_actions(s, llm))

    # 알람 관련
    g.add_node("hitl_alarm_opt_in", lambda s: n_hitl_alarm_opt_in(s, llm))
    g.add_node("build_alarm_plan", lambda s: n_build_alarm_plan(s, llm))

    # 최종 응답 생성
    g.add_node("finalize", lambda s: n_finalize(s, llm))

    # 시작 노드 설정
    g.set_entry_point("parse_input_meta")

    # ---------------------------
    # 2️⃣ 기본 흐름 정의
    # ---------------------------

    # 입력 → (extract_doctor || extract_clinical 병렬) → 진단 여부 판단
    # ※ 비식별화(redacted_transcript)는 runner에서 graph.invoke() 전에 완료됨
    g.add_edge("parse_input_meta", "extract_doctor")
    g.add_edge("parse_input_meta", "extract_clinical")
    g.add_edge("extract_doctor", "has_diag")
    g.add_edge("extract_clinical", "has_diag")

    # ---------------------------
    # 3️⃣ 진단 여부 분기
    # ---------------------------

    # 진단 있음 → 스레드 관리
    # 진단 없고 증상 있음 → 증상 임시 스레드 생성 후 종료
    # 진단 없고 증상도 없음 → 바로 종료
    g.add_conditional_edges(
        "has_diag",
        lambda s: (
            "diagnosis" if s.get("has_diagnosis")
            else "symptom" if s.get("has_symptom")
            else "no"
        ),
        {"diagnosis": "is_existing", "symptom": "create_symptom_thread", "no": "finalize"},
    )
    g.add_edge("create_symptom_thread", "retrieve_memories")

    # ---------------------------
    # 4️⃣ 기존 스레드 여부 분기
    # ---------------------------

    g.add_conditional_edges(
        "is_existing",
        lambda s: "load" if s.get("is_existing") else "create",
        {"load": "load_thread", "create": "create_thread"},
    )

    # 로드/생성 후 → 메모리 조회 → 종료 여부 판단
    g.add_edge("load_thread", "retrieve_memories")
    g.add_edge("create_thread", "retrieve_memories")
    g.add_edge("retrieve_memories", "detect_closure")

    # ---------------------------
    # 5️⃣ 스레드 종료 여부 분기
    # ---------------------------

    g.add_conditional_edges(
        "detect_closure",
        lambda s: "close" if s.get("should_close") else "keep",
        {"close": "close_thread", "keep": "has_guideline"},
    )

    # 종료 시 바로 finalize
    g.add_edge("close_thread", "finalize")

    # ---------------------------
    # 6️⃣ 가이드라인 확보
    # ---------------------------

    # 이미 가이드라인 있으면 요약
    # 증상 스레드(진단명 없음): 가이드라인/RAG/guardrail 전체 스킵 → 바로 plan_next_actions
    #   (n_has_guideline에서 이미 has_guideline=False 강제, 여기서 구조적으로 차단)
    # 그 외 → RAG 검색
    g.add_conditional_edges(
        "has_guideline",
        lambda s: (
            "yes" if s.get("has_guideline")
            else "symptom" if s.get("has_symptom")
            else "no"
        ),
        {"yes": "summarize_guidelines", "symptom": "plan_next_actions", "no": "rag_query_sanitize"},
    )

    # 요약 → 보완 → 안전성 검사
    g.add_edge("summarize_guidelines", "rag_supplement")

    # 검색 → 가이드라인 변환 → 보완 → 안전성 검사
    g.add_edge("rag_query_sanitize", "rag_search")
    g.add_edge("rag_search", "rag_to_guidelines")
    g.add_edge("rag_to_guidelines", "rag_supplement")

    g.add_edge("rag_supplement", "safety_guardrail")

    # ---------------------------
    # 7️⃣ Guardrail 라우팅
    # ---------------------------

    # allow / caution → 정상 흐름
    # hitl             → 충돌 검토 (기존 HITL 노드 재활용)
    # block            → 즉시 종료 (의료진 상담 안내)
    g.add_conditional_edges(
        "safety_guardrail",
        lambda s: s.get("guardrail_route", "allow"),
        {
            "allow":   "should_reflect",
            "caution": "should_reflect",
            "hitl":    "hitl_alarm_opt_in",
            "block":   "finalize",
        },
    )

    g.add_conditional_edges(
        "should_reflect",
        lambda s: "yes" if s.get("should_reflect") else "no",
        {"yes": "reflect_patient_state", "no": "plan_next_actions"},
    )

    g.add_edge("reflect_patient_state", "plan_next_actions")

    # ---------------------------
    # 8️⃣ 행동 계획 분기
    # ---------------------------

    g.add_conditional_edges(
        "plan_next_actions",
        lambda s: s.get("plan_action", "finalize"),
        {
            "ask_hitl": "hitl_alarm_opt_in",   # 알람 동의 물어보기
            "build_alarm": "build_alarm_plan", # 바로 알람 생성
            "finalize": "finalize"             # 그냥 종료
        },
    )

    # ---------------------------
    # 9️⃣ HITL 알람 동의 분기
    # ---------------------------

    g.add_conditional_edges(
        "hitl_alarm_opt_in",
        lambda s: "yes" if s.get("alarm_opt_in") is True else "no",
        {"yes": "build_alarm_plan", "no": "finalize"},
    )

    # 알람 생성 후 종료
    g.add_edge("build_alarm_plan", "finalize")
    g.add_edge("finalize", END)

    # 그래프 컴파일 후 반환
    return g.compile()