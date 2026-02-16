"""데이터 파싱 유틸리티"""

import json
import re
from typing import Any


def parse_json_safely(text: str) -> Any:
    """
    텍스트에서 JSON을 안전하게 파싱

    Args:
        text: JSON을 포함한 텍스트

    Returns:
        파싱된 JSON 객체 또는 빈 딕셔너리
    """
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
