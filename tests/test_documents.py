"""Tests for document processing and endpoints."""

import io
from unittest.mock import MagicMock, patch


class TestDocumentProcessor:
    """Test document processor functionality."""

    def test_supported_extensions(self):
        """Test that supported extensions are defined."""
        from app.core.document_processor import DocumentProcessor

        processor = DocumentProcessor()
        assert ".pdf" in processor.SUPPORTED_EXTENSIONS
        assert ".txt" in processor.SUPPORTED_EXTENSIONS
        assert ".csv" in processor.SUPPORTED_EXTENSIONS

    def test_processor_initialization(self, mock_settings):
        """Test processor initialization with settings."""
        from app.core.document_processor import DocumentProcessor

        processor = DocumentProcessor(chunk_size=500, chunk_overlap=100)
        assert processor.chunk_size == 500
        assert processor.chunk_overlap == 100

    def test_split_documents(self, mock_settings, sample_chunks):
        """Test document splitting."""
        from app.core.document_processor import DocumentProcessor

        processor = DocumentProcessor()
        # The splitter should handle chunks appropriately
        result = processor.split_documents(sample_chunks)
        assert isinstance(result, list)


class TestDocumentEndpoints:
    """Test document API endpoints."""

    def test_get_collection_info(self, client, mock_vector_store):
        """Test getting collection information."""
        response = client.get("/documents/info")

        assert response.status_code == 200
        data = response.json()
        assert "collection_name" in data
        assert "total_documents" in data
        assert "status" in data

    def test_upload_invalid_file_type(self, client):
        """Test uploading unsupported file type."""
        # Create a mock file with unsupported extension
        file_content = b"test content"
        files = {"file": ("test.xyz", io.BytesIO(file_content), "application/octet-stream")}

        with patch("app.api.routes.documents.DocumentProcessor") as mock_processor:
            mock_instance = MagicMock()
            mock_instance.process_upload.side_effect = ValueError("Unsupported file extension")
            mock_processor.return_value = mock_instance

            response = client.post("/documents/upload", files=files)

            assert response.status_code == 400

    def test_upload_valid_text_file(self, client, mock_vector_store):
        """Test uploading a valid text file."""
        file_content = b"This is test content for the RAG system."
        files = {"file": ("test.txt", io.BytesIO(file_content), "text/plain")}

        with patch("app.api.routes.documents.DocumentProcessor") as mock_processor:
            from langchain_core.documents import Document

            mock_instance = MagicMock()
            mock_instance.process_upload.return_value = [
                Document(
                    page_content="This is test content",
                    metadata={"source": "test.txt"},
                )
            ]
            mock_processor.return_value = mock_instance

            response = client.post("/documents/upload", files=files)

            assert response.status_code == 200
            data = response.json()
            assert data["filename"] == "test.txt"
            assert "chunks_created" in data
            assert "document_ids" in data

    def test_delete_collection(self, client, mock_vector_store):
        """Test deleting the collection."""
        response = client.delete("/documents/collection")

        assert response.status_code == 200
        data = response.json()
        assert "message" in data
