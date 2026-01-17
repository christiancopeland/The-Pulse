"""
Local Embeddings Service using sentence-transformers.

Replaces Ollama embeddings with fully local, no-external-API embedding generation.
Uses the same interface as OllamaEmbeddings for drop-in replacement.

Model: all-mpnet-base-v2 (768 dimensions)
- Same dimensions as nomic-embed-text for Qdrant compatibility
- Runs entirely locally with no external dependencies
- GPU acceleration if available (CUDA/MPS)
"""

from typing import List, Optional
import asyncio
import time

from app.core.logging import get_logger

logger = get_logger(__name__)

# Lazy load the model to avoid import-time overhead
_model = None
_model_lock = asyncio.Lock()


class LocalEmbeddingError(Exception):
    """Exception raised for embedding errors."""
    pass


class LocalEmbeddings:
    """
    Generate embeddings using sentence-transformers.

    Uses all-mpnet-base-v2 model (768 dimensions) for semantic
    vector representation compatible with Qdrant.

    This is a drop-in replacement for OllamaEmbeddings.
    """

    MODEL_NAME = "all-mpnet-base-v2"
    MODEL = "all-mpnet-base-v2"  # Alias for backward compatibility
    DIMENSIONS = 768

    def __init__(self, model_name: Optional[str] = None):
        """
        Initialize local embeddings.

        Args:
            model_name: Optional model name override (default: all-mpnet-base-v2)
        """
        self.model_name = model_name or self.MODEL_NAME
        self._model = None
        self._logger = logger

    async def _get_model(self):
        """Lazy load the embedding model."""
        global _model

        if _model is not None:
            return _model

        async with _model_lock:
            # Double-check after acquiring lock
            if _model is not None:
                return _model

            try:
                from sentence_transformers import SentenceTransformer

                self._logger.info(f"Loading embedding model: {self.model_name}")
                start = time.time()

                # Load model in thread pool to avoid blocking
                loop = asyncio.get_event_loop()
                _model = await loop.run_in_executor(
                    None,
                    lambda: SentenceTransformer(self.model_name)
                )

                elapsed = time.time() - start
                self._logger.info(f"Embedding model loaded in {elapsed:.1f}s")

                return _model

            except ImportError:
                raise LocalEmbeddingError(
                    "sentence-transformers not installed. "
                    "Run: pip install sentence-transformers"
                )
            except Exception as e:
                raise LocalEmbeddingError(f"Failed to load embedding model: {e}")

    async def generate(self, text: str) -> List[float]:
        """
        Generate embedding for a single text.

        Args:
            text: Text to embed

        Returns:
            List of floats representing the embedding vector (768 dimensions)

        Raises:
            LocalEmbeddingError: If embedding generation fails
        """
        if not text or not text.strip():
            raise LocalEmbeddingError("Cannot generate embedding for empty text")

        start_time = time.time()

        try:
            model = await self._get_model()

            # Run encoding in thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            embedding = await loop.run_in_executor(
                None,
                lambda: model.encode(text, convert_to_numpy=True).tolist()
            )

            elapsed_ms = (time.time() - start_time) * 1000
            self._logger.debug(
                f"Generated embedding ({len(embedding)} dims) in {elapsed_ms:.0f}ms"
            )

            return embedding

        except LocalEmbeddingError:
            raise
        except Exception as e:
            raise LocalEmbeddingError(f"Embedding generation failed: {e}") from e

    async def generate_batch(
        self,
        texts: List[str],
        max_concurrent: int = 5
    ) -> List[List[float]]:
        """
        Generate embeddings for multiple texts.

        Note: sentence-transformers is efficient at batch processing,
        so we process all texts at once rather than with semaphores.

        Args:
            texts: List of texts to embed
            max_concurrent: Ignored (kept for interface compatibility)

        Returns:
            List of embedding vectors
        """
        if not texts:
            return []

        start_time = time.time()

        try:
            model = await self._get_model()

            # Filter out empty texts, keeping track of indices
            valid_texts = []
            valid_indices = []
            for i, text in enumerate(texts):
                if text and text.strip():
                    valid_texts.append(text)
                    valid_indices.append(i)

            if not valid_texts:
                return [[0.0] * self.DIMENSIONS for _ in texts]

            # Batch encode in thread pool
            loop = asyncio.get_event_loop()
            valid_embeddings = await loop.run_in_executor(
                None,
                lambda: model.encode(valid_texts, convert_to_numpy=True).tolist()
            )

            # Reconstruct full results with zero vectors for empty texts
            embeddings = [[0.0] * self.DIMENSIONS for _ in texts]
            for i, embedding in zip(valid_indices, valid_embeddings):
                embeddings[i] = embedding

            elapsed_ms = (time.time() - start_time) * 1000
            self._logger.debug(
                f"Generated {len(valid_texts)} embeddings in {elapsed_ms:.0f}ms "
                f"({elapsed_ms/len(valid_texts):.0f}ms/embedding)"
            )

            return embeddings

        except LocalEmbeddingError:
            raise
        except Exception as e:
            self._logger.error(f"Batch embedding failed: {e}")
            # Return zero vectors on failure
            return [[0.0] * self.DIMENSIONS for _ in texts]

    async def health_check(self) -> bool:
        """
        Check if the embedding model is loaded and working.

        Returns:
            True if healthy, False otherwise
        """
        try:
            model = await self._get_model()

            # Quick test embedding
            test_embedding = await self.generate("test")
            return len(test_embedding) == self.DIMENSIONS

        except Exception as e:
            self._logger.error(f"Health check failed: {e}")
            return False


# Backward compatibility aliases
OllamaEmbeddings = LocalEmbeddings
OllamaEmbeddingError = LocalEmbeddingError


# Singleton instance for easy access
_embeddings_instance: Optional[LocalEmbeddings] = None


def get_embeddings() -> LocalEmbeddings:
    """Get or create the global LocalEmbeddings instance."""
    global _embeddings_instance
    if _embeddings_instance is None:
        _embeddings_instance = LocalEmbeddings()
    return _embeddings_instance


async def generate_embedding(text: str) -> List[float]:
    """
    Convenience function to generate a single embedding.

    Args:
        text: Text to embed

    Returns:
        Embedding vector (768 dimensions)
    """
    return await get_embeddings().generate(text)


# Test function
async def _test_embeddings():
    """Test the local embeddings service."""
    print("Testing Local Embeddings...")

    embeddings = LocalEmbeddings()

    # Test health check
    print("\n1. Health check:")
    healthy = await embeddings.health_check()
    print(f"   Healthy: {healthy}")

    # Test single embedding
    print("\n2. Single embedding:")
    text = "The quick brown fox jumps over the lazy dog."
    embedding = await embeddings.generate(text)
    print(f"   Text: {text[:50]}...")
    print(f"   Dimensions: {len(embedding)}")
    print(f"   Sample values: {embedding[:5]}")

    # Test batch embedding
    print("\n3. Batch embedding:")
    texts = [
        "Hello world",
        "The Pulse is an intelligence platform",
        "Claude is a helpful AI assistant",
    ]
    batch_embeddings = await embeddings.generate_batch(texts)
    print(f"   Texts: {len(texts)}")
    print(f"   Embeddings: {len(batch_embeddings)}")
    for i, emb in enumerate(batch_embeddings):
        print(f"   [{i}] {len(emb)} dims, sample: {emb[:3]}")

    print("\nAll tests completed!")


if __name__ == "__main__":
    asyncio.run(_test_embeddings())
