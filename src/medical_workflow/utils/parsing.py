"""데이터 파싱 유틸리티"""

import json
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


def parse_json_safely(text: str, node_name: str = "") -> Any:
    """
    텍스트에서 JSON을 안전하게 파싱

    Args:
        text: JSON을 포함한 텍스트
        node_name: 호출 노드명 (에러 로그 식별용)

    Returns:
        파싱된 JSON 객체 또는 빈 딕셔너리
    """
    tag = f"[{node_name}] " if node_name else ""

    try:
        return json.loads(text)
    except Exception:
        pass

    m = re.search(r"\{.*\}|\[.*\]", text, re.DOTALL)
    if not m:
        logger.error(f"{tag}[PARSE ERROR] JSON 블록을 찾을 수 없음")
        logger.error(f"{tag}[RAW] {text!r}")
        return {}

    try:
        return json.loads(m.group(0))
    except Exception:
        logger.exception(f"{tag}[PARSE ERROR] JSON 추출 실패")
        logger.error(f"{tag}[RAW] {text!r}")
        return {}
