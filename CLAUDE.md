# Medical Workflow

## 개요

환자의 헬스 리터러시 향상을 위한 Agent 기반 진료 관리 서비스.
진료 녹음 텍스트를 입력받아 임상 정보를 추출하고, 질병별 스레드로 누적 관리하며, 생활습관 알람을 생성한다.

## 프로젝트 구조

```
main.py                              # 엔트리포인트 (thin wrapper)
src/medical_workflow/
├── __init__.py
├── config.py                        # 환경 변수, LLM/Tavily 초기화
├── state.py                         # WFState TypedDict
├── stores.py                        # THREAD_STORE, VISIT_STORE, 헬퍼
├── graph.py                         # build_graph()
├── runner.py                        # run_many(), main()
└── nodes/
    ├── __init__.py
    ├── input.py                     # 메타 파싱, 개인정보 비식별화
    ├── extraction.py                # LLM 임상정보 추출, 진단 판단
    ├── thread.py                    # 스레드 CRUD, 종료 감지
    ├── memory.py                    # 메모리 조회, 리플렉션
    ├── guidelines.py                # 가이드라인 유무 판단, 요약, 안전성
    ├── search.py                    # Tavily 검색 파이프라인
    ├── planning.py                  # 액션 계획, HITL 동의
    ├── alarm.py                     # 알람 계획 생성
    └── finalize.py                  # 메모리/이벤트 저장, 최종 응답
data/medical_2.csv                   # 서울대병원 의학정보 (병명, 생활가이드, 식이요법)
notebooks/practice_rag.ipynb         # ChromaDB RAG 프로토타입 (main.py와 별도 동작)
tests/                               # 테스트 (향후 추가)
docs/                                # 기획서, 멘토링 리뷰, 아키텍처 다이어그램
```

## 기술 스택

| 구성 | 기술 | 비고 |
|:--|:--|:--|
| LLM | Solar pro2 (Upstage API) | temperature=0.1 |
| 임베딩 | solar-embedding-1-large (Upstage) | 노트북에서만 사용 |
| 오케스트레이션 | LangGraph StateGraph | Workflow 방식 |
| 외부 검색 | Tavily (nodes/search.py) | 의사 가이드라인 없을 때 보조 |
| 벡터DB | ChromaDB (노트북) | medical_2.csv 기반 RAG |
| 저장소 | In-memory dict | THREAD_STORE, VISIT_STORE |
| 패키지 관리 | uv + pyproject.toml | Python >=3.10 |
| 트레이싱 | LangSmith | 선택사항 |

## 워크플로우

### 파이프라인 흐름

```
Recording_*.txt 입력
  → 메타 파싱 (날짜, 환자ID)
  → 개인정보 비식별화 (이메일/전화/주민번호/주소 마스킹)
  → LLM 임상 정보 추출 (진단명, 가이드라인)
  → 진단 여부 분기
      ├─ 없음 → 종료
      └─ 있음 → 스레드 관리 (신규 생성 | 기존 로드)
          → 메모리 조회 (최근 8개 memory + 3개 event)
          → LLM 종료 감지 (치료 완료?)
              ├─ 종료 → 스레드 닫기 → 종료
              └─ 계속 → 가이드라인 분기
                  ├─ 의사 가이드라인 있음 → LLM 요약
                  └─ 없음 → Tavily 검색 → LLM 가이드라인 변환
              → 안전성 체크
              → Reflection (3회마다 or 가이드라인 5개 이상)
              → 계획 수립
                  ├─ HITL: 알람 동의 질문
                  ├─ 알람 생성: 카테고리별 시간표
                  └─ 종료
```

### 노드 (23개 그래프 노드)

LLM을 사용하는 노드: `extract_clinical`, `detect_closure`, `summarize_guidelines`, `tavily_to_guidelines`, `reflect_patient_state` (5개)

### 조건부 분기 (7개)

| 분기점 | 조건 | 경로 |
|:--|:--|:--|
| has_diag | 진단 존재 여부 | → 스레드관리 or 종료 |
| is_existing | 기존 스레드 여부 | → 로드 or 생성 |
| detect_closure | 치료 완료 여부 | → 닫기 or 계속 |
| has_guideline | 의사 가이드라인 여부 | → 요약 or Tavily |
| should_reflect | 반성 트리거 | → Reflection or 스킵 |
| plan_next_actions | 3가지 경로 | → HITL / 알람 / 종료 |
| hitl_alarm_opt_in | 환자 동의 여부 | → 알람생성 or 종료 |

## 구현 현황

| 항목 | 상태 | 비고 |
|:--|:--|:--|
| 진료 기록 자동화 | 완료 | src/medical_workflow/ |
| 생활습관 알람 | 완료 | nodes/alarm.py |
| 개인정보 비식별화 | 완료 | 정규식 기반 마스킹 |
| Memory & Reflection | 완료 | 3회마다 환자 상태 요약 |
| HITL 알람 동의 | 완료 | 환자 동의 후 알람 생성 |
| 스레드 종료 감지 | 완료 | LLM 판단 |
| RAG 프로토타입 | 완료 | notebooks/practice_rag.ipynb (별도 동작) |
| STT (Whisper/Daglo) | 미구현 | 텍스트 입력으로 대체 |
| RAG 통합 | 미구현 | 노트북에서만 별도 동작 |
| 환자용 DB (PostgreSQL) | 미구현 | In-memory dict 사용 |
| 임상 기록 문서화 | 미구현 | 의료진 공유용 보고서 |
| 환자 Q&A | 미구현 | |
| 체크리스트 추적 | 미구현 | 알람 계획 생성만 가능 |

## 환경 변수 및 실행

README.md 참조
