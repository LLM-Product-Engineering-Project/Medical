
# LLM 기능 공백 목록

LLM 파라미터를 받지만 실제로는 규칙 기반(rule-based)으로만 동작하는 노드 목록.
**나중에 LLM으로 교체하거나 보강할 때 이 파일을 참고하라.**

분석 기준: AST로 `llm` Name 노드 실제 사용 여부 확인 (2026-02-19 기준)

---

## 기능 공백 (LLM 도입 효과가 높은 것)

### 1. `nodes/alarm.py` — `n_build_alarm_plan`

**현재 동작**
카테고리별로 고정 시간을 배정한다.
```python
if cat == "medication":
    plan_items.append({"time": "09:00", "action": text})
    plan_items.append({"time": "21:00", "action": text})
elif cat in ("lifestyle", "diet", "exercise"):
    plan_items.append({"time": "10:00", "action": text})
    plan_items.append({"time": "19:00", "action": text})
else:
    plan_items.append({"time": "12:00", "action": text})
```

**LLM 도입 시 기대 효과**
- 환자의 생활 패턴(직장인/노인/어린이)을 메모리에서 읽어 최적 시간대 배정
- 가이드라인 텍스트를 해석해 중복·충돌 항목 자동 제거
- 알람 우선순위 판단 (복약 > 식이 > 운동 순 등)

**구현 힌트**
```python
prompt = f"""
환자 메모리: {retrieved_memories}
가이드라인: {guidelines}
환자에게 맞는 하루 알람 일정표를 JSON으로 생성하라.
각 항목: {{"time": "HH:MM", "action": "...", "priority": 1-5}}
최대 12개. 중복 제거. 의학적으로 안전한 시간대.
"""
```

---

### 2. `nodes/planning.py` — `n_plan_next_actions`

**현재 동작**
단순 if/else 분기로 `plan_action`을 결정한다.
```python
if alarm_opt_in is True:
    return {**s, "plan_action": "build_alarm", ...}
if alarm_opt_in is False:
    return {**s, "plan_action": "finalize", ...}
# alarm_opt_in is None → has_any_guideline 여부로 분기
```

**LLM 도입 시 기대 효과**
- 환자 상태, 가이드라인 수, 이전 방문 이력을 종합해 더 지능적인 다음 행동 결정
- "알람을 물어볼지" 판단 자체도 맥락 기반으로 수행 가능

**구현 힌트**
현재 로직이 간단하고 명확하므로 LLM 우선순위 낮음. 복잡한 분기가 추가될 때 도입 검토.

---

### 3. `nodes/search.py` — `n_rag_query_sanitize`

**현재 동작**
진단명에 "관리 방법"을 붙인 고정 문자열을 쿼리로 사용한다.
```python
query = f"{diagnosis} 관리 방법"
```

**LLM 도입 시 기대 효과**
- 진료 전사 내용에서 환자가 특별히 궁금해하는 부분을 추출해 쿼리 생성
- 동반 질환, 복약 이력을 반영한 복합 쿼리 ("당뇨 + 신부전 식이 관리" 등)
- 검색 품질 향상으로 RAG 가이드라인 정확도 증가

**구현 힌트**
```python
prompt = f"""
진단명: {diagnosis}
진료 전사: {doctor_text}
위 내용을 바탕으로 의료 정보 검색에 가장 적합한 쿼리 1개를 생성하라.
쿼리만 출력 (설명 없이).
"""
```

---

### 4. `nodes/finalize.py` — `n_finalize`

**현재 동작**
조건별 하드코딩된 템플릿 문자열로 `user_message`를 생성한다.
```python
if s.get("guardrail_route") == "block":
    final_answer["user_message"] = "🚫 안전 검증에서 위험한 내용이 감지되어..."
elif critical_errors:
    final_answer["user_message"] = "⚠️ 일부 의료 정보 처리에 실패했습니다..."
elif warnings:
    final_answer["user_message"] = "\n".join(warnings)
```

**LLM 도입 시 기대 효과**
- 가이드라인·경고·에러를 종합해 환자 맞춤형 자연어 최종 응답 생성
- 진단명과 가이드라인을 반영한 personalized 요약 메시지
- 헬스 리터러시 수준에 맞춘 쉬운 언어로 변환

**구현 힌트**
```python
prompt = f"""
환자 진단: {diagnosis_key}
가이드라인: {safe_guidelines}
guardrail 결과: {guardrail_route}
경고: {warnings}

위 내용을 바탕으로 환자가 이해하기 쉬운 2-3문장 안내 메시지를 작성하라.
의료 용어를 최소화하고, 다음 행동을 명확히 안내하라.
"""
```

---

## 서명만 정리 대상 (LLM 불필요, `llm` 파라미터 제거 권장)

아래 함수들은 순수 로직/데이터 조작이므로 `llm` 파라미터가 불필요하다.
현재는 graph.py의 `lambda s: func(s, llm)` 래핑과의 일관성을 위해 유지 중이나,
추후 시그니처 정리 시 제거 가능하다.

| 함수 | 실제 동작 |
|:--|:--|
| `extraction.py::n_extract_doctor` | `redacted_transcript → doctor_text` 단순 복사 |
| `extraction.py::n_has_diagnosis` | `diagnoses` 리스트 유무 체크 |
| `guidelines.py::n_has_guideline` | `doctor_guidelines` 유무 bool 체크 |
| `planning.py::n_hitl_alarm_opt_in` | 캐시 조회 후 hitl_payload 반환 |
| `thread.py::n_is_existing` | THREAD_STORE 키 존재 여부 확인 |
| `thread.py::n_create_thread` | dict 생성 및 저장 |
| `thread.py::n_load_thread` | dict 로드 |
| `thread.py::n_close_thread` | dict status 필드 업데이트 |
| `finalize.py::n_finalize` | 응답 조립 (위 기능 공백과 중복) |

---

## 우선순위 권장 순서

1. **`n_rag_query_sanitize`** — 구현 쉽고 RAG 품질에 직접 영향. 단일 LLM 호출.
2. **`n_build_alarm_plan`** — 서비스 핵심 기능. 환자 맞춤 알람으로 차별화 가능.
3. **`n_finalize`** — 최종 사용자 경험에 직접 영향. personalized 메시지.
4. **`n_plan_next_actions`** — 현재 로직이 단순하므로 우선순위 낮음.
