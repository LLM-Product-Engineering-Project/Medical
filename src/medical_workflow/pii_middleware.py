"""PII Middleware — 진료 전사에서 환자·의사 이름 비식별화

그래프 노드가 아닌 미들웨어로 동작: runner에서 graph.invoke() 전에 호출한다.
정규식 기반으로 한국 이름만 탐지하며, LLM 호출을 사용하지 않는다.

탐지 방식:
  성씨(1자) + 이름(1~2자 한글) + 호칭/조사 패턴
  예) "홍길동 씨", "김철수님", "박민준 환자"
"""

import re

# 통계청 한국인 성씨 빈도 상위 (~80개)
_SURNAME_CHARS = (
    "김이박최정강조윤장임"
    "한오서신권황안송류전"
    "홍고문양손배백허유남"
    "심노하곽성차주우구민"
    "나지엄채원천방공현함"
    "변염여추도소석선설마"
    "길봉기반왕금육인맹제"
    "모탁명위형편표라범어"
    "피사태진경복기반왕금"
)

# 이름 뒤에 오는 호칭·조사 (look-ahead)
# 호칭이 있을 때만 이름으로 판단 → 일반 단어와 구분
_TITLE_LOOKAHEAD = (
    r"씨가|씨는|씨의|씨를|씨가|씨도|씨만|씨한테"
    r"|님이|님은|님의|님을|님께|님과|님도"
    r"|씨|님|환자분|환자|선생님"
)

_NAME_RE = re.compile(
    rf"[{_SURNAME_CHARS}]"          # 성씨 (1자)
    r"[\uAC00-\uD7A3]{1,2}"         # 이름 (1~2자 한글 음절)
    rf"(?=[ \t]*(?:{_TITLE_LOOKAHEAD}))",
    re.UNICODE,
)


def redact_pii(transcript: str) -> str:
    """진료 전사에서 한국 이름을 [REDACTED_NAME]으로 치환한다."""
    return _NAME_RE.sub("[REDACTED_NAME]", transcript)
