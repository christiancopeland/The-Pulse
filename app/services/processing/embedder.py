"""
Embedding generation and Qdrant storage for news items.

Generates vector embeddings for news content and stores them
in Qdrant for semantic search capabilities.

PROC-006: Qdrant Embedding Pipeline

Uses Ollama's nomic-embed-text model (768 dimensions) for
fully local, open-source embeddings.
"""
from typing import List, Optional, Dict, Any
from dataclasses import dataclass
from datetime import datetime, timezone
import logging
import os
import re
import uuid
import asyncio
import time

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance, VectorParams, PointStruct,
    Filter, FieldCondition, MatchValue
)

from app.models.news_item import NewsItem
# Using local embeddings (sentence-transformers) instead of Ollama
from app.services.local_embeddings import LocalEmbeddings as OllamaEmbeddings, LocalEmbeddingError as OllamaEmbeddingError

logger = logging.getLogger(__name__)


@dataclass
class EmbeddingResult:
    """Result of embedding generation."""
    item_id: str
    qdrant_id: str
    success: bool
    error: Optional[str] = None
    embedding_time_ms: float = 0.0

    def __repr__(self):
        status = "OK" if self.success else "FAILED"
        return f"<EmbeddingResult({status}, id={self.item_id[:8]})>"


class EmbeddingError(Exception):
    """Exception raised for embedding errors."""
    pass


