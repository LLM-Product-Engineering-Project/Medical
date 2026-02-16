"""의료 진료 전사 분석 워크플로우 - 엔트리포인트"""

import sys
import os

# src 디렉토리를 모듈 검색 경로에 추가
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from dotenv import load_dotenv
load_dotenv()

print("UPSTAGE_API_KEY loaded:", bool(os.getenv("UPSTAGE_API_KEY")))
print("UPSTAGE_API_KEY head:", (os.getenv("UPSTAGE_API_KEY") or "")[:6])

from medical_workflow.runner import main

if __name__ == "__main__":
    main()
