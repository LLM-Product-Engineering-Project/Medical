"""test_rag_batch_embedding.py

Unit tests for the batch embedding optimization in build_medical_vector_db().
Verifies that embed_documents() is called once with all texts (batch)
instead of multiple sequential embed_query() calls.
"""

import os
import tempfile
from unittest.mock import patch, MagicMock

import pandas as pd
import pytest


def _make_csv(tmp_path: str) -> str:
    """Create a minimal medical CSV for testing."""
    csv_path = os.path.join(tmp_path, "medical.csv")
    df = pd.DataFrame(
        {
            "병명": ["감기", "두통", "소화불량"],
            "생활가이드": ["휴식을 취하세요", "조용한 곳에서 쉬세요", "소화제를 복용하세요"],
            "식이요법/생활가이드": ["따뜻한 물을 마시세요", "카페인을 피하세요", "기름진 음식을 피하세요"],
        }
    )
    df.to_csv(csv_path, index=False, encoding="utf-8-sig")
    return csv_path


@patch("medical_workflow.nodes.rag.UpstageEmbeddings")
@patch("medical_workflow.nodes.rag.Chroma")
def test_batch_embedding_used(mock_chroma_cls, mock_embeddings_cls):
    """build_medical_vector_db should use embed_documents() for batch embedding."""
    mock_embeddings = MagicMock()
    mock_embeddings_cls.return_value = mock_embeddings

    # embed_documents returns a list of vectors (one per text)
    fake_vectors = [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6], [0.7, 0.8, 0.9]]
    mock_embeddings.embed_documents.return_value = fake_vectors

    mock_db = MagicMock()
    mock_chroma_cls.from_embeddings.return_value = mock_db

    with tempfile.TemporaryDirectory() as tmp:
        csv_path = _make_csv(tmp)
        persist_dir = os.path.join(tmp, "chroma_db")
        os.makedirs(persist_dir)

        from medical_workflow.nodes.rag import build_medical_vector_db

        result = build_medical_vector_db(file_path=csv_path, persist_dir=persist_dir)

    # Key assertion: embed_documents called ONCE with all texts (batch)
    mock_embeddings.embed_documents.assert_called_once()
    call_args = mock_embeddings.embed_documents.call_args[0][0]
    assert len(call_args) == 3, f"Expected 3 texts, got {len(call_args)}"
    assert "감기" in call_args[0]

    # Verify from_embeddings was used (not from_texts)
    mock_chroma_cls.from_embeddings.assert_called_once()
    mock_chroma_cls.from_texts.assert_not_called()

    # Verify text_embeddings format: list of (text, vector) tuples
    te_arg = mock_chroma_cls.from_embeddings.call_args[1]["text_embeddings"]
    assert len(te_arg) == 3
    assert te_arg[0] == (call_args[0], fake_vectors[0])

    assert result is mock_db


@patch("medical_workflow.nodes.rag.UpstageEmbeddings")
@patch("medical_workflow.nodes.rag.Chroma")
def test_persisted_db_loads_without_embedding(mock_chroma_cls, mock_embeddings_cls):
    """When persist_dir has existing data, no embedding calls should be made."""
    mock_embeddings = MagicMock()
    mock_embeddings_cls.return_value = mock_embeddings

    mock_db = MagicMock()
    mock_chroma_cls.return_value = mock_db

    with tempfile.TemporaryDirectory() as tmp:
        persist_dir = os.path.join(tmp, "chroma_db")
        os.makedirs(persist_dir)
        # Write a dummy file so os.listdir() is non-empty
        with open(os.path.join(persist_dir, "test"), "w") as f:
            f.write("data")

        from medical_workflow.nodes.rag import build_medical_vector_db

        result = build_medical_vector_db(file_path="unused.csv", persist_dir=persist_dir)

    # No embedding calls should be made
    mock_embeddings.embed_documents.assert_not_called()
    mock_embeddings.embed_query.assert_not_called()

    # Chroma should be constructed directly (not from_texts or from_embeddings)
    mock_chroma_cls.assert_called_once()
    assert result is mock_db
