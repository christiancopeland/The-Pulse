# Atomic Implementation Plan: Phase 2 - Temporal Backend Infrastructure

**Created:** 2026-01-15
**Parent Document:** [specs/ATOMIC_entity-graph-visualization-soa_2026-01-15.md](./ATOMIC_entity-graph-visualization-soa_2026-01-15.md)
**Status:** Implementation Complete ✓

---

## Overview

Phase 2 adds database schema and API support for temporal visualization of the entity graph. This enables users to see when entities first appeared, track relationship evolution over time, and filter the graph by time range.

**Phase 2 Features:**
- PULSE-VIZ-005: Entity Temporal Schema
- PULSE-VIZ-006: ~~Relationship Temporal Schema~~ (ALREADY DONE - EntityRelationship has first_seen/last_seen)
- PULSE-VIZ-007: Populate Temporal Metadata (Backfill)
- PULSE-VIZ-008: Temporal API Endpoint

**Estimated Time:** 5 hours (reduced from 6 since VIZ-006 is complete)

---

## Prerequisites: Phase 1 Bug Fixes

**Before starting Phase 2, these Phase 1 bugs MUST be fixed:**

### BUG-001: Click Isolation Breaks on Hover

**Symptom:** When clicking an entity, isolation locks correctly. However, hovering over another entity breaks the isolation lock.

**Expected Behavior:** Isolation should ONLY break when clicking the background, not on hover.

**Root Cause:** The `enterNode` event handler is calling `highlightNode()` which overrides the `focusedEntityId` lock state.

**Fix Location:** `static/js/pulse-dashboard.js` - modify `enterNode` handler to check `focusedEntityId` before applying hover isolation.

**Acceptance Criteria:**
- [x] Click entity A → isolation locks on A
- [x] Hover entity B → isolation stays on A (no change)
- [x] Click background → isolation clears, full graph restored

---

### BUG-002: Sources Panel Shows No Sources

**Symptom:** Clicking "show sources" opens the panel but displays "No sources found for this entity"

**Root Causes Identified:**

1. **API Response Format Mismatch**
   - API (`get_entity_mentions`) returns: `[{...}, {...}]` (raw list)
   - Frontend expects: `{ mentions: [{...}, {...}] }` (wrapped object)
   - Location: `app/services/entity_tracker.py:433` returns list directly

2. **Missing news_items Source**
   - Query only joins `documents` and `news_articles` tables
   - Most auto-extracted entities come from `news_items` (automated collection)
   - The `entity_mentions.news_item_id` column exists but isn't queried
   - Location: `app/services/entity_tracker.py:378-416`

**Fix Locations:**
- `app/api/v1/entities/routes.py:182-203` - Wrap return value in `{"mentions": mentions}`
- `app/services/entity_tracker.py:378-416` - Add `news_items` CTE to union query

**Acceptance Criteria:**
- [x] API returns `{"mentions": [...], "total": N}` structure
- [x] Query includes news_items as third source type
- [x] Sources panel displays sources from documents, news_articles, AND news_items

---

## Phase 2 Features

### PULSE-VIZ-005: Entity Temporal Schema

**ID:** PULSE-VIZ-005
**Estimated Time:** 1 hour
**Dependencies:** None

#### Description

Add `first_seen` and `last_seen` timestamp columns to the `tracked_entities` table via migration script. These columns enable temporal filtering and visualization of when entities entered the intelligence picture.

#### Files to Modify

| File | Changes |
|------|---------|
| `app/models/entities.py` | Add `first_seen`, `last_seen` Column definitions to TrackedEntity |
| `app/scripts/migrate_entity_temporal.py` | NEW: Migration script to add columns |

#### Implementation Contract

```python
# In app/models/entities.py, add to TrackedEntity class:

class TrackedEntity(Base):
    # ... existing columns ...

    # Temporal tracking - when entity first/last appeared in content
    first_seen = Column(DateTime(timezone=True), nullable=True, index=True)
    last_seen = Column(DateTime(timezone=True), nullable=True, index=True)
```

