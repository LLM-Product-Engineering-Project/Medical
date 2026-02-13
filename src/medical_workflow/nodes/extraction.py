"""임상 정보 추출 노드"""

from medical_workflow.state import WFState
from medical_workflow.stores import parse_json_safely


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
    resp = llm.invoke(prompt)
    extracted = parse_json_safely(resp.content)
    if not isinstance(extracted, dict):
        extracted = {}
    extracted.setdefault("diagnoses", [])
    extracted.setdefault("doctor_guidelines", [])
    return {**s, "extracted": extracted}


def n_has_diagnosis(s: WFState, llm) -> WFState:
    d = (s.get("extracted") or {}).get("diagnoses") or []
    if not d:
        return {**s, "has_diagnosis": False, "diagnosis_key": None}
    return {**s, "has_diagnosis": True, "diagnosis_key": d[0].get("name")}
