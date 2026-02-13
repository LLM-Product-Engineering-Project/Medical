"""
의료 진료 전사 분석 워크플로우
- LangGraph 기반 agentic workflow
- Memory & Reflection 기능 포함
"""

import os
import re
import json
import glob
from datetime import datetime
from typing import TypedDict, Optional, Dict, Any, List, Literal

from langgraph.graph import StateGraph, END
from langchain_openai import ChatOpenAI
from langchain_tavily import TavilySearch

# .env 파일 로드
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv가 없으면 환경 변수에서 직접 읽기

# ============================================================
# 환경 변수 설정
# ============================================================

def load_env_keys():
    """환경 변수에서 API 키 로드"""
    required_keys = [
        'LANGSMITH_API_KEY',
        'UPSTAGE_API_KEY',
        'TAVILY_API_KEY',
    ]

    missing_keys = []
    for key in required_keys:
        if not os.environ.get(key):
            missing_keys.append(key)

    if missing_keys:
        print(f"경고: 다음 환경 변수가 설정되지 않았습니다: {', '.join(missing_keys)}")
        print("실행하려면 다음 환경 변수를 설정하세요:")
        for key in missing_keys:
            print(f"  export {key}='your_key_here'")

    # LangSmith 설정
    os.environ.setdefault("LANGSMITH_TRACING_V2", "true")
    os.environ.setdefault("LANGSMITH_ENDPOINT", "https://api.smith.langchain.com")
    os.environ.setdefault("LANGSMITH_PROJECT", "agentic-workflow")


# ============================================================
# Stores
# ============================================================

THREAD_STORE: Dict[str, Dict[str, Any]] = {}
VISIT_STORE: Dict[str, Dict[str, Any]] = {}


def thread_key(patient_id: str, diagnosis_key: str) -> str:
    return f"{patient_id}::{diagnosis_key}"


def now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def parse_json_safely(text: str) -> Any:
    try:
        return json.loads(text)
    except Exception:
        m = re.search(r"\{.*\}|\[.*\]", text, re.DOTALL)
        if not m:
            return {}
        try:
            return json.loads(m.group(0))
        except Exception:
            return {}


def upsert_visit_record(s: Dict[str, Any]) -> None:
    pid = s.get("patient_id", "p1")
    vdate = s.get("visit_date")
    if not vdate:
        return

    VISIT_STORE.setdefault(pid, {})
    rec = VISIT_STORE[pid].setdefault(
        vdate,
        {
            "visit_date": vdate,
            "visit_ids": [],
            "transcripts": [],
            "final_answers": [],
            "alarm_plans": [],
        },
    )

    if s.get("visit_id"):
        rec["visit_ids"].append(s["visit_id"])
    if s.get("transcript"):
        rec["transcripts"].append(s["transcript"])
    if s.get("final_answer"):
        rec["final_answers"].append(s["final_answer"])
    if s.get("alarm_plan"):
        rec["alarm_plans"].append(s["alarm_plan"])


# ============================================================
# State
# ============================================================

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


# ============================================================
# Nodes
# ============================================================

def n_parse_input_meta(s: WFState) -> WFState:
    fn = s.get("input_filename", "")
    m = re.search(r"Recording_(\d{8})\.txt$", fn)
    if m:
        ymd = m.group(1)
        s = {**s, "visit_date": f"{ymd[:4]}-{ymd[4:6]}-{ymd[6:]}"}

    s = {**s, "patient_id": "p1"}  # 단일 환자 가정
    return s


