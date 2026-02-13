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

### 3. 환경 변수 설정

`.env` 파일을 편집하여 API 키를 입력:

```
UPSTAGE_API_KEY=your_key_here       # 필수 - Solar pro2 LLM
TAVILY_API_KEY=your_key_here        # 필수 - 웹 검색
LANGSMITH_API_KEY=your_key_here     # 선택 - 트레이싱
```

## 실행

`Recording_YYYYMMDD.txt` 형식의 진료 전사 텍스트 파일을 프로젝트 루트에 배치 후 실행:

```
Medical/
├── Recording_20240101.txt
├── Recording_20240102.txt
├── main.py                         # 엔트리포인트 (thin wrapper)
└── src/medical_workflow/           # 핵심 로직
    ├── runner.py                   # 멀티 파일 러너
    ├── graph.py                    # LangGraph 워크플로우
    ├── state.py                    # 상태 정의
    ├── config.py                   # 환경 변수 로드
    ├── stores.py                   # In-memory 저장소
    └── nodes/                      # 그래프 노드들
```

```bash
# 가상환경 활성화 후
source .venv/bin/activate
python main.py

# 또는 uv로 직접 실행
uv run python main.py
```

## 주요 기능

1. **개인정보 비식별화** - 이메일, 전화번호, 주민등록번호, 주소 자동 마스킹
2. **임상 정보 추출** - LLM 기반 진단명, 치료 가이드라인 추출
3. **스레드 관리** - 질병별 진료 기록 연속성 유지
4. **Memory & Reflection** - 누적 기록 기반 환자 상태 요약
5. **외부 검색** - Tavily를 통한 질병 관리 가이드라인 보완
6. **HITL 알람** - 환자 동의 후 생활습관 알람 일정표 생성

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

## 문제 해결

| 증상 | 원인 | 해결 |
|:--|:--|:--|
| `환경 변수가 설정되지 않았습니다` | API 키 미설정 | `.env` 파일에 키 입력 |
| `Recording_*.txt 파일을 찾을 수 없습니다` | 입력 파일 없음 | 프로젝트 루트에 파일 배치 |
| `uv: command not found` | uv 미설치 | `pip install uv` 또는 `brew install uv` |
| 패키지 설치 오류 | 가상환경 문제 | `rm -rf .venv && uv sync` |
