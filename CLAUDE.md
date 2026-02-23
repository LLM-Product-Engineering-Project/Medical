# Medical Workflow

## 개요

환자의 헬스 리터러시 향상을 위한 Agent 기반 진료 관리 서비스.
진료 녹음 텍스트를 입력받아 임상 정보를 추출하고, 질병별 스레드로 누적 관리하며, 생활습관 알람을 생성한다.

⚠️ 중요 변경 사항
본 시스템은 이제 "Safety Guardrail 4단 구조"를 명시적으로 워크플로우에 통합한다.
안전성 판단은 단일 노드(safety_guardrail)에서 수행되며,
해당 노드는 Risk Filter → Context Check → Source Check → Policy Routing을 내부적으로 수행한다.

## 프로젝트 구조

```
main.py                              # 엔트리포인트 (thin wrapper)
src/medical_workflow/
├── __init__.py
├── config.py                        # 환경 변수 로드
├── state.py                         # WFState TypedDict
├── stores.py                        # 하위 호환성 래퍼
├── guardrail_policy.py              # Safety Guardrail 정책 테이블
├── pii_middleware.py                # PII 미들웨어 (한국 이름 비식별화, 그래프 외부)
├── graph.py                         # build_graph()
├── runner.py                        # run_many(), run_from_xlsx(), main()
├── utils/                           # 유틸리티 패키지
│   ├── llm.py                       # safe_llm_invoke
│   ├── parsing.py                   # parse_json_safely
│   └── helpers.py                   # thread_key, now_iso, symptom_thread_key
├── stores/                          # 저장소 패키지
│   ├── thread.py                    # THREAD_STORE 관리
│   └── visit.py                     # VISIT_STORE 관리
└── nodes/
    ├── __init__.py
    ├── input.py                     # 메타 파싱
    ├── extraction.py                # LLM 임상정보 추출, 진단 판단
    ├── thread.py                    # 스레드 CRUD, 종료 감지, 증상→진단 승격
    ├── memory.py                    # 메모리 조회, 리플렉션
    ├── guidelines.py                # 가이드라인 유무 판단, 요약, 안전성
    ├── rag.py                       # ChromaDB 벡터 DB 구축 및 검색
    ├── search.py                    # RAG 파이프라인 (쿼리 정제, 보완)
    ├── planning.py                  # 액션 계획, HITL 동의
    ├── alarm.py                     # 알람 계획 생성
    └── finalize.py                  # 메모리/이벤트 저장, 최종 응답
data/medical_2.csv                   # 서울대병원 의학정보 (병명, 생활가이드, 식이요법)
data/recordings/                     # 진료 전사 텍스트 (Recording_YYYYMMDD.txt)
data/testcase(50).xlsx               # 테스트 케이스 50건 (patient, diagnosis, interview)
tests/                               # 노드 단위 테스트 및 성능 측정
docs/                                # 기획서, 멘토링 리뷰, LLM 기능 공백 목록
```

## 기술 스택

| 구성 | 기술 | 비고 |
|:--|:--|:--|
| LLM | Solar pro2 (Upstage API) | temperature=0.1 |
| 임베딩 | solar-embedding-1-large (Upstage) | medical_2.csv RAG용 |
| 오케스트레이션 | LangGraph StateGraph | Workflow 방식 |
| RAG 검색 | ChromaDB (nodes/rag.py) | 서울대병원 의학정보 기반 |
| 저장소 | In-memory dict | THREAD_STORE, VISIT_STORE |
| 에러 핸들링 | safe_llm_invoke() | LLM 노드 전체 적용 |
| 패키지 관리 | uv + pyproject.toml | Python >=3.10 |
| 트레이싱 | LangSmith | 선택사항 |

## 워크플로우

### 파이프라인 흐름

```
data/recordings/Recording_*.txt 또는 testcase(50).xlsx 입력 (uv run python main.py [patient_id])
  → 메타 파싱 (날짜, 환자ID)
  → 개인정보 비식별화 (pii_middleware: 한국 이름 탐지·마스킹, graph.invoke() 전 실행)
  → LLM 의사 발화 분리 + 임상 정보 추출 (진단명, 증상, 가이드라인) [에러 핸들링]
  → 진단/증상 여부 분기
      ├─ 진단 있음 → 스레드 관리 (신규 생성 | 기존 로드 | 4단계 LLM 매칭)
      ├─ 증상만 있음 → 증상 임시 스레드 생성 → 메모리 조회 → 계획 수립 → 종료
      └─ 모두 없음 → 종료
          → 메모리 조회 (최근 8개 memory + 3개 event)
          → LLM 종료 감지 (치료 완료?) [에러 핸들링]
              ├─ 종료 → 스레드 닫기 → 종료
              └─ 계속 → 가이드라인 분기
                  ├─ 의사 가이드라인 있음 → LLM 요약 [에러 핸들링] → RAG 보완
                  ├─ 증상 임시 스레드 → 바로 계획 수립 (가이드라인/RAG/guardrail 스킵)
                  └─ 없음 → RAG 쿼리 정제 → RAG 검색 → LLM 가이드라인 변환 → RAG 보완
              → 안전성 체크 (Safety Guardrail)
              → Reflection (3회마다 or 가이드라인 5개 이상) [에러 핸들링]
              → 계획 수립
                  ├─ HITL: 알람 동의 질문
                  ├─ 알람 생성: 카테고리별 시간표
                  └─ 종료 (에러/경고 정보 포함)
```

