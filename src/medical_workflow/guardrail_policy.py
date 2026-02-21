"""
Safety Guardrail 정책 테이블 및 reason_code taxonomy

이 파일의 값을 수정하면 가드레일 동작 전체가 바뀐다.
예외 규칙을 노드 코드에 하드코딩하지 말고, 반드시 이 파일의 테이블을 수정하라.
"""

# ── Risk Factor 가중치 테이블 ─────────────────────────────────────────────────
# 여러 factor가 동시에 탐지되면 가중합(min(1.0, sum))을 risk_score로 사용.
RISK_WEIGHTS: dict[str, float] = {
    "RISK_DRUG_DOSAGE_CHANGE":       1.0,   # 약물 용량 변경 지시
    "RISK_TREATMENT_STOP":           1.0,   # 치료 중단 권고
    "RISK_EMERGENCY_DISMISSAL":      1.0,   # 응급 증상 무시·축소
    "RISK_NEW_DIAGNOSIS_ASSERTION":  0.9,   # 검사 없이 새 질병 단정
    "RISK_GENERAL_DANGER":           0.5,   # 기타 위험 권고
}

# ── 라우팅 정책 테이블 ────────────────────────────────────────────────────────
# 평가 우선순위: block → hitl(conflict) → hitl(risk) → caution → allow
ROUTING_POLICY: dict[str, dict] = {
    "block":   {"risk_score_min":     0.7},
    "hitl":    {"risk_score_min":     0.4,
                "conflict_score_min": 0.6},
    "caution": {"evidence_score_max": 0.3},
    "allow":   {},
}

# ── Reason Code Taxonomy ──────────────────────────────────────────────────────
# Risk Filter
REASON_RISK_DRUG_DOSAGE_CHANGE       = "RISK_DRUG_DOSAGE_CHANGE"
REASON_RISK_TREATMENT_STOP           = "RISK_TREATMENT_STOP"
REASON_RISK_EMERGENCY_DISMISSAL      = "RISK_EMERGENCY_DISMISSAL"
REASON_RISK_NEW_DIAGNOSIS_ASSERTION  = "RISK_NEW_DIAGNOSIS_ASSERTION"
REASON_RISK_GENERAL_DANGER           = "RISK_GENERAL_DANGER"
REASON_RISK_CLEAR                    = "RISK_CLEAR"

# Context Check
REASON_CONFLICT_COMORBIDITY_DIET          = "CONFLICT_COMORBIDITY_DIET"
REASON_CONFLICT_COMORBIDITY_MEDICATION    = "CONFLICT_COMORBIDITY_MEDICATION"
REASON_CONFLICT_ALLERGY_CONTRAINDICATION  = "CONFLICT_ALLERGY_CONTRAINDICATION"
REASON_CONFLICT_GENERAL                   = "CONFLICT_GENERAL"
REASON_CONFLICT_NONE                      = "CONFLICT_NONE"

# Source Check
REASON_EVIDENCE_DOCTOR_DIRECT    = "EVIDENCE_DOCTOR_DIRECT"
REASON_EVIDENCE_RAG_RETRIEVED    = "EVIDENCE_RAG_RETRIEVED"
REASON_EVIDENCE_RAG_VERIFIED     = "EVIDENCE_RAG_VERIFIED"    # LLM 검증 통과
REASON_EVIDENCE_RAG_UNVERIFIED   = "EVIDENCE_RAG_UNVERIFIED"  # LLM 검증 실패
REASON_EVIDENCE_MIXED            = "EVIDENCE_MIXED"           # doctor + rag 혼합
REASON_EVIDENCE_NO_SOURCE        = "EVIDENCE_NO_SOURCE"

# Policy Routing
REASON_ROUTE_BLOCK_HIGH_RISK       = "ROUTE_BLOCK_HIGH_RISK"
REASON_ROUTE_HITL_CONFLICT         = "ROUTE_HITL_CONFLICT"
REASON_ROUTE_HITL_MEDIUM_RISK      = "ROUTE_HITL_MEDIUM_RISK"
REASON_ROUTE_CAUTION_LOW_EVIDENCE  = "ROUTE_CAUTION_LOW_EVIDENCE"
REASON_ROUTE_ALLOW                 = "ROUTE_ALLOW"

# ── RAG retriever_score 테이블 ────────────────────────────────────────────────
RAG_DEFAULT_RETRIEVER_SCORE: float = 0.7   # LLM 검증 미수행 시 기본값
RAG_VERIFIED_SCORE:          float = 0.8   # LLM 검증 통과
RAG_UNVERIFIED_SCORE:        float = 0.4   # LLM 검증 실패
