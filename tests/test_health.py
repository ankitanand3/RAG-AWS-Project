"""Tests for health check endpoints."""


class TestHealthEndpoints:
    """Test health check endpoints."""

    def test_health_check(self, client):
        """Test basic health check endpoint."""
        response = client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "timestamp" in data
        assert "version" in data

    def test_root_endpoint(self, client):
        """Test root endpoint returns HTML."""
        response = client.get("/")

        assert response.status_code == 200
        assert response.headers["content-type"] == "text/html; charset=utf-8"
        assert "<!DOCTYPE html>" in response.text or "<html" in response.text

    def test_readiness_check(self, client, mock_vector_store):
        """Test readiness check endpoint."""
        response = client.get("/health/ready")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ready"
        assert data["qdrant_connected"] is True
        assert "collection_info" in data

    def test_docs_available(self, client):
        """Test that Swagger docs are available."""
        response = client.get("/docs")
        assert response.status_code == 200

    def test_openapi_available(self, client):
        """Test that OpenAPI schema is available."""
        response = client.get("/openapi.json")
        assert response.status_code == 200
        data = response.json()
        assert "openapi" in data
        assert "paths" in data
