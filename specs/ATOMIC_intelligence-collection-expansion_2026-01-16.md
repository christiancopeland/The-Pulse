# Atomic Implementation Plan: Intelligence Collection Expansion

**Created:** 2026-01-16
**Parent Feature:** Intelligence Collection Gap Analysis
**Estimated Total Time:** 12.5 hours
**Priority:** HIGH - Addresses critical blind spots identified in gap analysis

---

## Executive Summary

This spec breaks down the intelligence collection expansion into atomic, independently-testable features. Based on the comprehensive gap analysis, we're addressing blind spots in:

1. AI Provider Content (100% missing → CRITICAL)
2. Security Advisories (70% missing → CRITICAL)
3. Academic Research Breadth (70% missing → HIGH)
4. Federal Criminal Intelligence (50% missing → HIGH)
5. Think Tank Analysis (40% missing → MEDIUM)
6. Dead Leg Cleanup (maintenance)

All data sources are **FREE** with no API keys required except optional ones for higher rate limits.

---

## Architecture Context

### Existing Infrastructure

| File | Purpose | Modification Type |
|------|---------|-------------------|
| [config.py](app/services/collectors/config.py) | Feed URLs, category mappings | ADD entries |
| [rss_collector.py](app/services/collectors/rss_collector.py) | RSS collection logic | NO CHANGES |
| [ranker.py](app/services/processing/ranker.py) | Source credibility scores | ADD scores |
| [__init__.py](app/services/collectors/__init__.py) | Collector registry | MINOR updates |

### Integration Points

```
config.py (RSS_FEEDS, RSS_CATEGORY_MAP)
    ↓
RSSCollector (auto-fetches all feeds)
    ↓
NewsItem (stored in DB)
    ↓
RelevanceRanker (scores by source_scores, category_importance)
    ↓
BriefingGenerator (uses ranked items)
```

**Key insight:** Adding RSS feeds requires ONLY config.py updates. The RSSCollector automatically processes any feeds in `RSS_FEEDS` dict.

---

## Atomic Features

### Phase 1: Config-Only Changes (No New Code)

These features require ONLY adding entries to existing config dicts. No new classes or logic needed.

---

#### PULSE-COLLECT-001: AI Provider RSS Feeds

**Description:** Add RSS feeds from major AI model providers to capture official announcements, research publications, and capability updates.

**Estimated Time:** 30 minutes

**Files Modified:**
- `app/services/collectors/config.py` - Add 9 feeds to RSS_FEEDS, RSS_CATEGORY_MAP
- `app/services/processing/ranker.py` - Add source scores

**Implementation:**

```python
# config.py - Add to RSS_FEEDS dict
RSS_FEEDS = {
    # ... existing feeds ...

    # AI Provider Blogs (Tier 1 - Primary Intelligence)
    "openai_blog": "https://openai.com/blog/rss.xml",
    "anthropic_blog": "https://www.anthropic.com/feed.xml",
    "google_ai": "https://blog.google/technology/ai/rss/",
    "meta_ai": "https://ai.meta.com/blog/rss/",
    "microsoft_research": "https://www.microsoft.com/en-us/research/feed/",
    "huggingface_blog": "https://huggingface.co/blog/feed.xml",
    "nvidia_ai": "https://blogs.nvidia.com/feed/",
    "stability_ai": "https://stability.ai/news/rss.xml",
    "mistral_ai": "https://mistral.ai/feed.xml",
}

# config.py - Add to RSS_CATEGORY_MAP
RSS_CATEGORY_MAP = {
    # ... existing mappings ...

    # AI Providers -> tech_ai category
    "openai_blog": "tech_ai",
    "anthropic_blog": "tech_ai",
    "google_ai": "tech_ai",
    "meta_ai": "tech_ai",
    "microsoft_research": "tech_ai",
    "huggingface_blog": "tech_ai",
    "nvidia_ai": "tech_ai",
    "stability_ai": "tech_ai",
    "mistral_ai": "tech_ai",
}
```

