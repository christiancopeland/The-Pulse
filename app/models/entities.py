"""
Entity tracking models for The Pulse.

Includes:
- TrackedEntity: Named entities being tracked (people, orgs, etc.)
- EntityMention: Occurrences of entities in documents/articles
- EntityRelationship: Relationships between entities (supports, opposes, etc.)
"""
from typing import Dict, Optional, List
from sqlalchemy import Column, String, Integer, Float, JSON, ForeignKey, UniqueConstraint, Index, CheckConstraint, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from datetime import datetime, timezone, date
import uuid
from ..database import Base

class TrackedEntity(Base):
    """
    Model for storing tracked entities.

    Attributes:
        entity_id (UUID): Unique identifier for the entity
        user_id (UUID): ID of the user who created/owns this entity
        name (str): Name of the entity (stored in lowercase for case-insensitive matching)
        entity_type (str): Type of entity (PERSON, ORG, LOCATION, CUSTOM)
        created_at (str): ISO format timestamp of when the entity was created
        entity_metadata (JSON): Additional metadata about the entity
        first_seen (DateTime): When entity first appeared in content (VIZ-005)
        last_seen (DateTime): When entity most recently appeared in content (VIZ-005)
    """
    __tablename__ = "tracked_entities"

    entity_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False)
    name = Column(String, nullable=False)
    name_lower = Column(String, nullable=False)
    entity_type = Column(String, nullable=False)
    created_at = Column(String, nullable=False, default=lambda: datetime.now(timezone.utc))
    entity_metadata = Column(JSON, nullable=True)

    # VIZ-005: Temporal tracking - when entity first/last appeared in content
    first_seen = Column(DateTime(timezone=True), nullable=True, index=True)
    last_seen = Column(DateTime(timezone=True), nullable=True, index=True)

    __table_args__ = (
        UniqueConstraint('user_id', 'name_lower', name='uq_user_entity_name'),
        Index('ix_tracked_entities_name_lower_trgm', 'name_lower', postgresql_using='gist', postgresql_ops={'name_lower': 'gist_trgm_ops'}),
        # B-tree index for exact matches (faster than trigram for exact lookups)
        Index('ix_tracked_entities_name_lower_btree', 'name_lower'),
        # Index for user filtering
        Index('ix_tracked_entities_user_id', 'user_id'),
    )
    
    def __repr__(self):
        return f"<TrackedEntity(name='{self.name}', type='{self.entity_type}')>"
    
    def to_dict(self) -> Dict:
        """Convert entity to dictionary representation"""
        return {
            "entity_id": str(self.entity_id),
            "user_id": str(self.user_id),
            "name": self.name,
            "entity_type": self.entity_type,
            "created_at": self.created_at,
            "entity_metadata": self.entity_metadata or {},
            "first_seen": self.first_seen.isoformat() if self.first_seen else None,
            "last_seen": self.last_seen.isoformat() if self.last_seen else None
        }

class EntityMention(Base):
    """
    Model for storing entity mentions in documents, news articles, and news items.

    Attributes:
        mention_id (UUID): Unique identifier for the mention
        entity_id (UUID): ID of the referenced tracked entity
        document_id (UUID): ID of the document containing the mention (if from document)
        news_article_id (UUID): ID of the news article containing the mention (if from on-demand scraped news)
        news_item_id (UUID): ID of the news item containing the mention (if from automated collection)
        user_id (UUID): ID of the user who owns this mention
        chunk_id (str): ID of the document chunk containing the mention
        context (str): Surrounding text context of the mention
        timestamp (str): ISO format timestamp of when the mention was found
    """
    __tablename__ = "entity_mentions"

    mention_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entity_id = Column(UUID(as_uuid=True), ForeignKey("tracked_entities.entity_id", ondelete="CASCADE"))
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.document_id", ondelete="CASCADE"), nullable=True)
    news_article_id = Column(UUID(as_uuid=True), ForeignKey("news_articles.id", ondelete="CASCADE"), nullable=True)
    news_item_id = Column(UUID(as_uuid=True), ForeignKey("news_items.id", ondelete="CASCADE"), nullable=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False)
    chunk_id = Column(String, nullable=False)
    context = Column(String, nullable=False)
    timestamp = Column(String, nullable=False, default=lambda: datetime.utcnow().isoformat())

    __table_args__ = (
        # Ensure exactly one of document_id, news_article_id, or news_item_id is set
        CheckConstraint(
            '(CASE WHEN document_id IS NOT NULL THEN 1 ELSE 0 END + '
            'CASE WHEN news_article_id IS NOT NULL THEN 1 ELSE 0 END + '
            'CASE WHEN news_item_id IS NOT NULL THEN 1 ELSE 0 END) = 1',
            name='check_one_source_id'
        ),
        # Indexes for co-mention and relationship discovery queries
        Index('ix_entity_mentions_entity_id', 'entity_id'),
        Index('ix_entity_mentions_news_item_id', 'news_item_id'),
        Index('ix_entity_mentions_document_id', 'document_id'),
        Index('ix_entity_mentions_news_article_id', 'news_article_id'),
        Index('ix_entity_mentions_timestamp', 'timestamp'),
        # Composite index for entity + timestamp queries
        Index('ix_entity_mentions_entity_timestamp', 'entity_id', 'timestamp'),
    )
    
    def __repr__(self):
        source_id = self.document_id or self.news_article_id or self.news_item_id
        if self.document_id:
            source_type = "document"
        elif self.news_article_id:
            source_type = "news_article"
        else:
            source_type = "news_item"
        return f"<EntityMention(entity_id='{self.entity_id}', {source_type}_id='{source_id}')>"

    def to_dict(self) -> Dict:
        """Convert mention to dictionary representation"""
        return {
            "mention_id": str(self.mention_id),
            "entity_id": str(self.entity_id),
            "document_id": str(self.document_id) if self.document_id else None,
            "news_article_id": str(self.news_article_id) if self.news_article_id else None,
            "news_item_id": str(self.news_item_id) if self.news_item_id else None,
            "user_id": str(self.user_id),
            "chunk_id": self.chunk_id,
            "context": self.context,
            "timestamp": self.timestamp
        }


