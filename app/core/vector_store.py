"""Vector store module for Qdrant operations."""

from functools import lru_cache
from typing import Any
from uuid import uuid4

from langchain_core.documents import Document
from langchain_qdrant import QdrantVectorStore
from qdrant_client import QdrantClient
from qdrant_client.http.exceptions import UnexpectedResponse
from qdrant_client.http.models import Distance, VectorParams

from app.config import get_settings
from app.core.embeddings import get_embeddings
from app.utils.logger import get_logger

logger = get_logger(__name__)
settings = get_settings()

# Embedding dimensions for different OpenAI models
EMBEDDING_DIMENSIONS = {
    "text-embedding-3-small": 1536,
    "text-embedding-3-large": 3072,
    "text-embedding-ada-002": 1536,
}


def get_embedding_dimension() -> int:
    """Get embedding dimension based on configured model.

    Returns:
        Embedding dimension for the configured model
    """
    model = settings.embedding_model
    dimension = EMBEDDING_DIMENSIONS.get(model)

    if dimension is None:
        logger.warning(
            f"Unknown embedding model '{model}', defaulting to 1536 dimensions. "
            f"Known models: {list(EMBEDDING_DIMENSIONS.keys())}"
        )
        return 1536

    logger.debug(f"Using {dimension} dimensions for model '{model}'")
    return dimension


@lru_cache
def get_qdrant_client() -> QdrantClient:
    """Get cached Qdrant client instance.

    Returns:
        Configured QdrantClient instance
    """
    logger.info(f"Connecting to Qdrant at: {settings.qdrant_url}")

    # For local Docker deployment, api_key is optional
    client_kwargs = {"url": settings.qdrant_url}
    if settings.qdrant_api_key:
        client_kwargs["api_key"] = settings.qdrant_api_key
        logger.info("Using Qdrant with API key authentication")
    else:
        logger.info("Using Qdrant without authentication (local Docker mode)")

    client = QdrantClient(**client_kwargs)

    logger.info("Qdrant client connected successfully")
    return client


class VectorStoreService:
    """Service for managing vector store operations."""

    def __init__(self, collection_name: str | None = None):
        """Initialize vector store service.

        Args:
            collection_name: Name of the Qdrant collection (default from settings)
        """
        self.collection_name = collection_name or settings.collection_name
        self.client = get_qdrant_client()
        self.embeddings = get_embeddings()

        # Ensure collection exists
        self._ensure_collection()

        # Initialize LangChain Qdrant vector store
        # Check if collection exists and get its vector name
        vector_name = self._get_vector_name()

        self.vector_store = QdrantVectorStore(
            client=self.client,
            collection_name=self.collection_name,
            embedding=self.embeddings,
            vector_name=vector_name,
        )

        logger.info(f"VectorStoreService initialized for collection: {self.collection_name}")

    def _ensure_collection(self) -> None:
        """Ensure the collection exists, create if not."""
        try:
            collection_info = self.client.get_collection(self.collection_name)
            logger.info(
                f"Collection '{self.collection_name}' exists with "
                f"{collection_info.points_count} points"
            )
        except UnexpectedResponse:
            embedding_dim = get_embedding_dimension()
            logger.info(
                f"Creating collection: {self.collection_name} " f"with {embedding_dim} dimensions"
            )
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(
                    size=embedding_dim,
                    distance=Distance.COSINE,
                ),
            )
            logger.info(f"Collection '{self.collection_name}' created successfully")

    def _get_vector_name(self) -> str:
        """Get the vector field name from existing collection or use default.

        Returns:
            Vector field name to use
        """
        try:
            collection_info = self.client.get_collection(self.collection_name)
            vectors_config = collection_info.config.params.vectors

            # Handle named vectors (dict-like structure)
            if isinstance(vectors_config, dict):
                # Named vectors - get the first vector name
                vector_names = list(vectors_config.keys())
                if vector_names:
                    vector_name = vector_names[0]
                    logger.info(f"Using existing vector field: '{vector_name}'")
                    return vector_name

            # Single default vector (VectorParams object - unnamed)
            logger.info("Using default unnamed vector field")
            return ""

        except Exception as e:
            # Collection doesn't exist or error reading config, use default
            logger.warning(f"Could not detect vector name, using default: {e}")
            return ""

    def add_documents(self, documents: list[Document]) -> list[str]:
        """Add documents to the vector store.

        Args:
            documents: List of Document objects to add

        Returns:
            List of document IDs
        """
        if not documents:
            logger.warning("No documents to add")
            return []

        logger.info(f"Adding {len(documents)} documents to collection")

        # Generate unique IDs for each document
        ids = [str(uuid4()) for _ in documents]

        # Add to vector store
        self.vector_store.add_documents(documents, ids=ids)

        logger.info(f"Successfully added {len(documents)} documents")
        return ids

    def search(
        self,
        query: str,
        k: int | None = None,
    ) -> list[Document]:
        """Search for similar documents.

        Args:
            query: Search query
            k: Number of results to return (default from settings)

        Returns:
            List of similar Document objects
        """
        k = k or settings.retrieval_k
        logger.debug(f"Searching for: {query[:50]}... (k={k})")

        results = self.vector_store.similarity_search(query, k=k)

        logger.debug(f"Found {len(results)} results")
        return results

    def search_with_scores(
        self,
        query: str,
        k: int | None = None,
    ) -> list[tuple[Document, float]]:
        """Search for similar documents with relevance scores.

        Args:
            query: Search query
            k: Number of results to return

        Returns:
            List of (Document, score) tuples
        """
        k = k or settings.retrieval_k
        logger.debug(f"Searching with scores for: {query[:50]}... (k={k})")

        results = self.vector_store.similarity_search_with_score(query, k=k)

        logger.debug(f"Found {len(results)} results with scores")
        return results

    def get_retriever(self, k: int | None = None) -> Any:
        """Get a retriever for the vector store.

        Args:
            k: Number of documents to retrieve

        Returns:
            LangChain retriever object
        """
        k = k or settings.retrieval_k

        return self.vector_store.as_retriever(
            search_type="similarity",
            search_kwargs={"k": k},
        )

    def delete_collection(self) -> None:
        """Delete the entire collection."""
        logger.warning(f"Deleting collection: {self.collection_name}")
        self.client.delete_collection(self.collection_name)
        logger.info(f"Collection '{self.collection_name}' deleted")

    def get_collection_info(self) -> dict:
        """Get information about the collection.

        Returns:
            Dictionary with collection statistics
        """
        try:
            info = self.client.get_collection(self.collection_name)
            return {
                "name": self.collection_name,
                "points_count": info.points_count,
                "indexed_vectors_count": info.indexed_vectors_count,
                "status": info.status.value,
            }
        except UnexpectedResponse:
            return {
                "name": self.collection_name,
                "points_count": 0,
                "indexed_vectors_count": 0,
                "status": "not_found",
            }

    def health_check(self) -> bool:
        """Check if vector store is healthy.

        Returns:
            True if healthy, False otherwise
        """
        try:
            self.client.get_collections()
            return True
        except Exception as e:
            logger.error(f"Vector store health check failed: {e}")
            return False