```python
# ranker.py - Add to source_scores dict
source_scores: Dict[str, float] = field(default_factory=lambda: {
    # ... existing scores ...

    # AI Provider blogs (high credibility - primary sources)
    "openai": 9.5,
    "anthropic": 9.5,
    "google_ai": 9.0,
    "meta_ai": 9.0,
    "microsoft_research": 9.0,
    "huggingface": 8.5,
    "nvidia": 8.5,
    "stability": 8.0,
    "mistral": 8.5,
})
```

**Acceptance Criteria:**
- [ ] All 9 RSS feeds added to RSS_FEEDS
- [ ] Category mappings added (all → tech_ai)
- [ ] Source scores added to ranker (8.0-9.5 range)
- [ ] RSS collector fetches new feeds without errors
- [ ] Items appear in news_items table with correct category

**Test Command:**
```bash
# Verify feeds are parseable
curl -s "https://openai.com/blog/rss.xml" | head -20
curl -s "https://www.anthropic.com/feed.xml" | head -20

# Trigger collection and check logs
curl -X POST http://localhost:8000/api/v1/collection/run?collector_name=RSS%20Feeds
```

**Risks:**
- Some AI providers may change RSS URLs or disable feeds
- Rate limiting unlikely for RSS (standard HTTP GET)

**Dependencies:** None

---

#### PULSE-COLLECT-002: Security Advisory RSS Feeds

**Description:** Add RSS feeds from cybersecurity news sources and official advisory channels.

**Estimated Time:** 30 minutes

**Files Modified:**
- `app/services/collectors/config.py` - Add 6 feeds
- `app/services/processing/ranker.py` - Add source scores

**Implementation:**

```python
# config.py - Add to RSS_FEEDS dict
RSS_FEEDS = {
    # ... existing feeds ...

    # Security Advisories & News (Tier 1 - Critical Intelligence)
    "cisa_alerts": "https://www.cisa.gov/uscert/ncas/alerts.xml",
    "cisa_current": "https://www.cisa.gov/uscert/ncas/current-activity.xml",
    "hacker_news_security": "https://feeds.feedburner.com/TheHackersNews",
    "bleeping_computer": "https://www.bleepingcomputer.com/feed/",
    "the_register_security": "https://www.theregister.com/security/headlines.atom",
    "dark_reading": "https://www.darkreading.com/rss.xml",
}

# config.py - Add to RSS_CATEGORY_MAP
RSS_CATEGORY_MAP = {
    # ... existing mappings ...

    # Security sources -> cyber category
    "cisa_alerts": "cyber",
    "cisa_current": "cyber",
    "hacker_news_security": "cyber",
    "bleeping_computer": "cyber",
    "the_register_security": "cyber",
    "dark_reading": "cyber",
}
```

```python
# ranker.py - Add to source_scores dict
source_scores: Dict[str, float] = field(default_factory=lambda: {
    # ... existing scores ...

    # Security sources (CISA is government authoritative)
    "cisa": 10.0,  # Official US government advisories
    "hacker_news_security": 8.0,  # TheHackerNews (not YC HN)
    "bleeping_computer": 8.0,
    "the_register": 7.5,
    "dark_reading": 7.5,
})
```

**Acceptance Criteria:**
- [ ] All 6 RSS feeds added
- [ ] Category mappings added (all → cyber)
- [ ] CISA sources scored at 10.0 (authoritative)
- [ ] Items appear with correct categorization

**Test Command:**
```bash
curl -s "https://www.cisa.gov/uscert/ncas/alerts.xml" | head -20
```

**Dependencies:** None

---

#### PULSE-COLLECT-003: Federal Criminal Intelligence Feeds

**Description:** Add RSS feeds from FBI, DOJ, and other federal law enforcement for criminal intelligence.

**Estimated Time:** 30 minutes

**Files Modified:**
- `app/services/collectors/config.py` - Add 5 feeds
- `app/services/processing/ranker.py` - Add source scores

**Implementation:**

