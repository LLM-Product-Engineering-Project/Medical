# LLM 노드 단독 테스트

각 LLM 노드를 전체 워크플로우와 독립적으로 테스트하기 위한 파일들입니다.

## 📋 테스트 파일 목록

### LLM 노드 개별 테스트

| 파일명 | 노드 | 기능 | Severity |
|:--|:--|:--|:--|
| `test_extract_clinical.py` | n_extract_clinical | 진료 기록에서 진단명과 가이드라인 추출 | high |
| `test_detect_closure.py` | n_detect_closure | 치료 종료 여부 판단 | medium |
| `test_summarize_guidelines.py` | n_summarize_guidelines | 의사 조언을 환자용 2문장 요약 | medium |
| `test_rag_to_guidelines.py` | n_rag_to_guidelines | RAG 검색 결과를 가이드라인으로 변환 | high |
| `test_reflect_patient_state.py` | n_reflect_patient_state | 누적 메모리를 바탕으로 환자 상태 요약 | low |

### 통합 테스트

| 파일명 | 테스트 범위 | 설명 |
|:--|:--|:--|
| `test_rag_integration.py` | RAG 파이프라인 전체 | 벡터 DB 구축 → 검색 → 가이드라인 변환 |

## 🚀 실행 방법

### 전제 조건
```bash
# .env 파일에 API 키가 설정되어 있어야 함
UPSTAGE_API_KEY=your_key_here
LANGSMITH_API_KEY=your_key_here
```

### 개별 테스트 실행
```bash
# 프로젝트 루트에서 실행
cd C:\Users\yebin\Desktop\Medical

# LLM 노드 개별 테스트
python tests/test_extract_clinical.py
python tests/test_detect_closure.py
python tests/test_summarize_guidelines.py
python tests/test_rag_to_guidelines.py
python tests/test_reflect_patient_state.py

# RAG 통합 테스트 (시간 소요: 벡터 DB 구축)
python tests/test_rag_integration.py
```

### 전체 테스트 한 번에 실행
```bash
# Bash 환경에서
for test in tests/test_*.py; do
    echo "=== Running $test ==="
    python "$test"
    echo ""
done
```

## 📊 테스트 케이스 구성

### 1. test_extract_clinical.py
- **케이스 1**: 정상적인 진료 기록 (당뇨병 진단)
- **케이스 2**: 진단명 없는 일반 상담
- **케이스 3**: 복잡한 진료 (다중 진단 + 상세 가이드라인)

**출력 예시**:
```json
{
  "diagnoses": [
    {"name": "당뇨병", "confidence": 0.95}
  ],
  "doctor_guidelines": [
    {"category": "diet", "text": "단 음식을 피하세요", "source": "doctor"},
    {"category": "exercise", "text": "매일 30분 걷기", "source": "doctor"}
  ]
}
```

### 2. test_detect_closure.py
- **케이스 1**: 치료 종료 (완치 선언)
- **케이스 2**: 치료 계속 (경과 관찰)
- **케이스 3**: 애매한 상황 (경과는 좋지만 추적 필요)
- **케이스 4**: 치료 종료 (전원/이송)

**출력 예시**:
```json
{
  "should_close": true/false
}
```

### 3. test_summarize_guidelines.py
- **케이스 1**: 간단한 진료 (감기)
- **케이스 2**: 복잡한 당뇨병 관리 지침
- **케이스 3**: 고혈압 + 운동 제한

**출력 예시**:
```
doctor_summary: "저염식을 실천하고 매일 혈압을 체크하세요. 규칙적인 운동과 금연이 중요합니다."
```

### 4. test_rag_to_guidelines.py
- **케이스 1**: 당뇨병 RAG 결과
- **케이스 2**: 고혈압 RAG 결과
- **케이스 3**: 빈 RAG 결과 (에러 핸들링)
- **케이스 4**: 복잡한 RAG 결과 (약물 + 식이 + 운동)

**출력 예시**:
```json
[
  {
    "category": "diet",
    "text": "단순당을 피하고 복합 탄수화물을 섭취하세요",
    "source": "rag"
  },
  {
    "category": "exercise",
    "text": "식후 30분 후 가벼운 산책을 하세요",
    "source": "rag"
  }
]
```

### 5. test_reflect_patient_state.py
- **케이스 1**: 첫 방문 (메모리 없음)
- **케이스 2**: 누적 방문 (메모리 있음, 3회차)
- **케이스 3**: 복잡한 케이스 (가이드라인 5개 이상)

**출력 예시**:
```
patient_reflection: "고혈압으로 저염식과 운동을 시작했습니다.
혈압이 점차 감소하는 추세를 보이고 있습니다.
약물 복용과 생활습관 개선을 꾸준히 지속하고 있습니다."
```

### 6. test_rag_integration.py (통합 테스트)
- **케이스 1**: 당뇨병 RAG 파이프라인
- **케이스 2**: 고혈압 RAG 파이프라인
- **케이스 3**: 고지혈증 RAG 파이프라인
- **케이스 4**: 희귀 질환 (에러 핸들링)
- **케이스 5**: 폐암 (복잡한 정보)

