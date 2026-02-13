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

    # tavily
    tavily_query: Optional[str]
    tavily_raw: Optional[Dict[str, Any]]
    rag_guidelines: Optional[List[Dict[str, Any]]]

    # safety
    safe_guidelines: Optional[List[Dict[str, Any]]]

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

    # output
    final_answer: Dict[str, Any]
