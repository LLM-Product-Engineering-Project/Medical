"""메모리 조회 및 리플렉션 노드"""

import json

from medical_workflow.state import WFState
from medical_workflow.stores import THREAD_STORE, thread_key, now_iso


def n_retrieve_memories(s: WFState) -> WFState:
    """
    간단 휴리스틱 retriever:
    - 최근 N개 memory + 최근 N개 event에서 요약된 memory를 우선 사용
    """
    thread = s.get("thread") or {}
    memories = thread.get("memories", []) or []
    events = thread.get("events", []) or []

    recent_mem = memories[-8:]
    recent_ev = events[-3:]

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

    key = thread_key(s["patient_id"], s["diagnosis_key"])
    t = THREAD_STORE.get(key)
    if t is not None:
        from medical_workflow.nodes.thread import _ensure_thread_defaults
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
