"""
Enhanced GDELT news collector for The Pulse.

Collects geopolitical events, crime news, financial events, military activity,
and cyber security news from the GDELT Project API (FREE, unlimited).

GDELT monitors news media worldwide in 65+ languages and provides structured
event data with tone analysis, geographic coding, and theme classification.

API Documentation: https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/
"""
import asyncio
import aiohttp
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from urllib.parse import urlencode
import logging

from .base import BaseCollector, CollectedItem
from .config import API_TIMEOUT_SECONDS, GDELT_CRIME_THEMES

logger = logging.getLogger(__name__)


# Enhanced query templates for intelligence collection
GDELT_QUERY_TEMPLATES: Dict[str, Dict[str, Any]] = {
    "geopolitics": {
        "query": "sourcelang:english (domain:reuters.com OR domain:apnews.com OR domain:bbc.com)",
        "category": "geopolitics",
        "description": "Major news from authoritative sources",
    },
    "crime_international": {
        "query": "(theme:CRIME OR theme:TERROR OR theme:ARREST OR theme:KILL) sourcelang:english",
        "category": "crime_international",
        "description": "International crime and terrorism",
    },
    "military_activity": {
        "query": "(theme:MILITARY OR theme:ARMED_CONFLICT OR theme:TAX_FNCACT_MILITARY) sourcelang:english",
        "category": "military",
        "description": "Military operations and armed conflicts",
    },
    "political_instability": {
        "query": "(theme:POLITICAL_TURMOIL OR theme:PROTEST OR theme:ELECTION OR theme:COUP) sourcelang:english",
        "category": "political",
        "description": "Political unrest and governance events",
    },
    "cyber_security": {
        "query": "(cyber AND (attack OR breach OR hack OR ransomware)) OR theme:CYBER_ATTACK sourcelang:english",
        "category": "cyber",
        "description": "Cybersecurity incidents and threats",
    },
    "financial_events": {
        "query": "(theme:ECON_BANKRUPTCY OR theme:ECON_STOCKMARKET OR theme:ECON_DEBT) sourcelang:english",
        "category": "financial",
        "description": "Financial and economic events",
    },
    "sanctions": {
        "query": "(sanctions OR embargo OR \"asset freeze\") (domain:.gov OR domain:reuters.com OR domain:ft.com) sourcelang:english",
        "category": "sanctions",
        "description": "Sanctions and trade restrictions",
    },
    "government_official": {
        "query": "(domain:.gov OR domain:.mil) sourcelang:english",
        "category": "government",
        "description": "Official government and military sources",
    },
}


