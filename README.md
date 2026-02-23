# Medical Workflow

환자의 헬스 리터러시 향상을 위한 Agent 기반 진료 관리 서비스 - 진료 녹음 텍스트를 분석하여 질병별 기록을 누적 관리하고 생활습관 알람을 생성합니다.

> 아키텍처, 워크플로우 상세, 구현 현황은 [CLAUDE.md](CLAUDE.md) 참조

## 설치

### 1. uv 설치

```bash
# macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# 또는 Homebrew (macOS)
brew install uv
```

### 2. 프로젝트 설정

```bash
uv sync
```

> **참고**: `uv sync`는 자동으로 `.venv` 가상환경을 생성하고 모든 의존성을 설치합니다.

### 3. 환경 변수 설정

`.env` 파일을 편집하여 API 키를 입력:

```
UPSTAGE_API_KEY=your_key_here       # 필수 - Solar pro2 LLM, 임베딩
LANGSMITH_API_KEY=your_key_here     # 선택 - 트레이싱
```

> **참고**: Tavily API는 더 이상 사용하지 않습니다. ChromaDB 기반 RAG로 대체되었습니다.

## 실행

`Recording_YYYYMMDD.txt` 형식의 진료 전사 텍스트 파일을 `data/recordings/`에 배치 후 실행:

```
Medical/
├── main.py                         # 엔트리포인트 (thin wrapper)
├── data/
│   ├── recordings/
│   │   └── Recording_YYYYMMDD.txt  # 진료 전사 텍스트 (txt 모드 입력)
│   ├── medical_2.csv               # 서울대병원 의학정보
│   ├── testcase(50).xlsx           # 테스트 케이스 (환자별 케이스)
│   └── chroma_db/                  # ChromaDB 영속 저장 (자동 생성)
└── src/medical_workflow/           # 핵심 로직
    ├── runner.py                   # run_many(), run_from_xlsx(), main()
    ├── graph.py                    # LangGraph 워크플로우
    ├── state.py                    # 상태 정의
    ├── config.py                   # 환경 변수 로드
    ├── pii_middleware.py           # PII 미들웨어 (한국 이름 비식별화)
    ├── stores.py                   # 하위 호환 래퍼
    ├── utils/                      # 유틸리티 패키지
    │   ├── llm.py                  # safe_llm_invoke
    │   ├── parsing.py              # parse_json_safely
    │   └── helpers.py              # thread_key, now_iso, symptom_thread_key
    ├── stores/                     # 저장소 패키지
    │   ├── thread.py               # THREAD_STORE 관리
    │   └── visit.py                # VISIT_STORE 관리
    └── nodes/                      # 그래프 노드들 (24개)
        ├── input.py                # 메타 파싱
        ├── extraction.py           # 임상 정보 추출
        ├── thread.py               # 스레드 관리, 증상→진단 승격
        ├── memory.py               # 메모리 조회, 리플렉션
        ├── guidelines.py           # 가이드라인 처리
        ├── rag.py                  # ChromaDB 벡터 DB 구축 및 검색
        ├── search.py               # RAG 파이프라인 (쿼리 정제, 보완)
        ├── planning.py             # 액션 계획
        ├── alarm.py                # 알람 생성
        └── finalize.py             # 최종 응답
```

```bash
# ── txt 모드: data/recordings/ 디렉토리의 Recording_*.txt 파일 처리 ──
uv run python main.py

# ── xlsx 모드: testcase(50).xlsx에서 특정 환자 케이스 처리 ──
uv run python main.py p01          # p01 환자의 모든 케이스 처리
uv run python main.py p12          # p12 환자의 케이스 처리

# ── 옵션 ──
uv run python main.py --reset_stores           # 스토어 초기화 후 실행 (txt 모드)
uv run python main.py p01 --reset_stores       # 스토어 초기화 후 xlsx 모드
uv run python main.py --xlsx data/testcase(50).xlsx p01  # xlsx 경로 직접 지정

# 가상환경 활성화 후 실행 (대안)
# Windows
.venv\Scripts\activate
python main.py p01
```

## 주요 기능

1. **개인정보 비식별화** - 한국 이름 탐지·마스킹 (`pii_middleware.py`, 그래프 실행 전 처리)
2. **임상 정보 추출** - LLM 기반 진단명, 증상, 치료 가이드라인 추출 (에러 핸들링 적용)
3. **스레드 관리** - 질병별 진료 기록 연속성 유지 (LLM 4단계 매칭: 동명이진·표현차이·증상→진단 승격)
4. **증상 임시 스레드** - 진단 없이 증상만 있을 때 스레드 생성, 진단 확정 시 자동 승격
5. **Memory & Reflection** - 누적 기록 기반 환자 상태 요약
6. **RAG 검색** - ChromaDB + 서울대병원 의학정보 (medical_2.csv) 기반 가이드라인 제공 (보완 포함)
7. **HITL 알람** - 환자 동의 후 생활습관 알람 일정표 생성
8. **에러 핸들링** - LLM 노드 실패 시 안전한 fallback 및 명시적 경고

