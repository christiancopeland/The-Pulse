# ATOMIC Spec: Intelligence Data Source Expansion

**Created:** 2026-01-17
**Status:** Complete
**Parent Document:** `~/Desktop/workshop-claude-migration/data/research/pulse_data_sources.md`
**Related Spec:** `ATOMIC_intelligence-collection-expansion_2026-01-16.md` (prior RSS/collector work)

---

## Overview

Expand The Pulse intelligence collection capabilities by integrating 12 new data sources identified in the pulse_data_sources.md research document. These sources fill gaps in threat intelligence, humanitarian monitoring, crime statistics, and legal intelligence.

### Sources to Add

| Tier | Source | Domain | Cost |
|------|--------|--------|------|
| 1 | FBI Crime Data Explorer | Crime Statistics | Free |
| 1 | AlienVault OTX | Threat Intelligence | Free |
| 1 | Have I Been Pwned | Breach Monitoring | $3.50/mo |
| 2 | ReliefWeb API | Humanitarian | Free |
| 2 | US State Department RSS | Foreign Policy | Free |
| 2 | CourtListener/RECAP | Legal Intelligence | Free |
| 2 | GTD | Terrorism Data | Free |
| 3 | ICEWS | Early Warning | Free |
| 3 | MISP | Threat Intel Platform | Free (self-hosted) |
| 3 | Shodan | Infrastructure Vuln | $60-500/mo |
| 3 | Eurostat Crime | EU Crime Stats | Free |
| 3 | HDX | Humanitarian Data | Free |

---

## Phase 1: RSS Feed Additions

### DATASRC-001: State Department RSS Feeds

**Description:** Add US State Department RSS feeds to existing RSS collector configuration.

**Acceptance Criteria:**
- [ ] State Dept press releases feed added to `RSS_FEEDS` dict
- [ ] State Dept travel advisories feed added
- [ ] State Dept policy statements feed added
- [ ] Category mapping added to `RSS_CATEGORY_MAP` (→ `government`)
- [ ] Manual collection test passes
- [ ] Items appear with correct category in database

**Implementation:**
```python
# In app/services/collectors/config.py RSS_FEEDS dict:
"state_dept_press": "https://www.state.gov/rss-feed/press-releases/feed/",
"state_dept_travel": "https://www.state.gov/rss-feed/travel-advisories/feed/",
"state_dept_briefings": "https://www.state.gov/rss-feed/department-press-briefings/feed/",
```

**Estimated Time:** 1 hour
**Status:** [ ] Not Started

---

## Phase 2: REST API Collectors

### DATASRC-002: AlienVault OTX Collector

**Description:** Collect threat intelligence from AlienVault Open Threat Exchange - IOCs, malware hashes, threat pulses from community.

**API Reference:** https://otx.alienvault.com/api

**Acceptance Criteria:**
- [ ] `OTXCollector` class created extending `BaseCollector`
- [ ] Fetches subscribed pulses (requires free API key)
- [ ] Extracts IOCs: IPs, domains, file hashes, URLs
- [ ] Maps to `cyber` category
- [ ] Stores pulse metadata (tags, adversary, malware families)
- [ ] Rate limiting respected (1000 requests/hour)
- [ ] Manual collection test passes

**Data Model:**
```python
CollectedItem(
    source="otx",
    source_name="AlienVault OTX",
    category="cyber",
    title="Pulse: {pulse_name}",
    summary="{description}",
    url="https://otx.alienvault.com/pulse/{pulse_id}",
    metadata={
        "pulse_id": str,
        "adversary": str,
        "malware_families": list,
        "tags": list,
        "ioc_count": int,
        "iocs": {
            "ipv4": list,
            "domain": list,
            "hostname": list,
            "file_hash_md5": list,
            "file_hash_sha256": list,
            "url": list,
        }
    }
)
```

**Environment Variables:**
```bash
OTX_API_KEY=your-free-api-key  # Get from https://otx.alienvault.com/api
```

