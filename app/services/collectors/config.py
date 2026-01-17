"""
Collection configuration for The Pulse.

Contains all settings for collectors including feed URLs, API endpoints,
scrape targets, rate limiting, and source prioritization.
"""
import os
from pathlib import Path

# Rate limiting
SCRAPE_DELAY_SECONDS = 2.0  # Delay between scrape requests
RSS_TIMEOUT_SECONDS = 30
API_TIMEOUT_SECONDS = 60

# Reddit settings
REDDIT_CLIENT_ID = os.getenv("REDDIT_CLIENT_ID", "")
REDDIT_CLIENT_SECRET = os.getenv("REDDIT_CLIENT_SECRET", "")
REDDIT_USER_AGENT = os.getenv("REDDIT_USER_AGENT", "ThePulse/1.0")
# Intelligence-relevant subreddits (replaced RC hobby subreddits)
REDDIT_SUBREDDITS = [
    "geopolitics",      # Geopolitical analysis and discussion
    "worldnews",        # International news
    "intelligence",     # Intelligence community discussions
    "credibledefense",  # Defense analysis
    "cybersecurity",    # Cyber threats and security
    "Economics",        # Economic intelligence
]
REDDIT_POSTS_PER_SUB = 25

# Subreddit to category mapping for proper classification
# NOTE: All keys must be lowercase as subreddit names are lowercased before lookup
REDDIT_CATEGORY_MAP = {
    "geopolitics": "geopolitics",
    "worldnews": "geopolitics",
    "intelligence": "geopolitics",
    "credibledefense": "military",
    "cybersecurity": "cyber",
    "economics": "financial",  # Matches "Economics" subreddit (lowercased)
}

# ArXiv settings - Expanded categories for broader research coverage
ARXIV_CATEGORIES = [
    # AI/ML (existing)
    "cs.AI",   # Artificial Intelligence
    "cs.LG",   # Machine Learning
    "cs.CL",   # Computation and Language (NLP)

    # Security (NEW - critical gap)
    "cs.CR",   # Cryptography and Security

    # Systems (NEW - infrastructure intelligence)
    "cs.DC",   # Distributed Computing
    "cs.NI",   # Networking and Internet

    # Software Engineering (NEW)
    "cs.SE",   # Software Engineering

    # Robotics/Autonomous Systems
    "cs.RO",   # Robotics
]
ARXIV_MAX_PAPERS = 100  # Increased to accommodate more categories