## 에러 핸들링

워크플로우는 LLM 호출 실패 시에도 안전하게 동작합니다:

- **자동 복구**: 개별 노드 실패 시 보수적 기본값 사용
- **투명성**: `final_answer`에 에러/경고 정보 포함
- **의료 안전**: 중요 정보 부족 시 명시적 경고 표시

```python
# 최종 응답 예시
{
    "diagnosis_key": "고혈압",
    "guidelines": [...],
    "has_errors": True,
    "has_critical_errors": False,
    "data_completeness": "complete",
    "warnings": ["ℹ️ 치료 종료 여부를 판단할 수 없어 진료를 계속합니다."]
}
```

## 커스터마이징

```python
from medical_workflow.runner import run_many

# 입력 디렉토리 변경
run_many("/path/to/recordings", reset_stores=False)

# 환자 ID 변경
run_many("/path/to/recordings", default_patient_id="patient_123")

# 스토어 초기화 (처음부터 새로 시작)
run_many("/path/to/recordings", reset_stores=True)
```

```python
from medical_workflow.runner import run_from_xlsx

# xlsx 모드: 특정 환자 케이스 처리
run_from_xlsx("p01", xlsx_path="data/testcase(50).xlsx")
run_from_xlsx("p01", xlsx_path="data/testcase(50).xlsx", reset_stores=True)
```

## 문제 해결

| 증상 | 원인 | 해결 |
|:--|:--|:--|
| `환경 변수가 설정되지 않았습니다` | UPSTAGE_API_KEY 미설정 | `.env` 파일에 키 입력 |
| `Recording_*.txt 파일을 찾을 수 없습니다` | 입력 파일 없음 | 프로젝트 루트에 파일 배치 |
| `uv: command not found` | uv 미설치 | `pip install uv` 또는 `brew install uv` |
| 패키지 설치 오류 | 가상환경 문제 | `rm -rf .venv && uv sync` |
| `final_answer`에 에러 포함 | LLM 호출 일부 실패 | 정상 동작 (fallback 사용), 로그 확인 |
| ChromaDB 초기화 오류 | medical_2.csv 파일 없음 | data/ 디렉토리에 CSV 파일 확인 |

## 프로젝트 구조 개선사항

### 최근 리팩토링 (2026-02)

**Phase 1-3 완료: 모듈화 및 표준화**

1. **유틸리티 분리** (`src/medical_workflow/utils/`)
   - `llm.py`: 안전한 LLM 호출 (`safe_llm_invoke`)
   - `parsing.py`: JSON 파싱 유틸리티
   - `helpers.py`: 공통 헬퍼 함수

2. **저장소 분리** (`src/medical_workflow/stores/`)
   - `thread.py`: 스레드 저장소 관리
   - `visit.py`: 방문 기록 저장소 관리
   - `stores.py`: 하위 호환성 유지 래퍼

3. **환경 표준화**
   - ✅ `.venv` 표준 가상환경 사용 (Python 3.12)
   - ✅ `uv` 단일 패키지 관리자
   - ✅ `pyproject.toml` 기반 의존성 관리

4. **정리된 파일**
   - ❌ `requirements.txt`, `requirements-dev.txt` (중복 제거)
   - ❌ `.python-version` (pyproject.toml로 통일)
   - ❌ `notebooks/` (docs/archived/로 이동)

**Phase 4: 버그 수정 및 안정화 (2026-02)**

5. **주요 버그 수정**

   | 버그 | 파일 | 수정 내용 |
   |:--|:--|:--|
   | JSON 유효성 검사 오판 | `utils/llm.py` | `{"should_close": false}` 등 falsy 값을 빈 응답으로 오인 → `not any(parsed.values())` 조건 제거 |
   | alarm_opt_in 덮어쓰기 | `nodes/thread.py` | `n_load_thread`가 state의 `alarm_opt_in=True`를 THREAD_STORE의 `None`으로 덮어쓰는 문제 수정 |
   | 이벤트/메모리 중복 적재 | `nodes/finalize.py` | 2차 `graph.invoke` 시 동일 visit_id 이벤트·메모리 중복 저장 방지 |
   | VISIT_STORE 중복 기록 | `nodes/alarm.py` | `upsert_visit_record` 이중 호출 제거 |
   | 그래프 중복 엣지 | `graph.py` | `add_edge("finalize", END)` 중복 등록 제거 |
   | patient_id 하드코딩 | `nodes/input.py` | `"p1"` 고정값 → 미설정 시에만 기본값 적용 |

6. **Safety Guardrail idempotency**
   - `state.py`에 `safety_checked: bool` 필드 추가
   - 2차 `graph.invoke` 재진입 시 `safety_guardrail` 중복 실행 방지
   - `decision_log` 항상 4개만 기록 (누적 없음)

7. **xlsx 입력 모드 추가**
   - `runner.py`에 `run_from_xlsx()` 함수 추가
   - `uv run python main.py {patient_id}` 형식으로 testcase xlsx 처리