**Estimated Time:** 3 hours
**Status:** [ ] Not Started

---

### DATASRC-003: ReliefWeb API Collector

**Description:** Collect humanitarian crisis reports, disaster updates, and situation reports from UN OCHA's ReliefWeb.

**API Reference:** https://reliefweb.int/help/api

**Acceptance Criteria:**
- [ ] `ReliefWebCollector` class created
- [ ] Fetches recent reports (last 24 hours)
- [ ] Filters by report type: situation reports, flash updates, assessments
- [ ] Extracts country, disaster type, organization
- [ ] Maps to `humanitarian` category (add to CATEGORY_LABELS)
- [ ] No API key required
- [ ] Manual collection test passes

**Data Model:**
```python
CollectedItem(
    source="reliefweb",
    source_name="ReliefWeb",
    category="humanitarian",
    title="{report_title}",
    summary="{body_excerpt}",
    url="{report_url}",
    metadata={
        "report_id": int,
        "report_type": str,  # "Situation Report", "Flash Update", etc.
        "countries": list,
        "disaster_types": list,
        "organizations": list,
        "themes": list,
    }
)
```

**Estimated Time:** 2 hours
**Status:** [ ] Not Started

---

### DATASRC-004: FBI Crime Data Explorer Collector

**Description:** Collect US crime statistics from FBI's Crime Data Explorer API (UCR/NIBRS data).

**API Reference:** https://cde.ucr.cjis.gov/LATEST/webapp/#/pages/docApi

**Acceptance Criteria:**
- [ ] `FBICrimeDataCollector` class created
- [ ] Fetches national crime trends (latest year)
- [ ] Fetches state-level summaries
- [ ] Supports offense types: violent crime, property crime, homicide
- [ ] Maps to `crime_national` category
- [ ] Requires API key (free registration)
- [ ] Manual collection test passes

**Data Model:**
```python
CollectedItem(
    source="fbi_crime_data",
    source_name="FBI Crime Data Explorer",
    category="crime_national",
    title="Crime Statistics: {jurisdiction} - {year}",
    summary="{offense_type}: {count} incidents ({rate} per 100k)",
    url="https://cde.ucr.cjis.gov/",
    metadata={
        "year": int,
        "jurisdiction": str,  # "National", state name, or agency
        "offense_type": str,
        "count": int,
        "rate_per_100k": float,
        "data_source": str,  # "UCR" or "NIBRS"
    }
)
```

**Environment Variables:**
```bash
FBI_CDE_API_KEY=your-free-api-key
```

**Estimated Time:** 3 hours
**Status:** [ ] Not Started

---

### DATASRC-005: CourtListener Collector

**Description:** Collect federal court opinions and case information from CourtListener (free PACER mirror).

**API Reference:** https://www.courtlistener.com/api/rest-info/

**Acceptance Criteria:**
- [ ] `CourtListenerCollector` class created
- [ ] Fetches recent opinions (last 7 days)
- [ ] Filters by court type: SCOTUS, Circuit Courts, District Courts
- [ ] Extracts case name, docket number, judges, citations
- [ ] Maps to `legal` category (add to CATEGORY_LABELS)
- [ ] No API key required for basic access
- [ ] Manual collection test passes

**Data Model:**
```python
CollectedItem(
    source="courtlistener",
    source_name="CourtListener",
    category="legal",
    title="{case_name}",
    summary="{opinion_excerpt}",
    url="https://www.courtlistener.com/opinion/{id}/",
    metadata={
        "docket_number": str,
        "court": str,
        "court_id": str,
        "judges": list,
        "date_filed": str,
        "citation": str,
        "precedential_status": str,
    }
)
```

**Estimated Time:** 3 hours
**Status:** [ ] Not Started

---

### DATASRC-006: Have I Been Pwned Collector

**Description:** Monitor for new data breaches and compromised credentials via HIBP API.

**API Reference:** https://haveibeenpwned.com/API/v3

