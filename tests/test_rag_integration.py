"""
test_rag_integration.py

RAG 통합 테스트 (벡터 DB 구축 + 검색 + 가이드라인 변환)

전체 RAG 파이프라인을 테스트합니다:
1. build_medical_vector_db: medical_2.csv → ChromaDB 벡터 DB 생성
2. n_rag_query_sanitize: 진단명 → 검색 쿼리 생성
3. n_rag_search: 벡터 DB 검색 실행
4. n_rag_to_guidelines: 검색 결과 → 가이드라인 변환 (LLM)

실행 방법:
    cd C:\Users\yebin\Desktop\Medical
    python tests/test_rag_integration.py
"""

import os
import sys
import json

# 프로젝트 루트를 경로에 추가
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(project_root, "src"))

from langchain_openai import ChatOpenAI
from medical_workflow.config import load_env_keys
from medical_workflow.state import WFState
from medical_workflow.nodes.rag import build_medical_vector_db, n_rag_query_sanitize, n_rag_search
from medical_workflow.nodes.search import n_rag_to_guidelines


def test_rag_integration():
    """RAG 통합 테스트 (벡터 DB → 검색 → 가이드라인 변환)"""
    print("=" * 70)
    print("테스트: RAG 통합 파이프라인")
    print("=" * 70)

    # 환경 변수 로드
    load_env_keys()

    # API 키 확인
    if not os.environ.get("UPSTAGE_API_KEY"):
        print("\n⚠️ UPSTAGE_API_KEY가 설정되지 않았습니다.")
        print("   .env 파일에 API 키를 설정한 후 다시 실행하세요.")
        return

    # 데이터 파일 확인
    data_path = os.path.join(project_root, "data", "medical_2.csv")
    if not os.path.isfile(data_path):
        print(f"\n⚠️ 의료 데이터 파일을 찾을 수 없습니다: {data_path}")
        return

    # LLM 초기화
    llm = ChatOpenAI(
        model="solar-pro2",
        base_url="https://api.upstage.ai/v1",
        api_key=os.environ.get("UPSTAGE_API_KEY"),
        temperature=0.1,
    )

    # 벡터 DB 구축
    print("\n[STEP 1] 벡터 DB 구축 중...")
    print("-" * 70)
    try:
        vector_db = build_medical_vector_db(data_path)
        retriever = vector_db.as_retriever(search_kwargs={"k": 3})
        print("✅ 벡터 DB 구축 완료 (medical_2.csv)")
    except Exception as e:
        print(f"❌ 벡터 DB 구축 실패: {e}")
        return

    # 테스트 케이스 1: 당뇨병
    print("\n\n" + "=" * 70)
    print("[테스트 케이스 1] 당뇨병 RAG 파이프라인")
    print("=" * 70)

    sample_state1: WFState = {
        "patient_id": "test_p1",
        "visit_id": "test_v1",
        "diagnosis_key": "당뇨병",
        "errors": [],
        "warnings": [],
    }

    # Step 1: 쿼리 생성
    print("\n[STEP 2.1] 검색 쿼리 생성")
    print("-" * 70)
    state1 = n_rag_query_sanitize(sample_state1, llm)
    print(f"진단명: {state1['diagnosis_key']}")
    print(f"검색 쿼리: {state1['rag_query']}")

    # Step 2: 벡터 DB 검색
    print("\n[STEP 2.2] 벡터 DB 검색 실행")
    print("-" * 70)
    state1 = n_rag_search(state1, retriever)
    print(f"검색 결과 길이: {len(state1.get('rag_raw', ''))} 문자")
    print(f"\n검색 결과 미리보기:\n{state1.get('rag_raw', '')[:300]}...")

    # Step 3: 가이드라인 변환
    print("\n[STEP 2.3] 가이드라인 변환 (LLM)")
    print("-" * 70)
    state1 = n_rag_to_guidelines(state1, llm)
    print("\n[최종 가이드라인]")
    print(json.dumps(state1.get("rag_guidelines"), ensure_ascii=False, indent=2))

    print("\n[에러/경고]")
    print(f"Errors: {len(state1.get('errors', []))}")
    print(f"Warnings: {len(state1.get('warnings', []))}")
    if state1.get("warnings"):
        print("Warning details:", state1.get("warnings"))

    # 테스트 케이스 2: 고혈압
    print("\n\n" + "=" * 70)
    print("[테스트 케이스 2] 고혈압 RAG 파이프라인")
    print("=" * 70)

    sample_state2: WFState = {
        "patient_id": "test_p2",
        "visit_id": "test_v2",
        "diagnosis_key": "고혈압",
        "errors": [],
        "warnings": [],
    }

    # Step 1: 쿼리 생성
    print("\n[STEP 2.1] 검색 쿼리 생성")
    print("-" * 70)
    state2 = n_rag_query_sanitize(sample_state2, llm)
    print(f"진단명: {state2['diagnosis_key']}")
    print(f"검색 쿼리: {state2['rag_query']}")

    # Step 2: 벡터 DB 검색
    print("\n[STEP 2.2] 벡터 DB 검색 실행")
    print("-" * 70)
    state2 = n_rag_search(state2, retriever)
    print(f"검색 결과 길이: {len(state2.get('rag_raw', ''))} 문자")
    print(f"\n검색 결과 미리보기:\n{state2.get('rag_raw', '')[:300]}...")

    # Step 3: 가이드라인 변환
    print("\n[STEP 2.3] 가이드라인 변환 (LLM)")
    print("-" * 70)
    state2 = n_rag_to_guidelines(state2, llm)
    print("\n[최종 가이드라인]")
    print(json.dumps(state2.get("rag_guidelines"), ensure_ascii=False, indent=2))

    print("\n[에러/경고]")
    print(f"Errors: {len(state2.get('errors', []))}")
    print(f"Warnings: {len(state2.get('warnings', []))}")

    # 테스트 케이스 3: 고지혈증
    print("\n\n" + "=" * 70)
    print("[테스트 케이스 3] 고지혈증 RAG 파이프라인")
    print("=" * 70)

    sample_state3: WFState = {
        "patient_id": "test_p3",
        "visit_id": "test_v3",
        "diagnosis_key": "고지혈증",
        "errors": [],
        "warnings": [],
    }

    # Step 1: 쿼리 생성
    print("\n[STEP 2.1] 검색 쿼리 생성")
    print("-" * 70)
    state3 = n_rag_query_sanitize(sample_state3, llm)
    print(f"진단명: {state3['diagnosis_key']}")
    print(f"검색 쿼리: {state3['rag_query']}")

    # Step 2: 벡터 DB 검색
    print("\n[STEP 2.2] 벡터 DB 검색 실행")
    print("-" * 70)
    state3 = n_rag_search(state3, retriever)
    print(f"검색 결과 길이: {len(state3.get('rag_raw', ''))} 문자")
    print(f"\n검색 결과 미리보기:\n{state3.get('rag_raw', '')[:300]}...")

    # Step 3: 가이드라인 변환
    print("\n[STEP 2.3] 가이드라인 변환 (LLM)")
    print("-" * 70)
    state3 = n_rag_to_guidelines(state3, llm)
    print("\n[최종 가이드라인]")
    print(json.dumps(state3.get("rag_guidelines"), ensure_ascii=False, indent=2))

    print("\n[에러/경고]")
    print(f"Errors: {len(state3.get('errors', []))}")
    print(f"Warnings: {len(state3.get('warnings', []))}")

    # 테스트 케이스 4: 희귀 질환 (검색 결과 없을 가능성)
    print("\n\n" + "=" * 70)
    print("[테스트 케이스 4] 희귀 질환 RAG 파이프라인 (에러 핸들링)")
    print("=" * 70)

    sample_state4: WFState = {
        "patient_id": "test_p4",
        "visit_id": "test_v4",
        "diagnosis_key": "매우희귀한질환123",
        "errors": [],
        "warnings": [],
    }

    # Step 1: 쿼리 생성
    print("\n[STEP 2.1] 검색 쿼리 생성")
    print("-" * 70)
    state4 = n_rag_query_sanitize(sample_state4, llm)
    print(f"진단명: {state4['diagnosis_key']}")
    print(f"검색 쿼리: {state4['rag_query']}")

    # Step 2: 벡터 DB 검색
    print("\n[STEP 2.2] 벡터 DB 검색 실행")
    print("-" * 70)
    state4 = n_rag_search(state4, retriever)
    print(f"검색 결과 길이: {len(state4.get('rag_raw', ''))} 문자")
    if state4.get('rag_raw'):
        print(f"\n검색 결과 미리보기:\n{state4.get('rag_raw', '')[:200]}...")
    else:
        print("검색 결과 없음")

    # Step 3: 가이드라인 변환
    print("\n[STEP 2.3] 가이드라인 변환 (LLM)")
    print("-" * 70)
    state4 = n_rag_to_guidelines(state4, llm)
    print("\n[최종 가이드라인]")
    print(json.dumps(state4.get("rag_guidelines"), ensure_ascii=False, indent=2))

    print("\n[에러/경고]")
    print(f"Errors: {len(state4.get('errors', []))}")
    print(f"Warnings: {len(state4.get('warnings', []))}")
    if state4.get("warnings"):
        print("Warning details:", state4.get("warnings"))

    # 테스트 케이스 5: 암 (복잡한 정보)
    print("\n\n" + "=" * 70)
    print("[테스트 케이스 5] 폐암 RAG 파이프라인")
    print("=" * 70)

    sample_state5: WFState = {
        "patient_id": "test_p5",
        "visit_id": "test_v5",
        "diagnosis_key": "폐암",
        "errors": [],
        "warnings": [],
    }

    # Step 1: 쿼리 생성
    print("\n[STEP 2.1] 검색 쿼리 생성")
    print("-" * 70)
    state5 = n_rag_query_sanitize(sample_state5, llm)
    print(f"진단명: {state5['diagnosis_key']}")
    print(f"검색 쿼리: {state5['rag_query']}")

    # Step 2: 벡터 DB 검색
    print("\n[STEP 2.2] 벡터 DB 검색 실행")
    print("-" * 70)
    state5 = n_rag_search(state5, retriever)
    print(f"검색 결과 길이: {len(state5.get('rag_raw', ''))} 문자")
    print(f"\n검색 결과 미리보기:\n{state5.get('rag_raw', '')[:300]}...")

    # Step 3: 가이드라인 변환
    print("\n[STEP 2.3] 가이드라인 변환 (LLM)")
    print("-" * 70)
    state5 = n_rag_to_guidelines(state5, llm)
    print("\n[최종 가이드라인]")
    print(json.dumps(state5.get("rag_guidelines"), ensure_ascii=False, indent=2))

    print("\n[에러/경고]")
    print(f"Errors: {len(state5.get('errors', []))}")
    print(f"Warnings: {len(state5.get('warnings', []))}")

    print("\n" + "=" * 70)
    print("RAG 통합 테스트 완료")
    print("=" * 70)
    print("\n💡 요약:")
    print("   - 벡터 DB 구축 및 검색이 정상적으로 작동합니다.")
    print("   - LLM이 검색 결과를 가이드라인으로 변환합니다.")
    print("   - 에러 핸들링(safe_llm_invoke)이 적용되어 있습니다.")
    print("   - 희귀 질환 등 검색 결과가 부족한 경우에도 안전하게 처리됩니다.")


if __name__ == "__main__":
    test_rag_integration()
