"""
RSS feed collector for The Pulse.

Collects items from multiple RSS feeds including news sources (Reuters, AP, BBC),
tech sources (Ars Technica, Hacker News), and specialized feeds (RC industry, local news).
"""
import asyncio
import aiohttp
import feedparser
from datetime import datetime, timezone
from typing import List, Dict, Optional
import logging

from .base import BaseCollector, CollectedItem
from .config import RSS_FEEDS, RSS_CATEGORY_MAP, RSS_TIMEOUT_SECONDS

logger = logging.getLogger(__name__)


class RSSCollector(BaseCollector):
    """Collects items from RSS feeds."""

    def __init__(
        self,
        feeds: Optional[Dict[str, str]] = None,
        category_map: Optional[Dict[str, str]] = None,
        items_per_feed: int = 25,
    ):
        """
        Initialize RSS collector.

        Args:
            feeds: Dict of feed_name -> feed_url. Uses config default if None.
            category_map: Dict of feed_name -> category. Uses config if None.
            items_per_feed: Maximum items to collect per feed.
        """
        super().__init__()
        self.feeds = feeds or RSS_FEEDS
        self.category_map = category_map or RSS_CATEGORY_MAP
        self.items_per_feed = items_per_feed

    @property
    def name(self) -> str:
        return "RSS Feeds"

    @property
    def source_type(self) -> str:
        return "rss"

    async def _fetch_feed(
        self,
        session: aiohttp.ClientSession,
        feed_name: str,
        feed_url: str,
    ) -> List[CollectedItem]:
        """Fetch and parse a single RSS feed."""
        items = []
        try:
            self._logger.debug(f"Fetching feed: {feed_name} ({feed_url})")

            async with session.get(
                feed_url,
                timeout=aiohttp.ClientTimeout(total=RSS_TIMEOUT_SECONDS),
            ) as response:
                if response.status != 200:
                    self._logger.warning(
                        f"Feed {feed_name} returned status {response.status}"
                    )
                    return items

                content = await response.text()
                feed = feedparser.parse(content)

                if feed.bozo:
                    self._logger.warning(
                        f"Feed {feed_name} has parsing issues: {feed.bozo_exception}"
                    )

                for entry in feed.entries[:self.items_per_feed]:
                    try:
                        # Parse publication date
                        published = self._parse_date(entry)

                        # Get summary
                        summary = ""
                        if hasattr(entry, 'summary'):
                            summary = self.clean_text(entry.summary)
                        elif hasattr(entry, 'description'):
                            summary = self.clean_text(entry.description)

                        # Get category from feed name
                        category = self.category_map.get(feed_name, "general")

                        items.append(CollectedItem(
                            source="rss",
                            source_name=self._format_source_name(feed_name),
                            source_url=feed_url,
                            category=category,
                            title=self.clean_text(entry.get('title', 'Untitled')),
                            summary=self.truncate_text(summary, 500),
                            url=entry.get('link', ''),
                            published=published,
                            author=entry.get('author', ''),
                            metadata={
                                "feed": feed_name,
                                "author": entry.get('author', ''),
                            },
                            raw_content=summary,
                        ))
                    except Exception as e:
                        self._logger.debug(f"Failed to parse entry in {feed_name}: {e}")
                        continue

                self._logger.debug(f"Feed {feed_name}: parsed {len(items)} items")

        except asyncio.TimeoutError:
            self._logger.warning(
                f"Feed {feed_name} timed out after {RSS_TIMEOUT_SECONDS}s"
            )
        except Exception as e:
            self._logger.warning(f"Feed {feed_name} error: {type(e).__name__}: {e}")

        return items

    def _parse_date(self, entry) -> datetime:
        """Parse date from RSS entry."""
        try:
            if hasattr(entry, 'published_parsed') and entry.published_parsed:
                return datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
            elif hasattr(entry, 'updated_parsed') and entry.updated_parsed:
                return datetime(*entry.updated_parsed[:6], tzinfo=timezone.utc)
        except Exception:
            pass
        return datetime.now(timezone.utc)

    def _format_source_name(self, feed_name: str) -> str:
        """Format feed name for display."""
        name_map = {
            "reuters_world": "Reuters",
            "ap_top": "AP News",
            "bbc_world": "BBC World",
            "ars_technica": "Ars Technica",
            "hacker_news": "Hacker News",
            "big_squid_rc": "Big Squid RC",
            "chattanoogan_breaking": "Chattanoogan",
            "wdef_news": "WDEF News",
        }
        return name_map.get(feed_name, feed_name.replace("_", " ").title())

    async def collect(self) -> List[CollectedItem]:
        """Fetch all RSS feeds in parallel."""
        self._logger.info(f"Fetching {len(self.feeds)} RSS feeds")
        all_items = []

        async with aiohttp.ClientSession() as session:
            tasks = [
                self._fetch_feed(session, name, url)
                for name, url in self.feeds.items()
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for name, result in zip(self.feeds.keys(), results):
                if isinstance(result, Exception):
                    self._logger.error(f"Feed {name} failed: {result}")
                elif isinstance(result, list):
                    all_items.extend(result)

        self._logger.info(
            f"RSS collection complete: {len(all_items)} items from {len(self.feeds)} feeds"
        )
        return all_items
