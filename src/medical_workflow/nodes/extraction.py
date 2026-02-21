"""임상 정보 추출 노드"""

from medical_workflow.state import WFState
from medical_workflow.stores import THREAD_STORE, safe_llm_invoke
from medical_workflow.utils.helpers import normalize_cancer_diagnosis


def n_extract_doctor(s: WFState, llm) -> WFState:
    transcript = s.get("redacted_transcript", s.get("transcript", ""))

    # 빈 입력 차단
    if not transcript or not transcript.strip():
        error = {
            "node": "extract_doctor",
            "error_type": "EmptyInput",
            "message": "transcript가 비어 있습니다.",
            "severity": "high",
        }
        return {"doctor_text": "", "errors": s.get("errors", []) + [error]}

    prompt = f"""아래는 진료실 대화 전사 텍스트이다.
의사(doctor)가 발화한 것으로 추정되는 내용만 추출하여 원문 그대로 이어붙여 반환하라.

판단 기준:
- 진단, 처방, 검사 지시, 생활 권고, 복약 안내, 추적 관찰 등 의료 전문가 발화를 의사 발언으로 간주한다.
- 환자·보호자의 증상 호소, 질문, 대답은 제외한다.
- 화자 구분 표시([의사], [환자], Doctor:, P: 등)가 있으면 이를 우선 활용한다.
- 화자 구분이 없으면 문맥으로 판단한다.

출력 형식:
- 의사 발언 원문만, 줄바꿈으로 구분하여 출력한다.
- 설명, 요약, 기타 부가 텍스트는 일절 포함하지 않는다.
- 추출할 의사 발언이 없으면 빈 문자열을 반환한다.

전사 텍스트:
{transcript}"""

    fallback = transcript  # 실패 시 전체 전사를 그대로 사용
    doctor_text, error = safe_llm_invoke(
        llm, prompt,
        node_name="extract_doctor",
        fallback_value=fallback,
        parse_json=False,
        severity="medium",
    )

    if not isinstance(doctor_text, str) or not doctor_text.strip():
        doctor_text = transcript

    # 병렬 노드: 자신이 소유한 필드만 반환
    result: dict = {"doctor_text": doctor_text}
    if error:
        result["errors"] = s.get("errors", []) + [error]
    return result


