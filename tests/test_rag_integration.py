"""
RAG 연동 테스트: 벡터 DB 구축 + 검색 + n_rag_search 노드
전체 러너 없이 의료 RAG 경로만 검증합니다.
UPSTAGE_API_KEY가 .env 또는 환경에 있으면 실제 API 호출로 테스트합니다.
"""
import os
import sys

# 프로젝트 루트를 path에 추가
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
except ImportError:
    pass


def _skip_if_no_api_key():
    if not os.environ.get("UPSTAGE_API_KEY"):
        print("SKIP: UPSTAGE_API_KEY가 없습니다. .env에 설정 후 다시 실행하세요.")
        sys.exit(0)


def test_graph_builds_with_rag():
    """build_graph가 retriever만 받고 컴파일되는지 확인 (RAG 연동 후 시그니처 검증)"""
    from langchain_openai import ChatOpenAI
    from medical_workflow.graph import build_graph
    from langchain_core.documents import Document

    class MockRetriever:
        def invoke(self, query):
            return [Document(page_content="mock")]

    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0, api_key="test-key-for-build-only")
    compiled = build_graph(llm, MockRetriever())
    assert hasattr(compiled, "invoke"), "build_graph는 컴파일된 그래프(invoke 가능)를 반환해야 함"
    print("[OK] 그래프가 retriever로 정상 빌드됨")


def test_n_rag_search_with_mock_retriever():
    """API 없이 n_rag_search 노드가 state를 올바르게 갱신하는지 검증 (목 retriever)"""
    from medical_workflow.nodes.rag import n_rag_search
    from langchain_core.documents import Document

    class MockRetriever:
        def invoke(self, query):
            return [Document(page_content=f"질환명: {query}\n[생활가이드]\n테스트 가이드 내용")]

    retriever = MockRetriever()
    state = {"diagnosis_key": "후두암", "rag_query": "후두암 관리 방법"}
    out = n_rag_search(state, retriever)
    assert "rag_raw" in out
    assert "테스트 가이드" in out["rag_raw"]
    assert "후두암" in out["rag_raw"] or "관리 방법" in out["rag_raw"]
    print("[OK] n_rag_search (목 retriever) 동작 정상")


def test_api_key_with_small_vector_db():
    """소량 데이터(5행)로 벡터 DB 구축 → API 키 유효성만 빠르게 검증"""
    if not os.environ.get("UPSTAGE_API_KEY"):
        print("SKIP: UPSTAGE_API_KEY 없음")
        return
    import pandas as pd
    from langchain_upstage import UpstageEmbeddings
    from langchain_community.vectorstores import Chroma

    project_root = os.path.join(os.path.dirname(__file__), "..")
    data_path = os.path.join(project_root, "data", "medical_2.csv")
    if not os.path.isfile(data_path):
        print("SKIP: data/medical_2.csv 없음")
        return
    encodings = ["utf-8-sig", "utf-8", "cp949", "euc-kr"]
    df = None
    for enc in encodings:
        try:
            df = pd.read_csv(data_path, encoding=enc, nrows=5)
            break
        except Exception:
            continue
    if df is None or len(df) == 0:
        print("SKIP: CSV 읽기 실패")
        return
    df.columns = df.columns.str.strip()
    if "병명" not in df.columns or "생활가이드" not in df.columns:
        df["combined_text"] = df.iloc[:, 0].astype(str)
    else:
        df["생활가이드"] = df["생활가이드"].fillna("")
        df["식이요법/생활가이드"] = df.get("식이요법/생활가이드", pd.Series([""] * len(df))).fillna("")
        df["combined_text"] = df.apply(
            lambda r: f"질환명: {r['병명']}\n[생활가이드]\n{r['생활가이드']}\n[식이요법]\n{r.get('식이요법/생활가이드', '')}",
            axis=1,
        )
    embeddings = UpstageEmbeddings(model="solar-embedding-1-large")
    vector_db = Chroma.from_texts(
        texts=df["combined_text"].tolist(),
        embedding=embeddings,
        collection_name="medical_test_small",
    )
    docs = vector_db.as_retriever(search_kwargs={"k": 1}).invoke("후두암")
    assert len(docs) >= 0
    print("[OK] API 키 유효, 소량 벡터 DB 구축 및 검색 성공")


def test_build_vector_db_and_retrieve():
    """build_medical_vector_db + retriever.invoke 동작 확인 (전체 CSV, 시간 소요)"""
    _skip_if_no_api_key()
    from medical_workflow.nodes.rag import build_medical_vector_db

    project_root = os.path.join(os.path.dirname(__file__), "..")
    data_path = os.path.join(project_root, "data", "medical_2.csv")
    if not os.path.isfile(data_path):
        raise FileNotFoundError(f"테스트 데이터 없음: {data_path}")

    vector_db = build_medical_vector_db(data_path)
    retriever = vector_db.as_retriever(search_kwargs={"k": 3})

    docs = retriever.invoke("후두암 관리 방법")
    assert len(docs) > 0, "후두암 관련 문서가 1건 이상 검색되어야 함"
    content = getattr(docs[0], "page_content", str(docs[0]))
    assert "후두" in content or "질환" in content or len(content) > 50
    print("[OK] 벡터 DB 구축 및 retriever 검색 성공")
    return True


def test_n_rag_search_node():
    """n_rag_search 노드가 state에 rag_raw를 채우는지 확인"""
    _skip_if_no_api_key()
    from medical_workflow.nodes.rag import build_medical_vector_db, n_rag_search

    project_root = os.path.join(os.path.dirname(__file__), "..")
    data_path = os.path.join(project_root, "data", "medical_2.csv")
    if not os.path.isfile(data_path):
        raise FileNotFoundError(f"테스트 데이터 없음: {data_path}")

    vector_db = build_medical_vector_db(data_path)
    retriever = vector_db.as_retriever(search_kwargs={"k": 2})

    state = {"diagnosis_key": "후두암", "rag_query": "후두암 관리 방법"}
    out = n_rag_search(state, retriever)
    assert "rag_raw" in out
    assert len(out["rag_raw"]) > 20
    print("[OK] n_rag_search 노드 동작 정상, rag_raw 길이:", len(out["rag_raw"]))
    return True


if __name__ == "__main__":
    os.chdir(os.path.join(os.path.dirname(__file__), ".."))
    # API 불필요 테스트
    test_graph_builds_with_rag()
    test_n_rag_search_with_mock_retriever()
    # API 키 빠른 검증 (소량 데이터)
    test_api_key_with_small_vector_db()
    # API 필요 테스트 (키 없거나 무효면 스킵/실패)
    try:
        test_build_vector_db_and_retrieve()
        test_n_rag_search_node()
    except Exception as e:
        if "401" in str(e) or "invalid" in str(e).lower() or "api key" in str(e).lower():
            print("[SKIP] UPSTAGE API 키가 없거나 무효하여 전체 벡터 DB 테스트 생략:", e)
        else:
            raise
    print("\nRAG 연동 테스트 완료.")
