"""인메모리 저장소 및 유틸리티 함수"""

import json
import re
import logging
from datetime import datetime
from typing import Dict, Any, Optional, Tuple

logger = logging.getLogger(__name__)

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


def safe_llm_invoke(
    llm,
    prompt: str,
    node_name: str,
    fallback_value: Any,
    parse_json: bool = False,
    severity: str = "medium"
) -> Tuple[Any, Optional[Dict[str, Any]]]:
    """
    안전한 LLM 호출 래퍼

    Args:
        llm: LLM 객체
        prompt: 프롬프트 문자열
        node_name: 노드 이름 (에러 추적용)
        fallback_value: 실패 시 반환할 기본값
        parse_json: JSON 파싱 여부
        severity: 에러 심각도 ("high", "medium", "low")

    Returns:
        (result, error_info)
        - result: 성공 시 LLM 응답, 실패 시 fallback_value
        - error_info: 에러 발생 시 Dict, 성공 시 None
    """
    try:
        resp = llm.invoke(prompt)
        content = resp.content

        if parse_json:
            parsed = parse_json_safely(content)
            # 빈 JSON 응답 체크
            if not parsed or (isinstance(parsed, dict) and not any(parsed.values())):
                raise ValueError("LLM returned empty or invalid JSON")
            return parsed, None

        # 빈 텍스트 응답 체크
        if not content or not content.strip():
            raise ValueError("LLM returned empty response")

        return content, None

    except Exception as e:
        logger.error(f"[{node_name}] LLM call failed: {e}", exc_info=True)

        error_info = {
            "node": node_name,
            "timestamp": now_iso(),
            "error_type": type(e).__name__,
            "message": str(e),
            "fallback_used": True,
            "severity": severity
        }
        return fallback_value, error_info


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
