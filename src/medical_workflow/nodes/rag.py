"""의료 RAG 검색 노드 — 신뢰할 수 있는 의료 지식 베이스 기반 검색"""

import pandas as pd

from langchain_upstage import UpstageEmbeddings
from langchain_community.vectorstores import Chroma

from medical_workflow.state import WFState


def build_medical_vector_db(file_path: str):
    """
    의료 CSV(병명, 생활가이드, 식이요법/생활가이드)로 Chroma 벡터 DB 구축.
    practice_rag.ipynb 로직을 모듈화한 함수.
    """
    encodings = ["utf-8-sig", "utf-8", "cp949", "euc-kr"]
    df = None
    for enc in encodings:
        try:
            df = pd.read_csv(file_path, encoding=enc)
            break
        except Exception:
            continue

    if df is None:
        raise ValueError("파일을 읽을 수 없습니다. 경로와 인코딩을 확인하세요.")

    df.columns = df.columns.str.strip()
    df["생활가이드"] = df["생활가이드"].fillna("")
    df["식이요법/생활가이드"] = df["식이요법/생활가이드"].fillna("")
    df["combined_text"] = df.apply(
        lambda row: f"질환명: {row['병명']}\n[생활가이드]\n{row['생활가이드']}\n[식이요법]\n{row['식이요법/생활가이드']}",
        axis=1,
    )

    embeddings = UpstageEmbeddings(model="solar-embedding-1-large")
    vector_db = Chroma.from_texts(
        texts=df["combined_text"].tolist(),
        embedding=embeddings,
        collection_name="medical_info",
    )
    return vector_db


def n_rag_search(s: WFState, retriever) -> WFState:
    """
    WFState의 rag_query(또는 diagnosis_key)로 RAG 검색 후,
    rag_raw에 검색 결과 텍스트를 넣어 n_rag_to_guidelines에서 사용.
    """
    query = (s.get("rag_query") or "").strip()
    if not query and s.get("diagnosis_key"):
        query = f"{s['diagnosis_key']} 관리 방법"

    if not query:
        return {**s, "rag_raw": "검색 쿼리가 없습니다."}

    try:
        docs = retriever.invoke(query)
    except Exception:
        return {**s, "rag_raw": "RAG 검색 중 오류가 발생했습니다."}

    if not docs:
        return {**s, "rag_raw": "해당 질환에 대한 신뢰 가능한 가이드가 없습니다."}

    raw_text = "\n\n---\n\n".join(getattr(d, "page_content", str(d)) for d in docs)
    return {**s, "rag_raw": raw_text}
