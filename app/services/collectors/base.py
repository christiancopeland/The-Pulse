"""
Base collector class and core data structures for The Pulse collection engine.

All collectors inherit from BaseCollector and implement the collect() method.
Collectors fetch data from external sources and return NewsItem objects.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
import hashlib
import re
import time
import logging

from app.models.news_item import NewsItem, CollectionRun
from app.database import get_db

logger = logging.getLogger(__name__)


@dataclass
class CollectedItem:
    """
    Intermediate data structure for collected items.

    Collectors create CollectedItem instances which are then
    converted to NewsItem database models for storage.
    """
    source: str           # e.g., "rss", "gdelt", "arxiv", "reddit"
    source_name: str      # e.g., "Reuters", "AP News"
    category: str         # e.g., "geopolitics", "crime_local", "tech_ai"
    title: str
    summary: str          # Pre-extracted or first 500 chars
    url: str
    published: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    raw_content: str = ""  # Full text if available
    author: str = ""
    source_url: str = ""   # Feed URL or API endpoint

    @property
    def item_id(self) -> str:
        """Generate unique ID for this item (MD5 hash)."""
        content = f"{self.title}:{self.source}:{self.url}"
        return hashlib.md5(content.encode()).hexdigest()

    @property
    def content_hash(self) -> str:
        """Generate SHA-256 hash of content for deduplication."""
        content = self.raw_content or self.summary or self.title
        return hashlib.sha256(content.encode()).hexdigest()

    def to_news_item(self) -> NewsItem:
        """Convert to NewsItem database model."""
        return NewsItem(
            source_type=self.source,
            source_name=self.source_name,
            source_url=self.source_url,
            title=self.title,
            content=self.raw_content,
            summary=self.summary,
            url=self.url,
            published_at=self.published,
            author=self.author,
            categories=[self.category] if self.category else [],
            item_metadata=self.metadata,
            content_hash=self.content_hash,
        )

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "item_id": self.item_id,
            "source": self.source,
            "source_name": self.source_name,
            "category": self.category,
            "title": self.title,
            "summary": self.summary,
            "url": self.url,
            "published": self.published.isoformat() if self.published else None,
            "metadata": self.metadata,
            "raw_content": self.raw_content[:1000] if self.raw_content else "",
        }

    @classmethod
    def from_dict(cls, data: dict) -> "CollectedItem":
        """Create from dictionary."""
        pub = data.get("published")
        if pub and isinstance(pub, str):
            try:
                pub = datetime.fromisoformat(pub.replace('Z', '+00:00'))
            except ValueError:
                pub = datetime.now(timezone.utc)
        return cls(
            source=data["source"],
            source_name=data.get("source_name", data["source"]),
            category=data["category"],
            title=data["title"],
            summary=data["summary"],
            url=data["url"],
            published=pub or datetime.now(timezone.utc),
            metadata=data.get("metadata", {}),
            raw_content=data.get("raw_content", ""),
        )


class BaseCollector(ABC):
    """
    Abstract base class for all content collectors.

    Subclasses must implement:
    - collect() -> List[CollectedItem]: Fetch items from source
    - name (property) -> str: Human-readable collector name
    - source_type (property) -> str: Source type identifier
    """

    def __init__(self):
        self._logger = logging.getLogger(f"collectors.{self.__class__.__name__}")
        self.is_running = False
        self.last_run: Optional[datetime] = None
        self.last_run_items: int = 0
        self.error_count: int = 0
        self.consecutive_failures: int = 0

    @abstractmethod
    async def collect(self) -> List[CollectedItem]:
        """
        Fetch items from this source.

        Must be implemented by subclasses. Should return a list of
        CollectedItem instances representing the fetched content.
        """
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable name for this collector (e.g., 'RSS Feeds')."""
        pass

    @property
    def source_type(self) -> str:
        """Source type identifier (e.g., 'rss', 'gdelt'). Defaults to class name."""
        return self.__class__.__name__.replace("Collector", "").lower()

    async def run(self, db_session=None) -> CollectionRun:
        """
        Execute collection with tracking and error handling.

        Creates a CollectionRun record, executes collect(), processes
        results for deduplication, and stores new items.

        Args:
            db_session: Optional database session. If not provided,
                       creates a new session.

        Returns:
            CollectionRun with statistics about this run.
        """
        run = CollectionRun(
            collector_type=self.source_type,
            collector_name=self.name,
            status="running"
        )

        start_time = time.time()
        self.is_running = True
        self._logger.info(f"[COLLECT] [{self.name}] Starting collection run")

        try:
            # Execute collection
            self._logger.debug(f"[COLLECT] [{self.name}] Fetching from source...")
            items = await self.collect()

            run.items_collected = len(items)
            self._logger.info(
                f"[COLLECT] [{self.name}] Fetched {len(items)} items from source"
            )

            # Process and deduplicate if db_session provided
            if db_session and items:
                new_items, duplicates = await self._process_items(items, db_session)
                run.items_new = len(new_items)
                run.items_duplicate = duplicates
            else:
                run.items_new = len(items)
                run.items_duplicate = 0
                if items:
                    self._logger.warning(
                        f"[COLLECT] [{self.name}] No DB session - items not persisted"
                    )

            run.status = "completed"
            run.completed_at = datetime.now(timezone.utc)

            elapsed = time.time() - start_time
            self.last_run = datetime.now(timezone.utc)
            self.last_run_items = run.items_new
            self.consecutive_failures = 0

            self._logger.info(
                f"[COLLECT] [{self.name}] Run completed in {elapsed:.2f}s: "
                f"fetched={run.items_collected}, new={run.items_new}, "
                f"duplicates={run.items_duplicate}"
            )

        except Exception as e:
            run.status = "failed"
            run.error_message = f"{type(e).__name__}: {str(e)}"
            run.completed_at = datetime.now(timezone.utc)
            self.error_count += 1
            self.consecutive_failures += 1

            elapsed = time.time() - start_time
            self._logger.error(
                f"[COLLECT] [{self.name}] Run FAILED after {elapsed:.2f}s: {e}",
                exc_info=True
            )

        finally:
            self.is_running = False

            # Save run record if db_session provided
            if db_session:
                try:
                    db_session.add(run)
                    await db_session.commit()
                    self._logger.debug(
                        f"[COLLECT] [{self.name}] Run record saved: id={run.id}"
                    )
                except Exception as e:
                    self._logger.error(f"[COLLECT] [{self.name}] Failed to save run record: {e}")

        return run

    async def _process_items(
        self,
        items: List[CollectedItem],
        db_session
    ) -> tuple:
        """
        Deduplicate and save items to database.

        Args:
            items: List of CollectedItem to process
            db_session: Database session

        Returns:
            Tuple of (new_items_list, duplicate_count)
        """
        from sqlalchemy import select

        new_items = []
        duplicates = 0

        self._logger.debug(
            f"[INDEX] [{self.name}] Processing {len(items)} items for indexing"
        )

        for idx, item in enumerate(items):
            try:
                # Check for duplicate by URL or content hash
                news_item = item.to_news_item()

                # Check by URL first (faster)
                stmt = select(NewsItem).where(NewsItem.url == news_item.url)
                result = await db_session.execute(stmt)
                existing = result.scalar_one_or_none()

                if existing:
                    duplicates += 1
                    self._logger.debug(
                        f"[INDEX] [{self.name}] DUPLICATE (url): {item.url[:80]}"
                    )
                    continue

                # Check by content hash
                if news_item.content_hash:
                    stmt = select(NewsItem).where(
                        NewsItem.content_hash == news_item.content_hash
                    )
                    result = await db_session.execute(stmt)
                    existing = result.scalar_one_or_none()

                    if existing:
                        duplicates += 1
                        self._logger.debug(
                            f"[INDEX] [{self.name}] DUPLICATE (hash): {item.url[:80]}"
                        )
                        continue

                # New item - add to database
                db_session.add(news_item)
                new_items.append(news_item)

                self._logger.info(
                    f"[INDEX] [{self.name}] NEW item queued: "
                    f"source={item.source_name}, title=\"{item.title[:60]}...\", "
                    f"url={item.url[:80]}"
                )

            except Exception as e:
                self._logger.warning(
                    f"[INDEX] [{self.name}] Failed to process item {idx}: {e}, url={item.url[:80] if item.url else 'N/A'}"
                )
                continue

        try:
            await db_session.commit()
            # After commit, log the IDs of new items
            for news_item in new_items:
                self._logger.info(
                    f"[INDEX] [{self.name}] INDEXED: id={news_item.id}, "
                    f"url={news_item.url[:80] if news_item.url else 'N/A'}"
                )
        except Exception as e:
            self._logger.error(
                f"[INDEX] [{self.name}] Failed to commit {len(new_items)} items: {e}"
            )
            await db_session.rollback()

        self._logger.info(
            f"[INDEX] [{self.name}] Indexing complete: "
            f"indexed={len(new_items)}, duplicates={duplicates}"
        )

        return new_items, duplicates

    def get_status(self) -> dict:
        """Return collector status for monitoring."""
        # Determine health status
        if self.consecutive_failures >= 3:
            health = "unhealthy"
        elif self.consecutive_failures >= 1:
            health = "degraded"
        else:
            health = "healthy"

        return {
            "name": self.name,
            "source_type": self.source_type,
            "is_running": self.is_running,
            "last_run": self.last_run.isoformat() if self.last_run else None,
            "last_run_items": self.last_run_items,
            "error_count": self.error_count,
            "consecutive_failures": self.consecutive_failures,
            "health": health,
        }

    def truncate_text(self, text: str, max_length: int = 500) -> str:
        """Truncate text to max_length, preserving word boundaries."""
        if not text or len(text) <= max_length:
            return text or ""
        truncated = text[:max_length].rsplit(" ", 1)[0]
        return truncated + "..."

    def clean_text(self, text: str) -> str:
        """Clean text by removing extra whitespace and HTML artifacts."""
        if not text:
            return ""
        # Remove HTML tags
        text = re.sub(r'<[^>]+>', '', text)
        # Remove extra whitespace
        text = re.sub(r'\s+', ' ', text)
        return text.strip()