**파이프라인 구조**:
```
1. 벡터 DB 구축 (medical_2.csv → ChromaDB)
2. 검색 쿼리 생성 (n_rag_query_sanitize)
3. 벡터 DB 검색 (n_rag_search)
4. 가이드라인 변환 (n_rag_to_guidelines)
```

**출력 예시**:
```
[STEP 2.1] 검색 쿼리 생성
진단명: 당뇨병
검색 쿼리: 당뇨병 관리 방법

[STEP 2.2] 벡터 DB 검색 실행
검색 결과 길이: 1245 문자
검색 결과 미리보기:
질환명: 당뇨병
[생활가이드]
규칙적인 식사와 운동이 중요합니다...

[STEP 2.3] 가이드라인 변환 (LLM)
[최종 가이드라인]
[
  {
    "category": "diet",
    "text": "단순당을 피하고 복합 탄수화물을 섭취하세요",
    "source": "rag"
  },
  ...
]
```

## 🔍 테스트 출력 구조

각 테스트는 다음 정보를 출력합니다:

```
[입력]
- 노드에 전달된 상태(state) 정보

[출력]
- 노드 실행 후 반환된 결과

[에러/경고]
- Errors: 발생한 에러 개수 및 상세 정보
- Warnings: 사용자에게 전달되는 경고 메시지
```

## 🛠️ 커스텀 테스트 실행 방법

### 방법 1: 특정 케이스만 선택해서 실행 (주석 처리)

테스트 파일을 열어서 원하지 않는 케이스를 주석 처리합니다.

**예시: test_extract_clinical.py**

```python
def test_extract_clinical():
    # ... 초기화 코드 ...

    # 테스트 케이스 1만 실행
    print("\n[테스트 케이스 1] 정상적인 진료 기록 - 당뇨병 진단")
    # ... 케이스 1 코드 ...

    # 케이스 2, 3은 주석 처리 (실행 안 함)
    # print("\n\n[테스트 케이스 2] 진단명 없는 일반 상담")
    # sample_state2: WFState = { ... }
    # result2 = n_extract_clinical(sample_state2, llm)
    # ...

    # print("\n\n[테스트 케이스 3] 복잡한 진료")
    # sample_state3: WFState = { ... }
    # result3 = n_extract_clinical(sample_state3, llm)
    # ...
```

### 방법 2: 나만의 입력 데이터로 테스트

테스트 파일의 `sample_state` 변수를 직접 수정합니다.

**예시 1: test_extract_clinical.py - 진료 기록 수정**

```python
# 원본 케이스 1
sample_state1: WFState = {
    "patient_id": "test_p1",
    "visit_id": "test_v1",
    "doctor_text": """
안녕하세요 환자분. 오늘 검사 결과를 보니 혈당이 많이 높습니다.
당뇨병으로 진단됩니다. 앞으로 식이요법과 운동이 매우 중요합니다.
    """.strip(),
    "errors": [],
    "warnings": [],
}

# 나만의 진료 기록으로 변경
sample_state1: WFState = {
    "patient_id": "my_patient",
    "visit_id": "my_visit",
    "doctor_text": """
여기에 테스트하고 싶은
진료 기록을 자유롭게 입력하세요.
예: 복통이 심하시네요. 위염으로 보입니다.
    """.strip(),
    "errors": [],
    "warnings": [],
}
```

**예시 2: test_rag_integration.py - 질병명 변경**

```python
# 원본
sample_state1: WFState = {
    "patient_id": "test_p1",
    "visit_id": "test_v1",
    "diagnosis_key": "당뇨병",
    "errors": [],
    "warnings": [],
}

# 다른 질병으로 변경
sample_state1: WFState = {
    "patient_id": "test_p1",
    "visit_id": "test_v1",
    "diagnosis_key": "간염",  # 원하는 질병명으로 변경
    "errors": [],
    "warnings": [],
}
```

**예시 3: test_rag_to_guidelines.py - RAG 결과 수정**

```python
# 나만의 RAG 검색 결과 테스트
sample_state1: WFState = {
    "patient_id": "test_p1",
    "visit_id": "test_v1",
    "diagnosis_key": "천식",
    "rag_raw": {
        "results": [
            {
                "content": "천식 환자는 먼지와 알레르기 유발 물질을 피해야 합니다.",
                "metadata": {"source": "서울대병원"}
            },
            {
                "content": "흡입기를 항상 휴대하고, 발작 시 즉시 사용하세요.",
                "metadata": {"source": "서울대병원"}
            }
        ]
    },
    "errors": [],
    "warnings": [],
}
```

### 방법 3: 커스텀 케이스 추가

기존 테스트 케이스 뒤에 새로운 케이스를 추가합니다.

**예시: test_detect_closure.py에 케이스 추가**

