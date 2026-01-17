"""
RC manufacturer collector for The Pulse.

Collects new product information from RC hobby manufacturers via web scraping.
Uses the unified crawl4ai service to extract product announcements.
"""
import asyncio
from datetime import datetime, timezone
from typing import List
import logging

from .base import BaseCollector, CollectedItem
from .config import SCRAPE_TARGETS, SCRAPE_DELAY_SECONDS

# Import the unified crawl4ai service
try:
    from app.services.crawl4ai_service import Crawl4AIService, CRAWL4AI_AVAILABLE
except ImportError:
    CRAWL4AI_AVAILABLE = False

logger = logging.getLogger(__name__)


class RCManufacturerCollector(BaseCollector):
    """Collects new product info from RC manufacturers."""

    def __init__(self):
        super().__init__()
        # Filter to RC industry targets only
        self.targets = {
            k: v for k, v in SCRAPE_TARGETS.items()
            if v.get("category") == "rc_industry"
        }
        self._logger.debug(f"Initialized with {len(self.targets)} targets")

    @property
    def name(self) -> str:
        return "RC Manufacturers"

    @property
    def source_type(self) -> str:
        return "rc_manufacturer"

    async def _scrape_with_crawl4ai(
        self,
        source_name: str,
        url: str,
    ) -> List[CollectedItem]:
        """Scrape manufacturer site using the unified crawl4ai service."""
        items = []

        if not CRAWL4AI_AVAILABLE:
            self._logger.warning("crawl4ai service not available")
            return items

        try:
            async with Crawl4AIService() as service:
                content, final_url, metadata = await service.fetch(url)

                if content:
                    # Parse content for product info
                    lines = content.split('\n')
                    current_product = None

                    for line in lines:
                        line = line.strip()
                        if not line:
                            continue

                        # Headers often indicate products
                        if line.startswith('#'):
                            if current_product and current_product.title:
                                items.append(current_product)
                            title = line.lstrip('#').strip()
                            if title and len(title) > 5:
                                current_product = CollectedItem(
                                    source="rc_manufacturer",
                                    source_name=self._format_source_name(source_name),
                                    source_url=url,
                                    category="rc_industry",
                                    title=self.clean_text(title),
                                    summary="",
                                    url=final_url,
                                    published=datetime.now(timezone.utc),
                                    metadata={"type": "product"},
                                    raw_content="",
                                )
                        elif current_product and not current_product.summary:
                            # First non-header line after product title
                            current_product = CollectedItem(
                                source=current_product.source,
                                source_name=current_product.source_name,
                                source_url=current_product.source_url,
                                category=current_product.category,
                                title=current_product.title,
                                summary=self.truncate_text(self.clean_text(line), 500),
                                url=current_product.url,
                                published=current_product.published,
                                metadata=current_product.metadata,
                                raw_content=line,
                            )

                    if current_product and current_product.title:
                        items.append(current_product)

                    # If no structured products found, create single summary item
                    if not items and content:
                        page_title = metadata.get("title") or f"New Releases from {self._format_source_name(source_name)}"
                        items.append(CollectedItem(
                            source="rc_manufacturer",
                            source_name=self._format_source_name(source_name),
                            source_url=url,
                            category="rc_industry",
                            title=self.clean_text(page_title),
                            summary=self.truncate_text(self.clean_text(content), 500),
                            url=final_url,
                            published=datetime.now(timezone.utc),
                            metadata={"type": "summary"},
                            raw_content=content[:2000],
                        ))

        except Exception as e:
            self._logger.warning(f"Failed to scrape {source_name} with crawl4ai: {e}")

        self._logger.debug(f"Scraped {len(items)} items from {source_name}")
        return items[:10]  # Limit items per source

    def _format_source_name(self, source_name: str) -> str:
        """Format source name for display."""
        name_map = {
            "horizon_hobby": "Horizon Hobby",
            "traxxas": "Traxxas",
            "fms_hobby": "FMS Hobby",
        }
        return name_map.get(source_name, source_name.replace("_", " ").title())

    async def collect(self) -> List[CollectedItem]:
        """Collect from all RC manufacturer sources."""
        all_items = []

        if not self.targets:
            self._logger.warning(
                "RC Manufacturers collector has no targets configured. "
                "Add entries with category='rc_industry' to SCRAPE_TARGETS in config.py, "
                "or disable this collector if RC monitoring is not needed."
            )
            return all_items

        self._logger.info(f"Starting collection from {len(self.targets)} RC sources")

        # Scrape sequentially with delay to be respectful
        for name, config in self.targets.items():
            try:
                url = config.get("url")
                if url:
                    self._logger.debug(f"Scraping {name}: {url}")
                    scraped = await self._scrape_with_crawl4ai(name, url)
                    all_items.extend(scraped)
                    self._logger.info(f"{name}: collected {len(scraped)} items")
                    await asyncio.sleep(SCRAPE_DELAY_SECONDS)
            except Exception as e:
                self._logger.error(f"Error collecting from {name}: {e}")
                continue

        self._logger.info(f"RC collection complete: {len(all_items)} total items")
        return all_items