**Acceptance Criteria:**
- [ ] `HIBPCollector` class created
- [ ] Fetches recent breaches (new additions)
- [ ] Extracts breach metadata: name, domain, breach date, data types
- [ ] Maps to `cyber` category
- [ ] Requires API key ($3.50/mo)
- [ ] Rate limiting: 10 requests/minute
- [ ] Manual collection test passes

**Data Model:**
```python
CollectedItem(
    source="hibp",
    source_name="Have I Been Pwned",
    category="cyber",
    title="Breach: {breach_name}",
    summary="{description}",
    url="https://haveibeenpwned.com/PwnedWebsites#{breach_name}",
    metadata={
        "breach_name": str,
        "domain": str,
        "breach_date": str,
        "added_date": str,
        "pwn_count": int,
        "data_classes": list,  # "Email addresses", "Passwords", etc.
        "is_verified": bool,
        "is_sensitive": bool,
    }
)
```

**Environment Variables:**
```bash
HIBP_API_KEY=your-api-key  # $3.50/mo from https://haveibeenpwned.com/API/Key
```

**Estimated Time:** 2 hours
**Status:** [ ] Not Started

---

### DATASRC-007: Eurostat Crime Collector

**Description:** Collect European crime statistics from Eurostat's SDMX API.

**API Reference:** https://ec.europa.eu/eurostat/web/sdmx-infospace/welcome

**Acceptance Criteria:**
- [ ] `EurostatCrimeCollector` class created
- [ ] Fetches crime statistics by country (EU-27)
- [ ] Offense types: homicide, robbery, theft, assault
- [ ] Maps to `crime_international` category
- [ ] No API key required
- [ ] Annual data (check for updates monthly)
- [ ] Manual collection test passes

**Data Model:**
```python
CollectedItem(
    source="eurostat",
    source_name="Eurostat Crime Statistics",
    category="crime_international",
    title="EU Crime: {country} - {offense_type} ({year})",
    summary="{count} recorded offenses",
    url="https://ec.europa.eu/eurostat/databrowser/view/crim_off_cat/",
    metadata={
        "country": str,
        "country_code": str,
        "year": int,
        "offense_type": str,
        "count": int,
        "rate_per_100k": float,
    }
)
```

**Estimated Time:** 2 hours
**Status:** [ ] Not Started

---

### DATASRC-008: HDX Collector

**Description:** Collect humanitarian datasets from OCHA's Humanitarian Data Exchange.

**API Reference:** https://data.humdata.org/documentation

**Acceptance Criteria:**
- [ ] `HDXCollector` class created
- [ ] Fetches recently updated datasets
- [ ] Filters by tags: crisis, displacement, refugees, food-security
- [ ] Extracts organization, country, update frequency
- [ ] Maps to `humanitarian` category
- [ ] No API key required
- [ ] Manual collection test passes

**Data Model:**
```python
CollectedItem(
    source="hdx",
    source_name="Humanitarian Data Exchange",
    category="humanitarian",
    title="{dataset_title}",
    summary="{notes_excerpt}",
    url="https://data.humdata.org/dataset/{name}",
    metadata={
        "dataset_id": str,
        "organization": str,
        "countries": list,
        "tags": list,
        "last_modified": str,
        "update_frequency": str,
        "resources_count": int,
    }
)
```

**Estimated Time:** 2 hours
**Status:** [ ] Not Started

---

## Phase 3: Bulk Data Collectors

### DATASRC-009: GTD Collector

**Description:** Collect terrorism incident data from the Global Terrorism Database (START/UMD).

**Data Source:** https://www.start.umd.edu/gtd/

**Acceptance Criteria:**
- [ ] `GTDCollector` class created
- [ ] Downloads annual CSV bulk file
- [ ] Parses incident data: location, group, attack type, casualties
- [ ] Maps to `terrorism` category (add to CATEGORY_LABELS)
- [ ] Stores only new incidents (compare to last run)
- [ ] Handles large file efficiently (200k+ records)
- [ ] Manual collection test passes