### 노드 (24개 그래프 노드)

LLM을 사용하는 노드 (8개, 모두 에러 핸들링 적용):
- `extract_clinical` (severity: high) - 임상 정보 추출
- `detect_closure` (severity: medium) - 치료 종료 판단
- `summarize_guidelines` (severity: medium) - 가이드라인 요약
- `rag_query_sanitize` (severity: medium) - RAG 검색 쿼리 LLM 정제
- `rag_to_guidelines` (severity: high) - RAG 가이드라인 생성
- `rag_supplement` (severity: medium) - 가이드라인 2개 이하 시 RAG로 보완 (최소 5개 확보)
- `reflect_patient_state` (severity: low) - 환자 상태 리플렉션
- `safety_guardrail` (severity: medium) - 위험·충돌 탐지 (Risk Filter + Context Check)

# 🛡 Safety Guardrail 설계

## Guardrail 구조 (논리 계층)

Safety Guardrail은 다음 4단계로 구성된다.

1. Risk Filter
2. Context Check
3. Source Check
4. Policy Routing

이 네 단계는 단일 노드 `safety_guardrail` 내부에서 순차적으로 실행된다.

Guardrail은 가이드라인 생성 이후, Reflection 및 Planning 이전에 반드시 통과해야 한다.

---

# 🔎 Safety Guardrail 상세 규칙

## 1️⃣ Risk Filter

### 목적
명백히 위험한 의료 발화를 사전에 차단한다.

### 차단 조건 예시
- 약물 용량 변경 지시
- 치료 중단 권고
- 새로운 진단 단정
- 응급 증상 무시 또는 축소

### 상태 값

```python
state.guardrail_risk_score: float  # 0.0–1.0 위험도 가중합
```

### 정책
- risk_score >= 0.7 → 즉시 `block`
- risk_score >= 0.4 → 다음 단계 진행 (hitl 후보)
- risk_score < 0.4 → 다음 단계 진행

---

## 2️⃣ Context Check

### 목적
환자 맥락과 생성된 권고의 충돌 여부를 판단한다.

### 입력
- 환자 메모리 (기저질환, 최근 상태 등)
- 현재 진단 정보
- 생성된 가이드라인

### 상태 값

```python
state.guardrail_conflict_score: float  # 0.0–1.0 충돌 심각도 최댓값
```

### 정책
- conflict_score >= 0.6 → `hitl`
- conflict_score < 0.6 → 다음 단계 진행

---

## 3️⃣ Source Check

### 목적
가이드라인의 근거 신뢰도를 평가한다.

### 평가 기준
- 진료기록 직접 발화 기반 → 신뢰도 높음
- 내부 guideline DB 기반 → 중간 신뢰도
- RAG 검색 기반 → evidence 존재 여부 확인
- evidence 없는 강한 권고 → 신뢰도 낮음

### 상태 값

```python
state.guardrail_evidence_score: float  # evidence_items retriever_score 평균
```

### 정책
- evidence_score < 0.3 → `caution`
- evidence_score >= 0.3 → 다음 단계 진행

---

## 4️⃣ Policy Routing

### 최종 라우트 값

```python
state.guardrail_route = "allow" | "caution" | "hitl" | "block"
```

### 라우팅 규칙

| 조건 | 결과 |
|------|------|
| risk_score >= 0.7 | block |
| conflict_score >= 0.6 또는 risk_score >= 0.4 | hitl |
| evidence_score < 0.3 | caution |
| 그 외 | allow |

---

## State 값 (실제 구현)

```python
state.guardrail_risk_score:     float  # 0.0–1.0 위험도 가중합
state.guardrail_conflict_score: float  # 0.0–1.0 충돌 심각도 최댓값
state.guardrail_evidence_score: float  # evidence_items retriever_score 평균
state.guardrail_route:          "allow" | "caution" | "hitl" | "block"
state.guardrail_decision_log:   List[Dict]  # 4단계 판단 로그
state.safety_checked:           bool   # idempotency guard (2차 호출 중복 실행 방지)
```

> **Idempotency**: `safety_checked=True`이면 2차 `graph.invoke` 재진입 시 노드를 스킵하고 기존 결과를 그대로 반환한다. `decision_log`는 항상 해당 실행분 4개만 기록한다 (이전 state 값 이어받지 않음).

---

# 🔐 설계 원칙

