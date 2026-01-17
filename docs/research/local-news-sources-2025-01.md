# Local News & Data Sources Research

**Date:** January 13, 2025  
**Purpose:** Expand The Pulse coverage for Lafayette GA, Chattanooga TN, and surrounding areas

---

## Executive Summary

Research identified 20+ local news sources and data feeds across the Northwest Georgia and Southeast Tennessee corridor. Key findings:

- **DiscoverWalker.com** is the primary hyperlocal source for Walker County with active RSS
- **ChattaData** provides open data API for Chattanooga city data
- Regional TV stations (WRCB, WTVC, WDEF) all have RSS feeds
- Several county newspapers serve the broader region

---

## Priority Sources for Integration

### Tier 1: Immediate Integration (RSS Ready)

| Source | RSS Feed URL | Category | Notes |
|--------|-------------|----------|-------|
| DiscoverWalker.com | `https://www.discoverwalker.com/feed/` | local | Primary Walker County source, daily updates |
| Walker Arrest Reports | `https://www.discoverwalker.com/category/walker-arrest-reports/feed/` | crime_local | Daily detention intake reports |
| WRCB Local 3 | `https://www.wrcbtv.com/rss` | local | NBC affiliate, regional coverage |
| WTVC NewsChannel 9 | `https://newschannel9.com/rss` | local | ABC affiliate, regional coverage |
| AllOnGeorgia Walker | `https://allongeorgia.com/walker-county/feed/` | local | Statewide news, Walker section |
| LaFayette Underground | `https://thelafayetteunderground.com/feed/` | local | Government watchdog blog |

### Tier 2: API Integration Required

| Source | API/URL | Category | Integration Notes |
|--------|---------|----------|-------------------|
| ChattaData | `https://chattadata.org/api/` | data | Open data portal - crime, permits, crashes, budget |
| Broadcastify | `https://broadcastify.com/listen/ctid/2460` | scanner | Live police/fire audio feeds (streaming) |

### Tier 3: Manual Verification Needed

| Source | URL | Category | Status |
|--------|-----|----------|--------|
| Northwest Georgia News | northwestgeorgianews.com | local | Parent site for Catoosa/Walker papers |
| Cleveland Daily Banner | clevelandbanner.com | local | Bradley County TN, RSS unconfirmed |
| Dalton Daily Citizen | daltondailycitizen.com | local | Whitfield County GA, RSS unconfirmed |
| Chattanooga Times Free Press | timesfreepress.com | local | Major regional daily, RSS via Feedspot |
| NOOGAtoday | noogatoday.6amcity.com | local | Email newsletter format |

---

## Detailed Source Information

### Lafayette / Walker County, Georgia

**DiscoverWalker.com** (PRIMARY SOURCE)
- URL: https://www.discoverwalker.com
- RSS: `https://www.discoverwalker.com/feed/`
- Content: Local news, arrest reports, government meetings, events, jobs
- Publishing: Multiple times daily
- Associated: WQCH 1590 AM / Georgia 93.7 FM radio

**Content Sections:**
- Local News: /category/local
- Arrest Reports: /category/walker-arrest-reports
- Government Meetings: /category/government-meetings
- Events: /events/

**The LaFayette Underground**
- URL: https://thelafayetteunderground.com
- RSS: Available
- Content: Independent local news, government accountability

**Walker County Government**
- URL: https://www.walkercountyga.gov
- RSS: None detected
- Content: Meeting schedules, agendas, county services

### Chattanooga / Hamilton County, Tennessee

**ChattaData** (OPEN DATA PORTAL)
- URL: https://chattadata.org
- API: https://chattadata.org/api/
- Content: Crime data, building permits, traffic crashes, city budget
- Access: Free REST API

**TV Stations:**
| Station | Affiliation | URL | RSS |
|---------|-------------|-----|-----|
| WRCB | NBC | local3news.com | Yes |
| WTVC | ABC | newschannel9.com | Yes |
| WDEF | CBS | wdef.com | Confirmed |
| WTCI | PBS | wtcitv.org | No (educational) |

**Digital/Magazine:**
- Chattanooga Pulse (chattanoogapulse.com) - Arts & entertainment
- NOOGAtoday (noogatoday.6amcity.com) - Daily curated newsletter