**Data Model:**
```python
CollectedItem(
    source="gtd",
    source_name="Global Terrorism Database",
    category="terrorism",
    title="Incident: {city}, {country} - {attack_type}",
    summary="{summary}",
    url="https://www.start.umd.edu/gtd/search/IncidentSummary.aspx?gtdid={event_id}",
    metadata={
        "event_id": str,
        "year": int,
        "month": int,
        "day": int,
        "country": str,
        "region": str,
        "city": str,
        "latitude": float,
        "longitude": float,
        "attack_type": str,
        "target_type": str,
        "group_name": str,
        "weapon_type": str,
        "killed": int,
        "wounded": int,
    }
)
```

**Notes:**
- Academic/research use is free
- Commercial use requires license
- Data updated annually

**Estimated Time:** 3 hours
**Status:** [ ] Not Started

---

### DATASRC-010: ICEWS Collector

**Description:** Collect political event data from the Integrated Crisis Early Warning System (Lockheed Martin, via Harvard Dataverse).

**Data Source:** https://dataverse.harvard.edu/dataverse/icews

**Acceptance Criteria:**
- [ ] `ICEWSCollector` class created
- [ ] Downloads daily event files from Dataverse
- [ ] Parses event data: actors, event type, intensity, location
- [ ] Maps to `geopolitics` category
- [ ] Stores only new events (by event ID)
- [ ] Handles SQLite format or tab-delimited files
- [ ] Manual collection test passes

**Data Model:**
```python
CollectedItem(
    source="icews",
    source_name="ICEWS Early Warning",
    category="geopolitics",
    title="{source_actor} → {target_actor}: {event_type}",
    summary="{event_text}",
    url="https://dataverse.harvard.edu/dataverse/icews",
    metadata={
        "event_id": str,
        "event_date": str,
        "source_actor": str,
        "source_country": str,
        "target_actor": str,
        "target_country": str,
        "event_type": str,
        "cameo_code": str,
        "intensity": float,
        "latitude": float,
        "longitude": float,
    }
)
```

**Estimated Time:** 4 hours
**Status:** [ ] Not Started

---

## Phase 4: Complex/Optional Integration

### DATASRC-011: MISP Integration

**Description:** Integrate with self-hosted MISP (Malware Information Sharing Platform) instance for threat intelligence aggregation.

**Prerequisites:**
- MISP instance deployed (Docker or bare metal)
- API key generated

**Acceptance Criteria:**
- [ ] `MISPCollector` class created
- [ ] Connects to MISP REST API
- [ ] Fetches recent events and attributes
- [ ] Supports STIX export format
- [ ] Maps to `cyber` category
- [ ] Configurable MISP URL
- [ ] Manual collection test passes

**Environment Variables:**
```bash
MISP_URL=https://your-misp-instance.local
MISP_API_KEY=your-api-key
MISP_VERIFY_SSL=true
```

**Estimated Time:** 6 hours
**Status:** [ ] Not Started (requires MISP deployment)

---

### DATASRC-012: Shodan Collector

**Description:** Collect internet-exposed device and vulnerability data from Shodan.

**API Reference:** https://developer.shodan.io/api

**Acceptance Criteria:**
- [ ] `ShodanCollector` class created
- [ ] Monitors saved searches/alerts
- [ ] Fetches recently discovered vulnerable devices
- [ ] Extracts: IP, port, service, CVEs, organization
- [ ] Maps to `cyber` category
- [ ] Requires paid API key ($60-500/mo)
- [ ] Rate limiting: depends on tier
- [ ] Manual collection test passes

**Data Model:**
```python
CollectedItem(
    source="shodan",
    source_name="Shodan",
    category="cyber",
    title="Exposed: {product} on {ip}:{port}",
    summary="{org} - {vulns_count} vulnerabilities",
    url="https://www.shodan.io/host/{ip}",
    metadata={
        "ip": str,
        "port": int,
        "transport": str,
        "product": str,
        "version": str,
        "os": str,
        "organization": str,
        "asn": str,
        "country": str,
        "vulns": list,  # CVE IDs
        "tags": list,
    }
)
```