# RSS Feeds
# Dict of feed_name -> feed_url
# Focused on intelligence-relevant sources (RC feeds removed)
RSS_FEEDS = {
    # World News / Geopolitics (Tier 1)
    "reuters_world": "https://feeds.reuters.com/Reuters/worldNews",
    "ap_top": "https://apnews.com/apf-topnews/feed",
    "bbc_world": "https://feeds.bbci.co.uk/news/world/rss.xml",
    "al_jazeera": "https://www.aljazeera.com/xml/rss/all.xml",

    # Defense & Military (Tier 1)
    "defense_news": "https://www.defensenews.com/arc/outboundfeeds/rss/category/global/?outputType=xml",
    "breaking_defense": "https://breakingdefense.com/feed/",
    "war_on_rocks": "https://warontherocks.com/feed/",

    # Foreign Policy & Analysis (Tier 1)
    "foreign_policy": "https://foreignpolicy.com/feed/",
    "lawfare": "https://www.lawfaremedia.org/rss.xml",
    "council_fr": "https://www.cfr.org/rss.xml",

    # Think Tanks & Analysis (Tier 1 - Deep Analysis) - Verified 2026-01-16
    # NOTE: Brookings/Carnegie/Chatham House RSS feeds unavailable or blocked
    "csis_analysis": "https://www.csis.org/rss.xml",
    "rand_commentary": "https://www.rand.org/pubs/commentary.xml",
    "atlantic_council": "https://www.atlanticcouncil.org/feed/",

    # AI Provider Blogs (Tier 1 - Primary Intelligence) - Verified 2026-01-16
    "openai_blog": "https://openai.com/news/rss.xml",
    "google_ai": "https://blog.google/innovation-and-ai/technology/ai/rss/",
    "deepmind": "https://deepmind.google/blog/rss.xml",
    "huggingface_blog": "https://huggingface.co/blog/feed.xml",
    "nvidia_ai": "https://blogs.nvidia.com/feed/",
    "stability_ai": "https://stability.ai/news?format=rss",

    # Security Advisories & News (Tier 1 - Critical Intelligence) - Verified 2026-01-16
    # NOTE: CISA killed RSS feeds in May 2025, shifted to email/social media only
    "hacker_news_security": "https://feeds.feedburner.com/TheHackersNews",
    "bleeping_computer": "https://www.bleepingcomputer.com/feed/",
    "the_register_security": "https://www.theregister.com/security/headlines.atom",
    "dark_reading": "https://www.darkreading.com/rss.xml",

    # Federal Law Enforcement (Tier 1 - Criminal Intelligence) - Verified 2026-01-16
    # NOTE: DOJ/ATF/DEA/USMS RSS feeds are blocked or unavailable
    "fbi_news": "https://www.fbi.gov/feeds/national-press-releases/RSS",

    # National Security & Defense Analysis - Verified 2026-01-16
    "just_security": "https://www.justsecurity.org/feed/",
    "cipher_brief": "https://www.thecipherbrief.com/feeds/feed.rss",
    "long_war_journal": "https://www.longwarjournal.org/feed",

    # Academic Preprints & Science Journals - Verified 2026-01-16
    # NOTE: SSRN blocks public RSS access (403), PubMed requires custom search-generated feeds
    "biorxiv_all": "http://connect.biorxiv.org/biorxiv_xml.php?subject=all",
    "biorxiv_neuro": "http://connect.biorxiv.org/biorxiv_xml.php?subject=neuroscience",
    "medrxiv_all": "http://connect.medrxiv.org/medrxiv_xml.php?subject=all",
    "nature_journal": "https://www.nature.com/nature.rss",
    "science_news": "https://www.science.org/rss/news_current.xml",

    # Tech & Cyber (Tier 3)
    "ars_technica": "https://feeds.arstechnica.com/arstechnica/technology-lab",
    "hacker_news": "https://hnrss.org/frontpage",
    "krebs_security": "https://krebsonsecurity.com/feed/",
    "threatpost": "https://threatpost.com/feed/",

    # Local (Tier 2)
    "chattanoogan_breaking": "https://www.chattanoogan.com/Breaking-News/feed.rss",
    "wdef_news": "https://www.wdef.com/feed/",
    "wrcb_news": "https://www.local3news.com/search/?f=rss",  # Fixed 2026-01-16
}

# Feed to category mapping
RSS_CATEGORY_MAP = {
    # Geopolitics
    "reuters_world": "geopolitics",
    "ap_top": "geopolitics",
    "bbc_world": "geopolitics",
    "al_jazeera": "geopolitics",
    "foreign_policy": "geopolitics",
    "council_fr": "geopolitics",
    "lawfare": "geopolitics",

    # Military/Defense
    "defense_news": "military",
    "breaking_defense": "military",
    "war_on_rocks": "military",

    # AI Providers -> tech_ai category
    "openai_blog": "tech_ai",
    "google_ai": "tech_ai",
    "deepmind": "tech_ai",
    "huggingface_blog": "tech_ai",
    "nvidia_ai": "tech_ai",
    "stability_ai": "tech_ai",

    # Tech
    "ars_technica": "tech_general",
    "hacker_news": "tech_general",

    # Cyber Security
    "krebs_security": "cyber",
    "threatpost": "cyber",
    "hacker_news_security": "cyber",
    "bleeping_computer": "cyber",
    "the_register_security": "cyber",
    "dark_reading": "cyber",

    # Federal law enforcement -> crime_national category
    "fbi_news": "crime_national",

    # National security analysis -> geopolitics/military
    "just_security": "geopolitics",
    "cipher_brief": "geopolitics",
    "long_war_journal": "military",

    # Think tanks -> geopolitics
    "csis_analysis": "geopolitics",
    "rand_commentary": "geopolitics",
    "atlantic_council": "geopolitics",

    # Academic preprints -> research
    "biorxiv_all": "research",
    "biorxiv_neuro": "research",
    "medrxiv_all": "research",
    "nature_journal": "research",
    "science_news": "research",

    # Local
    "chattanoogan_breaking": "local",
    "wdef_news": "local",
    "wrcb_news": "local",
}

