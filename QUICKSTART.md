# 빠른 시작 가이드 (uv 사용)

## 1단계: uv 설치

```bash
# macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# 또는 Homebrew (macOS)
brew install uv
```

## 2단계: 프로젝트 설정

```bash
# 프로젝트 디렉토리로 이동
cd /Users/yebin/Desktop/medical

# 가상환경 생성 및 패키지 설치 (한 번에)
uv sync

# 또는 단계별로
uv venv                    # 가상환경 생성
source .venv/bin/activate  # 가상환경 활성화
uv pip install -e .        # 패키지 설치
```

## 3단계: 환경 변수 설정

```bash
# .env 파일 생성
cp .env.example .env

# .env 파일을 편집하여 API 키 입력
# UPSTAGE_API_KEY=your_key_here
# TAVILY_API_KEY=your_key_here
# LANGSMITH_API_KEY=your_key_here (선택사항)
```

또는 직접 export:

```bash
export UPSTAGE_API_KEY='your_upstage_api_key'
export TAVILY_API_KEY='your_tavily_api_key'
export LANGSMITH_API_KEY='your_langsmith_api_key'
```

## 4단계: 입력 파일 준비

`Recording_YYYYMMDD.txt` 형식의 파일을 프로젝트 디렉토리에 배치:

```
medical/
├── Recording_20240101.txt
├── Recording_20240102.txt
└── main.py
```

## 5단계: 실행

```bash
# 방법 1: 가상환경 활성화 후 실행
source .venv/bin/activate
python main.py

# 방법 2: uv run으로 직접 실행 (가상환경 자동 활성화)
uv run python main.py
```

## 추가 명령어

```bash
# 새 패키지 추가
uv pip install package_name

# 패키지 목록 확인
uv pip list

# 가상환경 비활성화
deactivate

# 가상환경 삭제 (재설정이 필요한 경우)
rm -rf .venv
uv venv
```

## 문제 해결

### uv가 설치되지 않는 경우
```bash
# Python을 통한 설치
pip install uv
```

### 가상환경 활성화가 안 되는 경우
```bash
# zsh (macOS 기본 쉘)
source .venv/bin/activate

# bash
source .venv/bin/activate

# fish
source .venv/bin/activate.fish
```

### 패키지 설치 오류
```bash
# 캐시 삭제 후 재설치
rm -rf .venv
uv venv
uv pip install -e .
```

## uv의 장점

- ⚡️ **빠른 속도**: pip보다 10-100배 빠른 패키지 설치
- 🔒 **의존성 잠금**: 재현 가능한 환경 보장
- 🎯 **간단한 사용**: 단일 명령어로 환경 구성
- 🚀 **최신 기능**: 최신 Python 패키징 표준 지원
