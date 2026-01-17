"""
Ollama-based embedding service for The Pulse.

Replaces OpenAI text-embedding-3-large with Ollama's nomic-embed-text
for fully local, open-source embeddings compatible with Qdrant.

Model: nomic-embed-text
Dimensions: 768
"""
from typing import List, Optional
import httpx
import asyncio
import logging
import os
import time

logger = logging.getLogger(__name__)


class OllamaEmbeddingError(Exception):
    """Exception raised for embedding errors."""
    pass


class OllamaEmbeddings:
    """
    Generate embeddings using Ollama's embedding API.

    Uses nomic-embed-text model (768 dimensions) for semantic
    vector representation compatible with Qdrant.
    """

    MODEL = "nomic-embed-text"
    DIMENSIONS = 768

    def __init__(
        self,
        api_url: Optional[str] = None,
        timeout: float = 60.0
    ):
        """
        Initialize Ollama embeddings client.

        Args:
            api_url: Ollama API URL (default: http://localhost:11434)
            timeout: Request timeout in seconds
        """
        self.api_url = api_url or os.getenv("OLLAMA_HOST", "http://localhost:11434")
        self.embed_endpoint = f"{self.api_url}/api/embed"
        self.timeout = timeout
        self._logger = logging.getLogger(f"{__name__}.OllamaEmbeddings")

    async def generate(self, text: str) -> List[float]:
        """
        Generate embedding for a single text.

        Args:
            text: Text to embed

        Returns:
            List of floats representing the embedding vector (768 dimensions)

        Raises:
            OllamaEmbeddingError: If embedding generation fails
        """
        if not text or not text.strip():
            raise OllamaEmbeddingError("Cannot generate embedding for empty text")

        start_time = time.time()

        payload = {
            "model": self.MODEL,
            "input": text
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(self.embed_endpoint, json=payload)

                if response.status_code != 200:
                    error_msg = f"Ollama embedding error: {response.status_code}"
                    try:
                        error_data = response.json()
                        error_msg += f" - {error_data.get('error', 'Unknown error')}"
                    except:
                        pass
                    raise OllamaEmbeddingError(error_msg)

                result = response.json()

                # Ollama returns embeddings in "embeddings" array
                # For single input, we get back a list with one embedding
                embeddings = result.get("embeddings", [])

                if not embeddings:
                    raise OllamaEmbeddingError("No embeddings returned from Ollama")

                embedding = embeddings[0]

                elapsed_ms = (time.time() - start_time) * 1000
                self._logger.debug(
                    f"Generated embedding ({len(embedding)} dims) in {elapsed_ms:.0f}ms"
                )

                return embedding

        except httpx.TimeoutException as e:
            raise OllamaEmbeddingError(
                f"Timeout generating embedding after {self.timeout}s"
            ) from e
        except httpx.ConnectError as e:
            raise OllamaEmbeddingError(
                f"Cannot connect to Ollama at {self.api_url}. Is Ollama running?"
            ) from e
        except OllamaEmbeddingError:
            raise
        except Exception as e:
            raise OllamaEmbeddingError(f"Embedding generation failed: {e}") from e

    async def generate_batch(
        self,
        texts: List[str],
        max_concurrent: int = 5
    ) -> List[List[float]]:
        """
        Generate embeddings for multiple texts.

        Args:
            texts: List of texts to embed
            max_concurrent: Maximum concurrent requests

        Returns:
            List of embedding vectors
        """
        if not texts:
            return []

        semaphore = asyncio.Semaphore(max_concurrent)

        async def embed_with_semaphore(text: str) -> List[float]:
            async with semaphore:
                return await self.generate(text)

        tasks = [embed_with_semaphore(t) for t in texts]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Process results, keeping track of failures
        embeddings = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                self._logger.error(f"Failed to embed text {i}: {result}")
                # Return zero vector for failed embeddings
                embeddings.append([0.0] * self.DIMENSIONS)
            else:
                embeddings.append(result)

        return embeddings

    async def health_check(self) -> bool:
        """
        Check if Ollama is running and the embedding model is available.

        Returns:
            True if healthy, False otherwise
        """
        try:
            # Check if model is available by listing models
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{self.api_url}/api/tags")

                if response.status_code != 200:
                    return False

                models = response.json().get("models", [])
                model_names = [m.get("name", "") for m in models]

                # Check if nomic-embed-text is available (may have version suffix)
                has_model = any(self.MODEL in name for name in model_names)

                if not has_model:
                    self._logger.warning(
                        f"Model {self.MODEL} not found. Available: {model_names}"
                    )
                    self._logger.info(
                        f"Run 'ollama pull {self.MODEL}' to download the model"
                    )

                return has_model

        except Exception as e:
            self._logger.error(f"Health check failed: {e}")
            return False


# Singleton instance for easy access
_embeddings_instance: Optional[OllamaEmbeddings] = None


def get_embeddings() -> OllamaEmbeddings:
    """Get or create the global OllamaEmbeddings instance."""
    global _embeddings_instance
    if _embeddings_instance is None:
        _embeddings_instance = OllamaEmbeddings()
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
