# Medical Workflow 전체 흐름 설명서

> 진료 녹음 텍스트를 입력받아 환자 맞춤 가이드라인과 생활습관 알람을 생성하는 Agent 기반 시스템의 입력부터 출력까지 전 과정을 설명한다.

---

## 목차

1. [시스템 전체 구조](#1-시스템-전체-구조)
2. [실행 진입점](#2-실행-진입점)
3. [Phase 1 — 입력 전처리](#3-phase-1--입력-전처리)
4. [Phase 2 — 임상 정보 추출](#4-phase-2--임상-정보-추출)
5. [Phase 3 — 스레드 관리](#5-phase-3--스레드-관리)
6. [Phase 4 — 메모리 조회 및 종료 감지](#6-phase-4--메모리-조회-및-종료-감지)
7. [Phase 5 — 가이드라인 확보](#7-phase-5--가이드라인-확보)
8. [Phase 6 — Safety Guardrail (4단계 안전 검증)](#8-phase-6--safety-guardrail-4단계-안전-검증)
9. [Phase 7 — Reflection 및 계획 수립](#9-phase-7--reflection-및-계획-수립)
10. [Phase 8 — HITL과 알람 생성](#10-phase-8--hitl과-알람-생성)
11. [Phase 9 — 최종 응답 생성](#11-phase-9--최종-응답-생성)
12. [2차 그래프 호출 (HITL 응답 처리)](#12-2차-그래프-호출-hitl-응답-처리)
13. [에러 핸들링 원칙](#13-에러-핸들링-원칙)
14. [저장소와 상태의 생명주기](#14-저장소와-상태의-생명주기)
15. [전체 흐름 요약 다이어그램](#15-전체-흐름-요약-다이어그램)

---

## 1. 시스템 전체 구조

이 시스템은 **LangGraph StateGraph** 위에서 동작하는 워크플로우이다. 모든 처리 단계는 "노드(node)"이고, 각 노드는 `WFState`라는 딕셔너리를 받아 수정된 딕셔너리를 돌려준다. 노드 사이의 연결은 "엣지(edge)"이며, 조건에 따라 분기하는 "조건부 엣지(conditional edge)"도 있다.

```
WFState (TypedDict)
  └── 모든 노드가 공유하는 단일 상태 객체
      예) transcript, extracted, diagnosis_key, safe_guidelines, guardrail_route, ...
```

상태 정의 파일: `src/medical_workflow/state.py`
그래프 정의 파일: `src/medical_workflow/graph.py`

그래프는 `build_graph(llm, retriever)` 함수로 만들어진다. 이 함수는 LLM 객체와 RAG 검색기를 인자로 받아, 모든 노드를 등록하고 엣지를 연결한 뒤 컴파일된 그래프를 반환한다. 개별 노드들은 LLM을 직접 보유하지 않고, `graph.py`에서 `lambda s: n_xxx(s, llm)` 형태로 래핑되어 주입된다.

---

## 2. 실행 진입점

### 두 가지 실행 모드

시스템은 `runner.py`의 `main()` 함수에서 시작된다. 실행 방식은 두 가지다.

**txt 모드** — `data/recordings/` 폴더의 `Recording_*.txt` 파일을 순서대로 처리한다.
```bash
uv run python main.py
```

**xlsx 모드** — `data/testcase(50).xlsx`의 특정 환자 케이스를 처리한다.
```bash
uv run python main.py p01
```

참조: `src/medical_workflow/runner.py:162-206`

### 초기화 과정

`_setup_workflow()` 함수에서 세 가지를 초기화한다.

1. **LLM 객체 생성**: Upstage의 Solar Pro2 모델을 `ChatOpenAI` 인터페이스로 초기화한다. temperature를 0.1로 낮게 설정해 일관성 있는 의료 정보 추출을 유도한다.

2. **벡터 DB 구축**: `data/medical_2.csv`(서울대병원 의학 정보)를 로드해 Chroma 벡터 DB를 만든다. `data/chroma_db/` 폴더에 DB가 이미 있으면 새로 만들지 않고 즉시 로드한다. 이 DB가 이후 RAG 검색의 지식 소스가 된다.

3. **그래프 컴파일**: `build_graph(llm, retriever)`를 호출해 실행 가능한 그래프를 얻는다.

참조: `src/medical_workflow/runner.py:18-46`, `src/medical_workflow/nodes/rag.py:12-68`

### 케이스별 처리

각 파일/케이스에 대해 `_process_single(graph, base_state, label)`이 호출된다. 이 함수가 `graph.invoke(base_state)`를 실행해 그래프를 시작한다. 초기 state는 다음과 같이 구성된다.

```python
base_state = {
    "patient_id":     "p01",
    "visit_id":       "v_0001",
    "input_filename": "Recording_20240315.txt",
    "transcript":     "의사: 고혈압 진단입니다. 저염식 유지하세요...",
    "alarm_opt_in":   None,
    "hitl_payload":   None,
}
```

참조: `src/medical_workflow/runner.py:49-71`

---

## 3. Phase 1 — 입력 전처리

그래프의 entry point는 `parse_input_meta`다.

### 노드 1: `parse_input_meta`

파일명에서 진료 날짜를 추출한다. `Recording_20240315.txt` 형태라면 `2024-03-15`로 변환해 `visit_date` 필드에 저장한다. `patient_id`가 없으면 기본값 `"p1"`을 사용하지만, runner에서 이미 올바른 값을 넣어주므로 실제로는 거의 동작하지 않는다.

참조: `src/medical_workflow/nodes/input.py:8-17`

### 노드 2: `deidentify_redact`

진료 전사 텍스트에서 개인 식별 정보를 정규식으로 마스킹한다. 변환 결과는 `redacted_transcript` 필드에 저장되며, 이후 모든 처리는 원본 `transcript` 대신 이 비식별화 텍스트를 사용한다.

| 제거 대상 | 치환 결과 |
|---|---|
| 이메일 주소 | `[REDACTED_EMAIL]` |
| 휴대폰·일반전화 번호 | `[REDACTED_PHONE]` |
| 주민등록번호 (13자리) | `[REDACTED_RRN]` |
| 도로명·지번 주소 | `[REDACTED_ADDRESS]` |

참조: `src/medical_workflow/nodes/input.py:20-33`

---

## 4. Phase 2 — 임상 정보 추출

### 노드 3: `extract_doctor`

단순한 복사 노드다. `redacted_transcript`를 `doctor_text` 필드로 복사해 이후 LLM 프롬프트에서 사용할 수 있게 한다.

참조: `src/medical_workflow/nodes/extraction.py:7-8`

### 노드 4: `extract_clinical` (LLM 호출)

이 시스템에서 가장 중요한 LLM 호출이다. `doctor_text`를 LLM에 넘겨 진단명과 의사 가이드라인을 구조화된 JSON으로 추출한다.

LLM에게 요청하는 출력 형식은 다음과 같다.

```json
{
  "diagnoses": [{"name": "고혈압", "confidence": 0.95}],
  "doctor_guidelines": [
    {"category": "diet", "text": "저염식 식단 유지", "source": "doctor"},
    {"category": "medication", "text": "혈압약 매일 복용", "source": "doctor"}
  ]
}
```

`category`는 `lifestyle`, `medication`, `diet`, `exercise`, `followup`, `warning`, `other` 중 하나다.

LLM 호출은 `safe_llm_invoke()`를 통해 이루어진다. 호출이 실패하면 `{"diagnoses": [], "doctor_guidelines": []}` 라는 빈 구조를 반환하고, 에러 정보는 `state["errors"]`에 누적된다. severity가 `"high"`이므로 실패 시 경고 메시지도 함께 추가된다.

참조: `src/medical_workflow/nodes/extraction.py:11-56`, `src/medical_workflow/utils/llm.py:15-70`

### 노드 5: `has_diag` → 분기

추출된 `diagnoses` 리스트가 비어있으면 `has_diagnosis=False`가 되고 그래프는 곧바로 `finalize`로 이동한다. 진단명이 있으면 첫 번째 진단명을 `diagnosis_key`로 설정하고 스레드 관리로 넘어간다.

```
has_diag 결과
  ├─ has_diagnosis = True  → is_existing (스레드 확인)
  └─ has_diagnosis = False → finalize (종료)
```

참조: `src/medical_workflow/nodes/extraction.py:59-63`, `src/medical_workflow/graph.py:101-105`

---

## 5. Phase 3 — 스레드 관리

**스레드(Thread)** 는 환자와 질병의 조합(`patient_id + diagnosis_key`)으로 만들어지는 진료 이력 컨테이너다. 예를 들어 `p01` 환자의 `고혈압` 스레드에는 해당 환자의 고혈압 관련 모든 방문 기록이 쌓인다. 스레드는 `THREAD_STORE`라는 인메모리 딕셔너리에 저장된다.

참조: `src/medical_workflow/stores/thread.py`

### 노드 6: `is_existing`

`THREAD_STORE`에 `"p01__고혈압"` 형태의 키가 있는지 확인해 `is_existing` 필드를 설정한다. 이 결과에 따라 두 경로로 분기한다.

```
is_existing 결과
  ├─ True  → load_thread  (기존 스레드 로드)
  └─ False → create_thread (새 스레드 생성)
```

참조: `src/medical_workflow/nodes/thread.py:17-19`

### 노드 7a: `create_thread`

처음 방문이면 스레드를 새로 만든다. 구조는 다음과 같다.

```python
{
    "thread_id":     "thread_p01_고혈압",
    "patient_id":    "p01",
    "diagnosis_key": "고혈압",
    "status":        "active",
    "events":        [],   # 방문 이력
    "memories":      [],   # 요약 메모리
    "reflections":   [],   # 환자 상태 리플렉션
    "alarm_opt_in":  None, # 알람 동의 여부
}
```

참조: `src/medical_workflow/nodes/thread.py:22-33`

### 노드 7b: `load_thread`

기존 스레드가 있으면 `THREAD_STORE`에서 불러온다. 이때 state에 이미 `alarm_opt_in=True` 또는 `False`가 있으면(2차 그래프 호출 시) 그 값을 우선 사용한다. 스레드 캐시의 값으로 덮어쓰지 않는 것이 핵심이다.

```python
state_opt = s.get("alarm_opt_in")
alarm_opt_in = state_opt if state_opt in (True, False) else t.get("alarm_opt_in")
```

참조: `src/medical_workflow/nodes/thread.py:36-43`

---

## 6. Phase 4 — 메모리 조회 및 종료 감지

### 노드 8: `retrieve_memories`

스레드에 쌓인 과거 기록을 가져온다. 최근 `memories` 8개와 최근 `events` 3개를 합쳐 `retrieved_memories`에 저장한다. 이 데이터는 이후 Safety Guardrail의 Context Check와 Reflection에서 환자의 맥락 정보로 활용된다.

```python
recent_mem = memories[-8:]   # 최근 방문 요약 메모리
recent_ev  = events[-3:]     # 최근 방문 이벤트 (간략 요약)
retrieved  = recent_mem + ev_mem
```

참조: `src/medical_workflow/nodes/memory.py:9-34`

### 노드 9: `detect_closure` (LLM 호출)

이번 진료 전사를 보고 "이 질병에 대한 관리(스레드)를 종료해야 하는가?"를 LLM이 판단한다. 예를 들어 "완치 판정을 받았습니다"나 "더 이상 진료가 필요 없습니다" 같은 내용이 있으면 `true`를 반환한다.

LLM 응답 형식:
```json
{"should_close": true}
```

LLM 호출 실패 시 기본값은 `{"should_close": false}`다. 판단 실패보다 치료를 계속하는 쪽이 안전하기 때문이다.

```
detect_closure 결과
  ├─ should_close = True  → close_thread → finalize
  └─ should_close = False → has_guideline (가이드라인 확보로)
```

참조: `src/medical_workflow/nodes/thread.py:46-77`, `src/medical_workflow/graph.py:126-133`

### 노드 9a: `close_thread` (종료 경로)

`should_close=True`이면 스레드의 `status`를 `"closed"`로 변경하고, 바로 `finalize`로 이동한다.

---

## 7. Phase 5 — 가이드라인 확보

가이드라인을 확보하는 경로는 두 가지다. 진료 전사에 의사가 직접 안내한 내용이 있으면 그것을 사용하고, 없으면 내부 RAG DB에서 검색한다.

```
has_guideline 결과
  ├─ True  → summarize_guidelines (의사 가이드라인 요약)
  └─ False → rag_query_sanitize → rag_search → rag_to_guidelines
```

참조: `src/medical_workflow/graph.py:141-153`

### 경로 A: 의사 가이드라인이 있는 경우

**노드 10a: `has_guideline`**

`extract_clinical`에서 추출한 `doctor_guidelines`가 존재하는지 확인한다.

**노드 11a: `summarize_guidelines`** (LLM 호출)

의사가 여러 가이드라인을 나열했을 때, 환자가 이해하기 쉬운 2문장 요약을 생성한다. 결과는 `doctor_summary`에 저장된다. LLM 호출 실패 시 `"의사 선생님의 조언을 확인하세요."`라는 기본 메시지를 사용한다.

참조: `src/medical_workflow/nodes/guidelines.py:11-29`

### 경로 B: 의사 가이드라인이 없는 경우

**노드 10b: `rag_query_sanitize`**

검색 쿼리를 만든다. 현재는 단순히 `"{진단명} 관리 방법"` 문자열을 사용한다.

참조: `src/medical_workflow/nodes/search.py:7-11`

**노드 11b: `rag_search`**

생성된 쿼리로 Chroma 벡터 DB를 검색한다. `data/medical_2.csv`에 수록된 서울대병원 의학 정보(병명, 생활가이드, 식이요법) 중 가장 유사한 문서 3개를 가져온다. 결과 텍스트는 `rag_raw`에 저장된다.

```python
docs = retriever.invoke(query)   # k=3개 검색
raw_text = "\n\n---\n\n".join(doc.page_content for doc in docs)
```

참조: `src/medical_workflow/nodes/rag.py:71-94`

**노드 12b: `rag_to_guidelines`** (LLM 호출)

`rag_raw`의 자유로운 텍스트를 구조화된 가이드라인 배열로 변환한다. 출력 형식은 의사 가이드라인과 동일하되 `source`가 `"rag"`로 표시된다.

```json
[
  {"category": "diet", "text": "저염식 권장", "source": "rag"},
  {"category": "exercise", "text": "주 3회 유산소 운동", "source": "rag"}
]
```

LLM 호출 실패 시 빈 배열 `[]`을 반환한다.

참조: `src/medical_workflow/nodes/search.py:14-51`

---

## 8. Phase 6 — Safety Guardrail (4단계 안전 검증)

모든 경로(의사 가이드라인/RAG 가이드라인)는 반드시 `safety_guardrail` 노드를 통과한다. 이 노드는 4단계를 순차적으로 실행해 가이드라인의 안전성을 평가하고 최종 라우팅 결정을 내린다.

**멱등성 보장**: state에 `safety_checked=True`가 있으면 즉시 기존 결과를 반환하고 재실행하지 않는다. 이는 2차 그래프 호출 시 중복 실행을 방지한다.

참조: `src/medical_workflow/nodes/guidelines.py:32-277`, `src/medical_workflow/guardrail_policy.py`

### Stage 1: Risk Filter (LLM 호출)

가이드라인에서 위험한 의료 지시를 탐지한다. LLM이 다음 5개 risk code 중 해당하는 것을 JSON으로 반환한다.

| Risk Code | 의미 | 가중치 |
|---|---|---|
| `RISK_DRUG_DOSAGE_CHANGE` | 환자가 약물 용량을 바꾸도록 지시 | 1.0 |
| `RISK_TREATMENT_STOP` | 기존 치료·약물 중단 권고 | 1.0 |
| `RISK_EMERGENCY_DISMISSAL` | 응급 증상 무시·축소 | 1.0 |
| `RISK_NEW_DIAGNOSIS_ASSERTION` | 검사 없이 새 질병 단정 진단 | 0.9 |
| `RISK_GENERAL_DANGER` | 기타 위험 권고 | 0.5 |

여러 위험 요소가 탐지되면 가중치를 합산해 `risk_score`(0.0–1.0)를 계산한다. 탐지된 게 없으면 `RISK_CLEAR`로 기록하고 score는 0.0이 된다.

### Stage 2: Context Check (LLM 호출)

환자의 과거 메모리(`retrieved_memories`)와 현재 가이드라인을 비교해 충돌을 탐지한다. 예를 들어 환자 메모리에 "당뇨 기저질환"이 기록되어 있는데 가이드라인이 "고당분 식품 권장"이라면 충돌로 탐지된다.

| Conflict Code | 의미 |
|---|---|
| `CONFLICT_COMORBIDITY_DIET` | 기저질환과 식이 가이드라인 충돌 |
| `CONFLICT_COMORBIDITY_MEDICATION` | 기저질환과 약물 권고 충돌 |
| `CONFLICT_ALLERGY_CONTRAINDICATION` | 알레르기·금기 위반 |
| `CONFLICT_GENERAL` | 기타 충돌 |

각 충돌 항목에는 0.0–1.0의 severity가 붙고, 가장 높은 값이 `conflict_score`가 된다.

### Stage 3: Source Check (규칙 기반)

가이드라인의 출처에 따라 신뢰도를 평가한다. LLM을 호출하지 않고 규칙 기반으로 처리한다.

| 출처 | 신뢰도 (retriever_score) | Reason Code |
|---|---|---|
| 의사 직접 발화 (`has_guideline=True`) | 1.0 | `EVIDENCE_DOCTOR_DIRECT` |
| RAG 검색 (`rag_guidelines`) | 0.7 (기본값) | `EVIDENCE_RAG_RETRIEVED` |
| 가이드라인 없음 | 0.0 | `EVIDENCE_NO_SOURCE` |

모든 항목의 retriever_score 평균이 `evidence_score`다.

### Stage 4: Policy Routing

세 점수(risk_score, conflict_score, evidence_score)를 `ROUTING_POLICY` 테이블과 비교해 최종 라우팅을 결정한다. 우선순위는 block > hitl > caution > allow 순이다.

| 조건 | 결과 |
|---|---|
| `risk_score >= 0.7` | `block` — 의료진 상담 안내 후 종료 |
| `conflict_score >= 0.6` | `hitl` — 전문가 검토 요청 |
| `risk_score >= 0.4` | `hitl` — 중간 위험도, 검토 필요 |
| `evidence_score < 0.3` | `caution` — 근거 부족 경고 후 진행 |
| 그 외 | `allow` — 정상 진행 |

```
guardrail_route 결과
  ├─ "block"   → finalize (가이드라인 비공개, 경고 메시지 출력)
  ├─ "hitl"    → hitl_alarm_opt_in
  ├─ "caution" → should_reflect (경고 메시지 포함)
  └─ "allow"   → should_reflect
```

모든 단계의 결정 근거는 `guardrail_decision_log`에 타임스탬프와 함께 기록된다. 각 단계마다 정확히 1개의 로그 항목이 생성되므로 최종 로그는 항상 4개다.

참조: `src/medical_workflow/graph.py:162-171`, `src/medical_workflow/guardrail_policy.py`

---

## 9. Phase 7 — Reflection 및 계획 수립

### 노드 13: `should_reflect`

Reflection(환자 상태 요약)이 필요한지 판단한다. 다음 두 조건 중 하나라도 충족되면 Reflection을 실행한다.

- 이 스레드의 누적 이벤트(방문) 수가 3의 배수인 경우
- 이번 방문에서 확보된 안전 가이드라인(`safe_guidelines`)이 5개 이상인 경우

참조: `src/medical_workflow/nodes/memory.py:37-51`

### 노드 14: `reflect_patient_state` (LLM 호출, 선택적)

과거 메모리와 이번 방문 가이드라인을 종합해 환자의 현재 상태를 3줄로 요약한다. 새로운 의료 조언을 만들지 않고 기존 기록을 정리하는 것이 목적이다. 생성된 요약은 `patient_reflection` 필드에 저장되고, 스레드의 `reflections` 배열에도 영구 저장된다. LLM 호출 실패 시 `"{진단명} 관련 진료를 받았습니다."`가 기본값이다.

참조: `src/medical_workflow/nodes/memory.py:54-106`

### 노드 15: `plan_next_actions`

다음 행동을 결정하는 분기 노드다. 스레드에 `alarm_opt_in`이 이미 캐싱된 경우(이전 방문에서 동의 여부를 결정했던 경우)에는 그 값을 사용해 HITL을 건너뛴다.

| 조건 | plan_action |
|---|---|
| `alarm_opt_in = True` | `"build_alarm"` (알람 바로 생성) |
| `alarm_opt_in = False` | `"finalize"` (알람 없이 종료) |
| `alarm_opt_in = None` + 가이드라인 존재 | `"ask_hitl"` (동의 질문) |
| `alarm_opt_in = None` + 가이드라인 없음 | `"finalize"` |

참조: `src/medical_workflow/nodes/planning.py:6-34`

---

## 10. Phase 8 — HITL과 알람 생성

### 노드 16: `hitl_alarm_opt_in`

Human-in-the-Loop 노드다. 스레드나 state에 `alarm_opt_in`이 이미 설정되어 있으면 그대로 통과한다. 설정이 없으면 `hitl_payload`를 만들어 state에 넣고 그래프 실행을 일단 멈춘다.

```python
"hitl_payload": {
    "type":          "hitl",
    "question":      "치료를 위한 생활습관 알람과 일정표를 만들어드릴까요?",
    "choices":       ["yes", "no"],
    "visit_date":    "2024-03-15",
    "diagnosis_key": "고혈압",
}
```

1차 `graph.invoke(base_state)` 호출은 여기서 결과를 반환한다. `runner.py`에서 이 payload를 감지하면 사용자에게 yes/no를 물어본다.

```
hitl_alarm_opt_in 결과
  ├─ alarm_opt_in = True  → build_alarm_plan
  └─ alarm_opt_in = False → finalize
```

참조: `src/medical_workflow/nodes/planning.py:37-56`, `src/medical_workflow/runner.py:56-71`

### 노드 17: `build_alarm_plan`

`safe_guidelines`를 카테고리별로 분류해 하루 알람 일정을 생성한다. 현재는 고정된 시간대 규칙을 사용한다.

| 카테고리 | 알람 시간 |
|---|---|
| `medication` (복약) | 09:00, 21:00 |
| `lifestyle`, `diet`, `exercise` | 10:00, 19:00 |
| 기타 | 12:00 |

최대 12개의 알람이 생성되며, 과거 방문의 가이드라인도 누적해서 포함한다. 결과는 `alarm_plan` 필드에 저장된다.

```json
{
  "patient_id": "p01",
  "start_date": "2024-03-15",
  "timezone":   "Asia/Seoul",
  "items": [
    {"time": "09:00", "action": "혈압약 복용"},
    {"time": "10:00", "action": "저염식 식단 유지"},
    {"time": "21:00", "action": "혈압약 복용"}
  ]
}
```

참조: `src/medical_workflow/nodes/alarm.py:9-46`

---

## 11. Phase 9 — 최종 응답 생성

### 노드 18: `finalize`

모든 경로의 마지막 노드다. 두 가지 작업을 수행한다.

**① 스레드에 이번 방문 기록 저장**

`_append_memory_and_event()`를 호출해 스레드의 `events`와 `memories`에 이번 방문 정보를 추가한다. `visit_id`가 이미 존재하면 중복 저장하지 않는다(2차 호출 방지).

```python
thread["events"].append({
    "visit_id":    "v_0001",
    "visit_date":  "2024-03-15",
    "guidelines":  safe_guidelines,
    "should_close": False,
})
thread["memories"].append({
    "text": "summary: 저염식 유지... | guidelines: 3 items",
    "importance": 0.6,
})
```

**② `final_answer` 딕셔너리 조립**

진단이 없는 단순 방문이면 `{"type": "general_visit"}`만 반환한다.
진단이 있는 경우 다음 구조의 최종 응답을 만든다.

```json
{
  "type":                  "disease_thread_update",
  "patient_id":            "p01",
  "visit_id":              "v_0001",
  "diagnosis_key":         "고혈압",
  "guidelines":            [...],
  "alarm_plan":            {...},
  "patient_reflection":    "환자는 고혈압 관리 중이며...",
  "guardrail_route":       "allow",
  "guardrail_risk_score":  0.0,
  "guardrail_decision_log": [...],
  "has_errors":            false,
  "data_completeness":     "complete",
  "user_message":          null
}
```

`guardrail_route`가 `"block"`이면 `guidelines` 필드는 빈 배열이고, `user_message`에 "반드시 담당 의료진과 직접 상담하시기 바랍니다." 메시지가 들어간다.

참조: `src/medical_workflow/nodes/finalize.py:69-143`

---

## 12. 2차 그래프 호출 (HITL 응답 처리)

HITL이 발생했을 때의 전체 흐름을 이해하는 것이 중요하다.

**1차 호출**: 정상 흐름으로 진행하다가 `hitl_alarm_opt_in`에서 `hitl_payload`를 만들고 멈춘다. 이 시점에서 `finalize`까지 도달해 `final_answer`와 함께 반환된다. 단, 알람 계획은 없다.

```python
result1 = graph.invoke(base_state)
# result1["hitl_payload"]가 존재하면 사용자 입력 대기
```

**사용자 입력**: runner가 `hitl_payload`를 출력하고 yes/no를 받는다.

**2차 호출**: `result1` 전체를 base로 하고 `alarm_opt_in`만 덮어써서 다시 `graph.invoke`를 호출한다.

```python
state2 = {**result1, "alarm_opt_in": True, "hitl_payload": None}
result2 = graph.invoke(state2)
```

2차 호출도 `parse_input_meta`부터 전체 그래프를 재실행한다. 하지만 이미 처리된 내용들은 state에 그대로 있으므로 대부분의 노드는 동일한 결과를 빠르게 통과한다. `n_load_thread`에서 `alarm_opt_in=True`가 state에 있으므로 올바르게 유지된다. `n_safety_guardrail`에서 `safety_checked=True`를 확인하고 즉시 반환해 중복 실행을 방지한다. `n_finalize`에서 `visit_id` 중복 체크로 이벤트 재적재를 막는다.

참조: `src/medical_workflow/runner.py:56-71`, `src/medical_workflow/nodes/guidelines.py:45-46`

---

## 13. 에러 핸들링 원칙

### safe_llm_invoke()

모든 LLM 호출은 이 함수를 통해 이루어진다. 호출 실패 시 예외를 발생시키지 않고 `(fallback_value, error_info)` 튜플을 반환한다. 워크플로우는 LLM 호출이 실패해도 중단되지 않는다.

```python
result, error = safe_llm_invoke(llm, prompt, node_name="...", fallback_value=..., severity="high")
if error:
    state["errors"].append(error)
```

참조: `src/medical_workflow/utils/llm.py:15-70`

### 심각도(severity) 분류

| 심각도 | 적용 노드 | 의미 |
|---|---|---|
| `high` | `extract_clinical`, `rag_to_guidelines` | 핵심 의료 정보 손실 가능 |
| `medium` | `detect_closure`, `summarize_guidelines`, `safety_guardrail_*` | 보조 기능 실패 |
| `low` | `reflect_patient_state` | 선택적 기능 실패 |

### 보수적 기본값

실패해도 워크플로우가 안전하게 계속되도록 기본값이 설계되어 있다.

| 노드 | 실패 시 기본값 | 이유 |
|---|---|---|
| `detect_closure` | `{"should_close": false}` | 치료를 계속하는 게 더 안전 |
| `safety_guardrail_risk` | `{"detected": []}` | 위험 없음으로 간주 (다음 단계에서 검증) |
| `extract_clinical` | `{"diagnoses": [], ...}` | 정보 없음으로 처리 |

---

## 14. 저장소와 상태의 생명주기

### 두 저장소

**THREAD_STORE**: 환자 + 진단명 조합의 스레드를 저장한다. 여러 방문에 걸쳐 누적되며, 메모리·이벤트·리플렉션이 쌓인다.

**VISIT_STORE**: 방문 단위의 기록을 저장한다. `upsert_visit_record()`로 `finalize`에서 저장된다.

두 저장소 모두 인메모리 딕셔너리다. 프로세스가 종료되면 데이터가 사라진다.

참조: `src/medical_workflow/stores/thread.py`, `src/medical_workflow/stores/visit.py`

### WFState의 흐름

```
graph.invoke(base_state) 호출
  → 각 노드가 {**s, "새로운_키": 값} 형태로 상태를 확장
  → 이전 상태는 보존되고, 새 키만 추가/덮어씀
  → 마지막 노드(finalize)의 반환값이 graph.invoke()의 반환값
```

상태는 불변(immutable) 방식으로 다뤄진다. 각 노드는 `s`를 직접 수정하지 않고 `{**s, "key": value}` 형태로 새 딕셔너리를 만들어 반환한다.

---

## 15. 전체 흐름 요약 다이어그램

```
[입력] Recording_*.txt 또는 xlsx interview 텍스트
    │
    ▼
[parse_input_meta]  → 파일명에서 날짜 추출, patient_id 설정
    │
    ▼
[deidentify_redact] → 이메일/전화/주민번호/주소 마스킹
    │
    ▼
[extract_doctor]    → redacted_transcript를 doctor_text로 복사
    │
    ▼
[extract_clinical]  ⚡LLM → 진단명, 의사 가이드라인 JSON 추출
    │
    ▼
[has_diag] ──── 진단 없음 ────────────────────────────────┐
    │                                                      │
  진단 있음                                               │
    ▼                                                      │
[is_existing] ── 신규 → [create_thread]                   │
    │            기존 → [load_thread]                      │
    ▼                                                      │
[retrieve_memories] → 최근 8개 메모리 + 3개 이벤트 조회   │
    │                                                      │
    ▼                                                      │
[detect_closure] ⚡LLM → 치료 종료 여부 판단              │
    │                                                      │
  종료 → [close_thread] ──────────────────────────────┐   │
  계속                                                 │   │
    ▼                                                  │   │
[has_guideline] ── 있음 → [summarize_guidelines] ⚡LLM │   │
    │              없음 → [rag_query_sanitize]         │   │
    │                         │                       │   │
    │                    [rag_search] (ChromaDB)       │   │
    │                         │                       │   │
    │                    [rag_to_guidelines] ⚡LLM     │   │
    │                         │                       │   │
    └─────────────────────────┘                       │   │
    ▼                                                  │   │
[safety_guardrail] ⚡LLM×2                             │   │
  Stage 1: Risk Filter     → risk_score                │   │
  Stage 2: Context Check   → conflict_score            │   │
  Stage 3: Source Check    → evidence_score            │   │
  Stage 4: Policy Routing  → guardrail_route           │   │
    │                                                  │   │
  block ──────────────────────────────────────────┐   │   │
  hitl  → [hitl_alarm_opt_in]                     │   │   │
  allow/caution                                   │   │   │
    ▼                                             │   │   │
[should_reflect] ── 예 → [reflect_patient_state] ⚡LLM│   │
    │               아니오                        │   │   │
    ▼                                             │   │   │
[plan_next_actions]                               │   │   │
  ask_hitl   → [hitl_alarm_opt_in] ─┐            │   │   │
  build_alarm → [build_alarm_plan]  │            │   │   │
  finalize ──────────────────────┐  │            │   │   │
                                 │  │            │   │   │
                        [hitl_alarm_opt_in]      │   │   │
                          yes → [build_alarm_plan]│   │   │
                          no ──────────────────┐ │   │   │
                                               │ │   │   │
                                   [build_alarm_plan]│   │
                                               │ │   │   │
                                               ▼ ▼   ▼   ▼
                                            [finalize]
                                               │
                                               ▼
                                          [최종 출력]
                                    final_answer 딕셔너리
```

⚡ LLM이 호출되는 노드 (6개): `extract_clinical`, `detect_closure`, `summarize_guidelines`, `rag_to_guidelines`, `safety_guardrail` (내부 2회), `reflect_patient_state`

---

*작성일: 2026-02-19*
*참조 코드베이스 기준: `src/medical_workflow/` 전체*
