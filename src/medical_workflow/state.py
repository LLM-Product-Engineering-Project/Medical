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
    # diagnosis_key와 분리된 상태 정보 (치료 단계·반응 등)
    disease_status: Optional[str]    # 예: "항암치료 반응 양호", "2차 항암치료 진행 중"

    # symptom thread
    has_symptom: bool
    symptom_keys: Optional[List[str]]    # 추출된 증상 목록
    symptom_summary: Optional[str]       # 스레드 키용 요약 (예: "발열_손발물집")

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
    rag_supplement_raw: Optional[str]    # rag_supplement가 검색한 원문 (guardrail 검증용)
    rag_guidelines: Optional[List[Dict[str, Any]]]
    rag_diagnosis_found: Optional[bool]  # CSV에 해당 진단명 존재 여부

    # safety
    safe_guidelines: Optional[List[Dict[str, Any]]]
    safety_checked: bool  # guardrail 이미 처리됨 (idempotency guard)

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
    has_errors: bool  # LLM 실패·빈입력 등 에러 발생 시 노드에서 직접 설정

    # output
    final_answer: Dict[str, Any]
