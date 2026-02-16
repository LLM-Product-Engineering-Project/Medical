"""방문 기록 저장소 관리"""

from typing import Dict, Any


VISIT_STORE: Dict[str, Dict[str, Any]] = {}


def upsert_visit_record(s: Dict[str, Any]) -> None:
    """방문 기록 저장"""
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
