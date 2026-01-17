"""
Processing pipeline for The Pulse collection engine.

This module provides content processing capabilities for collected news items:
- Content validation and filtering
- Relevance ranking and scoring
- Embedding generation for semantic search
- Entity extraction and relationship detection
- Full processing pipeline orchestration

Phase 3 of The Pulse Integration Plan.
"""
from .validator import ContentValidator, ValidationResult
from .ranker import RelevanceRanker
from .embedder import NewsItemEmbedder
from .pipeline import ProcessingPipeline

__all__ = [
    "ContentValidator",
    "ValidationResult",
    "RelevanceRanker",
    "NewsItemEmbedder",
    "ProcessingPipeline",
]