```python
# app/scripts/migrate_entity_temporal.py
"""
Migration script to add temporal columns to tracked_entities.

Run with: python -m app.scripts.migrate_entity_temporal
"""
import asyncio
from sqlalchemy import text
from app.database import async_engine

async def migrate():
    async with async_engine.begin() as conn:
        # Add first_seen column if not exists
        await conn.execute(text("""
            ALTER TABLE tracked_entities
            ADD COLUMN IF NOT EXISTS first_seen TIMESTAMP WITH TIME ZONE;
        """))

        # Add last_seen column if not exists
        await conn.execute(text("""
            ALTER TABLE tracked_entities
            ADD COLUMN IF NOT EXISTS last_seen TIMESTAMP WITH TIME ZONE;
        """))

        # Add indexes for temporal queries
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_tracked_entities_first_seen
            ON tracked_entities(first_seen);
        """))
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_tracked_entities_last_seen
            ON tracked_entities(last_seen);
        """))

    print("Migration complete: added first_seen, last_seen to tracked_entities")

if __name__ == "__main__":
    asyncio.run(migrate())
```

#### Acceptance Criteria

- [x] Migration runs without error
- [x] `first_seen` column exists in `tracked_entities` table
- [x] `last_seen` column exists in `tracked_entities` table
- [x] Indexes created for both columns
- [x] Existing rows have NULL for new columns (to be backfilled in VIZ-007)

---

### PULSE-VIZ-006: Relationship Temporal Schema

**ID:** PULSE-VIZ-006
**Status:** ALREADY COMPLETE

The `EntityRelationship` model already has:
- `first_seen = Column(DateTime(timezone=True))`
- `last_seen = Column(DateTime(timezone=True))`
- `mention_count = Column(Integer, default=1)`

**No implementation needed.** Proceed to VIZ-007.

---

### PULSE-VIZ-007: Populate Temporal Metadata (Backfill)

**ID:** PULSE-VIZ-007
**Estimated Time:** 2 hours
**Dependencies:** PULSE-VIZ-005 (columns must exist)

#### Description

Backfill `first_seen` and `last_seen` values for all existing entities by aggregating timestamps from their `entity_mentions`. This is a one-time migration that populates historical temporal data.

#### Files to Modify

| File | Changes |
|------|---------|
| `app/scripts/migrate_entity_temporal.py` | Add backfill function |

#### Implementation Contract

```python
# Add to app/scripts/migrate_entity_temporal.py

async def backfill_temporal_data():
    """
    Backfill first_seen/last_seen from entity_mentions.

    Uses MIN(timestamp) for first_seen and MAX(timestamp) for last_seen.
    Only updates entities that have mentions and NULL temporal fields.
    """
    async with async_engine.begin() as conn:
        # Backfill from entity_mentions timestamps
        result = await conn.execute(text("""
            UPDATE tracked_entities te
            SET
                first_seen = COALESCE(te.first_seen, agg.min_ts),
                last_seen = COALESCE(te.last_seen, agg.max_ts)
            FROM (
                SELECT
                    entity_id,
                    MIN(timestamp::timestamptz) as min_ts,
                    MAX(timestamp::timestamptz) as max_ts
                FROM entity_mentions
                GROUP BY entity_id
            ) agg
            WHERE te.entity_id = agg.entity_id
            AND (te.first_seen IS NULL OR te.last_seen IS NULL)
            RETURNING te.entity_id
        """))

        updated_count = len(result.fetchall())
        print(f"Backfilled temporal data for {updated_count} entities")

        # For entities with no mentions, use created_at as fallback
        await conn.execute(text("""
            UPDATE tracked_entities
            SET
                first_seen = created_at::timestamptz,
                last_seen = created_at::timestamptz
            WHERE first_seen IS NULL
        """))

async def migrate_and_backfill():
    """Run full migration: add columns then backfill."""
    await migrate()
    await backfill_temporal_data()

if __name__ == "__main__":
    asyncio.run(migrate_and_backfill())
```

#### Acceptance Criteria

- [x] All entities with mentions have `first_seen` populated from earliest mention
- [x] All entities with mentions have `last_seen` populated from latest mention
- [x] Entities without mentions use `created_at` as fallback
- [x] No NULL values remain in `first_seen` or `last_seen`
- [x] Script is idempotent (safe to run multiple times)

---

