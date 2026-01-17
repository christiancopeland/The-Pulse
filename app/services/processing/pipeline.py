"""
Main processing pipeline for The Pulse.

Orchestrates validation, ranking, entity extraction, relationship
detection, and embedding generation for collected news items.

Phase 3: Processing Pipeline
"""
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Set, Tuple
from datetime import datetime, timezone
import logging
import asyncio
import uuid as uuid_lib

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text

from app.models.news_item import NewsItem
from app.models.entities import TrackedEntity, EntityMention, EntityRelationship, RELATIONSHIP_TYPES
from .validator import ContentValidator, ValidationResult
from .ranker import RelevanceRanker, RankingResult
from .embedder import NewsItemEmbedder, EmbeddingResult

logger = logging.getLogger(__name__)

# Relationship indicators for pattern-based detection
RELATIONSHIP_PATTERNS = {
    "supports": ["supports", "endorses", "backs", "advocates for", "champions", "defends"],
    "opposes": ["opposes", "criticizes", "attacks", "condemns", "rejects", "denounces", "against"],
    "collaborates_with": ["works with", "partners with", "collaborates", "together with", "alongside", "met with", "meeting"],
    "leads": ["leads", "heads", "directs", "manages", "runs", "chairs"],
    "funds": ["funds", "finances", "invests in", "sponsors", "pays for"],
    "part_of": ["member of", "part of", "belongs to", "works for", "employed by", "joined"],
    "impacts": ["affects", "impacts", "influences", "changes", "shapes"],
    "responds_to": ["responds to", "reacted to", "answered", "replied to"],
    "regulates": ["regulates", "oversees", "monitors", "controls"],
}


@dataclass
class ProcessingStats:
    """Statistics from a processing run."""
    total_items: int = 0
    validated: int = 0
    validation_failed: int = 0
    ranked: int = 0
    entities_extracted: int = 0
    relationships_found: int = 0
    embedded: int = 0
    embedding_failed: int = 0
    processing_time_ms: float = 0.0

    def to_dict(self) -> dict:
        return {
            "total_items": self.total_items,
            "validated": self.validated,
            "validation_failed": self.validation_failed,
            "ranked": self.ranked,
            "entities_extracted": self.entities_extracted,
            "relationships_found": self.relationships_found,
            "embedded": self.embedded,
            "embedding_failed": self.embedding_failed,
            "processing_time_ms": round(self.processing_time_ms, 2),
        }


@dataclass
class ProcessingResult:
    """Result of processing a batch of items."""
    stats: ProcessingStats
    validation_results: Dict[str, ValidationResult] = field(default_factory=dict)
    ranking_results: List[RankingResult] = field(default_factory=list)
    embedding_results: List[EmbeddingResult] = field(default_factory=list)
    errors: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "stats": self.stats.to_dict(),
            "errors": self.errors[:10],  # Limit errors in response
        }