# Relationship types for EntityRelationship
RELATIONSHIP_TYPES = [
    "supports",           # Entity A supports Entity B
    "opposes",            # Entity A opposes Entity B
    "collaborates_with",  # Entity A works with Entity B
    "implements",         # Entity A implements Entity B (policy/program)
    "impacts",            # Entity A affects Entity B
    "responds_to",        # Entity A responds to Entity B's actions
    "part_of",            # Entity A is part of Entity B (org membership)
    "leads",              # Entity A leads/directs Entity B
    "funds",              # Entity A provides funding to Entity B
    "regulates",          # Entity A regulates/oversees Entity B
]


class EntityRelationship(Base):
    """
    Model for storing relationships between tracked entities.

    Tracks how entities are connected through their co-occurrence and
    explicit relationships detected in content. Relationships are
    directional (source -> target) with a type and optional description.

    Attributes:
        id: Unique identifier (UUID)
        source_entity_id: ID of the source entity
        target_entity_id: ID of the target entity
        relationship_type: Type of relationship (supports, opposes, etc.)
        description: Optional description of the relationship
        first_seen: When this relationship was first detected
        last_seen: Most recent detection of this relationship
        mention_count: How many times this relationship has been detected
        confidence: Confidence score (0.0-1.0) based on extraction quality
        user_id: Owner user (for user-specific relationships)
        metadata: Additional relationship data (JSONB)
    """
    __tablename__ = "entity_relationships"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_entity_id = Column(UUID(as_uuid=True), ForeignKey("tracked_entities.entity_id", ondelete="CASCADE"), nullable=False)
    target_entity_id = Column(UUID(as_uuid=True), ForeignKey("tracked_entities.entity_id", ondelete="CASCADE"), nullable=False)
    relationship_type = Column(String(50), nullable=False, index=True)
    description = Column(String)
    first_seen = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    last_seen = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    mention_count = Column(Integer, default=1)
    confidence = Column(Float, default=0.5)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=True)
    relationship_metadata = Column(JSON, nullable=True)

    # Relationships
    source_entity = relationship(
        "TrackedEntity",
        foreign_keys=[source_entity_id],
        backref="outgoing_relationships"
    )
    target_entity = relationship(
        "TrackedEntity",
        foreign_keys=[target_entity_id],
        backref="incoming_relationships"
    )

    __table_args__ = (
        # Unique constraint for relationship between two entities of same type
        UniqueConstraint('source_entity_id', 'target_entity_id', 'relationship_type',
                        name='uq_entity_relationship'),
        # Indexes for common queries
        Index('ix_entity_relationships_source', 'source_entity_id'),
        Index('ix_entity_relationships_target', 'target_entity_id'),
        Index('ix_entity_relationships_last_seen', 'last_seen'),
    )

    def __repr__(self):
        return f"<EntityRelationship({self.source_entity_id} -{self.relationship_type}-> {self.target_entity_id})>"

    def to_dict(self) -> Dict:
        """Convert relationship to dictionary representation"""
        return {
            "id": str(self.id),
            "source_entity_id": str(self.source_entity_id),
            "target_entity_id": str(self.target_entity_id),
            "relationship_type": self.relationship_type,
            "description": self.description,
            "first_seen": self.first_seen.isoformat() if self.first_seen else None,
            "last_seen": self.last_seen.isoformat() if self.last_seen else None,
            "mention_count": self.mention_count,
            "confidence": self.confidence,
            "user_id": str(self.user_id) if self.user_id else None,
            "metadata": self.relationship_metadata or {}
        }

    @classmethod
    def get_or_create(
        cls,
        db_session,
        source_id: str,
        target_id: str,
        relationship_type: str,
        description: Optional[str] = None,
        user_id: Optional[str] = None,
        confidence: float = 0.5
    ):
        """
        Find existing relationship or create new one.

        If relationship exists, updates last_seen and increments mention_count.
        """
        from sqlalchemy import select
        from sqlalchemy.orm import Session

        # This would typically be used in an async context
        # For now, provide the pattern for sync usage
        pass  # Implementation depends on async/sync context