```python
# config.py - Add to RSS_FEEDS dict
RSS_FEEDS = {
    # ... existing feeds ...

    # Federal Law Enforcement (Tier 1 - Criminal Intelligence)
    "fbi_news": "https://www.fbi.gov/feeds/fbi-news-stories/rss.xml",
    "doj_press": "https://www.justice.gov/feeds/opa/justice-news.xml",
    "atf_news": "https://www.atf.gov/news/rss.xml",
    "dea_news": "https://www.dea.gov/press-releases/rss.xml",
    "usms_news": "https://www.usmarshals.gov/news/rss.xml",
}

# config.py - Add to RSS_CATEGORY_MAP
RSS_CATEGORY_MAP = {
    # ... existing mappings ...

    # Federal law enforcement -> crime_national category
    "fbi_news": "crime_national",
    "doj_press": "crime_national",
    "atf_news": "crime_national",
    "dea_news": "crime_national",
    "usms_news": "crime_national",
}
```

```python
# ranker.py - Add to source_scores dict
source_scores: Dict[str, float] = field(default_factory=lambda: {
    # ... existing scores ...

    # Federal law enforcement (official government sources)
    "fbi": 10.0,
    "doj": 10.0,
    "justice": 10.0,  # Alternate match for DOJ
    "atf": 9.5,
    "dea": 9.5,
    "usmarshals": 9.5,
})
```

**Acceptance Criteria:**
- [ ] All 5 RSS feeds added
- [ ] Category mappings added (all → crime_national)
- [ ] Federal sources scored at 9.5-10.0

**Test Command:**
```bash
curl -s "https://www.fbi.gov/feeds/fbi-news-stories/rss.xml" | head -20
```

**Dependencies:** None

---

#### PULSE-COLLECT-004: Think Tank Analysis Feeds

**Description:** Add RSS feeds from major policy think tanks for deep geopolitical analysis.

**Estimated Time:** 30 minutes

**Files Modified:**
- `app/services/collectors/config.py` - Add 6 feeds
- `app/services/processing/ranker.py` - Add source scores

**Implementation:**

```python
# config.py - Add to RSS_FEEDS dict
RSS_FEEDS = {
    # ... existing feeds ...

    # Think Tanks & Analysis (Tier 1 - Deep Analysis)
    "csis_analysis": "https://www.csis.org/analysis/feed",
    "brookings": "https://www.brookings.edu/feed/",
    "rand_commentary": "https://www.rand.org/blog.xml",
    "carnegie": "https://carnegieendowment.org/rss/solr/?fa=experts",
    "atlantic_council": "https://www.atlanticcouncil.org/feed/",
    "chatham_house": "https://www.chathamhouse.org/rss.xml",
}

# config.py - Add to RSS_CATEGORY_MAP
RSS_CATEGORY_MAP = {
    # ... existing mappings ...

    # Think tanks -> geopolitics category
    "csis_analysis": "geopolitics",
    "brookings": "geopolitics",
    "rand_commentary": "geopolitics",
    "carnegie": "geopolitics",
    "atlantic_council": "geopolitics",
    "chatham_house": "geopolitics",
}
```

```python
# ranker.py - Add to source_scores dict
source_scores: Dict[str, float] = field(default_factory=lambda: {
    # ... existing scores ...

    # Think tanks (high credibility analysis)
    "csis": 9.0,
    "brookings": 9.0,
    "rand": 9.5,
    "carnegie": 9.0,
    "atlantic_council": 8.5,
    "chatham_house": 9.0,
})
```

**Acceptance Criteria:**
- [ ] All 6 RSS feeds added
- [ ] Category mappings added (all → geopolitics)
- [ ] Sources scored appropriately (8.5-9.5)

**Dependencies:** None

---

#### PULSE-COLLECT-005: Academic Preprint Feeds

**Description:** Add RSS feeds from bioRxiv, medRxiv, and other preprint servers to expand research coverage beyond ArXiv CS categories.

**Estimated Time:** 30 minutes

