"""알람 계획 생성 노드"""

from typing import Dict, Any, List

from medical_workflow.state import WFState
from medical_workflow.stores import THREAD_STORE, thread_key, upsert_visit_record


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