class ProcessingPipeline:
    """
    Orchestrates all processing steps for collected news items.

    Pipeline stages:
    1. Validation: Filter low-quality content
    2. Ranking: Calculate relevance scores
    3. Entity extraction: Find tracked entity mentions
    4. Relationship detection: Identify entity co-occurrences
    5. Embedding: Generate vectors for semantic search

    Each stage can be run independently or as part of the full pipeline.
    """

    def __init__(
        self,
        db_session: AsyncSession,
        openai_api_key: Optional[str] = None,
        strict_validation: bool = False,
        enable_embedding: bool = True,
    ):
        """
        Initialize pipeline.

        Args:
            db_session: Database session for entity operations
            openai_api_key: OpenAI API key for embeddings
            strict_validation: Use strict validation mode
            enable_embedding: Enable embedding generation (requires API key)
        """
        self.session = db_session
        self._logger = logging.getLogger(f"{__name__}.ProcessingPipeline")

        # Initialize components
        self.validator = ContentValidator(strict_mode=strict_validation)
        self.ranker = RelevanceRanker()
        self.embedder = NewsItemEmbedder(openai_api_key=openai_api_key) if enable_embedding else None

        self.enable_embedding = enable_embedding

        # Track entities for ranking and extraction
        self._tracked_entities: Set[str] = set()
        self._entity_id_map: Dict[str, str] = {}  # name_lower -> entity_id

    async def load_tracked_entities(self, user_id: Optional[str] = None) -> int:
        """
        Load tracked entities from database.

        Args:
            user_id: Optional user ID to filter entities

        Returns:
            Number of entities loaded
        """
        try:
            if user_id:
                stmt = select(TrackedEntity).where(TrackedEntity.user_id == user_id)
            else:
                stmt = select(TrackedEntity)

            result = await self.session.execute(stmt)
            entities = result.scalars().all()

            self._tracked_entities = {e.name_lower for e in entities}
            self._entity_id_map = {e.name_lower: str(e.entity_id) for e in entities}

            # Update ranker with tracked entities
            self.ranker.update_tracked_entities(self._tracked_entities)

            self._logger.info(f"Loaded {len(self._tracked_entities)} tracked entities")
            return len(self._tracked_entities)

        except Exception as e:
            self._logger.error(f"Error loading entities: {e}")
            return 0

    async def process_batch(
        self,
        items: List[NewsItem],
        skip_validation: bool = False,
        skip_embedding: bool = False,
    ) -> ProcessingResult:
        """
        Process a batch of news items through the full pipeline.

        Args:
            items: List of NewsItem to process
            skip_validation: Skip validation stage
            skip_embedding: Skip embedding stage

        Returns:
            ProcessingResult with stats and details
        """
        import time
        start_time = time.time()

        stats = ProcessingStats(total_items=len(items))
        result = ProcessingResult(stats=stats)

        if not items:
            return result

        self._logger.info(f"Processing batch of {len(items)} items")

        try:
            # Stage 1: Validation
            if not skip_validation:
                valid_items, validation_results = await self._stage_validation(items)
                result.validation_results = validation_results
                stats.validated = len(valid_items)
                stats.validation_failed = len(items) - len(valid_items)
            else:
                valid_items = items

            if not valid_items:
                self._logger.warning("No items passed validation")
                stats.processing_time_ms = (time.time() - start_time) * 1000
                return result

            # Stage 2: Ranking
            ranking_results = await self._stage_ranking(valid_items)
            result.ranking_results = ranking_results
            stats.ranked = len(ranking_results)

            # Apply scores to items
            self.ranker.apply_scores(valid_items, ranking_results)

            # Stage 3: Entity extraction
            entity_count = await self._stage_entity_extraction(valid_items)
            stats.entities_extracted = entity_count

            # Stage 4: Relationship detection
            relationship_count = await self._stage_relationship_detection(valid_items)
            stats.relationships_found = relationship_count

            # Stage 5: Embedding
            if self.enable_embedding and not skip_embedding and self.embedder:
                embedding_results = await self._stage_embedding(valid_items)
                result.embedding_results = embedding_results
                stats.embedded = sum(1 for r in embedding_results if r.success)
                stats.embedding_failed = sum(1 for r in embedding_results if not r.success)

                # Apply Qdrant IDs
                self.embedder.apply_qdrant_ids(valid_items, embedding_results)

            # Mark items as processed and save
            await self._update_items(valid_items)

            stats.processing_time_ms = (time.time() - start_time) * 1000
            self._logger.info(
                f"Batch processing complete: {stats.validated} valid, "
                f"{stats.entities_extracted} entities, {stats.embedded} embedded "
                f"in {stats.processing_time_ms:.0f}ms"
            )

        except Exception as e:
            self._logger.error(f"Pipeline error: {e}", exc_info=True)
            result.errors.append({"error": str(e), "stage": "pipeline"})

        return result

    async def _stage_validation(
        self,
        items: List[NewsItem]
    ) -> Tuple[List[NewsItem], Dict[str, ValidationResult]]:
        """Stage 1: Validate content quality."""
        self._logger.debug("Running validation stage")

        results = await self.validator.validate_batch(items)
        valid_items = self.validator.filter_valid(items, results)

        return valid_items, results

    async def _stage_ranking(self, items: List[NewsItem]) -> List[RankingResult]:
        """Stage 2: Calculate relevance scores."""
        self._logger.debug("Running ranking stage")

        results = await self.ranker.rank_batch(items)
        return results

    async def _stage_entity_extraction(self, items: List[NewsItem]) -> int:
        """
        Stage 3: Extract entity mentions from items.

        For each tracked entity, finds mentions in item content
        and creates EntityMention records.
        """
        self._logger.debug("Running entity extraction stage")

        if not self._tracked_entities:
            return 0

        total_mentions = 0

        for item in items:
            try:
                mentions = await self._extract_entities_from_item(item)
                total_mentions += mentions
            except Exception as e:
                self._logger.warning(f"Entity extraction failed for {item.id}: {e}")

        if total_mentions > 0:
            await self.session.commit()

        return total_mentions

    async def _extract_entities_from_item(self, item: NewsItem) -> int:
        """Extract entity mentions from a single news item."""
        content = f"{item.title or ''} {item.content or ''} {item.summary or ''}"
        content_lower = content.lower()

        if not content_lower.strip():
            return 0

        mentions_added = 0

        for entity_name_lower in self._tracked_entities:
            if entity_name_lower not in content_lower:
                continue

            entity_id = self._entity_id_map.get(entity_name_lower)
            if not entity_id:
                continue

            # Find all occurrences and extract context
            contexts = self._extract_contexts(content, entity_name_lower)

            for context in contexts:
                try:
                    mention = EntityMention(
                        entity_id=uuid_lib.UUID(entity_id),
                        news_item_id=item.id,  # Using news_item_id for NewsItem
                        user_id=await self._get_entity_user_id(entity_id),
                        chunk_id=f"{item.id}_0",
                        context=context[:500],  # Limit context length
                    )
                    self.session.add(mention)
                    mentions_added += 1

                except Exception as e:
                    self._logger.debug(f"Could not create mention: {e}")

        return mentions_added

    async def _get_entity_user_id(self, entity_id: str) -> uuid_lib.UUID:
        """Get user_id for an entity."""
        try:
            stmt = select(TrackedEntity.user_id).where(
                TrackedEntity.entity_id == uuid_lib.UUID(entity_id)
            )
            result = await self.session.execute(stmt)
            user_id = result.scalar_one_or_none()
            return user_id
        except Exception:
            # Return a default if not found
            return uuid_lib.UUID('00000000-0000-0000-0000-000000000000')

    def _extract_contexts(
        self,
        text: str,
        term: str,
        context_chars: int = 200
    ) -> List[str]:
        """Extract context windows around term occurrences."""
        contexts = []
        text_lower = text.lower()
        term_lower = term.lower()

        start = 0
        while True:
            pos = text_lower.find(term_lower, start)
            if pos == -1:
                break

            # Get context window
            ctx_start = max(0, pos - context_chars)
            ctx_end = min(len(text), pos + len(term) + context_chars)

            context = text[ctx_start:ctx_end]

            # Add ellipsis if truncated
            if ctx_start > 0:
                context = "..." + context
            if ctx_end < len(text):
                context = context + "..."

            contexts.append(context.strip())
            start = pos + 1

        return contexts

    async def _stage_relationship_detection(self, items: List[NewsItem]) -> int:
        """
        Stage 4: Detect relationships between entities.

        Entities that co-occur in the same item are considered related.
        Updates relationship mention counts and timestamps.
        """
        self._logger.debug("Running relationship detection stage")

        if len(self._tracked_entities) < 2:
            return 0

        relationships_found = 0

        for item in items:
            try:
                relationships = await self._detect_relationships_in_item(item)
                relationships_found += relationships
            except Exception as e:
                self._logger.warning(f"Relationship detection failed for {item.id}: {e}")

        if relationships_found > 0:
            await self.session.commit()

        return relationships_found

    async def _detect_relationships_in_item(self, item: NewsItem) -> int:
        """Detect entity co-occurrences in a single item with relationship type inference."""
        content = f"{item.title or ''} {item.content or ''} {item.summary or ''}"
        content_lower = content.lower()

        # Find which tracked entities appear in this item
        present_entities = [
            entity for entity in self._tracked_entities
            if entity in content_lower
        ]

        if len(present_entities) < 2:
            return 0

        relationships_added = 0

        # Split content into sentences for context-aware relationship detection
        sentences = content.replace("!", ".").replace("?", ".").split(".")

        # Create/update relationships for all pairs
        for i, entity1 in enumerate(present_entities):
            for entity2 in present_entities[i+1:]:
                try:
                    source_id = self._entity_id_map.get(entity1)
                    target_id = self._entity_id_map.get(entity2)

                    if not source_id or not target_id:
                        continue

                    # Find sentences where both entities co-occur
                    shared_contexts = []
                    for sentence in sentences:
                        sentence_lower = sentence.lower()
                        if entity1 in sentence_lower and entity2 in sentence_lower:
                            shared_contexts.append(sentence.strip())

                    # Infer relationship type from context
                    rel_type = self._infer_relationship_type(entity1, entity2, shared_contexts)

                    # Check if relationship exists
                    existing = await self._get_or_create_relationship(
                        source_id, target_id, relationship_type=rel_type
                    )

                    if existing:
                        relationships_added += 1

                except Exception as e:
                    self._logger.debug(f"Could not create relationship: {e}")

        return relationships_added

    def _infer_relationship_type(
        self,
        entity1: str,
        entity2: str,
        contexts: List[str]
    ) -> str:
        """
        Infer relationship type from context using pattern matching.

        Args:
            entity1: First entity name (lowercase)
            entity2: Second entity name (lowercase)
            contexts: List of sentences where both entities appear

        Returns:
            Relationship type string
        """
        if not contexts:
            return "co_occurrence"

        # Check each context for relationship indicators
        combined_context = " ".join(contexts).lower()

        for rel_type, indicators in RELATIONSHIP_PATTERNS.items():
            for indicator in indicators:
                if indicator in combined_context:
                    return rel_type

        # Default to co_occurrence if no pattern matched
        return "co_occurrence"

    async def _get_or_create_relationship(
        self,
        source_id: str,
        target_id: str,
        relationship_type: str = "co_occurrence"
    ) -> Optional[EntityRelationship]:
        """Get existing relationship or create new one with inferred type."""
        try:
            # Validate relationship type
            if relationship_type not in RELATIONSHIP_TYPES and relationship_type != "co_occurrence":
                relationship_type = "associated_with"

            # Check for existing relationship (in either direction) with same type
            stmt = select(EntityRelationship).where(
                ((EntityRelationship.source_entity_id == uuid_lib.UUID(source_id)) &
                 (EntityRelationship.target_entity_id == uuid_lib.UUID(target_id)) &
                 (EntityRelationship.relationship_type == relationship_type)) |
                ((EntityRelationship.source_entity_id == uuid_lib.UUID(target_id)) &
                 (EntityRelationship.target_entity_id == uuid_lib.UUID(source_id)) &
                 (EntityRelationship.relationship_type == relationship_type))
            )
            result = await self.session.execute(stmt)
            existing = result.scalar_one_or_none()

            if existing:
                # Update existing relationship
                existing.last_seen = datetime.now(timezone.utc)
                existing.mention_count = (existing.mention_count or 0) + 1
                # Increase confidence with more mentions (max 0.95)
                # Pattern-matched relationships start with higher confidence
                base_confidence = 0.4 if relationship_type != "co_occurrence" else 0.3
                existing.confidence = min(0.95, base_confidence + (existing.mention_count * 0.05))
                return existing
            else:
                # Create new relationship
                # Pattern-matched relationships get higher initial confidence
                initial_confidence = 0.5 if relationship_type != "co_occurrence" else 0.3
                description = f"Entities mentioned together in news content"
                if relationship_type != "co_occurrence":
                    description = f"Relationship detected via pattern matching: {relationship_type}"

                relationship = EntityRelationship(
                    source_entity_id=uuid_lib.UUID(source_id),
                    target_entity_id=uuid_lib.UUID(target_id),
                    relationship_type=relationship_type,
                    description=description,
                    confidence=initial_confidence,
                )
                self.session.add(relationship)
                return relationship

        except Exception as e:
            self._logger.debug(f"Relationship error: {e}")
            return None

    async def _stage_embedding(self, items: List[NewsItem]) -> List[EmbeddingResult]:
        """Stage 5: Generate embeddings for semantic search."""
        self._logger.debug("Running embedding stage")

        if not self.embedder:
            return []

        # Only embed items with enough content
        items_to_embed = [
            item for item in items
            if (item.content or item.summary or "").strip()
        ]

        if not items_to_embed:
            return []

        results = await self.embedder.embed_batch(items_to_embed, max_concurrent=3)
        return results

    async def _update_items(self, items: List[NewsItem]) -> None:
        """Mark items as processed and save to database."""
        for item in items:
            item.processed = 1  # Mark as processed

        try:
            await self.session.commit()
        except Exception as e:
            self._logger.error(f"Error saving items: {e}")
            await self.session.rollback()

    async def process_pending_items(
        self,
        limit: int = 100,
        user_id: Optional[str] = None,
    ) -> ProcessingResult:
        """
        Process pending (unprocessed) news items.

        Args:
            limit: Max items to process
            user_id: Optional user ID for entity filtering

        Returns:
            ProcessingResult
        """
        # Load tracked entities
        await self.load_tracked_entities(user_id)

        # Get pending items
        stmt = select(NewsItem).where(
            NewsItem.processed == 0
        ).order_by(
            NewsItem.collected_at.desc()
        ).limit(limit)

        result = await self.session.execute(stmt)
        items = list(result.scalars().all())

        if not items:
            self._logger.info("No pending items to process")
            return ProcessingResult(stats=ProcessingStats())

        return await self.process_batch(items)

    async def reprocess_items(
        self,
        item_ids: List[str],
        user_id: Optional[str] = None,
    ) -> ProcessingResult:
        """
        Reprocess specific items.

        Args:
            item_ids: List of NewsItem IDs to reprocess
            user_id: Optional user ID for entity filtering

        Returns:
            ProcessingResult
        """
        # Load tracked entities
        await self.load_tracked_entities(user_id)

        # Get items
        stmt = select(NewsItem).where(
            NewsItem.id.in_([uuid_lib.UUID(id) for id in item_ids])
        )

        result = await self.session.execute(stmt)
        items = list(result.scalars().all())

        return await self.process_batch(items)