**Files Modified:**
- `app/services/collectors/config.py` - Add 4 feeds
- `app/services/processing/ranker.py` - Add source scores

**Implementation:**

```python
# config.py - Add to RSS_FEEDS dict
RSS_FEEDS = {
    # ... existing feeds ...

    # Academic Preprints (Research Intelligence)
    "biorxiv_all": "http://connect.biorxiv.org/biorxiv_xml.php?subject=all",
    "medrxiv_all": "http://connect.medrxiv.org/medrxiv_xml.php?subject=all",
    "ssrn_new": "https://papers.ssrn.com/sol3/Jeljour_results.cfm?form_name=journalBrowse&journal_id=&Network=no&lim=false&npage=1&requesttype=RSS",
    "papers_with_code": "https://paperswithcode.com/latest/rss",
}

# config.py - Add to RSS_CATEGORY_MAP
RSS_CATEGORY_MAP = {
    # ... existing mappings ...

    # Academic preprints -> research category
    "biorxiv_all": "research",
    "medrxiv_all": "research",
    "ssrn_new": "research",
    "papers_with_code": "research",
}
```

```python
# ranker.py - Add to source_scores dict
source_scores: Dict[str, float] = field(default_factory=lambda: {
    # ... existing scores ...

    # Academic preprints
    "biorxiv": 9.0,
    "medrxiv": 9.0,
    "ssrn": 8.5,
    "papers_with_code": 8.5,
    "paperswithcode": 8.5,  # Alternate match
})
```

**Acceptance Criteria:**
- [ ] All 4 RSS feeds added
- [ ] Category mappings added (all → research)
- [ ] Sources scored appropriately

**Dependencies:** None

---

#### PULSE-COLLECT-006: ArXiv Category Expansion

**Description:** Expand ArXiv categories beyond cs.AI, cs.LG, cs.CL to include security, systems, and software engineering.

**Estimated Time:** 15 minutes

**Files Modified:**
- `app/services/collectors/config.py` - Expand ARXIV_CATEGORIES list

**Implementation:**

```python
# config.py - Expand ARXIV_CATEGORIES
# Before:
# ARXIV_CATEGORIES = ["cs.AI", "cs.LG", "cs.CL"]

# After:
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

    # Software Engineering (NEW - per user interest)
    "cs.SE",   # Software Engineering

    # Robotics/Autonomous Systems
    "cs.RO",   # Robotics
]

# Also increase max papers to accommodate more categories
ARXIV_MAX_PAPERS = 100  # Was 50
```

**Acceptance Criteria:**
- [ ] ARXIV_CATEGORIES expanded to 8 categories
- [ ] ARXIV_MAX_PAPERS increased to 100
- [ ] ArXiv collector fetches papers from new categories

**Test Command:**
```bash
# Trigger ArXiv collection and check for new categories
curl -X POST http://localhost:8000/api/v1/collection/run?collector_name=ArXiv
# Check logs for "Fetching up to 100 papers from categories"
```

**Dependencies:** None

---

#### PULSE-COLLECT-007: Ranker Category Importance Update

**Description:** Ensure new source categories (tech_ai, research) have appropriate importance scores.

**Estimated Time:** 15 minutes

**Files Modified:**
- `app/services/processing/ranker.py` - Update category_importance

**Implementation:**

```python
# ranker.py - Verify/update category_importance
category_importance: Dict[str, float] = field(default_factory=lambda: {
    # ... existing entries ...

    # Ensure these have appropriate scores:
    "tech_ai": 8.5,      # Was 8.0, increase for AI provider content
    "research": 8.0,     # Keep at 8.0 for academic papers
    "crime_national": 9.0,  # Add if missing

    # Keep cyber high
    "cyber": 9.0,        # Increase from 8.5 for CISA content
})
```

**Acceptance Criteria:**
- [ ] tech_ai category importance >= 8.5
- [ ] cyber category importance >= 9.0
- [ ] crime_national category exists and >= 9.0
- [ ] research category importance >= 8.0