### PULSE-VIZ-008: Temporal API Endpoint

**ID:** PULSE-VIZ-008
**Estimated Time:** 2 hours
**Dependencies:** PULSE-VIZ-007 (data must be backfilled)

#### Description

Add `GET /api/v1/network/timeline` endpoint that returns entity activity aggregated by day/week. This powers the timeline UI component in Phase 3.

#### Files to Modify

| File | Changes |
|------|---------|
| `app/api/v1/network/routes.py` | Add `/timeline` endpoint |

#### Implementation Contract

```python
# Add to app/api/v1/network/routes.py

from datetime import datetime, timedelta
from typing import Literal

class TimelineResponse(BaseModel):
    """Response model for timeline endpoint."""
    period: str  # 'day' or 'week'
    start_date: str
    end_date: str
    data: List[Dict]  # [{date, entity_count, mention_count, new_entities}]

@router.get("/timeline")
async def get_entity_timeline(
    period: Literal["day", "week"] = Query("day", description="Aggregation period"),
    days: int = Query(90, ge=7, le=365, description="Number of days to include"),
    db=Depends(get_db),
    current_user: LocalUser = Depends(get_local_user)
) -> TimelineResponse:
    """
    Get entity activity timeline for visualization.

    Returns aggregated counts of:
    - entity_count: Total entities active in this period
    - mention_count: Total mentions in this period
    - new_entities: Entities first seen in this period

    Args:
        period: Aggregation granularity ('day' or 'week')
        days: How far back to look (default 90 days)

    Returns:
        TimelineResponse with date-indexed activity data
    """
    end_date = datetime.now(timezone.utc)
    start_date = end_date - timedelta(days=days)

    # Determine date truncation based on period
    trunc_func = "date_trunc('day', timestamp::timestamptz)" if period == "day" else "date_trunc('week', timestamp::timestamptz)"

    query = text(f"""
        WITH mention_activity AS (
            SELECT
                {trunc_func} as period_date,
                COUNT(DISTINCT entity_id) as entity_count,
                COUNT(*) as mention_count
            FROM entity_mentions
            WHERE timestamp::timestamptz >= :start_date
            AND timestamp::timestamptz <= :end_date
            GROUP BY period_date
        ),
        new_entities AS (
            SELECT
                {trunc_func.replace('timestamp', 'first_seen')} as period_date,
                COUNT(*) as new_entities
            FROM tracked_entities
            WHERE first_seen >= :start_date
            AND first_seen <= :end_date
            AND user_id = :user_id
            GROUP BY period_date
        )
        SELECT
            COALESCE(m.period_date, n.period_date) as period_date,
            COALESCE(m.entity_count, 0) as entity_count,
            COALESCE(m.mention_count, 0) as mention_count,
            COALESCE(n.new_entities, 0) as new_entities
        FROM mention_activity m
        FULL OUTER JOIN new_entities n ON m.period_date = n.period_date
        ORDER BY period_date ASC
    """)

    result = await db.execute(query, {
        "start_date": start_date,
        "end_date": end_date,
        "user_id": current_user.user_id
    })

    data = [
        {
            "date": row.period_date.isoformat() if row.period_date else None,
            "entity_count": row.entity_count,
            "mention_count": row.mention_count,
            "new_entities": row.new_entities
        }
        for row in result
    ]

    return {
        "period": period,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "data": data
    }
```

#### API Response Example

```json
{
  "period": "day",
  "start_date": "2025-10-17T00:00:00Z",
  "end_date": "2026-01-15T00:00:00Z",
  "data": [
    {
      "date": "2025-10-17T00:00:00Z",
      "entity_count": 15,
      "mention_count": 42,
      "new_entities": 3
    },
    {
      "date": "2025-10-18T00:00:00Z",
      "entity_count": 22,
      "mention_count": 67,
      "new_entities": 7
    }
  ]
}
```

#### Acceptance Criteria

- [x] `GET /api/v1/network/timeline` returns 200 OK
- [x] Response includes `period`, `start_date`, `end_date`, `data` fields
- [x] Data array contains objects with `date`, `entity_count`, `mention_count`, `new_entities`
- [x] `period=day` returns daily granularity
- [x] `period=week` returns weekly granularity
- [x] `days` parameter correctly limits date range
- [x] `entity_type` parameter filters by entity type (added per spec question)

