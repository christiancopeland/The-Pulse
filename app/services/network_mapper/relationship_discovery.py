"""
Relationship Discovery Service for The Pulse.

Automatically discovers relationships between entities by analyzing:
- Co-mentions in news items and documents
- Contextual clues using LLM inference
- Explicit relationship indicators in text
"""

import asyncio
import json
import logging
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timezone, timedelta
from collections import defaultdict
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text, func

from app.models.entities import TrackedEntity, EntityMention, EntityRelationship, RELATIONSHIP_TYPES

logger = logging.getLogger(__name__)


class RelationshipDiscoveryService:
    """
    Automatically discover relationships from entity co-mentions
    and contextual analysis.
    """

    def __init__(
        self,
        db_session: AsyncSession,
        ollama_client=None,
        user_id: Optional[UUID] = None
    ):
        """
        Initialize the relationship discovery service.

        Args:
            db_session: Async SQLAlchemy session
            ollama_client: Optional Ollama client for LLM inference
            user_id: Optional user ID to filter entities
        """
        self.db = db_session
        self.ollama = ollama_client
        self.user_id = user_id

    async def discover_from_co_mentions(
        self,
        min_co_occurrences: int = 2,
        time_window_days: int = 30,
        use_llm: bool = True
    ) -> List[EntityRelationship]:
        """
        Discover relationships from entities mentioned together.

        Entities that frequently appear in the same content likely have
        some relationship. This method finds such co-occurrences and
        optionally uses LLM to infer the relationship type.

        Args:
            min_co_occurrences: Minimum times entities must appear together
            time_window_days: Only consider recent mentions
            use_llm: Whether to use LLM to infer relationship type

        Returns:
            List of discovered relationships
        """
        logger.info(f"Discovering relationships from co-mentions (min={min_co_occurrences})")

        # Find entity pairs that appear in same documents/news items
        cutoff = datetime.now(timezone.utc) - timedelta(days=time_window_days)

        # Query to find co-occurring entities
        query = text("""
            WITH mention_sources AS (
                SELECT
                    entity_id,
                    COALESCE(document_id, news_article_id, news_item_id) as source_id,
                    context
                FROM entity_mentions
                WHERE timestamp >= :cutoff
            )
            SELECT
                m1.entity_id as entity1_id,
                m2.entity_id as entity2_id,
                COUNT(DISTINCT m1.source_id) as co_occurrences,
                array_agg(DISTINCT m1.context) as contexts1,
                array_agg(DISTINCT m2.context) as contexts2
            FROM mention_sources m1
            JOIN mention_sources m2
                ON m1.source_id = m2.source_id
                AND m1.entity_id < m2.entity_id
            GROUP BY m1.entity_id, m2.entity_id
            HAVING COUNT(DISTINCT m1.source_id) >= :min_co
            ORDER BY co_occurrences DESC
            LIMIT 100
        """)

        result = await self.db.execute(query, {
            "cutoff": cutoff.isoformat(),
            "min_co": min_co_occurrences
        })

        pairs = result.fetchall()
        logger.info(f"Found {len(pairs)} entity pairs with sufficient co-occurrences")

        discovered_relationships = []

        for pair in pairs:
            entity1_id = pair.entity1_id
            entity2_id = pair.entity2_id
            co_occurrences = pair.co_occurrences
            contexts1 = pair.contexts1 or []
            contexts2 = pair.contexts2 or []

            # Determine relationship type
            if use_llm and self.ollama:
                relationship = await self._infer_relationship_with_llm(
                    entity1_id, entity2_id, contexts1, contexts2
                )
            else:
                relationship = {
                    "type": "associated_with",
                    "confidence": min(0.9, 0.5 + (co_occurrences * 0.05)),
                    "direction": "bidirectional"
                }

            if relationship and relationship.get("type"):
                # Create or update relationship
                rel = await self._create_or_update_relationship(
                    source_id=entity1_id,
                    target_id=entity2_id,
                    relationship_type=relationship["type"],
                    confidence=relationship.get("confidence", 0.5),
                    weight=co_occurrences,
                    description=relationship.get("evidence")
                )
                if rel:
                    discovered_relationships.append(rel)

                # If bidirectional, create reverse relationship too
                if relationship.get("direction") == "bidirectional":
                    await self._create_or_update_relationship(
                        source_id=entity2_id,
                        target_id=entity1_id,
                        relationship_type=relationship["type"],
                        confidence=relationship.get("confidence", 0.5),
                        weight=co_occurrences,
                        description=relationship.get("evidence")
                    )

        await self.db.commit()
        logger.info(f"Discovered {len(discovered_relationships)} new/updated relationships")

        return discovered_relationships

    async def discover_from_context(
        self,
        entity_id: UUID,
        max_contexts: int = 10
    ) -> List[Dict]:
        """
        Analyze mention contexts to discover relationships for a specific entity.

        Args:
            entity_id: Entity to analyze
            max_contexts: Maximum contexts to analyze

        Returns:
            List of discovered relationships with confidence scores
        """
        # Get recent contexts for this entity
        query = select(EntityMention).where(
            EntityMention.entity_id == entity_id
        ).order_by(
            EntityMention.timestamp.desc()
        ).limit(max_contexts)

        result = await self.db.execute(query)
        mentions = result.scalars().all()

        if not mentions:
            return []

        # Get the entity's name
        entity_result = await self.db.execute(
            select(TrackedEntity).where(TrackedEntity.entity_id == entity_id)
        )
        entity = entity_result.scalar_one_or_none()

        if not entity:
            return []

        discovered = []

        # Analyze each context for relationship indicators
        for mention in mentions:
            context = mention.context
            if not context:
                continue

            # Look for other tracked entities in the same context
            other_entities = await self._find_entities_in_context(context, exclude_id=entity_id)

            for other_entity in other_entities:
                # Use simple pattern matching or LLM to determine relationship
                if self.ollama:
                    relationship = await self._infer_relationship_from_context(
                        entity.name,
                        other_entity["name"],
                        context
                    )
                else:
                    relationship = await self._simple_relationship_detection(
                        entity.name,
                        other_entity["name"],
                        context
                    )

                if relationship:
                    discovered.append({
                        "source_entity": entity.name,
                        "target_entity": other_entity["name"],
                        "relationship_type": relationship["type"],
                        "confidence": relationship["confidence"],
                        "context": context[:200]
                    })

        return discovered

    async def discover_all_relationships(
        self,
        min_confidence: float = 0.3,
        batch_size: int = 50
    ) -> Dict:
        """
        Run full relationship discovery across all entities.

        Args:
            min_confidence: Minimum confidence threshold
            batch_size: Entities to process per batch

        Returns:
            Summary of discovery results
        """
        logger.info("Starting full relationship discovery")

        results = {
            "entities_processed": 0,
            "relationships_found": 0,
            "relationships_by_type": defaultdict(int),
            "errors": 0
        }

        # Get all entities
        query = select(TrackedEntity)
        if self.user_id:
            query = query.where(TrackedEntity.user_id == self.user_id)

        result = await self.db.execute(query)
        entities = result.scalars().all()

        # First pass: Co-mention discovery
        try:
            co_mention_rels = await self.discover_from_co_mentions(
                min_co_occurrences=2,
                use_llm=self.ollama is not None
            )
            results["relationships_found"] += len(co_mention_rels)
            for rel in co_mention_rels:
                results["relationships_by_type"][rel.relationship_type] += 1
        except Exception as e:
            logger.error(f"Co-mention discovery failed: {e}")
            results["errors"] += 1

        # Second pass: Context-based discovery for each entity
        for entity in entities:
            try:
                context_rels = await self.discover_from_context(entity.entity_id)
                for rel in context_rels:
                    if rel["confidence"] >= min_confidence:
                        await self._create_or_update_relationship(
                            source_id=entity.entity_id,
                            target_id=await self._get_entity_id_by_name(rel["target_entity"]),
                            relationship_type=rel["relationship_type"],
                            confidence=rel["confidence"]
                        )
                        results["relationships_found"] += 1
                        results["relationships_by_type"][rel["relationship_type"]] += 1

                results["entities_processed"] += 1

            except Exception as e:
                logger.error(f"Context discovery failed for {entity.name}: {e}")
                results["errors"] += 1
                continue

        await self.db.commit()

        logger.info(f"Discovery complete: {results}")
        return results

    async def _infer_relationship_with_llm(
        self,
        entity1_id: UUID,
        entity2_id: UUID,
        contexts1: List[str],
        contexts2: List[str]
    ) -> Optional[Dict]:
        """Use LLM to infer relationship type from contexts."""
        if not self.ollama:
            return None

        # Get entity names
        e1 = await self.db.execute(
            select(TrackedEntity).where(TrackedEntity.entity_id == entity1_id)
        )
        e2 = await self.db.execute(
            select(TrackedEntity).where(TrackedEntity.entity_id == entity2_id)
        )

        entity1 = e1.scalar_one_or_none()
        entity2 = e2.scalar_one_or_none()

        if not entity1 or not entity2:
            return None

        # Combine and limit contexts
        combined_contexts = []
        for c1, c2 in zip(contexts1[:3], contexts2[:3]):
            if c1:
                combined_contexts.append(c1[:300])
            if c2:
                combined_contexts.append(c2[:300])

        prompt = f"""Analyze the relationship between two entities based on text excerpts.

Entity 1: {entity1.name} (Type: {entity1.entity_type})
Entity 2: {entity2.name} (Type: {entity2.entity_type})

Contexts where they appear:
{chr(10).join(combined_contexts[:5])}

Determine the most likely relationship type from this list:
- supports (advocacy, endorsement)
- opposes (adversarial, criticism)
- collaborates_with (partnership, cooperation)
- implements (policy/program implementation)
- impacts (affects, influences)
- responds_to (reaction to actions)
- part_of (membership, subsidiary)
- leads (leadership, direction)
- funds (financial support)
- regulates (oversight, regulation)
- associated_with (general connection)

Return JSON only:
{{
    "type": "relationship_type",
    "direction": "entity1_to_entity2" | "entity2_to_entity1" | "bidirectional",
    "confidence": 0.0-1.0,
    "evidence": "Brief explanation"
}}

If no clear relationship, return {{"type": null}}"""

        try:
            response = await self.ollama.generate(
                model="qwen2.5-coder:14b",
                prompt=prompt,
                format="json"
            )

            if response:
                result = json.loads(response.get("response", "{}"))
                if result.get("type") and result["type"] != "null":
                    return result

        except Exception as e:
            logger.warning(f"LLM relationship inference failed: {e}")

        return None

    async def _infer_relationship_from_context(
        self,
        entity1_name: str,
        entity2_name: str,
        context: str
    ) -> Optional[Dict]:
        """Use LLM to infer relationship from a single context."""
        if not self.ollama:
            return None

        prompt = f"""What is the relationship between "{entity1_name}" and "{entity2_name}" in this text?

Text: {context[:500]}

Choose from: supports, opposes, collaborates_with, impacts, responds_to, part_of, leads, funds, regulates, associated_with

Return JSON:
{{"type": "relationship_type", "confidence": 0.0-1.0}}"""

        try:
            response = await self.ollama.generate(
                model="qwen2.5-coder:14b",
                prompt=prompt,
                format="json"
            )

            if response:
                return json.loads(response.get("response", "{}"))

        except Exception as e:
            logger.warning(f"Context relationship inference failed: {e}")

        return None

    async def _simple_relationship_detection(
        self,
        entity1_name: str,
        entity2_name: str,
        context: str
    ) -> Optional[Dict]:
        """Simple pattern-based relationship detection without LLM."""
        context_lower = context.lower()

        # Relationship indicators
        patterns = {
            "supports": ["supports", "endorses", "backs", "advocates for", "champions"],
            "opposes": ["opposes", "criticizes", "attacks", "condemns", "rejects"],
            "collaborates_with": ["works with", "partners with", "collaborates", "together with", "alongside"],
            "leads": ["leads", "heads", "directs", "manages", "runs"],
            "funds": ["funds", "finances", "invests in", "sponsors", "pays"],
            "part_of": ["member of", "part of", "belongs to", "works for", "employed by"],
            "impacts": ["affects", "impacts", "influences", "changes"],
        }

        for rel_type, indicators in patterns.items():
            for indicator in indicators:
                if indicator in context_lower:
                    return {
                        "type": rel_type,
                        "confidence": 0.4  # Low confidence for pattern matching
                    }

        return {
            "type": "associated_with",
            "confidence": 0.3
        }

    async def _find_entities_in_context(
        self,
        context: str,
        exclude_id: Optional[UUID] = None
    ) -> List[Dict]:
        """Find tracked entities mentioned in a context string."""
        context_lower = context.lower()

        query = select(TrackedEntity)
        if self.user_id:
            query = query.where(TrackedEntity.user_id == self.user_id)

        result = await self.db.execute(query)
        entities = result.scalars().all()

        found = []
        for entity in entities:
            if exclude_id and entity.entity_id == exclude_id:
                continue
            if entity.name_lower in context_lower:
                found.append({
                    "id": str(entity.entity_id),
                    "name": entity.name,
                    "entity_type": entity.entity_type
                })

        return found

    async def _create_or_update_relationship(
        self,
        source_id: UUID,
        target_id: UUID,
        relationship_type: str,
        confidence: float = 0.5,
        weight: int = 1,
        description: Optional[str] = None
    ) -> Optional[EntityRelationship]:
        """Create or update a relationship in the database."""
        try:
            # Check for existing
            existing = await self.db.execute(
                select(EntityRelationship).where(
                    EntityRelationship.source_entity_id == source_id,
                    EntityRelationship.target_entity_id == target_id,
                    EntityRelationship.relationship_type == relationship_type
                )
            )
            rel = existing.scalar_one_or_none()

            if rel:
                # Update existing
                rel.last_seen = datetime.now(timezone.utc)
                rel.mention_count = (rel.mention_count or 0) + weight
                rel.confidence = max(rel.confidence or 0, confidence)
                if description and not rel.description:
                    rel.description = description
                return rel
            else:
                # Create new
                rel = EntityRelationship(
                    source_entity_id=source_id,
                    target_entity_id=target_id,
                    relationship_type=relationship_type,
                    confidence=confidence,
                    description=description,
                    user_id=self.user_id
                )
                self.db.add(rel)
                return rel

        except Exception as e:
            logger.error(f"Failed to create/update relationship: {e}")
            return None

    async def _get_entity_id_by_name(self, name: str) -> Optional[UUID]:
        """Get entity ID by name."""
        result = await self.db.execute(
            select(TrackedEntity.entity_id).where(
                TrackedEntity.name_lower == name.lower()
            )
        )
        entity_id = result.scalar_one_or_none()
        return entity_id

    async def get_relationship_stats(self) -> Dict:
        """Get statistics about relationships in the system."""
        # Count by type
        type_query = text("""
            SELECT relationship_type, COUNT(*) as count
            FROM entity_relationships
            GROUP BY relationship_type
            ORDER BY count DESC
        """)

        result = await self.db.execute(type_query)
        by_type = {row.relationship_type: row.count for row in result}

        # Total count
        total_query = select(func.count(EntityRelationship.id))
        total_result = await self.db.execute(total_query)
        total = total_result.scalar() or 0

        # Recent relationships (last 7 days)
        recent_cutoff = datetime.now(timezone.utc) - timedelta(days=7)
        recent_query = select(func.count(EntityRelationship.id)).where(
            EntityRelationship.first_seen >= recent_cutoff
        )
        recent_result = await self.db.execute(recent_query)
        recent = recent_result.scalar() or 0

        return {
            "total_relationships": total,
            "recent_relationships": recent,
            "by_type": by_type,
            "available_types": RELATIONSHIP_TYPES
        }