**Dependencies:** PULSE-COLLECT-001 through 006

---

### Phase 2: Cleanup (Can be done anytime)

---

#### PULSE-COLLECT-008: Remove RC Manufacturer Collector

**Description:** Remove or disable the RCManufacturerCollector which has no targets configured and logs warnings every run.

**Estimated Time:** 15 minutes

**Files Modified:**
- `app/services/collectors/__init__.py` - Remove from get_all_collectors()

**Implementation:**

```python
# __init__.py - Remove RCManufacturerCollector from imports and get_all_collectors()

# Remove this import:
# from .rc_manufacturer_collector import RCManufacturerCollector

# Remove from __all__:
# "RCManufacturerCollector",

# In get_all_collectors(), remove this line:
# RCManufacturerCollector(),
```

**Alternative (Soft Disable):**
```python
# In get_all_collectors(), wrap in conditional:
if config.get("enable_rc_collector", False):
    collectors.append(RCManufacturerCollector())
```

**Acceptance Criteria:**
- [ ] No warnings about "RC Manufacturers collector has no targets" in logs
- [ ] Collector status endpoint no longer lists rc_manufacturers
- [ ] File can be kept for future use but not instantiated

**Dependencies:** None

---

#### PULSE-COLLECT-009: Fix/Replace Broken WRCB Feed

**Description:** The WRCB/Local3News RSS feed returns 404. Either find replacement or remove from config.

**Estimated Time:** 30 minutes

**Files Modified:**
- `app/services/collectors/config.py` - Update LOCAL_NEWS_SOURCES

**Implementation:**

Option A: Find alternative Chattanooga TV station RSS
```python
# Research alternative feeds:
# - WTVC (NewsChannel 9): Check for RSS
# - WRCB (News Channel 3): Confirm still dead
# - WDEF: Already have this one

# If found, add to LOCAL_NEWS_SOURCES:
LOCAL_NEWS_SOURCES = {
    "chattanoogan": {
        "url": "https://www.chattanoogan.com",
        "rss": "https://www.chattanoogan.com/Breaking-News/feed.rss",
        "category": "local",
    },
    "wtvc_news": {  # If RSS available
        "url": "https://newschannel9.com",
        "rss": "https://newschannel9.com/feed",  # Verify URL
        "category": "local",
    },
}
```

Option B: Remove dead comment and document
```python
# Already done - just verify no active references to WRCB
```

**Acceptance Criteria:**
- [ ] No 404 errors in RSS collection logs
- [ ] Either new local TV RSS added OR dead reference fully removed
- [ ] Documentation updated if no replacement found

**Dependencies:** None

---

### Phase 3: New Collector Classes (Higher Effort)

These require creating new Python files but follow the established BaseCollector pattern.

---

#### PULSE-COLLECT-010: NVD Vulnerability API Collector

**Description:** Create a new collector for NIST National Vulnerability Database to get structured CVE data.

**Estimated Time:** 3 hours

**Files Created:**
- `app/services/collectors/nvd_collector.py` - New collector class

**Files Modified:**
- `app/services/collectors/__init__.py` - Register collector
- `app/services/collectors/config.py` - Add NVD settings

**Implementation Pattern:**

