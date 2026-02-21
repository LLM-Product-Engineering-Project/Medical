"""입력 파싱 노드

비식별화는 PII Middleware(pii_middleware.py)에서 그래프 실행 전에 처리한다.
n_deidentify_redact는 테스트 코드 호환성을 위해 래퍼로만 남겨둔다.
"""

import re

from medical_workflow.state import WFState
from medical_workflow.pii_middleware import redact_pii


def n_parse_input_meta(s: WFState) -> WFState:
    fn = s.get("input_filename", "")
    m = re.search(r"Recording_(\d{8})\.txt$", fn)
    if m:
        ymd = m.group(1)
        s = {**s, "visit_date": f"{ymd[:4]}-{ymd[4:6]}-{ymd[6:]}"}

    if not s.get("patient_id"):
        s = {**s, "patient_id": "p1"}
    return s


def n_deidentify_redact(s: WFState) -> WFState:
    """테스트 호환용 래퍼 — 그래프 노드로는 더 이상 사용하지 않는다."""
    t = redact_pii(s.get("transcript", ""))
    return {**s, "redacted_transcript": t}
