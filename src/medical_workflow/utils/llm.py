"""LLM 호출 관련 유틸리티"""

import logging
from typing import Any, Optional, Tuple, Dict

logger = logging.getLogger(__name__)


def now_iso() -> str:
    """현재 시각을 ISO 포맷으로 반환 (임시, helpers로 이동 예정)"""
    from datetime import datetime
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


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
    from .parsing import parse_json_safely

    try:
        resp = llm.invoke(prompt)
        content = resp.content

        if parse_json:
            parsed = parse_json_safely(content, node_name=node_name)
            # 빈 JSON 응답 체크 (dict/list 자체가 비어있는 경우만 차단)
            # NOTE: {"should_close": false}, {"detected": []} 같은 falsy 값은 유효한 응답
            if not parsed:
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
