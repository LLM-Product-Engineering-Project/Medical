"""가이드라인 판단, 요약, 안전성 체크 노드"""

from medical_workflow.state import WFState
from medical_workflow.stores import safe_llm_invoke


def n_has_guideline(s: WFState, llm) -> WFState:
    # symptom 단계에서는 질환 기반 가이드라인 생성을 구조적으로 차단한다.
    # (진단명 없이 RAG/LLM이 질환 추론하는 것 방지)
    if s.get("has_symptom"):
        return {**s, "has_guideline": False}
    return {**s, "has_guideline": bool((s.get("extracted") or {}).get("doctor_guidelines"))}


def n_summarize_guidelines(s: WFState, llm) -> WFState:
    prompt = f"환자에게 전달 가능한 2문장 요약:\n{s['doctor_text']}"

    fallback = "의사 선생님의 조언을 확인하세요."
    summary, error = safe_llm_invoke(
        llm, prompt,
        node_name="summarize_guidelines",
        fallback_value=fallback,
        parse_json=False,
        severity="medium"
    )

    new_state = {**s, "doctor_summary": summary.strip() if isinstance(summary, str) else fallback}
    if error:
        errors = s.get("errors", [])
        errors.append(error)
        new_state["errors"] = errors

    return new_state


def n_safety_guardrail(s: WFState, llm) -> WFState:
    """
    4단계 Safety Guardrail (score 기반):
    1. Risk Filter    — LLM이 reason_code+span+detail 구조로 위험 요소 탐지 → risk_score 가중합
    2. Context Check  — LLM이 reason_code+severity 구조로 충돌 탐지 → conflict_score
    3. Source Check   — 규칙 기반으로 evidence_items 생성 → evidence_score
    4. Policy Routing — ROUTING_POLICY 테이블로 최종 route 결정 + decision_log 누적

    Idempotency: safety_checked=True이면 이미 처리된 run이므로 즉시 반환.
    """
    # ── Idempotency guard ─────────────────────────────────────────────────
    # 2차 graph.invoke(state2)에서 그래프가 재실행될 때 safety_guardrail이
    # 중복 호출되어 decision_log가 누적되는 것을 방지한다.
    if s.get("safety_checked"):
        return s
    from medical_workflow.guardrail_policy import (
        RISK_WEIGHTS, ROUTING_POLICY,
        RAG_VERIFIED_SCORE, RAG_UNVERIFIED_SCORE,
        REASON_RISK_CLEAR,
        REASON_CONFLICT_NONE,
        REASON_EVIDENCE_DOCTOR_DIRECT,
        REASON_EVIDENCE_RAG_VERIFIED, REASON_EVIDENCE_RAG_UNVERIFIED,
        REASON_EVIDENCE_MIXED,
        REASON_EVIDENCE_NO_SOURCE,
        REASON_ROUTE_BLOCK_HIGH_RISK, REASON_ROUTE_HITL_CONFLICT,
        REASON_ROUTE_HITL_MEDIUM_RISK, REASON_ROUTE_CAUTION_LOW_EVIDENCE, REASON_ROUTE_ALLOW,
    )
    from medical_workflow.stores import now_iso

    # 입력 가이드라인 결정: doctor_guidelines + rag_guidelines 항상 병합
    # - has_guideline=True 경로: rag_supplement가 rag 항목을 doctor_guidelines에 합칠 수 있고,
    #   별도로 rag_guidelines가 존재할 수도 있으므로 항상 양쪽을 합산한다.
    # - has_guideline=False 경로: doctor_guidelines=[] 이므로 사실상 rag_guidelines만.
    # - 프로덕션 실행 시 경로 분기 때문에 중복이 생기지 않는다.
    _doctor_guidelines = (s.get("extracted") or {}).get("doctor_guidelines") or []
    _rag_guidelines    = s.get("rag_guidelines") or []
    guidelines = _doctor_guidelines + _rag_guidelines

    errors = list(s.get("errors", []))
    warnings = list(s.get("warnings", []))
    # decision_log는 항상 이번 실행분만 기록 (이전 state 값 이어받지 않음)
    decision_log: list[dict] = []

    # ── Stage 1: Risk Filter ──────────────────────────────────────────────
    risk_prompt = (
        "아래 의료 가이드라인에서 위험한 의료 지시를 탐지하세요.\n\n"
        f"가이드라인:\n{guidelines}\n\n"
        "탐지 대상 reason_code (해당하는 것만):\n"
        "- RISK_DRUG_DOSAGE_CHANGE: 환자 스스로 처방 없이 약물 용량·종류를 임의로 변경하도록 지시하는 경우. "
        "의사가 정상적으로 처방을 추가하거나 변경하는 것, 복약 순응도를 당부하는 것은 해당하지 않음.\n"
        "- RISK_TREATMENT_STOP: 현재 진행 중인 치료·약물을 근거 없이 중단하도록 권고\n"
        "- RISK_EMERGENCY_DISMISSAL: 응급 증상(흉통·의식저하 등) 무시·축소\n"
        "- RISK_NEW_DIAGNOSIS_ASSERTION: 충분한 검사 없이 새 질병을 단정 진단\n"
        "- RISK_GENERAL_DANGER: 위 외 명백히 위험한 의료 권고\n\n"
        "해당 없으면 detected=[].\n"
        "반드시 JSON으로만 응답:\n"
        '{"detected": [{"reason_code": "RISK_DRUG_DOSAGE_CHANGE", '
        '"span": "위험한 문장 그대로", "detail": "판단 근거 한 줄"}]}'
    )
    risk_raw, risk_error = safe_llm_invoke(
        llm, risk_prompt,
        node_name="safety_guardrail_risk",
        fallback_value={"detected": []},
        parse_json=True,
        severity="medium",
    )
    if risk_error:
        errors.append(risk_error)

    detected_risks: list[dict] = (
        risk_raw.get("detected", []) if isinstance(risk_raw, dict) else []
    )
    risk_score = min(
        1.0,
        sum(RISK_WEIGHTS.get(r.get("reason_code", ""), 0.5) for r in detected_risks),
    )
    risk_reason_codes = (
        [r["reason_code"] for r in detected_risks if r.get("reason_code")]
        or [REASON_RISK_CLEAR]
    )
    decision_log.append({
        "stage": "risk_filter",
        "reason_codes": risk_reason_codes,
        "score": risk_score,
        "detail": (
            f"탐지된 위험 요소 {len(detected_risks)}개"
            + (f": {[r.get('span', '')[:40] for r in detected_risks]}" if detected_risks else "")
        ),
        "ts": now_iso(),
    })

    # ── Stage 2: Context Check ────────────────────────────────────────────
    memories = s.get("retrieved_memories") or []
    formatted_memories = (
        "\n".join(f"[mem_{i}] {m.get('text', str(m))}" for i, m in enumerate(memories))
        or "없음"
    )
    conflict_prompt = (
        "환자의 기존 건강 정보와 현재 가이드라인 간 의학적 충돌을 탐지하세요.\n\n"
        f"환자 메모리 (과거 진료 기록·맥락):\n{formatted_memories}\n\n"
        f"현재 진단: {s.get('diagnosis_key')}\n"
        f"현재 가이드라인:\n{guidelines}\n\n"
        "충돌 정의 (아래 경우만 해당):\n"
        "- 기저질환·알레르기 등으로 인해 권고 자체가 해당 환자에게 금기이거나 의학적으로 위험한 경우\n"
        "- 가이드라인 간 상충 (예: doctor 권고 vs RAG 권고가 반대 방향)\n\n"
        "충돌이 아닌 것 (탐지 금지):\n"
        "- 환자가 현재 가이드라인을 따르지 않고 있는 것 (비순응/adherence gap) → 충돌 아님\n"
        "- 메모리에 '운동 못함', '식이 조절 안 됨' 등 순응도 관련 내용 → 충돌 아님\n"
        "- 환자의 현재 상태와 가이드라인의 단순 차이 → 충돌 아님\n\n"
        "탐지 대상 reason_code (해당하는 것만):\n"
        "- CONFLICT_COMORBIDITY_DIET: 기저질환과 식이 가이드라인이 의학적으로 충돌\n"
        "- CONFLICT_COMORBIDITY_MEDICATION: 기저질환과 약물 권고가 의학적으로 충돌\n"
        "- CONFLICT_ALLERGY_CONTRAINDICATION: 알레르기·금기 위반\n\n"
        "severity는 0.0–1.0 (명확한 금기=1.0, 가능성=0.6).\n"
        "해당 없으면 detected=[].\n"
        "반드시 JSON으로만 응답:\n"
        '{"detected": [{"reason_code": "CONFLICT_COMORBIDITY_DIET", '
        '"memory_id": "mem_0", "span": "충돌 텍스트", "detail": "충돌 이유", "severity": 0.8}]}'
    )
    conflict_raw, conflict_error = safe_llm_invoke(
        llm, conflict_prompt,
        node_name="safety_guardrail_conflict",
        fallback_value={"detected": []},
        parse_json=True,
        severity="medium",
    )
    if conflict_error:
        errors.append(conflict_error)

    detected_conflicts: list[dict] = (
        conflict_raw.get("detected", []) if isinstance(conflict_raw, dict) else []
    )
    conflict_score = max(
        (c.get("severity", 0.5) for c in detected_conflicts),
        default=0.0,
    )
    conflict_reason_codes = (
        [c["reason_code"] for c in detected_conflicts if c.get("reason_code")]
        or [REASON_CONFLICT_NONE]
    )
    decision_log.append({
        "stage": "context_check",
        "reason_codes": conflict_reason_codes,
        "score": conflict_score,
        "detail": (
            f"탐지된 충돌 {len(detected_conflicts)}개"
            + (f": {[c.get('detail', '')[:40] for c in detected_conflicts]}" if detected_conflicts else "")
        ),
        "ts": now_iso(),
    })

    # ── Stage 3: Source Check (rule-based + LLM 검증) → evidence_items ───
    # [DEBUG] source_check 입력 현황 출력 — rag가 들어왔는데 0으로 떨어지는 지점 확인용
    _debug_sources = [g.get("source", "?") for g in guidelines]
    print(
        f"[DEBUG source_check] doctor_guidelines={len(_doctor_guidelines)}, "
        f"rag_guidelines={len(_rag_guidelines)}, "
        f"merged_total={len(guidelines)}, "
        f"sources={_debug_sources}",
        flush=True,
    )

    # RAG 원문: rag_search 결과 또는 rag_supplement 결과 중 사용 가능한 것
    rag_source_text = s.get("rag_raw") or s.get("rag_supplement_raw") or ""

    # RAG 가이드라인 일괄 LLM 검증
    rag_indices = [i for i, g in enumerate(guidelines) if g.get("source") == "rag"]
    rag_verified: dict[int, bool] = {}

    if rag_indices and rag_source_text:
        items_to_verify = [
            {"idx": i, "text": guidelines[i].get("text", "")}
            for i in rag_indices
        ]
        verify_prompt = (
            "아래 가이드라인 목록에서 각 항목이 검색 결과 원문에 실제로 근거하는 내용인지 확인하라.\n\n"
            f"가이드라인:\n{items_to_verify}\n\n"
            f"검색 결과 원문:\n{rag_source_text}\n\n"
            "JSON 배열만 응답 (다른 텍스트 없이):\n"
            '[{"idx": 0, "verified": true}, {"idx": 1, "verified": false}]'
        )
        verify_raw, verify_error = safe_llm_invoke(
            llm, verify_prompt,
            node_name="safety_guardrail_source_verify",
            fallback_value=[],
            parse_json=True,
            severity="medium",
        )
        if verify_error:
            errors.append(verify_error)
        if isinstance(verify_raw, list):
            for item in verify_raw:
                if isinstance(item, dict) and "idx" in item:
                    rag_verified[item["idx"]] = bool(item.get("verified", False))

    evidence_items = []
    for i, g in enumerate(guidelines):
        source = g.get("source", "")
        if source == "doctor":
            evidence_items.append({
                "span":            g.get("text", ""),
                "memory_id":       None,
                "source":          "doctor",
                "retriever_score": 1.0,
                "reason_code":     REASON_EVIDENCE_DOCTOR_DIRECT,
            })
        elif source == "rag":
            verified = rag_verified.get(i, False)
            evidence_items.append({
                "span":            g.get("text", ""),
                "memory_id":       None,
                "source":          "rag",
                "retriever_score": RAG_VERIFIED_SCORE if verified else RAG_UNVERIFIED_SCORE,
                "reason_code":     REASON_EVIDENCE_RAG_VERIFIED if verified else REASON_EVIDENCE_RAG_UNVERIFIED,
            })
        else:
            evidence_items.append({
                "span":            g.get("text", ""),
                "memory_id":       None,
                "source":          source,
                "retriever_score": 0.0,
                "reason_code":     REASON_EVIDENCE_NO_SOURCE,
            })

    # [DEBUG] evidence_items 최종 결과
    print(
        f"[DEBUG source_check] evidence_items={len(evidence_items)}, "
        f"item_sources={[e.get('source') for e in evidence_items]}",
        flush=True,
    )

    evidence_score = (
        sum(e["retriever_score"] for e in evidence_items) / len(evidence_items)
        if evidence_items else 0.0
    )
    # source_check summary: per-item reason_code set → 전체 소스 유형 한 줄 요약
    # doctor only → EVIDENCE_DOCTOR_DIRECT
    # rag only    → rag per-item codes (EVIDENCE_RAG_VERIFIED / EVIDENCE_RAG_UNVERIFIED)
    # doctor+rag  → EVIDENCE_MIXED  (rag 포함 시 doctor_direct 단독 표기 금지)
    _has_doctor = any(e.get("source") == "doctor" for e in evidence_items)
    _has_rag    = any(e.get("source") == "rag"    for e in evidence_items)
    if _has_doctor and _has_rag:
        evidence_reason_codes = [REASON_EVIDENCE_MIXED]
    elif _has_doctor:
        evidence_reason_codes = [REASON_EVIDENCE_DOCTOR_DIRECT]
    elif _has_rag:
        evidence_reason_codes = list({e["reason_code"] for e in evidence_items if e.get("source") == "rag"}) or [REASON_EVIDENCE_RAG_UNVERIFIED]
    else:
        evidence_reason_codes = [REASON_EVIDENCE_NO_SOURCE]
    decision_log.append({
        "stage": "source_check",
        "reason_codes": evidence_reason_codes,
        "score": evidence_score,
        "detail": f"evidence_items {len(evidence_items)}개, 평균 retriever_score={evidence_score:.2f}",
        "ts": now_iso(),
    })

    # ── Stage 4: Policy Routing ───────────────────────────────────────────
    policy = ROUTING_POLICY
    if risk_score >= policy["block"]["risk_score_min"]:
        guardrail_route = "block"
        route_reason   = REASON_ROUTE_BLOCK_HIGH_RISK
        route_detail   = (f"risk_score={risk_score:.2f} "
                          f">= block_threshold={policy['block']['risk_score_min']}")
    elif conflict_score >= policy["hitl"]["conflict_score_min"]:
        guardrail_route = "hitl"
        route_reason   = REASON_ROUTE_HITL_CONFLICT
        route_detail   = (f"conflict_score={conflict_score:.2f} "
                          f">= hitl_conflict_threshold={policy['hitl']['conflict_score_min']}")
    elif risk_score >= policy["hitl"]["risk_score_min"]:
        guardrail_route = "hitl"
        route_reason   = REASON_ROUTE_HITL_MEDIUM_RISK
        route_detail   = (f"risk_score={risk_score:.2f} "
                          f">= hitl_risk_threshold={policy['hitl']['risk_score_min']}")
    elif evidence_score < policy["caution"]["evidence_score_max"]:
        guardrail_route = "caution"
        route_reason   = REASON_ROUTE_CAUTION_LOW_EVIDENCE
        route_detail   = (f"evidence_score={evidence_score:.2f} "
                          f"< caution_threshold={policy['caution']['evidence_score_max']}")
    else:
        guardrail_route = "allow"
        route_reason   = REASON_ROUTE_ALLOW
        route_detail   = (f"risk={risk_score:.2f}, conflict={conflict_score:.2f}, "
                          f"evidence={evidence_score:.2f} → 모든 단계 통과")

    decision_log.append({
        "stage": "policy_routing",
        "reason_codes": [route_reason],
        "score": risk_score,
        "detail": route_detail,
        "ts": now_iso(),
    })

    # block 시 가이드라인 비공개
    safe_guidelines = [] if guardrail_route == "block" else guidelines

    if guardrail_route == "block":
        warnings.append(
            "🚫 안전 검증에서 위험한 내용이 감지되었습니다. "
            "반드시 담당 의료진과 직접 상담하세요."
        )
    elif guardrail_route == "hitl":
        warnings.append(
            "⚠️ 환자의 현재 상태와 가이드라인 간 충돌이 감지되었습니다. "
            "전문가 검토 후 진행하세요."
        )
    elif guardrail_route == "caution":
        warnings.append(
            "⚠️ 가이드라인의 근거가 충분하지 않습니다. 참고용으로만 활용하세요."
        )

    return {
        **s,
        "safety_checked":           True,
        "safe_guidelines":          safe_guidelines,
        "guardrail_risk_score":     risk_score,
        "guardrail_conflict_score": conflict_score,
        "guardrail_evidence_items": evidence_items,
        "guardrail_evidence_score": evidence_score,
        "guardrail_route":          guardrail_route,
        "guardrail_decision_log":   decision_log,
        "errors":                   errors,
        "warnings":                 warnings,
    }