# Local news sources with RSS feeds
LOCAL_NEWS_SOURCES = {
    "chattanoogan": {
        "url": "https://www.chattanoogan.com",
        "rss": "https://www.chattanoogan.com/Breaking-News/feed.rss",
        "category": "local",
    },
    # WRCB/Local3News RSS feed removed - redirects to 404 as of 2026-01
    # TODO: Find alternative Chattanooga TV station RSS feed
}

# Scrape targets (for crawl4ai/trafilatura)
# RC hobby targets removed - focus on intelligence-relevant sources
SCRAPE_TARGETS = {
    # Local crime/safety (Tier 2)
    "hamilton_911": {
        "url": "https://www.hamiltontn.gov/publicsafety/911/active911.aspx",
        "category": "crime_local",
    },
}

# GDELT settings
GDELT_CRIME_THEMES = [
    "CRIME",
    "TERROR",
    "ARREST",
    "KILL",
    "PROTEST",
    "CONFLICT",
]

# Source priority for deduplication (higher = preferred)
SOURCE_PRIORITY = {
    "reuters": 10,
    "ap": 10,
    "bbc": 9,
    "gdelt": 8,
    "arxiv": 10,
    "chattanoogan": 9,
    "reddit": 5,
    "rcgroups": 5,
    "horizon_hobby": 7,
    "traxxas": 7,
    "hacker_news": 6,
}

# Category labels for display
CATEGORY_LABELS = {
    "geopolitics": "World Situation",
    "crime_international": "Crime & Safety - International",
    "crime_national": "Crime & Safety - National",
    "crime_local": "Crime & Safety - Local",
    "tech_ai": "Tech & AI",
    "tech_general": "Tech & AI",
    "research": "Research",  # ArXiv papers and academic research
    "rc_industry": "RC Industry",
    "local": "Local News",
    "weather": "Weather & Logistics",
    # New categories (Phase 3)
    "conflict": "Armed Conflict",
    "military": "Military & Defense",
    "political": "Political Events",
    "cyber": "Cybersecurity",
    "financial": "Financial & Business",
    "sanctions": "Sanctions & Trade",
    "government": "Government Sources",
    "pep": "Politically Exposed Persons",
    "crime": "Crime & Criminal Networks",
    "watchlist": "Watchlist Entities",
    # New categories (Phase 4 - Data Source Expansion)
    "humanitarian": "Humanitarian & Crisis",
    "legal": "Legal & Court",
    "terrorism": "Terrorism & Extremism",
}

# ACLED settings (FREE for research)
ACLED_API_BASE = "https://api.acleddata.com/acled/read"

# OpenSanctions settings (FREE with rate limits)
OPENSANCTIONS_API_BASE = "https://api.opensanctions.org"

# SEC EDGAR settings (FREE government data)
SEC_EDGAR_API_BASE = "https://data.sec.gov"
SEC_FORM_TYPES = ["8-K", "10-K", "10-Q", "13-F", "4", "S-1", "SC 13D", "SC 13G"]

# Crime detection keywords for local news
CRIME_KEYWORDS = [
    'arrest', 'murder', 'robbery', 'assault', 'theft',
    'shooting', 'drug', 'police', 'sheriff', 'crime',
    'charged', 'indicted', 'suspect', 'victim', 'homicide',
    'burglary', 'arson', 'kidnapping', 'fraud',
]
