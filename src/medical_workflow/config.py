"""환경 변수 및 외부 서비스 초기화"""

import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


def load_env_keys():
    """환경 변수에서 API 키 로드"""
    required_keys = [
        "LANGSMITH_API_KEY",
        "UPSTAGE_API_KEY",
    ]

    missing_keys = []
    for key in required_keys:
        if not os.environ.get(key):
            missing_keys.append(key)

    if missing_keys:
        print(f"경고: 다음 환경 변수가 설정되지 않았습니다: {', '.join(missing_keys)}")
        print("실행하려면 다음 환경 변수를 설정하세요:")
        for key in missing_keys:
            print(f"  export {key}='your_key_here'")

    # LangSmith 설정
    os.environ.setdefault("LANGSMITH_TRACING_V2", "true")
    os.environ.setdefault("LANGSMITH_ENDPOINT", "https://api.smith.langchain.com")
    os.environ.setdefault("LANGSMITH_PROJECT", "agentic-workflow")
