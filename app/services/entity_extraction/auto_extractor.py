"""
Automatic Entity Extraction and Tracking Service.

Integrates GLiNER extraction and WikiData linking with the existing
EntityTrackingService for automated entity discovery and tracking
from news items and documents.

Features:
- Automatic entity extraction from new content
- WikiData disambiguation for extracted entities
- Integration with existing TrackedEntity/EntityMention models
- Batch processing for efficiency
- Confidence-based filtering
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Set, Tuple
from uuid import UUID
import uuid

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text

from app.core.logging import get_logger
from app.models.entities import TrackedEntity, EntityMention, EntityRelationship, RELATIONSHIP_TYPES
from app.models.news_item import NewsItem

from .gliner_extractor import IntelligenceEntityExtractor, ExtractedEntity
from .wikidata_linker import WikiDataLinker, LinkedEntity

logger = get_logger(__name__)


@dataclass
class RelationshipExtractionResult:
    """Result of relationship extraction from content."""
    source_id: UUID
    source_type: str
    relationships_extracted: int
    relationships_saved: int
    processing_time_ms: float = 0.0


@dataclass
class ExtractionResult:
    """Result of entity extraction from a single item."""
    source_id: UUID
    source_type: str  # 'news_item', 'document', 'news_article'
    extracted_entities: List[ExtractedEntity]
    linked_entities: Dict[str, Optional[LinkedEntity]]
    new_entities_created: int = 0
    mentions_created: int = 0
    processing_time_ms: float = 0.0


@dataclass
class BatchExtractionResult:
    """Result of batch entity extraction."""
    total_items: int
    items_processed: int
    total_entities_extracted: int
    unique_entities: int
    new_entities_created: int
    mentions_created: int
    errors: List[str] = field(default_factory=list)
    processing_time_seconds: float = 0.0


class AutoEntityExtractor:
    """
    Automatic entity extraction and tracking service.

    Combines GLiNER extraction with WikiData linking to automatically
    discover and track entities from content.

    Usage:
        extractor = AutoEntityExtractor(db_session, user_id)

        # Extract from single news item
        result = await extractor.extract_from_news_item(news_item_id)

        # Batch extract from recent news
        batch_result = await extractor.batch_extract_recent(hours=24)

        # Extract and auto-track high-confidence entities
        await extractor.extract_and_track(
            content="Putin met Xi in Moscow...",
            source_id=item_id,
            source_type="news_item",
            auto_track_threshold=0.8
        )
    """

    # Entity types to extract
    EXTRACT_TYPES = [
        "PERSON",
        "ORGANIZATION",
        "GOVERNMENT_AGENCY",
        "MILITARY_UNIT",
        "LOCATION",
        "POLITICAL_PARTY",
        "EVENT",
    ]

    # Minimum confidence for extraction
    MIN_EXTRACTION_CONFIDENCE = 0.5

    # Minimum confidence for auto-tracking
    MIN_TRACK_CONFIDENCE = 0.7

    # Minimum confidence for WikiData linking
    MIN_LINK_CONFIDENCE = 0.6

    # Sentinel value to distinguish "not provided" from "explicitly None"
    _NOT_PROVIDED = object()

    def __init__(
        self,
        db_session: AsyncSession,
        user_id: Optional[UUID] = None,
        extractor: Optional[IntelligenceEntityExtractor] = None,
        linker: Optional[WikiDataLinker] = None,
        wikidata_linker: Optional[WikiDataLinker] = _NOT_PROVIDED
    ):
        """
        Initialize the auto-extractor.

        Args:
            db_session: SQLAlchemy async session
            user_id: Owner user ID for tracked entities
            extractor: Custom GLiNER extractor instance
            linker: Custom WikiData linker instance (deprecated, use wikidata_linker)
            wikidata_linker: WikiData linker instance. Pass None to disable WikiData linking.
        """
        self.db = db_session
        self.user_id = user_id
        self.extractor = extractor or IntelligenceEntityExtractor(
            entity_types=self.EXTRACT_TYPES
        )

        # Determine linker: wikidata_linker takes precedence if provided
        if wikidata_linker is not self._NOT_PROVIDED:
            # wikidata_linker was explicitly provided (could be None to disable)
            self.linker = wikidata_linker
        elif linker is not None:
            # Use legacy linker parameter
            self.linker = linker
        else:
            # Create default linker
            self.linker = WikiDataLinker()

    async def extract_from_text(
        self,
        text: str,
        include_context: bool = True,
        link_to_wikidata: bool = True
    ) -> Tuple[List[ExtractedEntity], Dict[str, Optional[LinkedEntity]]]:
        """
        Extract and optionally link entities from text.

        Args:
            text: Text to process
            include_context: Include surrounding context in results
            link_to_wikidata: Attempt to link entities to WikiData

        Returns:
            Tuple of (extracted entities, WikiData links)
        """
        # Extract entities
        entities = await self.extractor.extract_async(
            text,
            threshold=self.MIN_EXTRACTION_CONFIDENCE,
            include_context=include_context
        )

        # Link to WikiData if requested and linker is available
        linked: Dict[str, Optional[LinkedEntity]] = {}
        if link_to_wikidata and entities and self.linker is not None:
            # Get unique entity texts
            unique_texts = list(set(e.normalized for e in entities))

            # Get entity types for linking
            text_to_type = {}
            for e in entities:
                if e.normalized not in text_to_type:
                    text_to_type[e.normalized] = e.entity_type

            # Link entities
            for entity_text in unique_texts:
                try:
                    entity_type = text_to_type.get(entity_text)
                    link_result = await self.linker.link_entity(
                        entity_text,
                        entity_type=entity_type,
                        min_confidence=self.MIN_LINK_CONFIDENCE
                    )
                    linked[entity_text] = link_result
                except Exception as e:
                    logger.warning(f"WikiData linking failed for '{entity_text}': {e}")
                    linked[entity_text] = None

        return entities, linked

    async def extract_from_news_item(
        self,
        news_item_id: UUID,
        auto_track: bool = False,
        auto_track_threshold: float = MIN_TRACK_CONFIDENCE
    ) -> ExtractionResult:
        """
        Extract entities from a news item.

        Args:
            news_item_id: ID of the news item
            auto_track: Automatically create TrackedEntity for high-confidence entities
            auto_track_threshold: Confidence threshold for auto-tracking

        Returns:
            ExtractionResult with extraction details
        """
        start_time = datetime.now()

        # Fetch news item
        result = await self.db.execute(
            select(NewsItem).where(NewsItem.id == news_item_id)
        )
        news_item = result.scalar_one_or_none()

        if not news_item:
            raise ValueError(f"News item not found: {news_item_id}")

        # Combine title and content for extraction
        text = f"{news_item.title or ''}\n\n{news_item.content or news_item.summary or ''}"

        # Extract entities
        entities, linked = await self.extract_from_text(text)

        # Auto-track if enabled
        new_entities = 0
        mentions_created = 0

        if auto_track and self.user_id and entities:
            new_entities, mentions_created = await self._auto_track_entities(
                entities=entities,
                linked=linked,
                source_id=news_item_id,
                source_type="news_item",
                threshold=auto_track_threshold
            )

        elapsed = (datetime.now() - start_time).total_seconds() * 1000

        return ExtractionResult(
            source_id=news_item_id,
            source_type="news_item",
            extracted_entities=entities,
            linked_entities=linked,
            new_entities_created=new_entities,
            mentions_created=mentions_created,
            processing_time_ms=elapsed
        )

    async def batch_extract_recent(
        self,
        hours: int = 24,
        limit: int = 100,
        auto_track: bool = False,
        auto_track_threshold: float = MIN_TRACK_CONFIDENCE,
        progress_callback: Optional[Callable[[int, int], Any]] = None
    ) -> BatchExtractionResult:
        """
        Batch extract entities from recent news items.

        Args:
            hours: Time window in hours
            limit: Maximum items to process
            auto_track: Automatically track high-confidence entities
            auto_track_threshold: Threshold for auto-tracking
            progress_callback: Optional async callback(processed, total) for progress updates

        Returns:
            BatchExtractionResult with summary
        """
        start_time = datetime.now()
        errors = []

        # Fetch recent unprocessed news items
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

        query = text("""
            SELECT id FROM news_items
            WHERE collected_at >= :cutoff
            AND processed = 0
            ORDER BY collected_at DESC
            LIMIT :limit
        """)

        result = await self.db.execute(query, {"cutoff": cutoff, "limit": limit})
        item_ids = [row[0] for row in result.fetchall()]

        total_items = len(item_ids)
        total_entities = 0
        unique_entities: Set[str] = set()
        new_entities = 0
        mentions = 0

        for i, item_id in enumerate(item_ids):
            # Report progress
            if progress_callback:
                try:
                    await progress_callback(i, total_items)
                except Exception as e:
                    logger.debug(f"Progress callback error: {e}")

            try:
                extraction = await self.extract_from_news_item(
                    item_id,
                    auto_track=auto_track,
                    auto_track_threshold=auto_track_threshold
                )

                total_entities += len(extraction.extracted_entities)
                unique_entities.update(e.normalized for e in extraction.extracted_entities)
                new_entities += extraction.new_entities_created
                mentions += extraction.mentions_created

            except Exception as e:
                error_msg = f"Failed to process {item_id}: {e}"
                logger.error(error_msg)
                errors.append(error_msg)

        # Final progress update
        if progress_callback:
            try:
                await progress_callback(total_items, total_items)
            except Exception as e:
                logger.debug(f"Progress callback error: {e}")

        elapsed = (datetime.now() - start_time).total_seconds()

        return BatchExtractionResult(
            total_items=total_items,
            items_processed=total_items - len(errors),
            total_entities_extracted=total_entities,
            unique_entities=len(unique_entities),
            new_entities_created=new_entities,
            mentions_created=mentions,
            errors=errors,
            processing_time_seconds=elapsed
        )

    async def _auto_track_entities(
        self,
        entities: List[ExtractedEntity],
        linked: Dict[str, Optional[LinkedEntity]],
        source_id: UUID,
        source_type: str,
        threshold: float
    ) -> Tuple[int, int]:
        """
        Auto-track high-confidence entities and create mentions.

        Uses WikiData QID-based deduplication when available, falling back
        to name-based matching. Per-entity error handling prevents one
        failed entity from blocking all subsequent entities in the batch.

        Returns:
            Tuple of (new entities created, mentions created)
        """
        new_entities = 0
        mentions_created = 0

        # Filter by confidence
        high_conf_entities = [e for e in entities if e.confidence >= threshold]

        for extracted in high_conf_entities:
            try:
                # Get or create TrackedEntity
                entity_name = extracted.normalized
                entity_type = extracted.entity_type

                # Use WikiData label if available
                wiki_link = linked.get(entity_name)
                wikidata_id = None
                if wiki_link:
                    entity_name = wiki_link.label
                    wikidata_id = wiki_link.wikidata_id
                    # Override type if WikiData provides better info
                    if wiki_link.entity_type != "UNKNOWN":
                        entity_type = wiki_link.entity_type

                # Step 1: Try to find by WikiData QID first (best deduplication)
                tracked_entity = None
                if wikidata_id:
                    tracked_entity = await self._find_entity_by_wikidata_id(wikidata_id)

                # Step 2: Fall back to name-based matching
                if not tracked_entity:
                    result = await self.db.execute(
                        select(TrackedEntity).where(
                            TrackedEntity.user_id == self.user_id,
                            TrackedEntity.name_lower == entity_name.lower()
                        )
                    )
                    tracked_entity = result.scalar_one_or_none()

                entity_created = False
                if not tracked_entity:
                    # Create new tracked entity
                    metadata = {
                        "auto_extracted": True,
                        "extraction_confidence": extracted.confidence,
                        "source": extracted.source,
                    }

                    if wiki_link:
                        metadata["wikidata_id"] = wiki_link.wikidata_id
                        metadata["wikidata_description"] = wiki_link.description
                        metadata["wikipedia_url"] = wiki_link.wikipedia_url
                        metadata["canonical_name"] = wiki_link.label
                        metadata["aliases"] = wiki_link.aliases

                    tracked_entity = TrackedEntity(
                        entity_id=uuid.uuid4(),
                        user_id=self.user_id,
                        name=entity_name,
                        name_lower=entity_name.lower(),
                        entity_type=entity_type,
                        created_at=datetime.now(timezone.utc).isoformat(),
                        entity_metadata=metadata
                    )
                    self.db.add(tracked_entity)
                    # Flush to ensure entity is in DB before creating mentions
                    await self.db.flush()
                    entity_created = True

                # Create mention
                mention_kwargs = {
                    "mention_id": uuid.uuid4(),
                    "entity_id": tracked_entity.entity_id,
                    "user_id": self.user_id,
                    "chunk_id": f"auto_{extracted.start}_{extracted.end}",
                    "context": extracted.context or extracted.text,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }

                # Set source ID based on type
                if source_type == "news_item":
                    mention_kwargs["news_item_id"] = source_id
                elif source_type == "document":
                    mention_kwargs["document_id"] = source_id
                elif source_type == "news_article":
                    mention_kwargs["news_article_id"] = source_id

                mention = EntityMention(**mention_kwargs)
                self.db.add(mention)

                # Commit this entity+mention as a unit
                await self.db.commit()

                if entity_created:
                    new_entities += 1
                mentions_created += 1

            except Exception as e:
                # Rollback failed entity and continue with next
                await self.db.rollback()
                logger.warning(f"Failed to track entity '{extracted.normalized}': {e}")
                continue

        return new_entities, mentions_created

    async def _find_entity_by_wikidata_id(self, wikidata_id: str) -> Optional[TrackedEntity]:
        """
        Find an existing entity by WikiData QID.

        This enables deduplication across different name variations of the
        same real-world entity (e.g., "Joe Biden" vs "Joseph R. Biden").

        Args:
            wikidata_id: The WikiData QID (e.g., "Q6279")

        Returns:
            TrackedEntity if found, None otherwise
        """
        try:
            # Query entities where metadata contains matching wikidata_id
            # Using PostgreSQL JSON operators
            result = await self.db.execute(
                select(TrackedEntity).where(
                    TrackedEntity.user_id == self.user_id,
                    TrackedEntity.entity_metadata['wikidata_id'].astext == wikidata_id
                )
            )
            return result.scalar_one_or_none()
        except Exception as e:
            logger.debug(f"WikiData QID lookup failed for {wikidata_id}: {e}")
            return None

    async def extract_relationships(
        self,
        text: str,
        entities: Optional[List[ExtractedEntity]] = None
    ) -> List[Dict[str, Any]]:
        """
        Extract relationships between entities in text.

        Uses co-occurrence within sentences to infer relationships.

        Args:
            text: Text to analyze
            entities: Pre-extracted entities (optional)

        Returns:
            List of relationship dicts
        """
        if entities is None:
            entities, _ = await self.extract_from_text(text, link_to_wikidata=False)

        if len(entities) < 2:
            return []

        relationships = []

        # Split into sentences
        sentences = text.replace("!", ".").replace("?", ".").split(".")

        # Find co-occurring entities in sentences
        for sentence in sentences:
            sentence_lower = sentence.lower()
            sentence_entities = [
                e for e in entities
                if e.normalized.lower() in sentence_lower
            ]

            # Create relationships for co-occurring entities
            for i, e1 in enumerate(sentence_entities):
                for e2 in sentence_entities[i + 1:]:
                    # Determine relationship type based on entity types
                    rel_type = self._infer_relationship_type(e1, e2, sentence)

                    relationships.append({
                        "source": e1.normalized,
                        "source_type": e1.entity_type,
                        "target": e2.normalized,
                        "target_type": e2.entity_type,
                        "relationship_type": rel_type,
                        "context": sentence.strip(),
                        "confidence": min(e1.confidence, e2.confidence) * 0.8
                    })

        return relationships

    def _infer_relationship_type(
        self,
        entity1: ExtractedEntity,
        entity2: ExtractedEntity,
        context: str
    ) -> str:
        """Infer relationship type from entity types and context."""
        context_lower = context.lower()

        # Check for explicit relationship indicators
        if any(word in context_lower for word in ["met with", "meeting", "talks"]):
            return "collaborates_with"
        if any(word in context_lower for word in ["attack", "strike", "target"]):
            return "opposes"
        if any(word in context_lower for word in ["support", "aid", "assist"]):
            return "supports"
        if any(word in context_lower for word in ["lead", "head", "chair"]):
            return "leads"
        if any(word in context_lower for word in ["member", "part of", "belongs"]):
            return "part_of"

        # Default based on entity types
        if entity1.entity_type == "PERSON" and entity2.entity_type == "ORGANIZATION":
            return "part_of"
        if entity1.entity_type == "LOCATION" and entity2.entity_type in ["PERSON", "ORGANIZATION"]:
            return "impacts"

        return "collaborates_with"

    async def extract_and_save_relationships(
        self,
        text: str,
        source_id: UUID,
        source_type: str,
        entities: Optional[List[ExtractedEntity]] = None
    ) -> RelationshipExtractionResult:
        """
        Extract relationships from text and save them to the database.

        This method bridges the gap between extraction and persistence,
        converting extracted relationship dicts into EntityRelationship records.

        Args:
            text: Text to analyze for relationships
            source_id: ID of the source document/news item
            source_type: Type of source ('news_item', 'document', etc.)
            entities: Pre-extracted entities (optional)

        Returns:
            RelationshipExtractionResult with stats
        """
        start_time = datetime.now()

        # Extract relationships
        relationships = await self.extract_relationships(text, entities)

        if not relationships:
            return RelationshipExtractionResult(
                source_id=source_id,
                source_type=source_type,
                relationships_extracted=0,
                relationships_saved=0,
                processing_time_ms=(datetime.now() - start_time).total_seconds() * 1000
            )

        saved_count = 0

        for rel in relationships:
            try:
                # Find entity IDs by name
                source_entity = await self._find_entity_by_name(rel["source"])
                target_entity = await self._find_entity_by_name(rel["target"])

                if not source_entity or not target_entity:
                    logger.debug(f"Could not find entities for relationship: {rel['source']} -> {rel['target']}")
                    continue

                # Validate relationship type
                rel_type = rel["relationship_type"]
                if rel_type not in RELATIONSHIP_TYPES:
                    rel_type = "associated_with"

                # Check for existing relationship
                existing = await self.db.execute(
                    select(EntityRelationship).where(
                        EntityRelationship.source_entity_id == source_entity.entity_id,
                        EntityRelationship.target_entity_id == target_entity.entity_id,
                        EntityRelationship.relationship_type == rel_type
                    )
                )
                existing_rel = existing.scalar_one_or_none()

                if existing_rel:
                    # Update existing relationship
                    existing_rel.last_seen = datetime.now(timezone.utc)
                    existing_rel.mention_count = (existing_rel.mention_count or 0) + 1
                    existing_rel.confidence = min(0.95, max(existing_rel.confidence or 0, rel.get("confidence", 0.5)))
                else:
                    # Create new relationship
                    new_rel = EntityRelationship(
                        source_entity_id=source_entity.entity_id,
                        target_entity_id=target_entity.entity_id,
                        relationship_type=rel_type,
                        description=rel.get("context", "")[:500] if rel.get("context") else None,
                        confidence=rel.get("confidence", 0.5),
                        user_id=self.user_id
                    )
                    self.db.add(new_rel)

                saved_count += 1

            except Exception as e:
                logger.warning(f"Failed to save relationship {rel}: {e}")
                continue

        # Commit all changes
        if saved_count > 0:
            try:
                await self.db.commit()
            except Exception as e:
                await self.db.rollback()
                logger.error(f"Failed to commit relationships: {e}")
                saved_count = 0

        elapsed = (datetime.now() - start_time).total_seconds() * 1000

        logger.info(f"Extracted {len(relationships)} relationships, saved {saved_count} for {source_type}:{source_id}")

        return RelationshipExtractionResult(
            source_id=source_id,
            source_type=source_type,
            relationships_extracted=len(relationships),
            relationships_saved=saved_count,
            processing_time_ms=elapsed
        )

    async def _find_entity_by_name(self, name: str) -> Optional[TrackedEntity]:
        """Find a tracked entity by name (case-insensitive)."""
        try:
            result = await self.db.execute(
                select(TrackedEntity).where(
                    TrackedEntity.user_id == self.user_id,
                    TrackedEntity.name_lower == name.lower()
                )
            )
            return result.scalar_one_or_none()
        except Exception as e:
            logger.debug(f"Entity lookup failed for '{name}': {e}")
            return None


# Import for backwards compatibility
from datetime import timedelta
