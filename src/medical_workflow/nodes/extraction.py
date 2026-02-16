"""임상 정보 추출 노드"""

from medical_workflow.state import WFState
from medical_workflow.stores import safe_llm_invoke


def n_extract_doctor(s: WFState, llm) -> WFState:
    return {**s, "doctor_text": s.get("redacted_transcript", s.get("transcript", ""))}


def n_extract_clinical(s: WFState, llm) -> WFState:
    prompt = f"""
의료 진료 전사에서 정보 추출.
JSON만 출력.

{{
  "diagnoses": [{{"name": "string", "confidence": 0.0}}],
  "doctor_guidelines": [
    {{"category":"lifestyle|medication|diet|exercise|followup|warning|other",
      "text":"string",
      "source":"doctor"}}
  ]
}}

전사:
{s["doctor_text"]}
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
    extracted.setdefault("doctor_guidelines", [])

    # 에러가 있으면 state에 추가
    new_state = {**s, "extracted": extracted}
    if error:
        errors = s.get("errors", [])
        errors.append(error)
        new_state["errors"] = errors

        # 의료 정보 추출 실패 시 경고 추가
        warnings = s.get("warnings", [])
        warnings.append("⚠️ 진료 내용에서 임상 정보 추출에 실패했습니다. 일부 정보가 누락될 수 있습니다.")
        new_state["warnings"] = warnings

    return new_state


def n_has_diagnosis(s: WFState, llm) -> WFState:
    d = (s.get("extracted") or {}).get("diagnoses") or []
    if not d:
        return {**s, "has_diagnosis": False, "diagnosis_key": None}
    return {**s, "has_diagnosis": True, "diagnosis_key": d[0].get("name")}