def n_extract_clinical(s: WFState, llm) -> WFState:
    transcript = s.get("redacted_transcript", s.get("transcript", ""))

    # 빈 입력 차단 — LLM 호출 전 즉시 에러 반환
    if not transcript or not transcript.strip():
        error = {
            "node": "extract_clinical",
            "error_type": "EmptyInput",
            "message": "transcript가 비어 있습니다. 임상 정보를 추출할 수 없습니다.",
            "severity": "high",
        }
        return {
            "extracted": {"diagnoses": [], "symptoms": [], "doctor_guidelines": []},
            "errors": s.get("errors", []) + [error],
            "warnings": s.get("warnings", []) + [
                "⚠️ 진료 전사가 비어 있어 임상 정보를 추출할 수 없습니다."
            ],
        }

    prompt = f"""
의료 진료 전사에서 정보 추출.
환자, 의사 구분 없이 대화 전체에서 의료적으로 언급된 내용을 추출한다.
JSON만 출력.

category 분류 기준:
- lifestyle  : 퇴원 후 집에서 실천하는 생활습관 권고 (수면, 위생, 금연 등)
- medication : 복약 안내 (약 이름, 용량, 복용 시간 등)
- diet       : 식이요법 (먹어야 할 것, 피해야 할 것)
- exercise   : 운동 권고
- followup   : 재진·외래 예약, 추적 관찰
- treatment  : 치료 방법 (시술, 처치, 수술, 재활 등 의료적 치료 행위)
- warning    : 반드시 지켜야 할 중요 경고·금기 사항 (생명·안전과 직결되는 것만)
- other      : 병원 내에서 즉시 처리되는 행위 (검사 시행, 치료실 이동, 주사 투여, 처치 등 퇴원 후 행동과 무관한 것)

{{
  "diagnoses": [{{"name": "string", "confidence": 0.0, "disease_status": "string|null"}}],
  "symptoms": [{{"name": "string"}}],
  "doctor_guidelines": [
    {{"category":"lifestyle|medication|diet|exercise|followup|treatment|warning|other",
      "text":"string",
      "source":"doctor"}}
  ]
}}

diagnoses 추출 기준:
- name: 반드시 ICD 호환 순수 질환명만 기재한다. 예: "폐암", "유방암", "제2형 당뇨병", "방광염", "급성폐렴"
  - 병기(1기/2기/stage IV 등)는 별도 처리하므로 name에 포함하지 않는다.
  - "항암치료 반응", "치료 완료", "경과 양호", "추적관찰 중" 등 상태·반응 표현은 disease_status에만 기재한다.
  - "종양" 같은 포괄적 표현보다 구체적 질환명(예: "폐암")을 우선한다.
- 반드시 포함해야 하는 경우:
  - 현재 치료 중이거나 경과 관찰 중인 질환 → 증상이 호전·소실 중이어도 포함
  - 추적 방문("경과 좋아졌어요", "많이 나아졌어요")에서 언급되는 기존 질환 → 포함
  - "방광염이 나았어요" → 방광염을 diagnoses에 포함, disease_status에 "증상 소실"
- disease_status: 치료 단계·반응·현재 상태를 간결히 기재한다. 없으면 null.
  예: "항암치료 반응 양호", "2차 항암치료 진행 중", "완치 판정", "증상 호전", "증상 소실"

symptoms 추출 기준:
- 확정 진단명이 없거나 불분명할 때 환자가 호소하거나 의사가 언급한 증상을 추출한다.
- 진단명이 명확히 있으면 symptoms는 빈 배열로 둔다.
- 다음은 symptom이 아니므로 symptoms에 포함하지 않는다:
  - "증상 소실", "증상 호전", "증상 완화", "좋아짐", "편해짐", "나았다" 등 경과·회복 표현
    → 해당 질환의 disease_status에 기재한다.
  - 치료 습관, 생활 지도("소변 참기 습관", "수분 섭취") → doctor_guidelines에 기재한다.
  - 의사의 처치·검사·권고 내용 → doctor_guidelines에 기재한다.

전사:
{transcript}
"""
    # 안전한 LLM 호출 with 기본값
    fallback = {"diagnoses": [], "doctor_guidelines": []}
    extracted, error = safe_llm_invoke(
        llm, prompt,
        node_name="extract_clinical",
        fallback_value=fallback,
        parse_json=True,
        severity="high"  # 의료 정보이므로 high
    )

    # 기본값 보장
    if not isinstance(extracted, dict):
        extracted = {}
    extracted.setdefault("diagnoses", [])
    extracted.setdefault("symptoms", [])
    extracted.setdefault("doctor_guidelines", [])

    # 암 계열 진단명에서 병기(1기, 2기, stage III 등) 제거
    for diag in extracted["diagnoses"]:
        if isinstance(diag, dict) and isinstance(diag.get("name"), str):
            diag["name"] = normalize_cancer_diagnosis(diag["name"])

    # 병렬 노드: 자신이 소유한 필드만 반환
    result: dict = {"extracted": extracted}
    if error:
        result["errors"] = s.get("errors", []) + [error]
        result["warnings"] = s.get("warnings", []) + [
            "⚠️ 진료 내용에서 임상 정보 추출에 실패했습니다. 일부 정보가 누락될 수 있습니다."
        ]
    return result


# closure 방문에서 THREAD_STORE 재연결 판단용 키워드
# - 의사가 질환명을 반복하지 않고 완치/종료 선언만 하는 경우 캐치
# - 띄어쓰기 변형(추적관찰/추적 관찰)을 모두 포함
# - 이 체크는 라우팅 목적으로만 사용; 실제 closure 확정은 n_detect_closure가 담당
_CLOSURE_HINTS = (
    "완치", "완전관해", "관해", "완쾌", "종결",
    "치료 완료", "치료 종료", "치료완료", "치료종료",
    "추적관찰 종료", "추적 관찰 종료",
    "더 이상 치료", "정상 판정", "정상으로",
    "나으셨", "나았",
    "회복", "소실", "사라졌", "없어졌",  # 증상 소실·회복 표현
)


def _diag_in_text(name: str, text: str) -> bool:
    """진단명이 텍스트에 등장하는지 확인 (어절 부분 매칭 허용).

    - 정확 매칭 우선: "방광염" in "방광염이네요" → True
    - 어절 부분 매칭: "발목 골절" vs "골절이네요" → "골절" in text → True
      (의사가 진단명 전체를 반복하지 않고 핵심어만 말하는 경우 대응)
    - 처치/가능성 언급만 있는 경우: "항생제 처방" → 질환명 토큰 없음 → False
    """
    if not name or not text:
        return False
    if name in text:
        return True
    # 2글자 이상 어절 중 하나라도 text에 등장하면 True
    for token in name.split():
        if len(token) >= 2 and token in text:
            return True
    return False


