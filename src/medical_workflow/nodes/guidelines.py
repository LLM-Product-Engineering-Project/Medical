"""가이드라인 판단, 요약, 안전성 체크 노드"""

from medical_workflow.state import WFState
from medical_workflow.stores import safe_llm_invoke


def n_has_guideline(s: WFState, llm) -> WFState:
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
    """
    from medical_workflow.guardrail_policy import (
        RISK_WEIGHTS, ROUTING_POLICY, RAG_DEFAULT_RETRIEVER_SCORE,
        REASON_RISK_CLEAR,
        REASON_CONFLICT_NONE,
        REASON_EVIDENCE_DOCTOR_DIRECT, REASON_EVIDENCE_RAG_RETRIEVED, REASON_EVIDENCE_NO_SOURCE,
        REASON_ROUTE_BLOCK_HIGH_RISK, REASON_ROUTE_HITL_CONFLICT,
        REASON_ROUTE_HITL_MEDIUM_RISK, REASON_ROUTE_CAUTION_LOW_EVIDENCE, REASON_ROUTE_ALLOW,
    )
    from medical_workflow.stores import now_iso

    # 입력 가이드라인 결정
    if s.get("has_guideline"):
        guidelines = (s.get("extracted") or {}).get("doctor_guidelines", [])
    else:
        guidelines = s.get("rag_guidelines") or []

    errors = list(s.get("errors", []))
    warnings = list(s.get("warnings", []))
    decision_log: list[dict] = list(s.get("guardrail_decision_log") or [])

    # ── Stage 1: Risk Filter ──────────────────────────────────────────────
    risk_prompt = (
        "아래 의료 가이드라인에서 위험한 의료 지시를 탐지하세요.\n\n"
        f"가이드라인:\n{guidelines}\n\n"
        "탐지 대상 reason_code (해당하는 것만):\n"
        "- RISK_DRUG_DOSAGE_CHANGE: 환자/비의료인이 약물 용량을 변경하도록 지시\n"
        "- RISK_TREATMENT_STOP: 기존 치료·약물·처방 중단 권고\n"
        "- RISK_EMERGENCY_DISMISSAL: 응급 증상(흉통·의식저하 등) 무시·축소\n"
        "- RISK_NEW_DIAGNOSIS_ASSERTION: 검사 없이 새 질병을 단정 진단\n"
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
        "환자의 기존 건강 정보와 현재 가이드라인 간 충돌을 탐지하세요.\n\n"
        f"환자 메모리:\n{formatted_memories}\n\n"
        f"현재 진단: {s.get('diagnosis_key')}\n"
        f"현재 가이드라인:\n{guidelines}\n\n"
        "탐지 대상 reason_code (해당하는 것만):\n"
        "- CONFLICT_COMORBIDITY_DIET: 기저질환과 식이 가이드라인 충돌\n"
        "- CONFLICT_COMORBIDITY_MEDICATION: 기저질환과 약물 권고 충돌\n"
        "- CONFLICT_ALLERGY_CONTRAINDICATION: 알레르기·금기 위반\n"
        "- CONFLICT_GENERAL: 기타 명확한 맥락 충돌\n\n"
        "severity는 0.0–1.0 (명확한 충돌=1.0, 가능성=0.6).\n"
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

    # ── Stage 3: Source Check (rule-based) → evidence_items ──────────────
    if s.get("has_guideline"):
        evidence_items = [
            {
                "span":             g.get("text", ""),
                "memory_id":        None,
                "source":           "doctor",
                "retriever_score":  1.0,
                "reason_code":      REASON_EVIDENCE_DOCTOR_DIRECT,
            }
            for g in guidelines
        ]
    elif guidelines:   # rag_guidelines 존재
        evidence_items = [
            {
                "span":             g.get("text", ""),
                "memory_id":        None,
                "source":           g.get("source", "rag"),
                "retriever_score":  RAG_DEFAULT_RETRIEVER_SCORE,
                "reason_code":      REASON_EVIDENCE_RAG_RETRIEVED,
            }
            for g in guidelines
        ]
    else:
        evidence_items = []

    evidence_score = (
        sum(e["retriever_score"] for e in evidence_items) / len(evidence_items)
        if evidence_items else 0.0
    )
    evidence_reason_codes = (
        list({e["reason_code"] for e in evidence_items})
        or [REASON_EVIDENCE_NO_SOURCE]
    )
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