**Environment Variables:**
```bash
SHODAN_API_KEY=your-paid-api-key
```

**Estimated Time:** 3 hours
**Status:** [ ] Not Started (optional, paid tier)

---

## Configuration Updates Required

### New Categories

Add to `CATEGORY_LABELS` in `config.py`:
```python
"humanitarian": "Humanitarian & Crisis",
"legal": "Legal & Court",
"terrorism": "Terrorism & Extremism",
```

### New Environment Variables

Add to `.env` / environment:
```bash
# Tier 1
OTX_API_KEY=           # Free from https://otx.alienvault.com/api
FBI_CDE_API_KEY=       # Free from FBI CDE registration
HIBP_API_KEY=          # $3.50/mo from https://haveibeenpwned.com/API/Key

# Tier 4 (Optional)
MISP_URL=              # Self-hosted MISP instance
MISP_API_KEY=          # MISP API key
SHODAN_API_KEY=        # Paid tier
```

---

## Implementation Order

### Priority A (High Value, Easy) - Do First
1. DATASRC-001: State Dept RSS (1 hr)
2. DATASRC-002: AlienVault OTX (3 hrs)
3. DATASRC-003: ReliefWeb (2 hrs)
4. DATASRC-005: CourtListener (3 hrs)

### Priority B (Good Value) - Do Second
5. DATASRC-004: FBI Crime Data (3 hrs)
6. DATASRC-006: Have I Been Pwned (2 hrs)
7. DATASRC-008: HDX (2 hrs)

### Priority C (Specialized) - Do Third
8. DATASRC-009: GTD (3 hrs)
9. DATASRC-007: Eurostat (2 hrs)
10. DATASRC-010: ICEWS (4 hrs)

### Priority D (Optional) - If Time/Budget Permits
11. DATASRC-012: Shodan (3 hrs, paid)
12. DATASRC-011: MISP (6 hrs, requires deployment)

---

## Total Estimated Time

| Priority | Features | Hours |
|----------|----------|-------|
| A | 4 | 9 hrs |
| B | 3 | 7 hrs |
| C | 3 | 9 hrs |
| D | 2 | 9 hrs |
| **Total** | **12** | **34 hrs** |

**Excluding optional Priority D:** 25 hours

---

## Testing Strategy

Each collector should have:
1. **Unit test:** Mock API responses, verify parsing
2. **Integration test:** Real API call (rate-limited), verify data storage
3. **Manual test:** Trigger via API, verify in storage browser

```bash
# Manual test pattern
curl -X POST "http://localhost:8000/api/v1/collection/run?collector_name=AlienVault%20OTX"
curl http://localhost:8000/api/v1/collection/items?source=otx&limit=10
```

---

## Progress Tracking

| ID | Feature | Status | Completed |
|----|---------|--------|-----------|
| DATASRC-001 | State Dept RSS | [x] BLOCKED | 2026-01-17 (feeds returning errors) |
| DATASRC-002 | AlienVault OTX | [x] | 2026-01-17 |
| DATASRC-003 | ReliefWeb | [x] | 2026-01-17 |
| DATASRC-004 | FBI Crime Data | [x] | 2026-01-17 |
| DATASRC-005 | CourtListener | [x] | 2026-01-17 |
| DATASRC-006 | Have I Been Pwned | [x] | 2026-01-17 |
| DATASRC-007 | Eurostat Crime | [x] | 2026-01-17 |
| DATASRC-008 | HDX | [x] | 2026-01-17 |
| DATASRC-009 | GTD | [x] | 2026-01-17 |
| DATASRC-010 | ICEWS | [x] | 2026-01-17 |
| DATASRC-011 | MISP | [x] | 2026-01-17 |
| DATASRC-012 | Shodan | [x] | 2026-01-17 |

**Implementation Complete:** 11/12 collectors implemented (1 blocked due to unavailable feeds)
