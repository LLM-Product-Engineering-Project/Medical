"""RAG 검색 파이프라인 노드 (구 Tavily)"""

from medical_workflow.state import WFState
from medical_workflow.stores import safe_llm_invoke


def n_rag_query_sanitize(s: WFState, llm) -> WFState:
    """RAG 검색 쿼리 생성 — 진단명 + 진료 전사 기반 LLM 쿼리"""
    diagnosis = (s.get("diagnosis_key") or "").strip()
    doctor_text = (s.get("doctor_text") or "").strip()

    fallback_query = f"{diagnosis} 관리 방법"

    prompt = f"""진단명: {diagnosis}
진료 전사: {doctor_text}

위 내용을 바탕으로 의료 정보 검색에 가장 적합한 한국어 검색 쿼리 1개를 생성하라.
동반 질환이나 복약 이력이 있으면 함께 반영하라.
쿼리만 출력하라 (설명 없이, 한 줄).
"""

    query, error = safe_llm_invoke(
        llm, prompt,
        node_name="rag_query_sanitize",
        fallback_value=fallback_query,
        parse_json=False,
        severity="medium"
    )

    # 빈 응답이거나 너무 길면 fallback 사용
    query = (query or "").strip()
    if not query or len(query) > 200:
        query = fallback_query

    new_state = {**s, "rag_query": query}
    if error:
        errors = s.get("errors", [])
        errors.append(error)
        new_state["errors"] = errors

    return new_state


def n_rag_supplement(s: WFState, llm, retriever) -> WFState:
    """가이드라인이 2개 이하이면 RAG로 보완하여 최소 5개 확보"""
    THRESHOLD = 2
    TARGET = 5

    if s.get("has_guideline"):
        current = list((s.get("extracted") or {}).get("doctor_guidelines", []))
    else:
        current = list(s.get("rag_guidelines") or [])

    # other(병원 내 처치)는 퇴원 후 행동과 무관하므로 최소 개수 산정에서 제외
    actionable = [g for g in current if g.get("category") != "other"]
    if len(actionable) > THRESHOLD:
        return s  # 이미 충분함

    # 증상 임시 스레드는 진단명 없이 RAG 검색 시 엉뚱한 질환 결과가 올 수 있으므로 스킵
    if s.get("has_symptom"):
        return s

    # has_guideline=False 경로는 n_rag_search에서 이미 판단한 결과를 사용
    if s.get("rag_diagnosis_found") is False:
        return s

    query = s.get("rag_query") or f"{s.get('diagnosis_key', '')} 생활 관리 방법"

    try:
        docs = retriever.invoke(query)
    except Exception:
        return s

    if not docs:
        return s

    # has_guideline=True 경로는 여기서 직접 진단명 존재 여부 확인
    diagnosis = (s.get("diagnosis_key") or "").strip()
    if s.get("has_guideline") and diagnosis:
        diagnosis_found = any(
            diagnosis in getattr(d, "page_content", "")
            for d in docs
        )
        if not diagnosis_found:
            warnings = list(s.get("warnings", []))
            warnings.append(f"⚠️ RAG에서 추출 불가: '{diagnosis}'에 해당하는 데이터가 의료 DB에 없습니다.")
            return {**s, "warnings": warnings}

    rag_text = "\n\n---\n\n".join(getattr(d, "page_content", str(d)) for d in docs)
    need = TARGET - len(actionable)
    existing_texts = "\n".join(f"- {g.get('text', '')}" for g in current) or "없음"
    # guardrail source check에서 LLM 검증에 사용할 원문 저장
    s = {**s, "rag_supplement_raw": rag_text}

    prompt = f"""아래 검색 결과에서 질병 관리 지침을 최대 {need}개 추출하라.

규칙:
- 검색 결과에 명시된 내용만 사용한다. 원문에 없는 내용을 추가하거나 강도를 높이지 않는다.
- 원문이 "알려진 바 없다", "연관성이 불분명하다" 등으로 표현한 경우 해당 항목은 포함하지 않는다.
- 기존 가이드라인과 중복되는 내용은 포함하지 않는다.

기존 가이드라인 (중복 제외 기준):
{existing_texts}

검색 결과:
{rag_text}

JSON 배열만 출력 (설명 없이):
[{{"category":"lifestyle|medication|diet|exercise|followup|treatment|warning|other","text":"string","source":"rag"}}]"""

    extra, error = safe_llm_invoke(
        llm, prompt,
        node_name="rag_supplement",
        fallback_value=[],
        parse_json=True,
        severity="medium",
    )

    if not isinstance(extra, list):
        extra = []

    # rag_supplement 추가 항목은 source="rag" 강제 (LLM 오출력 방지)
    for g in extra:
        if isinstance(g, dict):
            g["source"] = "rag"

    merged = current + extra[:need]

    new_state = {**s}
    if s.get("has_guideline"):
        extracted = dict(s.get("extracted") or {})
        extracted["doctor_guidelines"] = merged
        new_state["extracted"] = extracted
    else:
        new_state["rag_guidelines"] = merged

    if error:
        errors = list(s.get("errors", []))
        errors.append(error)
        new_state["errors"] = errors

    return new_state


def n_rag_to_guidelines(s: WFState, llm) -> WFState:
    """RAG 검색 결과를 가이드라인으로 변환"""
    if s.get("rag_diagnosis_found") is False:
        return {**s, "rag_guidelines": []}

    prompt = f"""아래 검색 결과에서 질병 관리 지침을 추출하라.

규칙:
- 검색 결과에 명시된 내용만 사용한다. 원문에 없는 내용을 추가하거나 강도를 높이지 않는다.
- 원문이 "알려진 바 없다", "연관성이 불분명하다" 등으로 표현한 경우 해당 항목은 포함하지 않는다.

각 원소:
{{"category":"lifestyle|medication|diet|exercise|followup|treatment|warning|other",
  "text":"string",
  "source":"rag"}}

검색 결과:
{s.get("rag_raw")}
"""

    fallback = []
    guidelines, error = safe_llm_invoke(
        llm, prompt,
        node_name="rag_to_guidelines",
        fallback_value=fallback,
        parse_json=True,
        severity="high"  # 가이드라인이므로 high
    )

    if not isinstance(guidelines, list):
        guidelines = []

    # LLM이 source를 잘못 설정할 수 있으므로 RAG 경로 아이템은 강제로 source="rag"
    for g in guidelines:
        if isinstance(g, dict):
            g["source"] = "rag"

    new_state = {**s, "rag_guidelines": guidelines}
    if error:
        errors = s.get("errors", [])
        errors.append(error)
        new_state["errors"] = errors

        warnings = s.get("warnings", [])
        warnings.append("⚠️ 검색 결과에서 가이드라인을 생성할 수 없습니다. 의료진과 상담하세요.")
        new_state["warnings"] = warnings

    return new_state
