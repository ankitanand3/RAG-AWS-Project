"""Pytest configuration and fixtures."""

import os
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# Set test environment variables before importing app
os.environ["OPENAI_API_KEY"] = "test-key"
os.environ["QDRANT_URL"] = "http://localhost:6333"
os.environ["QDRANT_API_KEY"] = "test-qdrant-key"
os.environ["LOG_LEVEL"] = "WARNING"


@pytest.fixture
def mock_settings():
    """Mock settings for testing."""
    with patch("app.config.get_settings") as mock:
        settings = MagicMock()
        settings.openai_api_key = "test-key"
        settings.qdrant_url = "http://localhost:6333"
        settings.qdrant_api_key = "test-key"
        settings.collection_name = "test_collection"
        settings.chunk_size = 500
        settings.chunk_overlap = 100
        settings.embedding_model = "text-embedding-3-small"
        settings.llm_model = "gpt-4o-mini"
        settings.llm_temperature = 0
        settings.retrieval_k = 4
        settings.log_level = "WARNING"
        settings.api_host = "0.0.0.0"
        settings.api_port = 8000
        settings.app_name = "RAG Q&A System"
        settings.app_version = "0.1.0"
        # RAGAS settings
        settings.enable_ragas_evaluation = True
        settings.ragas_timeout_seconds = 30.0
        settings.ragas_log_results = True
        settings.ragas_llm_model = None  # Defaults to llm_model
        settings.ragas_llm_temperature = None  # Defaults to llm_temperature
        settings.ragas_embedding_model = None  # Defaults to embedding_model
        mock.return_value = settings
        yield settings


@pytest.fixture
def mock_qdrant_client():
    """Mock Qdrant client."""
    with patch("app.core.vector_store.get_qdrant_client") as mock:
        client = MagicMock()
        client.get_collections.return_value = MagicMock(collections=[])
        client.get_collection.return_value = MagicMock(
            points_count=10,
            vectors_count=10,
            status=MagicMock(value="green"),
        )
        mock.return_value = client
        yield client


@pytest.fixture
def mock_embeddings():
    """Mock OpenAI embeddings."""
    with patch("app.core.embeddings.get_embeddings") as mock:
        embeddings = MagicMock()
        embeddings.embed_query.return_value = [0.1] * 1536
        embeddings.embed_documents.return_value = [[0.1] * 1536]
        mock.return_value = embeddings
        yield embeddings


@pytest.fixture
def mock_vector_store(mock_qdrant_client, mock_embeddings):
    """Mock vector store service."""
    with patch("app.core.vector_store.VectorStoreService") as mock:
        service = MagicMock()
        service.health_check.return_value = True
        service.get_collection_info.return_value = {
            "name": "test_collection",
            "points_count": 10,
            "vectors_count": 10,
            "status": "green",
        }
        service.add_documents.return_value = ["id1", "id2"]
        service.search.return_value = []
        mock.return_value = service
        yield service


@pytest.fixture
def mock_rag_chain():
    """Mock RAG chain."""
    with patch("app.core.rag_chain.RAGChain") as mock:
        chain = MagicMock()
        chain.query.return_value = "This is a test answer."
        chain.aquery.return_value = "This is a test answer."
        chain.query_with_sources.return_value = {
            "answer": "This is a test answer.",
            "sources": [{"content": "Test content", "metadata": {"source": "test.pdf"}}],
        }
        chain.aquery_with_sources.return_value = {
            "answer": "This is a test answer.",
            "sources": [{"content": "Test content", "metadata": {"source": "test.pdf"}}],
        }
        mock.return_value = chain
        yield chain


@pytest.fixture
def mock_rag_chain_with_evaluation():
    """Mock RAG chain with evaluation support."""
    with patch("app.core.rag_chain.RAGChain") as mock:
        chain = MagicMock()
        chain.query.return_value = "This is a test answer."
        chain.aquery.return_value = "This is a test answer."
        chain.query_with_sources.return_value = {
            "answer": "This is a test answer.",
            "sources": [{"content": "Test content", "metadata": {"source": "test.pdf"}}],
        }
        chain.aquery_with_sources.return_value = {
            "answer": "This is a test answer.",
            "sources": [{"content": "Test content", "metadata": {"source": "test.pdf"}}],
        }
        chain.aquery_with_evaluation.return_value = {
            "answer": "This is a test answer.",
            "sources": [{"content": "Test content", "metadata": {"source": "test.pdf"}}],
            "evaluation": {
                "faithfulness": 0.95,
                "answer_relevancy": 0.87,
                "evaluation_time_ms": 1200.5,
                "error": None,
            },
        }
        mock.return_value = chain
        yield chain


@pytest.fixture
def mock_rag_chain_with_evaluation_error():
    """Mock RAG chain with evaluation error."""
    with patch("app.core.rag_chain.RAGChain") as mock:
        chain = MagicMock()
        chain.query.return_value = "This is a test answer."
        chain.aquery.return_value = "This is a test answer."
        chain.query_with_sources.return_value = {
            "answer": "This is a test answer.",
            "sources": [{"content": "Test content", "metadata": {"source": "test.pdf"}}],
        }
        chain.aquery_with_sources.return_value = {
            "answer": "This is a test answer.",
            "sources": [{"content": "Test content", "metadata": {"source": "test.pdf"}}],
        }
        chain.aquery_with_evaluation.return_value = {
            "answer": "This is a test answer.",
            "sources": [{"content": "Test content", "metadata": {"source": "test.pdf"}}],
            "evaluation": {
                "faithfulness": None,
                "answer_relevancy": None,
                "evaluation_time_ms": None,
                "error": "Evaluation timeout after 30s",
            },
        }
        mock.return_value = chain
        yield chain


@pytest.fixture
def client(mock_vector_store, mock_rag_chain):
    """Create test client with mocked dependencies."""
    from app.main import app

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def sample_text_content():
    """Sample text content for testing."""
    return """
    This is a sample document for testing the RAG pipeline.

    Section 1: Introduction
    RAG stands for Retrieval-Augmented Generation.
    It combines information retrieval with text generation.

    Section 2: Components
    - Document Loader
    - Text Splitter
    - Embeddings
    - Vector Store
    - LLM
    """


@pytest.fixture
def sample_chunks():
    """Sample document chunks."""
    from langchain_core.documents import Document

    return [
        Document(
            page_content="This is chunk 1 about RAG.",
            metadata={"source": "test.txt", "chunk": 0},
        ),
        Document(
            page_content="This is chunk 2 about embeddings.",
            metadata={"source": "test.txt", "chunk": 1},
        ),
    ]
