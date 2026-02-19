"""워크플로우 상태 정의"""

from typing import TypedDict, Optional, Dict, Any, List, Literal

PlanAction = Literal["ask_hitl", "build_alarm", "finalize"]


class WFState(TypedDict, total=False):
    # input
    patient_id: str
    visit_id: str
    transcript: str
    input_filename: str
    visit_date: str

    # privacy
    redacted_transcript: str

    # extracted
    doctor_text: str
    extracted: Dict[str, Any]
    has_diagnosis: bool
    diagnosis_key: Optional[str]

    # thread
    is_existing: bool
    thread_id: Optional[str]
    thread: Optional[Dict[str, Any]]

    # memory retrieval
    retrieved_memories: Optional[List[Dict[str, Any]]]

    # guideline
    has_guideline: bool
    doctor_summary: Optional[str]

    # RAG
    rag_query: Optional[str]
    rag_raw: Optional[Dict[str, Any]]
    rag_guidelines: Optional[List[Dict[str, Any]]]

    # safety
    safe_guidelines: Optional[List[Dict[str, Any]]]

    # guardrail (score 기반)
    guardrail_risk_score:     Optional[float]                # 0.0–1.0 위험도 가중합
    guardrail_conflict_score: Optional[float]                # 0.0–1.0 충돌 심각도 최댓값
    guardrail_evidence_items: Optional[List[Dict[str, Any]]] # {span, memory_id, source, retriever_score, reason_code}
    guardrail_evidence_score: Optional[float]                # evidence_items retriever_score 평균
    guardrail_route:          Optional[Literal["allow", "caution", "hitl", "block"]]
    guardrail_decision_log:   Optional[List[Dict[str, Any]]] # 단계별 판단 로그 (재현 가능)

    # closure
    should_close: bool

    # reflection
    should_reflect: bool
    patient_reflection: Optional[str]

    # planning
    plan_action: PlanAction
    should_ask_hitl: bool

    # HITL
    alarm_opt_in: Optional[bool]
    hitl_payload: Optional[Dict[str, Any]]

    # alarm
    alarm_plan: Optional[Dict[str, Any]]

    # error tracking
    errors: List[Dict[str, Any]]
    warnings: List[str]

    # output
    final_answer: Dict[str, Any]