```python
# nvd_collector.py
"""
NVD (National Vulnerability Database) collector for The Pulse.

Collects recent CVE data from NIST's free REST API.
API Docs: https://nvd.nist.gov/developers/vulnerabilities
"""
import aiohttp
from datetime import datetime, timezone, timedelta
from typing import List, Optional
import logging

from .base import BaseCollector, CollectedItem
from .config import API_TIMEOUT_SECONDS

logger = logging.getLogger(__name__)

NVD_API_BASE = "https://services.nvd.nist.gov/rest/json/cves/2.0"


class NVDCollector(BaseCollector):
    """Collects recent CVE vulnerabilities from NIST NVD."""

    def __init__(
        self,
        days_back: int = 7,
        max_results: int = 100,
        severity_filter: Optional[List[str]] = None,  # CRITICAL, HIGH, MEDIUM, LOW
    ):
        super().__init__()
        self.days_back = days_back
        self.max_results = max_results
        self.severity_filter = severity_filter or ["CRITICAL", "HIGH"]

    @property
    def name(self) -> str:
        return "NVD Vulnerabilities"

    @property
    def source_type(self) -> str:
        return "nvd"

    async def collect(self) -> List[CollectedItem]:
        """Fetch recent CVEs from NVD API."""
        items = []

        # Calculate date range
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=self.days_back)

        params = {
            "pubStartDate": start_date.strftime("%Y-%m-%dT%H:%M:%S.000"),
            "pubEndDate": end_date.strftime("%Y-%m-%dT%H:%M:%S.000"),
            "resultsPerPage": self.max_results,
        }

        # Add severity filter if specified
        if self.severity_filter:
            params["cvssV3Severity"] = self.severity_filter[0]  # API takes one at a time

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    NVD_API_BASE,
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=API_TIMEOUT_SECONDS),
                ) as response:
                    if response.status != 200:
                        self._logger.error(f"NVD API returned {response.status}")
                        return items

                    data = await response.json()

                    for vuln in data.get("vulnerabilities", []):
                        cve = vuln.get("cve", {})
                        cve_id = cve.get("id", "")

                        # Extract description
                        descriptions = cve.get("descriptions", [])
                        desc_en = next(
                            (d["value"] for d in descriptions if d.get("lang") == "en"),
                            "No description available"
                        )

                        # Extract severity from CVSS v3.1
                        metrics = cve.get("metrics", {})
                        cvss_v31 = metrics.get("cvssMetricV31", [{}])[0] if metrics.get("cvssMetricV31") else {}
                        cvss_data = cvss_v31.get("cvssData", {})
                        severity = cvss_data.get("baseSeverity", "UNKNOWN")
                        base_score = cvss_data.get("baseScore", 0.0)

                        # Build title
                        title = f"[{severity}] {cve_id}: {desc_en[:100]}..."

                        items.append(CollectedItem(
                            source="nvd",
                            source_name="NIST NVD",
                            source_url="https://nvd.nist.gov",
                            category="cyber",
                            title=title,
                            summary=self.truncate_text(desc_en, 500),
                            url=f"https://nvd.nist.gov/vuln/detail/{cve_id}",
                            published=datetime.fromisoformat(
                                cve.get("published", "").replace("Z", "+00:00")
                            ),
                            metadata={
                                "cve_id": cve_id,
                                "severity": severity,
                                "base_score": base_score,
                                "vector_string": cvss_data.get("vectorString", ""),
                            },
                            raw_content=desc_en,
                        ))

            self._logger.info(f"Collected {len(items)} CVEs from NVD")

        except Exception as e:
            self._logger.error(f"NVD API error: {e}")

        return items
```

**Acceptance Criteria:**
- [ ] NVDCollector class created following BaseCollector pattern
- [ ] Fetches CRITICAL and HIGH severity CVEs from past 7 days
- [ ] Items categorized as "cyber"
- [ ] Registered in get_all_collectors()
- [ ] Appears in collector status endpoint

**API Notes:**
- NVD API is FREE, no key required
- Rate limit: 5 requests per 30 seconds (without API key)
- API key available for higher limits: https://nvd.nist.gov/developers/request-an-api-key

**Dependencies:** PULSE-COLLECT-002 (security category setup)

---

#### PULSE-COLLECT-011: Semantic Scholar API Collector

**Description:** Create collector for Semantic Scholar's free API to discover research papers with citation context.

**Estimated Time:** 3 hours

**Files Created:**
- `app/services/collectors/semantic_scholar_collector.py`

**Files Modified:**
- `app/services/collectors/__init__.py` - Register collector
- `app/services/collectors/config.py` - Add settings

**Implementation Pattern:**

