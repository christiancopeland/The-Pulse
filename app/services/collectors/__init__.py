"""
Collection Engine for The Pulse.

This module provides automated content collection from multiple sources:
- RSS Feeds (Reuters, AP, BBC, tech sites, RC industry, local news)
- GDELT API (geopolitical events, crime news, military, cyber, financial)
- ACLED API (armed conflict, protests, political violence) - FREE for research
- OpenSanctions (sanctions, PEP data, watchlists) - FREE
- SEC EDGAR (corporate filings, insider trading) - FREE government data
- ArXiv API (AI/ML research papers)
- Reddit (subreddit posts)
- Local News (Chattanooga/NW Georgia)
ALL DATA SOURCES ARE FREE - No paid APIs required (except Claude Code subscription).

Usage:
    from app.services.collectors import CollectionScheduler, get_all_collectors

    # Get all collectors
    collectors = get_all_collectors()

    # Create and start scheduler
    scheduler = CollectionScheduler()
    for collector in collectors:
        scheduler.register(collector, timedelta(hours=1))
    await scheduler.start()

Environment Variables (optional - collectors work without these):
    ACLED_API_KEY: Free API key from https://developer.acleddata.com/
    ACLED_EMAIL: Email for ACLED API access
    OPENSANCTIONS_API_KEY: Optional key for higher rate limits
    SEC_CONTACT_EMAIL: Contact email for SEC API (required by SEC policy)
"""
import os
from typing import List, Optional, Dict, Any

from .base import BaseCollector, CollectedItem
from .rss_collector import RSSCollector
from .gdelt_collector import GDELTCollector
from .arxiv_collector import ArxivCollector
from .reddit_collector import RedditCollector
from .local_news_collector import LocalNewsCollector
from .scheduler import CollectionScheduler

# New FREE collectors (Phase 3)
from .acled_collector import ACLEDCollector
from .opensanctions_collector import OpenSanctionsCollector
from .sec_edgar_collector import SECEdgarCollector

__all__ = [
    # Base classes
    "BaseCollector",
    "CollectedItem",
    # Original collectors
    "RSSCollector",
    "GDELTCollector",
    "ArxivCollector",
    "RedditCollector",
    "LocalNewsCollector",
    # New FREE collectors (Phase 3)
    "ACLEDCollector",
    "OpenSanctionsCollector",
    "SECEdgarCollector",
    # Scheduler
    "CollectionScheduler",
    # Factory function
    "get_all_collectors",
]


def get_all_collectors(config: Optional[Dict[str, Any]] = None) -> List[BaseCollector]:
    """
    Get instances of all available collectors.

    ALL collectors use FREE data sources:
    - RSS: Free public feeds
    - GDELT: Free unlimited API
    - ACLED: Free for research (requires registration)
    - OpenSanctions: Free with rate limits
    - SEC EDGAR: Free government data
    - ArXiv: Free research papers
    - Reddit: Free JSON API
    - Local News: Free RSS/scraping

    Args:
        config: Optional configuration dict with keys:
            - acled_api_key: ACLED API key
            - acled_email: ACLED registration email
            - opensanctions_api_key: OpenSanctions API key (optional)
            - sec_contact_email: Email for SEC User-Agent
            - gdelt_use_all_templates: Use all GDELT query templates
            - reddit_client_id: Reddit OAuth client ID (optional)
            - reddit_client_secret: Reddit OAuth secret (optional)

    Returns:
        List of collector instances ready to run.
    """
    config = config or {}

    collectors: List[BaseCollector] = [
        # Core FREE collectors (no API key required)
        RSSCollector(),
        GDELTCollector(
            use_all_templates=config.get("gdelt_use_all_templates", False)
        ),
        ArxivCollector(),
        LocalNewsCollector(),

        # SEC EDGAR - FREE government data (no API key)
        SECEdgarCollector(
            contact_email=config.get("sec_contact_email") or os.getenv("SEC_CONTACT_EMAIL"),
        ),

        # OpenSanctions - FREE with rate limits (API key optional for higher limits)
        OpenSanctionsCollector(
            api_key=config.get("opensanctions_api_key") or os.getenv("OPENSANCTIONS_API_KEY"),
        ),
    ]

    # ACLED - FREE for research (requires free registration)
    acled_key = config.get("acled_api_key") or os.getenv("ACLED_API_KEY")
    acled_email = config.get("acled_email") or os.getenv("ACLED_EMAIL")
    if acled_key and acled_email:
        collectors.append(ACLEDCollector(
            api_key=acled_key,
            email=acled_email,
        ))

    # Reddit - FREE via public JSON API or OAuth
    reddit_client_id = config.get("reddit_client_id") or os.getenv("REDDIT_CLIENT_ID")
    if reddit_client_id:
        # Use OAuth for higher rate limits
        collectors.append(RedditCollector())
    else:
        # Public JSON API works without credentials
        collectors.append(RedditCollector())

    return collectors


def get_collector_status() -> Dict[str, Dict[str, Any]]:
    """
    Get configuration status for all collectors.

    Returns dict with collector availability and configuration status.
    """
    return {
        "rss": {"configured": True, "cost": "FREE"},
        "gdelt": {"configured": True, "cost": "FREE"},
        "arxiv": {"configured": True, "cost": "FREE"},
        "reddit": {"configured": True, "cost": "FREE"},
        "local_news": {"configured": True, "cost": "FREE"},
        "sec_edgar": {"configured": True, "cost": "FREE (government data)"},
        "opensanctions": {
            "configured": True,
            "cost": "FREE (rate-limited)",
            "api_key_set": bool(os.getenv("OPENSANCTIONS_API_KEY")),
        },
        "acled": {
            "configured": bool(os.getenv("ACLED_API_KEY") and os.getenv("ACLED_EMAIL")),
            "cost": "FREE (research registration required)",
            "registration_url": "https://developer.acleddata.com/",
        },
    }