```python
def test_detect_closure():
    # ... 기존 케이스 1, 2, 3, 4 ...

    # 내가 추가한 커스텀 케이스
    print("\n\n[커스텀 케이스] 나만의 치료 종료 시나리오")
    print("-" * 70)

    my_custom_state: WFState = {
        "patient_id": "custom_p",
        "visit_id": "custom_v",
        "diagnosis_key": "무좀",
        "doctor_text": """
무좀이 완전히 나았습니다.
더 이상 약을 바르지 않으셔도 됩니다.
치료를 종료하겠습니다.
        """.strip(),
        "errors": [],
        "warnings": [],
    }

    result = n_detect_closure(my_custom_state, llm)
    print(f"\n[출력] should_close: {result.get('should_close')}")

    print("\n" + "=" * 70)
    print("커스텀 테스트 완료")
    print("=" * 70)
```

### 방법 4: 파일 복사해서 독립 실행

테스트 파일을 복사해서 나만의 버전을 만듭니다.

```bash
# 파일 복사
cp tests/test_extract_clinical.py tests/my_test_extract.py

# 내 파일 수정
# tests/my_test_extract.py 열어서 원하는 대로 수정

# 실행
python tests/my_test_extract.py
```

### 실전 예시

#### 📌 시나리오 1: API 비용 절약 - 케이스 1개만 실행

```python
# test_rag_integration.py 수정
def test_rag_integration():
    # ... 벡터 DB 구축 코드는 그대로 ...

    # 케이스 1만 실행
    print("\n\n" + "=" * 70)
    print("[테스트 케이스 1] 당뇨병 RAG 파이프라인")
    print("=" * 70)
    # ... 케이스 1 코드 ...

    # 케이스 2~5 모두 주석 처리
    # print("\n\n" + "=" * 70)
    # print("[테스트 케이스 2] 고혈압 RAG 파이프라인")
    # ...
```

#### 📌 시나리오 2: 특정 질병 집중 테스트

```python
# test_rag_integration.py에서 모든 케이스를 "고혈압"으로 변경
sample_state1["diagnosis_key"] = "고혈압"
sample_state2["diagnosis_key"] = "고혈압"
sample_state3["diagnosis_key"] = "고혈압"
# ...
```

#### 📌 시나리오 3: 빠른 디버깅

```python
# 테스트 중간에 디버깅 코드 추가
result1 = n_extract_clinical(sample_state1, llm)

# 디버깅 출력
print("=" * 50)
print("DEBUG INFO")
print("=" * 50)
print(f"Input length: {len(sample_state1['doctor_text'])}")
print(f"Diagnoses count: {len(result1.get('extracted', {}).get('diagnoses', []))}")
print(f"Guidelines count: {len(result1.get('extracted', {}).get('doctor_guidelines', []))}")
print(f"Has errors: {len(result1.get('errors', [])) > 0}")
print("=" * 50)

# 기존 출력
print("\n[출력]")
print(json.dumps(result1.get("extracted"), ensure_ascii=False, indent=2))
```

## 💡 추천 사용 시나리오

| 상황 | 추천 방법 | 예시 |
|:--|:--|:--|
| 특정 케이스만 빠르게 확인 | 방법 1 (주석 처리) | 케이스 1만 남기고 나머지 주석 |
| 새로운 진료 기록 테스트 | 방법 2 (데이터 수정) | doctor_text 내용 변경 |
| 다양한 질병 테스트 | 방법 2 (데이터 수정) | diagnosis_key 변경 |
| 반복 테스트 | 방법 3 (케이스 추가) | 기존 코드 유지하며 추가 |
| 독립적인 실험 | 방법 4 (파일 복사) | 원본 보존하며 자유롭게 수정 |

## 📝 주의사항

1. **API 키 필요**: 모든 테스트는 Upstage API를 호출하므로 API 키가 필요합니다.
2. **LLM 비용**: 각 테스트는 실제 LLM API를 호출하므로 비용이 발생합니다.
   - 💡 **비용 절약 팁**: 불필요한 케이스는 주석 처리하세요!
3. **결과 변동성**: temperature=0.1이지만 LLM 결과는 실행마다 약간 다를 수 있습니다.
4. **에러 핸들링**: 모든 노드는 `safe_llm_invoke`로 보호되어 있어, API 실패 시에도 fallback 값을 반환합니다.
5. **RAG 통합 테스트 시간**: `test_rag_integration.py`는 벡터 DB를 구축하므로 최초 실행 시 1-2분 정도 소요됩니다.
6. **파일 수정 시 백업**: 테스트 파일을 수정하기 전에 원본을 복사해두는 것을 권장합니다.

## 🔗 관련 파일

- **노드 구현**: `src/medical_workflow/nodes/`
  - `extraction.py` - 임상 정보 추출
  - `thread.py` - 스레드 관리 및 종료 감지
  - `guidelines.py` - 가이드라인 요약
  - `search.py` - RAG 검색 파이프라인
  - `memory.py` - 메모리 및 리플렉션
  - `rag.py` - RAG 벡터 DB 구축 및 검색

- **에러 핸들링**: `src/medical_workflow/utils/llm.py`
  - `safe_llm_invoke()` 함수

- **상태 정의**: `src/medical_workflow/state.py`
  - `WFState` TypedDict

- **의료 데이터**: `data/medical_2.csv`
  - 서울대병원 의학정보 (RAG용)
