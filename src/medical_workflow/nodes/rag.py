"""의료 RAG 검색 노드 — 신뢰할 수 있는 의료 지식 베이스 기반 검색"""

import os
import pandas as pd

from langchain_upstage import UpstageEmbeddings
from langchain_community.vectorstores import Chroma

from medical_workflow.state import WFState


def build_medical_vector_db(file_path: str, persist_dir: str | None = None):
    """
    의료 CSV(병명, 생활가이드, 식이요법/생활가이드)로 Chroma 벡터 DB 구축.

    - persist_dir가 존재하고 DB가 이미 있으면 → 즉시 로드
    - 없으면 CSV 기반으로 생성 후 디스크에 저장
    """

    embeddings = UpstageEmbeddings(model="solar-embedding-1-large")

    # ✅ 1. Persisted DB가 존재하면 바로 로드
    if persist_dir and os.path.exists(persist_dir) and os.listdir(persist_dir):
        print(f"[VectorDB] 기존 DB 로드: {persist_dir}")
        return Chroma(
            collection_name="medical_info",
            embedding_function=embeddings,
            persist_directory=persist_dir,
        )

    # ✅ 2. 없으면 CSV 읽어서 새로 생성
    print("[VectorDB] CSV 기반으로 새 DB 생성 중...")

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
        lambda row: f"질환명: {row['병명']}\n"
        f"[생활가이드]\n{row['생활가이드']}\n"
        f"[식이요법]\n{row['식이요법/생활가이드']}",
        axis=1,
    )

    vector_db = Chroma.from_texts(
        texts=df["combined_text"].tolist(),
        embedding=embeddings,
        collection_name="medical_info",
        persist_directory=persist_dir,  # 🔥 핵심 추가
    )

    # 명시적 persist (안전)
    if persist_dir:
        vector_db.persist()
        print(f"[VectorDB] DB 저장 완료: {persist_dir}")

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
        return {**s, "rag_raw": "해당 질환에 대한 신뢰 가능한 가이드가 없습니다.", "rag_diagnosis_found": False}

    # 진단명이 검색 결과에 실제로 포함되는지 확인 (CSV 첫 줄: "질환명: {병명}")
    diagnosis = (s.get("diagnosis_key") or "").strip()
    diagnosis_found = any(
        diagnosis in getattr(d, "page_content", "")
        for d in docs
    )

    raw_text = "\n\n---\n\n".join(
        getattr(d, "page_content", str(d)) for d in docs
    )

    new_state = {**s, "rag_raw": raw_text, "rag_diagnosis_found": diagnosis_found}

    if not diagnosis_found:
        warnings = list(s.get("warnings", []))
        warnings.append(f"⚠️ RAG에서 추출 불가: '{diagnosis}'에 해당하는 데이터가 의료 DB에 없습니다.")
        new_state["warnings"] = warnings

    return new_state