def n_has_diagnosis(s: WFState, llm) -> WFState:
    extracted = s.get("extracted") or {}
    diagnoses = extracted.get("diagnoses") or []
    symptoms  = extracted.get("symptoms") or []

    # ── 명시적 질환명 검증 ────────────────────────────────────────────────────
    # doctor_text(의사 발화)에 질환명(또는 핵심 어절)이 등장할 때만 diagnosis_key 생성.
    # 처치·검사·가능성 언급("항생제 처방", "감염 가능성")만으로는 생성 금지.
    # 어절 매칭: "발목 골절" 추출 + 의사가 "골절이네요"만 말해도 통과.
    doctor_text = s.get("doctor_text") or s.get("redacted_transcript") or s.get("transcript", "")
    explicit = [
        d for d in diagnoses
        if isinstance(d, dict)
        and isinstance(d.get("name"), str)
        and _diag_in_text(d["name"], doctor_text)
    ]

    if explicit:
        first = explicit[0]
        return {
            **s,
            "has_diagnosis":   True,
            "has_symptom":     False,
            "diagnosis_key":   first.get("name"),
            "disease_status":  first.get("disease_status"),
            "symptom_keys":    None,
            "symptom_summary": None,
        }

    if symptoms:
        # ── 멱등성 가드 ────────────────────────────────────────────────────────
        if s.get("has_symptom") and s.get("symptom_summary"):
            return {
                **s,
                "has_diagnosis": False,
                "has_symptom":   True,
                "diagnosis_key": None,
            }

        # ── THREAD_STORE 키워드 안전망 ─────────────────────────────────────────
        # LLM이 진단을 추출하지 못했지만, 전사에 기존 open diagnosis thread의
        # 진단명이 직접 언급된 경우 해당 thread로 attach한다.
        # (예: "방광염이 좋아졌어요" → 방광염 thread 재사용)
        # LLM 호출 없이 키워드 매칭으로 처리한다.
        patient_id = s.get("patient_id", "")
        transcript = s.get("redacted_transcript") or s.get("transcript", "")
        open_diag_threads = [
            v for v in THREAD_STORE.values()
            if v.get("patient_id") == patient_id
            and v.get("thread_type") != "symptom"
            and v.get("status") == "active"
        ]
        for thread in open_diag_threads:
            existing_diag = thread.get("diagnosis_key", "")
            if existing_diag and existing_diag in transcript:
                # 전사에 기존 진단명이 명시 → 해당 diagnosis thread로 라우팅
                return {
                    **s,
                    "has_diagnosis":   True,
                    "has_symptom":     False,
                    "diagnosis_key":   existing_diag,
                    "disease_status":  None,
                    "symptom_keys":    None,
                    "symptom_summary": None,
                }

        # ── 순수 신규 symptom ──────────────────────────────────────────────────
        # LLM이 {"name": "..."} 대신 문자열을 반환하는 경우도 처리
        symptom_keys = [
            (sym.get("name", "") if isinstance(sym, dict) else str(sym))
            for sym in symptoms
            if (sym.get("name") if isinstance(sym, dict) else sym)
        ]
        symptom_summary = "_".join(sorted(symptom_keys)[:3])
        return {
            **s,
            "has_diagnosis":   False,
            "has_symptom":     True,
            "diagnosis_key":   None,
            "disease_status":  None,
            "symptom_keys":    symptom_keys,
            "symptom_summary": symptom_summary,
        }

    # ── 진단 없음 + 증상 없음: closure 방문 재연결 체크 ───────────────────────
    # 마지막 방문에서 의사가 질환명을 반복하지 않고 완치 선언만 할 때 발생.
    # (예: "다 나으셨네요, 추적 관찰 종료합니다" → diagnoses=[], symptoms=[])
    # 활성 스레드 + (진단명 언급 OR 종료 키워드) → 기존 thread로 라우팅해 closure 처리.
    patient_id = s.get("patient_id", "")
    transcript = s.get("redacted_transcript") or s.get("transcript", "")
    open_diag_threads = [
        v for v in THREAD_STORE.values()
        if v.get("patient_id") == patient_id
        and v.get("thread_type") != "symptom"
        and v.get("status") == "active"
    ]
    for thread in open_diag_threads:
        existing_diag = thread.get("diagnosis_key", "")
        if not existing_diag:
            continue
        diag_in_transcript  = existing_diag in transcript
        closure_in_transcript = any(kw in transcript for kw in _CLOSURE_HINTS)
        if diag_in_transcript or closure_in_transcript:
            return {
                **s,
                "has_diagnosis":   True,
                "has_symptom":     False,
                "diagnosis_key":   existing_diag,
                "disease_status":  None,
                "symptom_keys":    None,
                "symptom_summary": None,
            }

    return {
        **s,
        "has_diagnosis":   False,
        "has_symptom":     False,
        "diagnosis_key":   None,
        "disease_status":  None,
        "symptom_keys":    None,
        "symptom_summary": None,
    }