- 안전 판단은 단일 노드에서 수행한다.
- 강한 의료 권고는 반드시 근거 기반이어야 한다.
- 근거 없는 권고는 강도를 낮춘다.
- 알람 생성은 `allow` 또는 `caution`일 때만 가능하다.
- `block` 상태에서는 의료진 상담 안내 메시지를 출력한다.


### 조건부 분기 (7개)

| 분기점 | 조건 | 경로 |
|:--|:--|:--|
| has_diag | 진단/증상 여부 | → 스레드관리 / 증상스레드생성 / 종료 |
| is_existing | 기존 스레드 여부 | → 로드 or 생성 |
| detect_closure | 치료 완료 여부 | → 닫기 or 계속 |
| has_guideline | 의사 가이드라인 여부 | → 요약 / 증상스레드(스킵) / RAG |
| should_reflect | 반성 트리거 | → Reflection or 스킵 |
| plan_next_actions | 3가지 경로 | → HITL / 알람 / 종료 |
| hitl_alarm_opt_in | 환자 동의 여부 | → 알람생성 or 종료 |

## 구현 현황

| 항목 | 상태 | 비고 |
|:--|:--|:--|
| 진료 기록 자동화 | 완료 | src/medical_workflow/ |
| 생활습관 알람 | 완료 | nodes/alarm.py (카테고리별 규칙 기반) |
| 개인정보 비식별화 | 완료 | pii_middleware.py (한국 이름 탐지·마스킹, 그래프 외부 미들웨어) |
| 증상 스레드 | 완료 | 진단 없이 증상만 있을 때 임시 스레드 생성, 진단 확정 시 자동 승격 |
| 스레드 LLM 매칭 | 완료 | 동명이진 / 표현 다른 진단 / 증상→진단 승격 4단계 탐색 |
| Memory & Reflection | 완료 | 3회마다 환자 상태 요약 |
| HITL 알람 동의 | 완료 | 환자 동의 후 알람 생성 |
| 스레드 종료 감지 | 완료 | LLM 판단 (에러 핸들링 포함) |
| RAG 통합 | 완료 | nodes/rag.py (ChromaDB + medical_2.csv) |
| 에러 핸들링 | 완료 | LLM 노드 전체 적용 (safe_llm_invoke) |
| Safety Guardrail | 완료 | 4단계 score 기반, idempotency 포함 |
| xlsx 입력 모드 | 완료 | uv run python main.py {patient_id} |
| STT (Whisper/Daglo) | 미구현 | 텍스트 입력으로 대체 |
| 환자용 DB (PostgreSQL) | 미구현 | In-memory dict 사용 |
| 임상 기록 문서화 | 미구현 | 의료진 공유용 보고서 |
| 환자 Q&A | 미구현 | |
| 체크리스트 추적 | 미구현 | 알람 계획 생성만 가능 |

## 에러 핸들링

### 개요

LLM 호출 실패 시에도 워크플로우가 중단되지 않도록 안전장치 구현.

### 핵심 메커니즘

**safe_llm_invoke() 래퍼 함수** (utils/llm.py)
- LLM 호출 실패 시 fallback 값 자동 반환
- 에러 정보 자동 생성 (노드명, 타임스탬프, 에러 타입, 심각도)
- 로깅 자동 기록

**State 에러 추적 필드** (state.py)
```python
errors: List[Dict[str, Any]]  # 노드별 에러 누적
warnings: List[str]            # 사용자 경고 메시지
```

### 에러 심각도 (Severity)

| Level | 적용 노드 | 동작 | 사용자 알림 |
|:--|:--|:--|:--|
| **high** | extract_clinical, rag_to_guidelines | 의료 정보 관련 | ⚠️ 명시적 경고 |
| **medium** | detect_closure, summarize_guidelines, rag_query_sanitize, rag_supplement, safety_guardrail | 보조 기능 | ℹ️ 안내 메시지 |
| **low** | reflect_patient_state | 선택 기능 | 에러만 기록 |

### 최종 응답 구조 (finalize.py)

```python
final_answer = {
    # ... 기존 필드 ...
    "has_errors": bool,
    "has_critical_errors": bool,  # severity=high 여부
    "errors": [...],               # 전체 에러 리스트
    "warnings": [...],             # 경고 메시지
    "data_completeness": "complete" | "incomplete",
    "user_message": "⚠️ 일부 의료 정보 처리 실패..."
}
```

### 보수적 기본값

| 노드 | 실패 시 동작 |
|:--|:--|
| extract_clinical | 빈 진단/가이드라인 반환 |
| detect_closure | should_close=false (치료 계속) |
| summarize_guidelines | "의사 선생님의 조언을 확인하세요." |
| rag_to_guidelines | 빈 가이드라인 배열 반환 |
| reflect_patient_state | "{진단명} 관련 진료를 받았습니다." |
| safety_guardrail | LLM 실패 시 detected=[] 반환, risk/conflict score=0.0으로 처리 |

## 환경 변수 및 실행

README.md 참조
