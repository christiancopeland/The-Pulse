"""
Unified model for all collected content from automated collectors.

This model represents items collected from various sources (RSS, GDELT, ArXiv,
Reddit, Local News, etc.) as part of the automated collection pipeline.
It is separate from NewsArticle which represents on-demand scraped articles.
"""
from sqlalchemy import Column, String, Integer, Float, DateTime, Text, Boolean, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
import uuid
import hashlib

from app.database import Base


class NewsItem(Base):
    """
    Unified model for all automatically collected content.

    This represents items from the SITREP-style collection pipeline:
    - RSS feeds (Reuters, AP, BBC, etc.)
    - GDELT API (geopolitical events)
    - ArXiv API (research papers)
    - Reddit (subreddit posts)
    - Local news sources
    - Custom scrapers

    Attributes:
        id: Unique identifier (UUID)
        source_type: Collector type (rss, gdelt, arxiv, reddit, local, scrape)
        source_name: Human-readable source name (e.g., "Reuters", "AP News")
        source_url: Feed URL or API endpoint
        title: Item title
        content: Full content if available
        summary: Short summary (max 500 chars)
        url: Original article/item URL
        published_at: Original publication date
        collected_at: When we collected this item
        author: Author name if available
        categories: List of category strings (geopolitics, tech_ai, etc.)
        processed: Processing state (0=pending, 1=processed, 2=failed)
        relevance_score: Calculated relevance score (0.0-1.0)
        content_hash: SHA-256 hash for deduplication
        qdrant_id: Vector embedding ID in Qdrant (if embedded)
        metadata: Source-specific metadata (JSONB)
    """
    __tablename__ = "news_items"

    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Source identification
    source_type = Column(String(50), nullable=False, index=True)
    source_name = Column(String(255), nullable=False)
    source_url = Column(Text)

    # Content fields
    title = Column(Text, nullable=False)
    content = Column(Text)
    summary = Column(Text)
    url = Column(Text, unique=True, index=True)

    # Timestamps
    published_at = Column(DateTime(timezone=True))
    collected_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)

    # Author and categorization
    author = Column(String(255))
    categories = Column(JSONB, default=list)

    # Processing state
    processed = Column(Integer, default=0, index=True)  # 0=pending, 1=processed, 2=failed
    relevance_score = Column(Float, default=0.0)

    # Deduplication
    content_hash = Column(String(64), index=True)

    # Vector embedding reference
    qdrant_id = Column(String(36))

    # Source-specific metadata
    item_metadata = Column(JSONB, default=dict)

    # Indexes for common queries
    __table_args__ = (
        Index('ix_news_items_source_collected', 'source_type', 'collected_at'),
        Index('ix_news_items_categories', 'categories', postgresql_using='gin'),
    )

    def __repr__(self):
        return f"<NewsItem(source={self.source_type!r}, title={self.title[:40] if self.title else ''}...)>"

    @property
    def item_id(self) -> str:
        """Generate deterministic ID for this item (matches SITREP pattern)."""
        content = f"{self.title}:{self.source_type}:{self.url}"
        return hashlib.md5(content.encode()).hexdigest()

    @classmethod
    def compute_content_hash(cls, content: str) -> str:
        """Compute SHA-256 hash of content for deduplication."""
        if not content:
            return ""
        return hashlib.sha256(content.encode()).hexdigest()

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": str(self.id),
            "item_id": self.item_id,
            "source_type": self.source_type,
            "source_name": self.source_name,
            "source_url": self.source_url,
            "title": self.title,
            "content": self.content[:1000] if self.content else None,
            "summary": self.summary,
            "url": self.url,
            "published_at": self.published_at.isoformat() if self.published_at else None,
            "collected_at": self.collected_at.isoformat() if self.collected_at else None,
            "author": self.author,
            "categories": self.categories or [],
            "processed": self.processed,
            "relevance_score": self.relevance_score,
            "metadata": self.item_metadata or {},
        }

    @classmethod
    def from_collected_item(cls, item: dict) -> "NewsItem":
        """
        Create from SITREP CollectedItem dict format.

        Args:
            item: Dict with keys: source, category, title, summary, url,
                  published, metadata, raw_content
        """
        published = item.get("published")
        if published and isinstance(published, str):
            from datetime import datetime
            try:
                published = datetime.fromisoformat(published.replace('Z', '+00:00'))
            except ValueError:
                published = None

        content = item.get("raw_content") or item.get("content") or ""

        return cls(
            source_type=item.get("source", "unknown"),
            source_name=item.get("source", "Unknown Source"),
            title=item.get("title", ""),
            content=content,
            summary=item.get("summary", ""),
            url=item.get("url", ""),
            published_at=published,
            categories=[item.get("category")] if item.get("category") else [],
            metadata=item.get("metadata", {}),
            content_hash=cls.compute_content_hash(content),
        )


class CollectionRun(Base):
    """
    Track each collection execution for monitoring and debugging.

    Records when collectors run, how many items were collected,
    success/failure status, and any error messages.

    Attributes:
        id: Unique identifier (UUID)
        collector_type: Type of collector (rss, gdelt, arxiv, etc.)
        collector_name: Human-readable collector name
        started_at: When the collection started
        completed_at: When the collection finished
        status: Current status (running, completed, failed)
        items_collected: Total items fetched
        items_new: New items (not duplicates)
        items_duplicate: Duplicate items skipped
        items_filtered: Items filtered by validation
        error_message: Error details if failed
        metadata: Additional run metadata (JSONB)
    """
    __tablename__ = "collection_runs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    collector_type = Column(String(50), nullable=False, index=True)
    collector_name = Column(String(255))
    started_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)
    completed_at = Column(DateTime(timezone=True))
    status = Column(String(20), default="running", index=True)  # running, completed, failed
    items_collected = Column(Integer, default=0)
    items_new = Column(Integer, default=0)
    items_duplicate = Column(Integer, default=0)
    items_filtered = Column(Integer, default=0)
    error_message = Column(Text)
    run_metadata = Column(JSONB, default=dict)

    def __repr__(self):
        return f"<CollectionRun(collector={self.collector_type!r}, status={self.status!r})>"

    @property
    def duration_seconds(self) -> float:
        """Calculate run duration in seconds."""
        if not self.completed_at or not self.started_at:
            return 0.0
        return (self.completed_at - self.started_at).total_seconds()

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": str(self.id),
            "collector_type": self.collector_type,
            "collector_name": self.collector_name,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "status": self.status,
            "duration_seconds": self.duration_seconds,
            "items_collected": self.items_collected,
            "items_new": self.items_new,
            "items_duplicate": self.items_duplicate,
            "items_filtered": self.items_filtered,
            "error_message": self.error_message,
            "metadata": self.run_metadata or {},
        }