```python
# semantic_scholar_collector.py
"""
Semantic Scholar API collector for The Pulse.

Fetches recent papers with AI-powered relevance from Semantic Scholar.
API Docs: https://api.semanticscholar.org/
"""
import aiohttp
from datetime import datetime, timezone
from typing import List, Optional
import logging

from .base import BaseCollector, CollectedItem
from .config import API_TIMEOUT_SECONDS

logger = logging.getLogger(__name__)

S2_API_BASE = "https://api.semanticscholar.org/graph/v1"


class SemanticScholarCollector(BaseCollector):
    """Collects recent papers from Semantic Scholar."""

    def __init__(
        self,
        query: str = "artificial intelligence",
        fields_of_study: Optional[List[str]] = None,
        max_papers: int = 50,
        api_key: Optional[str] = None,
    ):
        super().__init__()
        self.query = query
        self.fields_of_study = fields_of_study or ["Computer Science"]
        self.max_papers = max_papers
        self.api_key = api_key

    @property
    def name(self) -> str:
        return "Semantic Scholar"

    @property
    def source_type(self) -> str:
        return "semantic_scholar"

    async def collect(self) -> List[CollectedItem]:
        """Fetch recent papers from Semantic Scholar."""
        items = []

        headers = {}
        if self.api_key:
            headers["x-api-key"] = self.api_key

        params = {
            "query": self.query,
            "limit": self.max_papers,
            "fields": "title,abstract,authors,year,venue,publicationDate,url,citationCount,influentialCitationCount",
            "publicationDateOrYear": "2024-01-01:",  # Recent papers
        }

        try:
            async with aiohttp.ClientSession(headers=headers) as session:
                async with session.get(
                    f"{S2_API_BASE}/paper/search",
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=API_TIMEOUT_SECONDS),
                ) as response:
                    if response.status != 200:
                        self._logger.error(f"S2 API returned {response.status}")
                        return items

                    data = await response.json()

                    for paper in data.get("data", []):
                        paper_id = paper.get("paperId", "")

                        # Build author string
                        authors = paper.get("authors", [])
                        author_names = [a.get("name", "") for a in authors[:5]]
                        author_str = ", ".join(author_names)
                        if len(authors) > 5:
                            author_str += f" (+{len(authors) - 5} more)"

                        # Parse publication date
                        pub_date_str = paper.get("publicationDate")
                        if pub_date_str:
                            try:
                                pub_date = datetime.strptime(pub_date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                            except:
                                pub_date = datetime.now(timezone.utc)
                        else:
                            pub_date = datetime.now(timezone.utc)

                        items.append(CollectedItem(
                            source="semantic_scholar",
                            source_name="Semantic Scholar",
                            source_url="https://www.semanticscholar.org",
                            category="research",
                            title=paper.get("title", "Untitled"),
                            summary=self.truncate_text(paper.get("abstract", ""), 500),
                            url=paper.get("url") or f"https://www.semanticscholar.org/paper/{paper_id}",
                            published=pub_date,
                            author=author_str,
                            metadata={
                                "paper_id": paper_id,
                                "venue": paper.get("venue", ""),
                                "year": paper.get("year"),
                                "citation_count": paper.get("citationCount", 0),
                                "influential_citations": paper.get("influentialCitationCount", 0),
                            },
                            raw_content=paper.get("abstract", ""),
                        ))

            self._logger.info(f"Collected {len(items)} papers from Semantic Scholar")

        except Exception as e:
            self._logger.error(f"Semantic Scholar API error: {e}")

        return items
```

**Acceptance Criteria:**
- [ ] SemanticScholarCollector class created
- [ ] Fetches recent AI papers with abstracts
- [ ] Items categorized as "research"
- [ ] Captures citation metrics in metadata
- [ ] Registered in get_all_collectors()

**API Notes:**
- FREE tier: 100 requests/5 minutes
- API key available for higher limits
- No auth required for basic usage

**Dependencies:** PULSE-COLLECT-005 (research category setup)

---

## Dependency Graph