---

## Dependency Graph

```
Phase 1 Bug Fixes (REQUIRED FIRST)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
BUG-001 ─────────────┐
(Click Isolation)    │
                     ├──► Phase 2 Implementation
BUG-002 ─────────────┘
(Sources Panel)

Phase 2: Temporal Backend
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PULSE-VIZ-005 ──► PULSE-VIZ-007 ──► PULSE-VIZ-008
(Add Columns)     (Backfill)        (API Endpoint)

PULSE-VIZ-006: ALREADY COMPLETE (skip)
```

---

## Implementation Order

### Step 1: Fix Phase 1 Bugs (1.5 hours)
```
BUG-001 → BUG-002
```
**Deliverable:** Click isolation works correctly, sources panel shows entity mentions

### Step 2: Database Schema (1 hour)
```
PULSE-VIZ-005
```
**Deliverable:** `tracked_entities` table has `first_seen`, `last_seen` columns

### Step 3: Data Backfill (1.5 hours)
```
PULSE-VIZ-007
```
**Deliverable:** All entities have temporal data populated

### Step 4: API Endpoint (1 hour)
```
PULSE-VIZ-008
```
**Deliverable:** `/api/v1/network/timeline` returns aggregated activity data

---

## Testing Commands

```bash
# Run migration
python -m app.scripts.migrate_entity_temporal

# Verify columns exist
psql -U postgres -d research_platform -c "\d tracked_entities"

# Check backfill results
psql -U postgres -d research_platform -c "SELECT COUNT(*) FROM tracked_entities WHERE first_seen IS NOT NULL"

# Test timeline API
curl http://localhost:8000/api/v1/network/timeline?period=day&days=30

# Test sources panel (after bug fix)
curl http://localhost:8000/api/v1/entities/EntityName/mentions
```

---

## Summary

| Metric | Value |
|--------|-------|
| **Total Features** | 3 (VIZ-006 already done) |
| **Bug Fixes Required** | 2 |
| **Total Estimated Time** | 5 hours |
| **Files to Create** | 1 (`migrate_entity_temporal.py`) |
| **Files to Modify** | 3 (`entities.py`, `routes.py` x2) |

---

## Open Questions

- [x] Does EntityRelationship need temporal columns? → No, already has them
- [x] Should timeline endpoint support filtering by entity type? → Yes, add optional `entity_type` filter param
- [x] Should backfill handle entities with malformed timestamp strings? → Yes, gracefully remediate/skip malformed timestamps

---

## Known Issues (Discovered Post-Phase 2)

### BUG-003: Sources Panel Deactivates Isolation

**Symptom:** After clicking "for sources" on a tooltip, the sources panel loads but the graph isolation is deactivated - full graph becomes visible again.

**Expected Behavior:** Clicking "for sources" should NOT affect the current isolation state. The isolated view should persist while viewing sources.

**Fix Location:** `static/js/pulse-dashboard.js` - `showSourcesPanel()` function or related click handlers

**Status:** Not started

---

### BUG-004: Tooltip Background is Light (Unreadable)

**Symptom:** The entity hover tooltip now has a light background instead of dark, making the text difficult to read against the dark theme.

**Expected Behavior:** Tooltip should have dark background (`rgba(26, 26, 30, 0.95)`) with light text as originally designed.

**Possible Cause:** CSS override or incorrect style application. Check `sigint-theme.css` or inline tooltip styles in `createHoverTooltip()`.

**Status:** Not started

---

### BUG-005: Sources Panel Not Scrollable

**Symptom:** When the sources panel has many items, the list cannot be scrolled to view all sources.

**Expected Behavior:** The sources panel content should be scrollable when content exceeds the panel height.

**Fix Location:** `static/js/pulse-dashboard.js` - `showSourcesPanel()` or CSS for the sources panel container

**Status:** Not started

---

*Generated: 2026-01-15*
*Parent: [ATOMIC_entity-graph-visualization-soa_2026-01-15.md](./ATOMIC_entity-graph-visualization-soa_2026-01-15.md)*