class GDELTCollector(BaseCollector):
    """
    Enhanced GDELT collector for intelligence applications.

    Features:
    - Multiple predefined query templates for different intelligence domains
    - Tone analysis extraction for sentiment tracking
    - Geographic coding for location-based filtering
    - Theme classification for categorization
    - Parallel query execution for efficiency

    All queries are FREE and unlimited through GDELT DOC 2.0 API.
    """

    # GDELT API endpoints (all FREE)
    DOC_API = "https://api.gdeltproject.org/api/v2/doc/doc"
    GEO_API = "https://api.gdeltproject.org/api/v2/geo/geo"
    TV_API = "https://api.gdeltproject.org/api/v2/tv/tv"

    # Default intelligence-relevant templates (all 8 enabled)
    DEFAULT_TEMPLATES = [
        "geopolitics",
        "crime_international",
        "military_activity",
        "political_instability",
        "cyber_security",
        "financial_events",
        "sanctions",
        "government_official",
    ]

    def __init__(
        self,
        categories: Optional[List[str]] = None,
        max_items: int = 50,
        timespan: str = "24h",
        use_all_templates: bool = True,  # Changed default to True for intelligence use
    ):
        """
        Initialize enhanced GDELT collector.

        Args:
            categories: List of query template names to use
                       (e.g., ["geopolitics", "military_activity", "cyber_security"])
            max_items: Maximum items to fetch per query
            timespan: Time span for search (e.g., "24h", "48h", "7d")
            use_all_templates: If True, use all available query templates (default: True)
        """
        super().__init__()

        if use_all_templates:
            self.categories = self.DEFAULT_TEMPLATES
        else:
            self.categories = categories or ["geopolitics", "crime_international"]

        self.max_items = max_items
        self.timespan = timespan

    @property
    def name(self) -> str:
        return "GDELT"

    @property
    def source_type(self) -> str:
        return "gdelt"

    def _build_query(self, query_type: str) -> str:
        """Build GDELT API query URL using templates or fallback."""
        params = {
            "format": "json",
            "maxrecords": str(self.max_items),
            "timespan": self.timespan,
            "sort": "DateDesc",
        }

        # Use template if available
        if query_type in GDELT_QUERY_TEMPLATES:
            params["query"] = GDELT_QUERY_TEMPLATES[query_type]["query"]
        elif query_type == "geopolitics":
            # Legacy fallback
            params["query"] = (
                "sourcelang:english "
                "domain:reuters.com OR domain:apnews.com OR domain:bbc.com"
            )
        elif query_type == "crime_international":
            # Legacy fallback
            themes = " OR ".join([f"theme:{t}" for t in GDELT_CRIME_THEMES])
            params["query"] = f"({themes}) sourcelang:english"
        else:
            params["query"] = "sourcelang:english"

        return f"{self.DOC_API}?{urlencode(params)}"

    async def _fetch_gdelt(
        self,
        session: aiohttp.ClientSession,
        query_type: str,
    ) -> List[CollectedItem]:
        """Fetch articles from GDELT for a specific query type."""
        items = []
        url = self._build_query(query_type)

        # Get category from template or use query_type
        category = query_type
        if query_type in GDELT_QUERY_TEMPLATES:
            category = GDELT_QUERY_TEMPLATES[query_type].get("category", query_type)

        try:
            self._logger.debug(f"Querying GDELT for {query_type}")

            async with session.get(
                url,
                timeout=aiohttp.ClientTimeout(total=API_TIMEOUT_SECONDS),
            ) as response:
                if response.status != 200:
                    self._logger.warning(
                        f"GDELT {query_type} returned status {response.status}"
                    )
                    return items

                data = await response.json()
                articles = data.get("articles", [])

                self._logger.debug(
                    f"GDELT {query_type}: received {len(articles)} articles"
                )

                for article in articles:
                    try:
                        # Parse date (GDELT format: YYYYMMDDTHHMMSSZ)
                        date_str = article.get("seendate", "")
                        if date_str:
                            try:
                                published = datetime.strptime(
                                    date_str[:15], "%Y%m%dT%H%M%S"
                                ).replace(tzinfo=timezone.utc)
                            except ValueError:
                                published = datetime.now(timezone.utc)
                        else:
                            published = datetime.now(timezone.utc)

                        # Get domain for source name
                        domain = article.get("domain", "gdelt")
                        source_name = self._format_domain(domain)

                        # Extract tone for sentiment analysis
                        tone = article.get("tone", 0)
                        try:
                            tone = float(tone) if tone else 0.0
                        except (ValueError, TypeError):
                            tone = 0.0

                        items.append(CollectedItem(
                            source="gdelt",
                            source_name=source_name,
                            source_url=self.DOC_API,
                            category=category,
                            title=self.clean_text(article.get("title", "Untitled")),
                            summary=self.truncate_text(
                                article.get("title", ""), 500
                            ),  # GDELT doesn't provide summaries
                            url=article.get("url", ""),
                            published=published,
                            metadata={
                                "domain": domain,
                                "language": article.get("language", ""),
                                "sourcecountry": article.get("sourcecountry", ""),
                                "tone": tone,
                                "gdelt_query": query_type,
                                "socialimage": article.get("socialimage", ""),
                                "themes": article.get("themes", []),
                                "locations": article.get("locations", []),
                            },
                            raw_content="",
                        ))
                    except Exception as e:
                        self._logger.debug(f"Failed to parse GDELT article: {e}")
                        continue

        except asyncio.TimeoutError:
            self._logger.warning(
                f"GDELT {query_type} timed out after {API_TIMEOUT_SECONDS}s"
            )
        except Exception as e:
            self._logger.warning(f"GDELT {query_type} error: {type(e).__name__}: {e}")

        return items

    def _format_domain(self, domain: str) -> str:
        """Format domain as source name."""
        domain_names = {
            "reuters.com": "Reuters (via GDELT)",
            "apnews.com": "AP News (via GDELT)",
            "bbc.com": "BBC (via GDELT)",
            "bbc.co.uk": "BBC (via GDELT)",
            "nytimes.com": "NY Times (via GDELT)",
            "washingtonpost.com": "Washington Post (via GDELT)",
            "theguardian.com": "The Guardian (via GDELT)",
        }
        return domain_names.get(domain, f"{domain} (via GDELT)")

    async def collect(self) -> List[CollectedItem]:
        """Fetch all GDELT queries in parallel."""
        self._logger.info(f"Querying GDELT for categories: {self.categories}")
        all_items = []

        async with aiohttp.ClientSession() as session:
            tasks = [
                self._fetch_gdelt(session, cat)
                for cat in self.categories
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for cat, result in zip(self.categories, results):
                if isinstance(result, Exception):
                    self._logger.error(f"GDELT {cat} failed: {result}")
                elif isinstance(result, list):
                    all_items.extend(result)

        self._logger.info(f"GDELT collection complete: {len(all_items)} items")
        return all_items