```
Phase 1 (Parallel - No Dependencies):
┌─────────────────┬─────────────────┬─────────────────┬─────────────────┐
│ COLLECT-001     │ COLLECT-002     │ COLLECT-003     │ COLLECT-004     │
│ AI Providers    │ Security RSS    │ Federal Crime   │ Think Tanks     │
│ (30 min)        │ (30 min)        │ (30 min)        │ (30 min)        │
└────────┬────────┴────────┬────────┴────────┬────────┴────────┬────────┘
         │                 │                 │                 │
         │    ┌────────────┴─────────────────┴─────────────────┘
         │    │
         ▼    ▼
┌─────────────────┬─────────────────┬─────────────────┐
│ COLLECT-005     │ COLLECT-006     │ COLLECT-007     │
│ Academic RSS    │ ArXiv Expand    │ Ranker Update   │
│ (30 min)        │ (15 min)        │ (15 min)        │
└────────┬────────┴────────┬────────┴────────┬────────┘
         │                 │                 │
         └─────────────────┼─────────────────┘
                           │
Phase 2 (Cleanup - Anytime):
┌─────────────────┬─────────────────┐
│ COLLECT-008     │ COLLECT-009     │
│ Remove RC       │ Fix WRCB Feed   │
│ (15 min)        │ (30 min)        │
└─────────────────┴─────────────────┘

Phase 3 (New Collectors - After Phase 1):
                           │
                           ▼
┌─────────────────┬─────────────────┐
│ COLLECT-010     │ COLLECT-011     │
│ NVD Collector   │ Semantic Scholar│
│ (3 hrs)         │ (3 hrs)         │
└─────────────────┴─────────────────┘
```

---

## Summary

| Phase | Features | Total Time | Key Deliverable |
|-------|----------|------------|-----------------|
| Phase 1 | COLLECT-001 through 007 | 3.0 hrs | 30+ new RSS feeds, expanded ArXiv |
| Phase 2 | COLLECT-008, 009 | 0.75 hrs | Cleanup dead legs |
| Phase 3 | COLLECT-010, 011 | 6.0 hrs | 2 new API collectors |

**Grand Total:** 9.75 hours (~10 hours)

---

## Recommended Implementation Order

1. **COLLECT-001** - AI Providers (highest intelligence ROI)
2. **COLLECT-002** - Security Advisories (CISA is critical)
3. **COLLECT-003** - Federal Criminal (FBI/DOJ)
4. **COLLECT-006** - ArXiv Expansion (quick win)
5. **COLLECT-004** - Think Tanks
6. **COLLECT-005** - Academic Preprints
7. **COLLECT-007** - Ranker Update (aggregate scoring)
8. **COLLECT-008** - Remove RC Collector
9. **COLLECT-009** - Fix WRCB
10. **COLLECT-010** - NVD Collector (if time permits)
11. **COLLECT-011** - Semantic Scholar (if time permits)

---

## Testing Strategy

After implementing Phase 1:

```bash
# 1. Trigger full RSS collection
curl -X POST http://localhost:8000/api/v1/collection/run?collector_name=RSS%20Feeds

# 2. Check collection logs
tail -f logs/pulse.log | grep -E "(RSS|Fetching feed)"

# 3. Verify items in database
curl http://localhost:8000/api/v1/collection/items?limit=50 | jq '.items[] | {source_name, category, title}'

# 4. Check for new categories
curl http://localhost:8000/api/v1/collection/items/stats | jq '.by_category'

# 5. Generate briefing to verify ranking
curl http://localhost:8000/api/v1/synthesis/briefing | jq '.sections'
```

---

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| RSS URL changes | Medium | Low | Feeds are easy to update; log warnings for failed feeds |
| Rate limiting | Low | Low | RSS feeds rarely rate-limit; APIs have documented limits |
| Content format changes | Low | Medium | RSSCollector uses standard feedparser; robust to minor changes |
| CISA feeds unavailable | Very Low | Medium | Government feeds are stable; have alternative security sources |

---

*Spec created: 2026-01-16*
*Author: Claude (Atomic Breakdown Agent)*
