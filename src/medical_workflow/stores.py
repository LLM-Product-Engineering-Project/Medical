"""인메모리 저장소 및 유틸리티 함수"""

import json
import re
from datetime import datetime
from typing import Dict, Any

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
