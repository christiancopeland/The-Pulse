"""
Local news collector for The Pulse.

Collects news from local sources (Chattanooga/NW Georgia area) via RSS feeds
and web scraping. Automatically detects crime-related content.

Uses the unified crawl4ai service for web scraping.
"""
import asyncio
import aiohttp
import feedparser
from datetime import datetime, timezone
from typing import List, Optional
import logging

from .base import BaseCollector, CollectedItem
from .config import (
    LOCAL_NEWS_SOURCES,
    SCRAPE_TARGETS,
    SCRAPE_DELAY_SECONDS,
    RSS_TIMEOUT_SECONDS,
    CRIME_KEYWORDS,
)

# Import the unified crawl4ai service
try:
    from app.services.crawl4ai_service import Crawl4AIService, CRAWL4AI_AVAILABLE
except ImportError:
    CRAWL4AI_AVAILABLE = False

logger = logging.getLogger(__name__)


class LocalNewsCollector(BaseCollector):
    """Collects local news from Chattanooga/NW Georgia sources."""

    def __init__(self):
        super().__init__()
        self.sources = LOCAL_NEWS_SOURCES
        # Filter scrape targets to local/crime categories only
        self.scrape_targets = {
            k: v for k, v in SCRAPE_TARGETS.items()
            if v.get("category") in ["local", "crime_local"]
        }

    @property
    def name(self) -> str:
        return "Local News"

    @property
    def source_type(self) -> str:
        return "local"

    def _is_crime_content(self, title: str, summary: str) -> bool:
        """Check if content is crime-related."""
        text = (title + " " + summary).lower()
        return any(keyword in text for keyword in CRIME_KEYWORDS)

    async def _fetch_rss(
        self,
        session: aiohttp.ClientSession,
        source_name: str,
        source_config: dict,
    ) -> List[CollectedItem]:
        """Fetch local news from RSS feed."""
        items = []
        rss_url = source_config.get("rss")
        if not rss_url:
            return items

        try:
            self._logger.debug(f"Fetching local RSS: {source_name}")

            async with session.get(
                rss_url, timeout=aiohttp.ClientTimeout(total=RSS_TIMEOUT_SECONDS)
            ) as response:
                if response.status != 200:
                    self._logger.warning(
                        f"Local feed {source_name} returned status {response.status}"
                    )
                    return items

                content = await response.text()
                feed = feedparser.parse(content)

                for entry in feed.entries[:20]:
                    try:
                        # Parse date
                        published = datetime.now(timezone.utc)
                        if hasattr(entry, 'published_parsed') and entry.published_parsed:
                            published = datetime(
                                *entry.published_parsed[:6], tzinfo=timezone.utc
                            )

                        # Get summary
                        summary = ""
                        if hasattr(entry, 'summary'):
                            summary = self.clean_text(entry.summary)
                        elif hasattr(entry, 'description'):
                            summary = self.clean_text(entry.description)

                        title = self.clean_text(entry.get('title', 'Untitled'))

                        # Detect crime-related content
                        is_crime = self._is_crime_content(title, summary)
                        category = "crime_local" if is_crime else "local"

                        items.append(CollectedItem(
                            source="local",
                            source_name=self._format_source_name(source_name),
                            source_url=rss_url,
                            category=category,
                            title=title,
                            summary=self.truncate_text(summary, 500),
                            url=entry.get('link', ''),
                            published=published,
                            metadata={
                                "feed": source_name,
                                "is_crime": is_crime,
                            },
                            raw_content=summary,
                        ))
                    except Exception as e:
                        self._logger.debug(f"Failed to parse entry: {e}")
                        continue

                self._logger.debug(f"Local {source_name}: parsed {len(items)} items")

        except asyncio.TimeoutError:
            self._logger.warning(f"Local feed {source_name} timed out")
        except Exception as e:
            self._logger.warning(
                f"Local feed {source_name} error: {type(e).__name__}: {e}"
            )

        return items

    def _format_source_name(self, source_name: str) -> str:
        """Format source name for display."""
        name_map = {
            "chattanoogan": "Chattanoogan",
            "wrcb": "WRCB",
            "wdef": "WDEF",
        }
        return name_map.get(source_name, source_name.title())

    async def _scrape_with_crawl4ai(
        self,
        source_name: str,
        source_config: dict,
    ) -> List[CollectedItem]:
        """Scrape content using the unified crawl4ai service."""
        items = []
        url = source_config.get("url")
        if not url:
            return items

        if not CRAWL4AI_AVAILABLE:
            self._logger.warning("crawl4ai service not available")
            return items

        try:
            async with Crawl4AIService() as service:
                content, final_url, metadata = await service.fetch(url)

                if content:
                    content = content[:2000]
                    title = metadata.get("title") or f"Latest from {source_name.replace('_', ' ').title()}"

                    items.append(CollectedItem(
                        source="local",
                        source_name=source_name.replace("_", " ").title(),
                        source_url=url,
                        category=source_config.get("category", "local"),
                        title=self.clean_text(title),
                        summary=self.truncate_text(self.clean_text(content), 500),
                        url=final_url,
                        published=datetime.now(timezone.utc),
                        metadata={"scraped": True},
                        raw_content=content,
                    ))

        except Exception as e:
            self._logger.warning(f"crawl4ai failed for {source_name}: {e}")

        return items

    async def collect(self) -> List[CollectedItem]:
        """Collect from all local news sources."""
        all_items = []

        async with aiohttp.ClientSession() as session:
            # Collect from RSS feeds in parallel
            rss_tasks = [
                self._fetch_rss(session, name, config)
                for name, config in self.sources.items()
                if config.get("rss")
            ]
            rss_results = await asyncio.gather(*rss_tasks, return_exceptions=True)

            for result in rss_results:
                if isinstance(result, list):
                    all_items.extend(result)
                elif isinstance(result, Exception):
                    self._logger.debug(f"RSS task failed: {result}")

        # Scrape additional sources (sequentially with delay)
        for name, config in self.scrape_targets.items():
            try:
                scraped = await self._scrape_with_crawl4ai(name, config)
                all_items.extend(scraped)
                await asyncio.sleep(SCRAPE_DELAY_SECONDS)
            except Exception as e:
                self._logger.warning(f"Scraping {name} failed: {e}")
                continue

        self._logger.info(f"Local news collection complete: {len(all_items)} items")
        return all_items