class NewsItemEmbedder:
    """
    Generates embeddings for news items and stores in Qdrant.

    Uses Ollama's nomic-embed-text model (768 dimensions)
    for semantic vector representation of news content.

    The embeddings enable:
    - Semantic search across news items
    - Similar article discovery
    - Topic clustering
    - Research assistant context retrieval
    """

    COLLECTION_NAME = "news_items"
    EMBEDDING_DIMENSIONS = OllamaEmbeddings.DIMENSIONS  # 768

    # Chunk settings for long content
    MAX_CONTENT_LENGTH = 8000  # Max chars to embed

    def __init__(
        self,
        qdrant_host: Optional[str] = None,
        qdrant_port: Optional[int] = None,
    ):
        """
        Initialize embedder.

        Args:
            qdrant_host: Qdrant host (default: localhost)
            qdrant_port: Qdrant port (default: 6333)
        """
        self._logger = logging.getLogger(f"{__name__}.NewsItemEmbedder")

        # Ollama embeddings (local, no API key needed)
        self.embeddings = OllamaEmbeddings()

        # Qdrant client
        self.qdrant = QdrantClient(
            host=qdrant_host or os.getenv("QDRANT_HOST", "localhost"),
            port=qdrant_port or int(os.getenv("QDRANT_PORT", 6333))
        )

        # Ensure collection exists
        self._ensure_collection()

    def _ensure_collection(self):
        """Create Qdrant collection if it doesn't exist."""
        try:
            collections = self.qdrant.get_collections()
            collection_names = [c.name for c in collections.collections]

            if self.COLLECTION_NAME not in collection_names:
                self.qdrant.create_collection(
                    collection_name=self.COLLECTION_NAME,
                    vectors_config=VectorParams(
                        size=self.EMBEDDING_DIMENSIONS,
                        distance=Distance.COSINE
                    )
                )
                self._logger.info(
                    f"Created Qdrant collection: {self.COLLECTION_NAME} "
                    f"({self.EMBEDDING_DIMENSIONS} dims)"
                )
            else:
                self._logger.debug(f"Qdrant collection exists: {self.COLLECTION_NAME}")

        except Exception as e:
            self._logger.error(f"Error ensuring collection: {e}")
            raise

    def _sanitize_text(self, text: str) -> str:
        """Clean text for embedding."""
        if not text:
            return ""

        # Remove null bytes and control characters
        cleaned = text.replace('\x00', '')
        cleaned = ''.join(char for char in cleaned if ord(char) >= 32 or char in '\n\r\t')

        # Remove excessive whitespace
        cleaned = re.sub(r'\s+', ' ', cleaned)

        # Ensure valid UTF-8
        cleaned = cleaned.encode('utf-8', errors='ignore').decode('utf-8')

        return cleaned.strip()

    def _prepare_content(self, item: NewsItem) -> str:
        """Prepare item content for embedding."""
        parts = []

        # Include title with higher weight (repeated)
        if item.title:
            title = self._sanitize_text(item.title)
            parts.append(f"Title: {title}")

        # Include source
        if item.source_name:
            parts.append(f"Source: {item.source_name}")

        # Include categories
        if item.categories:
            cats = ", ".join(item.categories)
            parts.append(f"Categories: {cats}")

        # Include main content (or summary if no content)
        content = item.content or item.summary or ""
        content = self._sanitize_text(content)

        if content:
            # Truncate if too long
            if len(content) > self.MAX_CONTENT_LENGTH:
                content = content[:self.MAX_CONTENT_LENGTH] + "..."
            parts.append(f"Content: {content}")

        return "\n\n".join(parts)

    async def _generate_embedding(self, text: str) -> List[float]:
        """Generate embedding for text using Ollama."""
        try:
            return await self.embeddings.generate(text)
        except OllamaEmbeddingError as e:
            raise EmbeddingError(f"Embedding generation failed: {e}")

    async def embed(self, item: NewsItem) -> EmbeddingResult:
        """
        Generate embedding for a news item and store in Qdrant.

        Args:
            item: NewsItem to embed

        Returns:
            EmbeddingResult with success status
        """
        start_time = time.time()
        item_id = str(item.id)

        try:
            # Prepare content
            content = self._prepare_content(item)

            if not content.strip():
                return EmbeddingResult(
                    item_id=item_id,
                    qdrant_id="",
                    success=False,
                    error="No content to embed"
                )

            # Generate embedding using Ollama
            embedding = await self._generate_embedding(content)

            # Store in Qdrant
            qdrant_id = str(uuid.uuid4())

            point = PointStruct(
                id=qdrant_id,
                vector=embedding,
                payload={
                    "news_item_id": item_id,
                    "title": item.title,
                    "source_type": item.source_type,
                    "source_name": item.source_name,
                    "url": item.url,
                    "categories": item.categories or [],
                    "published_at": item.published_at.isoformat() if item.published_at else None,
                    "collected_at": item.collected_at.isoformat() if item.collected_at else None,
                    "embedded_at": datetime.now(timezone.utc).isoformat(),
                }
            )

            self.qdrant.upsert(
                collection_name=self.COLLECTION_NAME,
                points=[point]
            )

            elapsed_ms = (time.time() - start_time) * 1000
            self._logger.debug(f"Embedded item {item_id[:8]} in {elapsed_ms:.0f}ms")

            return EmbeddingResult(
                item_id=item_id,
                qdrant_id=qdrant_id,
                success=True,
                embedding_time_ms=elapsed_ms
            )

        except Exception as e:
            elapsed_ms = (time.time() - start_time) * 1000
            self._logger.error(f"Embedding failed for {item_id[:8]}: {e}")

            return EmbeddingResult(
                item_id=item_id,
                qdrant_id="",
                success=False,
                error=str(e),
                embedding_time_ms=elapsed_ms
            )

    async def embed_batch(
        self,
        items: List[NewsItem],
        max_concurrent: int = 5
    ) -> List[EmbeddingResult]:
        """
        Embed a batch of news items.

        Args:
            items: List of NewsItem to embed
            max_concurrent: Max concurrent embedding requests

        Returns:
            List of EmbeddingResult
        """
        results = []
        semaphore = asyncio.Semaphore(max_concurrent)

        async def embed_with_semaphore(item):
            async with semaphore:
                return await self.embed(item)

        # Process in batches
        tasks = [embed_with_semaphore(item) for item in items]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Convert exceptions to results
        final_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                final_results.append(EmbeddingResult(
                    item_id=str(items[i].id),
                    qdrant_id="",
                    success=False,
                    error=str(result)
                ))
            else:
                final_results.append(result)

        return final_results

    def apply_qdrant_ids(self, items: List[NewsItem], results: List[EmbeddingResult]) -> None:
        """
        Apply Qdrant IDs to news items in-place.

        Args:
            items: List of NewsItem
            results: Corresponding EmbeddingResult list
        """
        result_map = {r.item_id: r.qdrant_id for r in results if r.success}
        for item in items:
            item_id = str(item.id)
            if item_id in result_map:
                item.qdrant_id = result_map[item_id]

    async def search_similar(
        self,
        query: str,
        limit: int = 10,
        source_type: Optional[str] = None,
        categories: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Search for similar news items.

        Args:
            query: Search query text
            limit: Max results to return
            source_type: Optional filter by source type
            categories: Optional filter by categories

        Returns:
            List of search results with scores
        """
        # Generate query embedding using Ollama
        embedding = await self._generate_embedding(query)

        # Build filter
        filter_conditions = []
        if source_type:
            filter_conditions.append(
                FieldCondition(key="source_type", match=MatchValue(value=source_type))
            )

        query_filter = None
        if filter_conditions:
            query_filter = Filter(must=filter_conditions)

        # Search
        results = self.qdrant.search(
            collection_name=self.COLLECTION_NAME,
            query_vector=embedding,
            limit=limit,
            query_filter=query_filter,
        )

        # Format results
        formatted = []
        for result in results:
            formatted.append({
                "news_item_id": result.payload.get("news_item_id"),
                "title": result.payload.get("title"),
                "source_name": result.payload.get("source_name"),
                "url": result.payload.get("url"),
                "categories": result.payload.get("categories", []),
                "score": result.score,
            })

        return formatted

    async def delete_embedding(self, item_id: str) -> bool:
        """
        Delete embedding for a news item.

        Args:
            item_id: NewsItem ID

        Returns:
            True if deleted successfully
        """
        try:
            # Find points with this item_id
            results = self.qdrant.scroll(
                collection_name=self.COLLECTION_NAME,
                scroll_filter=Filter(
                    must=[FieldCondition(key="news_item_id", match=MatchValue(value=item_id))]
                ),
                limit=10,
            )

            if results[0]:
                point_ids = [p.id for p in results[0]]
                self.qdrant.delete(
                    collection_name=self.COLLECTION_NAME,
                    points_selector=point_ids,
                )
                return True

            return False

        except Exception as e:
            self._logger.error(f"Error deleting embedding: {e}")
            return False

    def get_collection_stats(self) -> Dict[str, Any]:
        """Get statistics about the news_items collection."""
        try:
            info = self.qdrant.get_collection(self.COLLECTION_NAME)
            return {
                "collection_name": self.COLLECTION_NAME,
                "points_count": info.points_count,
                "vectors_count": info.vectors_count,
                "status": info.status,
                "embedding_dimensions": self.EMBEDDING_DIMENSIONS,
                "embedding_model": OllamaEmbeddings.MODEL,
            }
        except Exception as e:
            self._logger.error(f"Error getting collection stats: {e}")
            return {"error": str(e)}

    async def health_check(self) -> Dict[str, Any]:
        """Check health of embedding service."""
        ollama_healthy = await self.embeddings.health_check()

        try:
            collections = self.qdrant.get_collections()
            qdrant_healthy = True
        except Exception:
            qdrant_healthy = False

        return {
            "ollama": {
                "healthy": ollama_healthy,
                "model": OllamaEmbeddings.MODEL,
            },
            "qdrant": {
                "healthy": qdrant_healthy,
                "collection": self.COLLECTION_NAME,
            },
            "overall_healthy": ollama_healthy and qdrant_healthy,
        }
