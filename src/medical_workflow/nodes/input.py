"""입력 파싱 및 개인정보 비식별화 노드"""

import re

from medical_workflow.state import WFState


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
