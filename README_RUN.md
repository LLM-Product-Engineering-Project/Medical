# 의료 진료 전사 분석 워크플로우 실행 가이드

## 설치 방법 (uv 사용)

### 1. uv 설치

```bash
# macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# 또는 Homebrew
brew install uv
```

### 2. 가상환경 생성 및 패키지 설치

```bash
# 가상환경 생성
uv venv

# 가상환경 활성화
source .venv/bin/activate  # macOS/Linux
# 또는
.venv\Scripts\activate  # Windows

# 패키지 설치
uv pip sync pyproject.toml
# 또는
uv pip install -e .
```

### 3. 환경 변수 설정

`.env.example` 파일을 `.env`로 복사하고 API 키를 입력하세요:

```bash
cp .env.example .env
```

`.env` 파일을 편집하여 다음 API 키를 설정하세요:
- `UPSTAGE_API_KEY`: Upstage AI API 키 (필수)
- `TAVILY_API_KEY`: Tavily Search API 키 (필수)
- `LANGSMITH_API_KEY`: LangSmith API 키 (선택사항, 트레이싱용)

## 실행 방법

### 입력 파일 준비

`Recording_YYYYMMDD.txt` 형식의 파일을 `main.py`와 같은 디렉토리에 배치하세요.

예시:
- `Recording_20240101.txt`
- `Recording_20240102.txt`

### 실행

```bash
# 가상환경이 활성화된 상태에서
python main.py

# 또는 uv를 사용하여 직접 실행
uv run python main.py
```

## 주요 기능

1. **개인정보 비식별화**: 이메일, 전화번호, 주민등록번호, 주소 자동 마스킹
2. **임상 정보 추출**: 진단명, 치료 가이드라인 추출
3. **스레드 관리**: 질병별 진료 기록 연속성 유지
4. **메모리 & 리플렉션**: 누적 진료 기록 기반 환자 상태 요약
5. **RAG 검색**: Tavily를 통한 질병 관리 가이드라인 검색
6. **알람 생성**: 환자 동의 시 생활습관 알람 및 일정표 생성

## 출력

각 방문 기록마다 다음 정보가 출력됩니다:
- 진단 정보
- 치료 가이드라인
- 스레드 상태
- 환자 상태 리플렉션 (조건부)
- 알람 계획 (환자 동의 시)

## 문제 해결

### API 키 오류
```
경고: 다음 환경 변수가 설정되지 않았습니다: UPSTAGE_API_KEY, TAVILY_API_KEY
```
→ 환경 변수가 올바르게 설정되었는지 확인하세요.

### 파일 없음 오류
```
Recording_*.txt 파일을 찾을 수 없습니다
```
→ 입력 파일이 올바른 디렉토리에 있고 파일명 형식이 맞는지 확인하세요.

## 커스터마이징

### 입력 디렉토리 변경

`main()` 함수에서 `input_dir`를 수정:

```python
def main():
    load_env_keys()
    input_dir = "/path/to/your/recordings"  # 원하는 경로로 변경
    run_many(input_dir, reset_stores=False)
```

### 환자 ID 변경

`run_many()` 함수 호출 시 `default_patient_id` 파라미터 변경:

```python
run_many(input_dir, default_patient_id="patient_123", reset_stores=False)
```

### 스토어 초기화

처음부터 새로 시작하려면 `reset_stores=True` 설정:

```python
run_many(input_dir, reset_stores=True)
```