**Emergency Services:**
- Hamilton County 911: hamiltontn911.gov/active-incidents.php (already integrated)
- Hamilton County Sheriff: hcsheriff.gov (mobile app, crime dashboard)
- Broadcastify: Live scanner feeds for Hamilton County

### Regional Coverage

**Northwest Georgia News Network**
- URL: northwestgeorgianews.com
- Coverage: Catoosa County News, Walker County Messenger
- Contact: 706-935-2621

**County Papers:**
| Paper | County | URL | Founded |
|-------|--------|-----|--------|
| Catoosa County News | Catoosa GA | northwestgeorgianews.com/catoosa_walker_news | - |
| Walker County Messenger | Walker GA | northwestgeorgianews.com/catoosa_walker_news | 1877 |
| Cleveland Daily Banner | Bradley TN | clevelandbanner.com | 1854 |
| Dalton Daily Citizen | Whitfield GA | daltondailycitizen.com | - |
| Dade County Sentinel | Dade GA | (sold to out-of-state) | - |
| Chatsworth Times | Murray GA | chatsworthtimes.com | - |

---

## Implementation Guide

### Adding RSS Feeds

Edit `app/services/collectors/config.py`:

```python
# Add to RSS_FEEDS dict
RSS_FEEDS = {
    # ... existing feeds ...
    
    # Walker County
    "discover_walker": "https://www.discoverwalker.com/feed/",
    "walker_arrests": "https://www.discoverwalker.com/category/walker-arrest-reports/feed/",
    "lafayette_underground": "https://thelafayetteunderground.com/feed/",
    
    # Regional TV
    "wrcb_local3": "https://www.wrcbtv.com/rss",
    "wtvc_newschannel9": "https://newschannel9.com/rss",
    
    # Statewide with local section
    "allongeorgia_walker": "https://allongeorgia.com/walker-county/feed/",
}

# Add to RSS_CATEGORY_MAP
RSS_CATEGORY_MAP = {
    # ... existing mappings ...
    "discover_walker": "local",
    "walker_arrests": "crime_local",
    "lafayette_underground": "local",
    "wrcb_local3": "local",
    "wtvc_newschannel9": "local",
    "allongeorgia_walker": "local",
}
```

### Creating ChattaData Collector

Create `app/services/collectors/chattadata_collector.py`:

```python
from typing import List
import aiohttp
from datetime import datetime
from .base import BaseCollector, CollectedItem

class ChattaDataCollector(BaseCollector):
    """Collector for Chattanooga Open Data Portal."""
    
    # Datasets of interest
    ENDPOINTS = {
        "crime": "https://chattadata.org/resource/xxxx.json",  # Find actual resource ID
        "permits": "https://chattadata.org/resource/yyyy.json",
        "crashes": "https://chattadata.org/resource/zzzz.json",
    }
    
    @property
    def name(self) -> str:
        return "ChattaData"
    
    @property
    def source_type(self) -> str:
        return "chattadata"
    
    async def collect(self) -> List[CollectedItem]:
        items = []
        async with aiohttp.ClientSession() as session:
            for dataset, url in self.ENDPOINTS.items():
                # Add $where clause for recent records
                # Add $limit for batch size
                async with session.get(url) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        for record in data:
                            items.append(self._record_to_item(record, dataset))
        return items
    
    def _record_to_item(self, record: dict, dataset: str) -> CollectedItem:
        # Map dataset fields to CollectedItem
        pass
```

---

## Next Steps

1. **Verify RSS URLs** - Test each feed URL to confirm they return valid XML
2. **Find ChattaData resource IDs** - Browse chattadata.org to identify relevant datasets
3. **Test category mappings** - Ensure new categories display properly in UI
4. **Monitor feed quality** - Some local sources may have irregular publishing

---

## Research Metadata

- **Codebase analyzed:** ~/The-Pulse (FastAPI-based, 9 collector types)
- **Existing local sources:** Chattanoogan, WDEF, Hamilton 911
- **Research agents:** 3 web-researchers (parallel dispatch)
- **Total research time:** ~6 minutes