def n_deidentify_redact(s: WFState) -> WFState:
    t = s.get("transcript", "")

    t = re.sub(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", "[REDACTED_EMAIL]", t)
    t = re.sub(r"\b01[016789]-?\d{3,4}-?\d{4}\b", "[REDACTED_PHONE]", t)
    t = re.sub(r"\b0\d{1,2}-?\d{3,4}-?\d{4}\b", "[REDACTED_PHONE]", t)
    t = re.sub(r"\b\d{6}-?\d{7}\b", "[REDACTED_RRN]", t)
    t = re.sub(
        r"(서울|부산|대구|인천|광주|대전|울산|세종|경기|강원|충북|충남|전북|전남|경북|경남|제주)\s?[^\n]{0,20}(구|군|시|동|로|길)\s?\d{0,4}",
        "[REDACTED_ADDRESS]",
        t,
    )

    return {**s, "redacted_transcript": t}


def n_extract_doctor(s: WFState, llm) -> WFState:
    return {**s, "doctor_text": s.get("redacted_transcript", s.get("transcript", ""))}


def n_extract_clinical(s: WFState, llm) -> WFState:
    prompt = f"""
의료 진료 전사에서 정보 추출.
JSON만 출력.

{{
  "diagnoses": [{{"name": "string", "confidence": 0.0}}],
  "doctor_guidelines": [
    {{"category":"lifestyle|medication|diet|exercise|followup|warning|other",
      "text":"string",
      "source":"doctor"}}
  ]
}}

전사:
{s["doctor_text"]}
"""
    resp = llm.invoke(prompt)
    extracted = parse_json_safely(resp.content)
    if not isinstance(extracted, dict):
        extracted = {}
    extracted.setdefault("diagnoses", [])
    extracted.setdefault("doctor_guidelines", [])
    return {**s, "extracted": extracted}


def n_has_diagnosis(s: WFState, llm) -> WFState:
    d = (s.get("extracted") or {}).get("diagnoses") or []
    if not d:
        return {**s, "has_diagnosis": False, "diagnosis_key": None}
    return {**s, "has_diagnosis": True, "diagnosis_key": d[0].get("name")}


def n_is_existing(s: WFState, llm) -> WFState:
    key = thread_key(s["patient_id"], s["diagnosis_key"])
    return {**s, "is_existing": key in THREAD_STORE}


def _ensure_thread_defaults(t: Dict[str, Any]) -> Dict[str, Any]:
    t.setdefault("events", [])
    t.setdefault("memories", [])      # Memory stream
    t.setdefault("reflections", [])   # Reflection outputs
    t.setdefault("alarm_opt_in", None)
    return t


def n_create_thread(s: WFState, llm) -> WFState:
    key = thread_key(s["patient_id"], s["diagnosis_key"])
    THREAD_STORE[key] = _ensure_thread_defaults(
        {
            "thread_id": f"thread_{s['patient_id']}_{s['diagnosis_key']}",
            "patient_id": s["patient_id"],
            "diagnosis_key": s["diagnosis_key"],
            "status": "active",
        }
    )
    t = THREAD_STORE[key]
    return {**s, "thread_id": t["thread_id"], "thread": t, "alarm_opt_in": t.get("alarm_opt_in")}


def n_load_thread(s: WFState, llm) -> WFState:
    key = thread_key(s["patient_id"], s["diagnosis_key"])
    t = THREAD_STORE[key]
    _ensure_thread_defaults(t)
    return {**s, "thread_id": t["thread_id"], "thread": t, "alarm_opt_in": t.get("alarm_opt_in")}


def n_retrieve_memories(s: WFState) -> WFState:
    """
    간단 휴리스틱 retriever:
    - 최근 N개 memory + 최근 N개 event에서 요약된 memory를 우선 사용
    """
    thread = s.get("thread") or {}
    memories = thread.get("memories", []) or []
    events = thread.get("events", []) or []

    # 최근성 우선
    recent_mem = memories[-8:]
    recent_ev = events[-3:]

    # event를 memory로 쓰기 위한 간단 projection
    ev_mem = []
    for ev in recent_ev:
        gs = ev.get("guidelines", []) or []
        ev_mem.append(
            {
                "ts": ev.get("visit_date") or "",
                "type": "event",
                "text": f"visit={ev.get('visit_id')} guidelines={len(gs)} close={ev.get('should_close')}",
                "importance": 0.4,
            }
        )

    retrieved = recent_mem + ev_mem
    return {**s, "retrieved_memories": retrieved}


def n_detect_closure(s: WFState, llm) -> WFState:
    prompt = f"""
이 진료에서 "{s.get("diagnosis_key","")}" 질병 관리(스레드)를 종료한다는 의미인가?
JSON만 출력.
{{"should_close": true/false}}

전사:
{s["doctor_text"]}
"""
    resp = llm.invoke(prompt)
    out = parse_json_safely(resp.content)
    should_close = False
    if isinstance(out, dict):
        should_close = bool(out.get("should_close", False))
    return {**s, "should_close": should_close}


def n_close_thread(s: WFState, llm) -> WFState:
    key = thread_key(s["patient_id"], s["diagnosis_key"])
    if key in THREAD_STORE:
        THREAD_STORE[key]["status"] = "closed"
    return s


def n_has_guideline(s: WFState, llm) -> WFState:
    return {**s, "has_guideline": bool((s.get("extracted") or {}).get("doctor_guidelines"))}


def n_summarize_guidelines(s: WFState, llm) -> WFState:
    resp = llm.invoke(f"환자에게 전달 가능한 2문장 요약:\n{s['doctor_text']}")
    return {**s, "doctor_summary": resp.content.strip()}


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


def n_safety_check(s: WFState, llm) -> WFState:
    if s.get("has_guideline"):
        return {**s, "safe_guidelines": (s.get("extracted") or {}).get("doctor_guidelines", [])}
    return {**s, "safe_guidelines": s.get("rag_guidelines") or []}


def n_should_reflect(s: WFState) -> WFState:
    """
    간단 트리거:
    - 이벤트가 누적될수록(예: 3회마다) reflection 생성
    - 또는 이번 방문 가이드라인이 많으면 reflection
    """
    thread = s.get("thread") or {}
    events = thread.get("events", []) or []
    gcount = len(s.get("safe_guidelines") or [])
    should = False
    if len(events) > 0 and (len(events) % 3 == 0):
        should = True
    if gcount >= 5:
        should = True
    return {**s, "should_reflect": should}


def n_reflect_patient_state(s: WFState, llm) -> WFState:
    """
    retrieved_memories + 이번 방문 핵심을 요약해서 patient_state reflection을 저장
    """
    retrieved = s.get("retrieved_memories") or []
    diag = s.get("diagnosis_key") or ""
    g = s.get("safe_guidelines") or []

    prompt = f"""
아래는 환자의 "{diag}" 관련 누적 기록 일부와 이번 방문 가이드라인이다.
의료 조언을 새로 만들지 말고, "상태 요약"만 3줄로 작성해라.
한국어로 작성, 너무 단정하지 말 것.

[누적 기록]
{json.dumps(retrieved, ensure_ascii=False)}

[이번 방문 가이드라인]
{json.dumps(g, ensure_ascii=False)}
"""
    resp = llm.invoke(prompt)
    reflection = resp.content.strip()

    # thread에 저장
    key = thread_key(s["patient_id"], s["diagnosis_key"])
    t = THREAD_STORE.get(key)
    if t is not None:
        _ensure_thread_defaults(t)
        t["reflections"].append(
            {
                "ts": now_iso(),
                "visit_id": s.get("visit_id"),
                "visit_date": s.get("visit_date"),
                "text": reflection,
            }
        )

    return {**s, "patient_reflection": reflection}


def n_plan_next_actions(s: WFState, llm) -> WFState:
    """
    계획 노드:
    - should_close면 finalize
    - alarm_opt_in이 True면 build_alarm (HITL 스킵)
    - alarm_opt_in이 None이고 안전 가이드라인이 있으면 ask_hitl
    - alarm_opt_in이 False면 finalize
    """
    thread = s.get("thread") or {}
    cached_opt = thread.get("alarm_opt_in")
    if cached_opt in (True, False):
        alarm_opt_in = cached_opt
    else:
        alarm_opt_in = s.get("alarm_opt_in")

    # close면 무조건 finalize
    if s.get("should_close"):
        return {**s, "plan_action": "finalize", "should_ask_hitl": False, "alarm_opt_in": alarm_opt_in}

    # 이미 opt-in이면 바로 알람 생성 경로
    if alarm_opt_in is True:
        return {**s, "plan_action": "build_alarm", "should_ask_hitl": False, "alarm_opt_in": True}

    # opt-out이면 종료
    if alarm_opt_in is False:
        return {**s, "plan_action": "finalize", "should_ask_hitl": False, "alarm_opt_in": False}

    # 아직 미정이면 HITL 여부 결정
    has_any_guideline = bool(s.get("safe_guidelines"))
    if has_any_guideline:
        return {**s, "plan_action": "ask_hitl", "should_ask_hitl": True, "alarm_opt_in": None}

    # 가이드라인 자체가 없으면(이론상 거의 없음) finalize
    return {**s, "plan_action": "finalize", "should_ask_hitl": False, "alarm_opt_in": None}


def n_hitl_alarm_opt_in(s: WFState, llm) -> WFState:
    thread = s.get("thread") or {}
    cached = thread.get("alarm_opt_in")

    # thread에 결정이 있으면 스킵
    if cached in (True, False):
        return {**s, "alarm_opt_in": cached, "hitl_payload": None}

    # 2차 호출(사용자 응답 입력됨)
    if s.get("alarm_opt_in") in (True, False):
        return {**s, "hitl_payload": None}

    # 1차 호출: 질문만 생성
    return {
        **s,
        "hitl_payload": {
            "type": "hitl",
            "question": "치료를 위한 생활습관 알람과 일정표를 만들어드릴까요?",
            "choices": ["yes", "no"],
            "visit_date": s.get("visit_date"),
            "diagnosis_key": s.get("diagnosis_key"),
        },
    }


def n_build_alarm_plan(s: WFState, llm) -> WFState:
    key = thread_key(s["patient_id"], s["diagnosis_key"])
    thread = THREAD_STORE.get(key, {})
    events = thread.get("events", [])

    guidelines: List[Dict[str, Any]] = []
    for ev in events:
        guidelines.extend(ev.get("guidelines", []))
    guidelines.extend(s.get("safe_guidelines") or [])

    visit_date = s.get("visit_date")

    plan_items = []
    for g in guidelines:
        text = (g.get("text") or "").strip()
        cat = g.get("category") or "general"
        if not text:
            continue

        if cat == "medication":
            plan_items.append({"time": "09:00", "action": text})
            plan_items.append({"time": "21:00", "action": text})
        elif cat in ("lifestyle", "diet", "exercise"):
            plan_items.append({"time": "10:00", "action": text})
            plan_items.append({"time": "19:00", "action": text})
        else:
            plan_items.append({"time": "12:00", "action": text})

    s2 = {
        **s,
        "alarm_plan": {
            "patient_id": s["patient_id"],
            "start_date": visit_date,
            "timezone": "Asia/Seoul",
            "items": plan_items[:12],
        },
    }
    upsert_visit_record(s2)
    return s2


def _append_memory_and_event(s: WFState) -> None:
    """
    Memory stream + event append를 finalize에서 한 번에 처리.
    """
    if not s.get("has_diagnosis", False):
        return

    key = thread_key(s["patient_id"], s["diagnosis_key"])
    thread = THREAD_STORE.get(key)
    if thread is None:
        return

    _ensure_thread_defaults(thread)

    # event append
    thread["events"].append(
        {
            "visit_id": s.get("visit_id"),
            "visit_date": s.get("visit_date"),
            "guidelines": s.get("safe_guidelines", []),
            "should_close": s.get("should_close", False),
        }
    )

    # memory append (간단 버전)
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

    # alarm_opt_in 확정은 스레드당 1회만
    if thread.get("alarm_opt_in") not in (True, False) and s.get("alarm_opt_in") in (True, False):
        thread["alarm_opt_in"] = s["alarm_opt_in"]


def n_finalize(s: WFState, llm) -> WFState:
    if not s.get("has_diagnosis", False):
        s2 = {**s, "final_answer": {"type": "general_visit"}}
        upsert_visit_record(s2)
        return s2

    # thread 업데이트(이벤트, 메모리, opt-in)
    _append_memory_and_event(s)

    key = thread_key(s["patient_id"], s["diagnosis_key"])
    thread = THREAD_STORE.get(key)

    s2 = {
        **s,
        "final_answer": {
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
        },
    }
    upsert_visit_record(s2)
    return s2


# ============================================================
# Graph (new workflow)
# ============================================================

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

    # hitl -> build_alarm or finalize (alarm_opt_in value)
    g.add_conditional_edges(
        "hitl_alarm_opt_in",
        lambda s: "yes" if s.get("alarm_opt_in") is True else "no",
        {"yes": "build_alarm_plan", "no": "finalize"},
    )

    # build_alarm_plan -> finalize -> END
    g.add_edge("build_alarm_plan", "finalize")
    g.add_edge("finalize", END)

    return g.compile()


# ============================================================
# Runner (multi files)
# ============================================================

def run_many(input_dir: str, default_patient_id: str = "p1", reset_stores: bool = False):
    """
    지정된 디렉토리에서 Recording_*.txt 파일들을 읽어서 처리

    Args:
        input_dir: 입력 파일이 있는 디렉토리
        default_patient_id: 기본 환자 ID
        reset_stores: True면 기존 스레드/방문 저장소 초기화
    """
    if reset_stores:
        THREAD_STORE.clear()
        VISIT_STORE.clear()

    llm = ChatOpenAI(
        model="solar-pro2",
        base_url="https://api.upstage.ai/v1",
        api_key=os.environ.get("UPSTAGE_API_KEY"),
        temperature=0.1,
    )
    tavily = TavilySearch(api_key=os.environ.get("TAVILY_API_KEY"))
    graph = build_graph(llm, tavily)

    paths = sorted(glob.glob(os.path.join(input_dir, "Recording_*.txt")))
    if not paths:
        print(f"Recording_*.txt 파일을 찾을 수 없습니다: {input_dir}")
        return

    print(f"\n총 {len(paths)}개의 파일을 처리합니다.\n")

    for i, path in enumerate(paths, 1):
        fn = os.path.basename(path)
        m = re.search(r"Recording_(\d{8})\.txt$", fn)
        visit_id = f"v_{m.group(1)}" if m else f"v_{i}"

        with open(path, "r", encoding="utf-8") as f:
            transcript = f.read()

        base_state: WFState = {
            "patient_id": default_patient_id,
            "visit_id": visit_id,
            "input_filename": fn,
            "transcript": transcript,
            "alarm_opt_in": None,
            "hitl_payload": None,
        }

        print(f"\n===== [{i}/{len(paths)}] {fn} =====")

        # 1차 호출
        result1 = graph.invoke(base_state)

        # 1) 방문 처리 결과 먼저 출력
        print(json.dumps(result1.get("final_answer", {}), ensure_ascii=False, indent=2))

        # 2) HITL 질문이 있으면 질문 출력 후 2차 호출
        hitl = result1.get("hitl_payload")
        if hitl:
            print("\n" + "="*50)
            print(json.dumps(hitl, ensure_ascii=False, indent=2))
            ans = input("\n알람/일정표 생성? (yes/no): ").strip().lower()
            alarm_opt_in = ans in ("y", "yes")

            state2: WFState = {
                **result1,
                "alarm_opt_in": alarm_opt_in,
                "hitl_payload": None,
            }
            result2 = graph.invoke(state2)

            print("\n최종 결과:")
            print(json.dumps(result2.get("final_answer", {}), ensure_ascii=False, indent=2))


def main():
    """메인 함수"""
    # 환경 변수 로드
    load_env_keys()

    # 현재 디렉토리에서 Recording_*.txt 파일 찾기
    input_dir = os.path.dirname(os.path.abspath(__file__))

    print("="*60)
    print("의료 진료 전사 분석 워크플로우")
    print("="*60)
    print(f"\n입력 디렉토리: {input_dir}")

    # 워크플로우 실행
    run_many(input_dir, reset_stores=False)

    print("\n" + "="*60)
    print("처리 완료")
    print("="*60)


if __name__ == "__main__":
    main()
