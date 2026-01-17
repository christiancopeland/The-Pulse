# Atomic Implementation Plan: Entity Graph Visualization SOA

**Created:** 2026-01-15
**Parent Document:** [docs/research/entity-graph-visualization-soa-2026-01.md](../docs/research/entity-graph-visualization-soa-2026-01.md)
**Status:** Ready for Implementation

---

## Overview

This document breaks down the Entity Graph Visualization SOA research into 22 atomic, implementable features organized across 6 phases with explicit dependencies.

**Atomicity Criteria Applied:**
- Each feature implementable in one focused session (2-4 hours max)
- Single, clear responsibility per feature
- Independently testable
- Well-defined inputs and outputs

---

## Phase 1: Bug Fixes (No Dependencies)

**Sprint Goal:** Fix critical UX blockers identified in production

| ID | Name | Description | Est. Time |
|----|------|-------------|-----------|
| PULSE-VIZ-001 | Custom Hover Label Renderer | Override Sigma.js hover rendering to use dark background (`rgba(26,26,30,0.95)`), cyan border (`#00d4ff`), and proper text contrast (`#e0e0e0`). Requires using `hoverRenderer` or `nodeReducer` API (not `defaultDrawNodeHover`). | 2 hrs |
| PULSE-VIZ-001.5 | **Hover Isolation Mode** | When hovering over an entity, hide ALL nodes and edges NOT connected to that entity. Shows only the hovered node + its 1-hop neighbors. Reveals subnetwork structure at a glance. Restore full graph on mouseout. | 2 hrs |
| PULSE-VIZ-001.6 | **Hover Modal → Source List** | Clicking the hover tooltip opens a sources panel showing all documents/articles where that entity appears. Lists source title, date, and context snippet. Enables drilling into provenance directly from the graph. | 2 hrs |
| PULSE-VIZ-001.7 | **Click Isolation Lock** | Clicking an entity locks the hover isolation state (only clicked entity + neighbors visible). Graph stays filtered until user clicks the background to restore full view. Allows focused exploration without holding hover. | 1.5 hrs |
| PULSE-VIZ-002 | Add ForceAtlas2 Library | Add `graphology-layout-forceatlas2` CDN script to `dashboard.html`, no behavior change yet | 0.5 hrs |
| PULSE-VIZ-003 | ForceAtlas2 Layout Integration | Replace server-side spring_layout with client-side ForceAtlas2 using `linLogMode: true`, `scalingRatio: 10`, `gravity: 0.5`, `barnesHutOptimize: true` | 3 hrs |
| PULSE-VIZ-004 | Disconnected Component Handler | Detect isolated nodes (no edges) and position them in a designated "orphan" area at bottom-right of graph instead of letting them drift | 2 hrs |

**Phase 1 Total:** 13 hours

### Acceptance Criteria - Phase 1

- [x] PULSE-VIZ-001: Hover labels readable on dark theme (dark background, light text) ✓ 2026-01-15 (HTML tooltip overlay approach)
- [x] PULSE-VIZ-001.5: Hovering over entity hides all non-connected nodes/edges; mouseout restores full graph ✓ 2026-01-15
- [x] PULSE-VIZ-001.6: Clicking hover modal opens sources list panel with entity mentions ✓ 2026-01-15
- [x] PULSE-VIZ-001.7: Clicking entity locks isolation view; clicking background restores full graph ✓ 2026-01-15
- [x] PULSE-VIZ-002: ForceAtlas2 library loads without console errors ✓ 2026-01-15
- [x] PULSE-VIZ-003: Graph nodes visibly spread into distinct clusters (not a blob) ✓ 2026-01-15
- [x] PULSE-VIZ-004: Isolated nodes positioned in predictable location, not drifting ✓ 2026-01-15

---

## Phase 2: Backend Temporal Infrastructure

**Sprint Goal:** Add database schema and API support for temporal visualization

| ID | Name | Description | Dependencies | Est. Time |
|----|------|-------------|--------------|-----------|
| PULSE-VIZ-005 | Entity Temporal Schema | Add `first_seen TIMESTAMP`, `last_seen TIMESTAMP` columns to `tracked_entities` table via migration script | None | 1 hr |
| PULSE-VIZ-006 | Relationship Temporal Schema | Add `first_observed TIMESTAMP`, `last_observed TIMESTAMP`, `observation_count INTEGER` to `entity_relationships` table | PULSE-VIZ-005 | 1 hr |
| PULSE-VIZ-007 | Populate Temporal Metadata | Backfill `first_seen`/`last_seen` from existing `EntityMention.timestamp` values using SQL aggregation | PULSE-VIZ-005 | 2 hrs |
| PULSE-VIZ-008 | Temporal API Endpoint | Add `GET /api/v1/network/timeline` endpoint returning entity activity aggregated by day/week with counts | PULSE-VIZ-007 | 2 hrs |

**Phase 2 Total:** 6 hours

### Acceptance Criteria - Phase 2

- [ ] PULSE-VIZ-005: Migration runs without error, columns exist in DB
- [ ] PULSE-VIZ-006: Relationship table has temporal columns
- [ ] PULSE-VIZ-007: Existing entities have `first_seen`/`last_seen` populated
- [ ] PULSE-VIZ-008: API returns JSON with `{date, entity_count, mention_count}` structure

---

## Phase 3: Timeline UI Component

**Sprint Goal:** Build interactive timeline below graph for temporal filtering

| ID | Name | Description | Dependencies | Est. Time |
|----|------|-------------|--------------|-----------|
| PULSE-VIZ-009 | Timeline Container HTML/CSS | Add `#entity-timeline` div below graph with range slider, date display span, and canvas element. Style with SIGINT theme. | None | 1 hr |
| PULSE-VIZ-010 | Timeline Canvas Renderer | Implement canvas-based timeline showing entity activity bars (similar to GitHub contribution graph). Color intensity = mention density. | PULSE-VIZ-009 | 4 hrs |
| PULSE-VIZ-011 | Time Range Filter | Add `filterGraphToTimeRange(startDate, endDate)` method that sets `hidden: true` on nodes outside date range | PULSE-VIZ-008, PULSE-VIZ-010 | 2 hrs |
| PULSE-VIZ-012 | Timeline-Graph Sync | Wire timeline slider `input` event to graph filter; clicking a timeline bar centers the range on that period | PULSE-VIZ-011 | 2 hrs |

**Phase 3 Total:** 9 hours

### Acceptance Criteria - Phase 3

- [ ] PULSE-VIZ-009: Timeline container visible below graph, styled consistently
- [ ] PULSE-VIZ-010: Canvas renders activity bars for date range
- [ ] PULSE-VIZ-011: Dragging slider hides/shows nodes based on time
- [ ] PULSE-VIZ-012: Graph and timeline stay synchronized on interaction

---

## Phase 4: Semantic Zoom

**Sprint Goal:** Implement zoom-level-dependent detail rendering (Shneiderman's mantra)

| ID | Name | Description | Dependencies | Est. Time |
|----|------|-------------|--------------|-----------|
| PULSE-VIZ-013 | Cluster Data API | Add `GET /api/v1/network/clusters` endpoint wrapping existing `get_clusters_for_visualization()` with `min_size` parameter | None | 1 hr |
| PULSE-VIZ-014 | Cluster Super-Nodes | Add cluster nodes to graphology graph with special styling: larger size, distinct color, label format "Entity +N" | PULSE-VIZ-013 | 2 hrs |
| PULSE-VIZ-015 | Camera Zoom Handler | Add `sigma.on('cameraUpdated')` listener that reads `camera.ratio` and calls `updateDetailLevel()` | PULSE-VIZ-003 | 1 hr |
| PULSE-VIZ-016 | Detail Level Switching | Implement `updateDetailLevel(ratio)`: ratio < 0.3 = clusters only, ratio < 1.0 = clusters + top-20 by centrality, ratio >= 1.0 = all nodes | PULSE-VIZ-014, PULSE-VIZ-015 | 3 hrs |

**Phase 4 Total:** 7 hours

### Acceptance Criteria - Phase 4

- [ ] PULSE-VIZ-013: API returns cluster list with `{cluster_id, size, members, representative, label}`
- [ ] PULSE-VIZ-014: Cluster nodes render distinctly from regular nodes
- [ ] PULSE-VIZ-015: Zoom changes trigger detail level evaluation
- [ ] PULSE-VIZ-016: Zooming out shows progressively less detail, zooming in shows more

---

## Phase 5: Entity Detail Panel

**Sprint Goal:** Rich entity information panel on node selection

| ID | Name | Description | Dependencies | Est. Time |
|----|------|-------------|--------------|-----------|
| PULSE-VIZ-017 | Entity Detail Panel HTML/CSS | Create slide-out panel (right side) with: type badge, entity name, confidence score, stats grid, relationships list container, sparkline container | None | 2 hrs |
| PULSE-VIZ-018 | Panel Population Logic | On `clickNode` event, fetch `/entities/{name}` and `/entities/{name}/relationships`, populate panel sections | PULSE-VIZ-017 | 2 hrs |
| PULSE-VIZ-019 | Entity Activity Sparkline | Add mini canvas sparkline in detail panel showing entity's mention frequency over time (last 30 days) | PULSE-VIZ-008, PULSE-VIZ-018 | 2 hrs |

**Phase 5 Total:** 6 hours

### Acceptance Criteria - Phase 5

- [ ] PULSE-VIZ-017: Panel slides in from right, styled with SIGINT theme
- [ ] PULSE-VIZ-018: Clicking node populates panel with entity data
- [ ] PULSE-VIZ-019: Sparkline renders mention activity trend

---

## Phase 6: Path Finding UI

**Sprint Goal:** Visual path discovery between entities

| ID | Name | Description | Dependencies | Est. Time |
|----|------|-------------|--------------|-----------|
| PULSE-VIZ-020 | Path Finding Mode Toggle | Add "Find Path" button to graph controls that enables path-finding mode. First click selects source (cyan highlight), second click selects target. | PULSE-VIZ-018 | 1 hr |
| PULSE-VIZ-021 | Path Highlight Visualization | Implement `findAndHighlightPath(sourceId, targetId)`: call `POST /network/path`, highlight path nodes in magenta (`#ff0066`), enlarge them, fade non-path nodes | PULSE-VIZ-020 | 2 hrs |
| PULSE-VIZ-022 | Path Info Display | Show path details in entity panel: path length, ordered list of intermediary nodes with relationship types, "Clear Path" button | PULSE-VIZ-021 | 1.5 hrs |

**Phase 6 Total:** 4.5 hours

### Acceptance Criteria - Phase 6

- [ ] PULSE-VIZ-020: "Find Path" button toggles mode, visual feedback on source selection
- [ ] PULSE-VIZ-021: Path highlights visually, non-path nodes fade
- [ ] PULSE-VIZ-022: Path details display in panel with clear action to reset

---

## Dependency Graph

```
Phase 1 (Bug Fixes)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PULSE-VIZ-001 ─────────────────────────────────────────────────────────┐
(Hover Label)                                                          │
                                                                       │
PULSE-VIZ-002 ──► PULSE-VIZ-003 ──────────────────────────────────┐    │
(Add FA2 Lib)     (FA2 Integration)                               │    │
                                                                  │    │
PULSE-VIZ-004                                                     │    │
(Disconnected)                                                    │    │
                                                                  │    │
Phase 2 (Backend Temporal)                                        │    │
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━│━━━━│━━
PULSE-VIZ-005 ──► PULSE-VIZ-006                                   │    │
(Entity Schema)   (Rel Schema)                                    │    │
      │                                                           │    │
      └──► PULSE-VIZ-007 ──► PULSE-VIZ-008 ───────────────────┐   │    │
           (Backfill)        (Timeline API)                   │   │    │
                                                              │   │    │
Phase 3 (Timeline UI)                                         │   │    │
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━│━━━│━━━━│━━
PULSE-VIZ-009 ──► PULSE-VIZ-010 ──┬──► PULSE-VIZ-011 ──► PULSE-VIZ-012
(Container)       (Canvas)        │    (Time Filter)      (Sync)
                                  │           ▲
                                  │           │
                                  └───────────┴─── needs PULSE-VIZ-008

Phase 4 (Semantic Zoom)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PULSE-VIZ-013 ──► PULSE-VIZ-014 ──┐
(Cluster API)     (Super-Nodes)   │
                                  ├──► PULSE-VIZ-016
PULSE-VIZ-015 ────────────────────┘    (Detail Switching)
(Zoom Handler)         ▲
                       │
                       └─── needs PULSE-VIZ-003

Phase 5 (Entity Detail)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PULSE-VIZ-017 ──► PULSE-VIZ-018 ──► PULSE-VIZ-019
(Panel HTML)      (Population)      (Sparkline)
                                         ▲
                                         │
                                         └─── needs PULSE-VIZ-008

Phase 6 (Path Finding)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PULSE-VIZ-020 ──► PULSE-VIZ-021 ──► PULSE-VIZ-022
(Mode Toggle)     (Highlight)       (Info Display)
      ▲
      │
      └─── needs PULSE-VIZ-018
```

---

## Summary

| Metric | Value |
|--------|-------|
| **Total Features** | 25 |
| **Total Estimated Time** | 45.5 hours |
| **Phases** | 6 |
| **Critical Path** | VIZ-001 → VIZ-001.5 → VIZ-001.7 → VIZ-002 → VIZ-003 → VIZ-015 → VIZ-016 |

### Implementation Progress

| Phase | Status | Completed |
|-------|--------|-----------|
| Phase 1 | **Complete** | 7/7 ✓ |
| Phase 2 | Pending | 0/4 |
| Phase 3 | Pending | 0/4 |
| Phase 4 | Pending | 0/4 |
| Phase 5 | Pending | 0/3 |
| Phase 6 | Pending | 0/3 |

---

## Recommended Implementation Order

### Sprint 1: Bug Fixes (7 hrs)
```
PULSE-VIZ-001 → PULSE-VIZ-002 → PULSE-VIZ-003 → PULSE-VIZ-004
```
**Deliverable:** Readable hover labels, properly spaced graph layout

### Sprint 2: Temporal Backend (6 hrs)
```
PULSE-VIZ-005 → PULSE-VIZ-006 → PULSE-VIZ-007 → PULSE-VIZ-008
```
**Deliverable:** Temporal data infrastructure, timeline API

### Sprint 3: Timeline UI (9 hrs)
```
PULSE-VIZ-009 → PULSE-VIZ-010 → PULSE-VIZ-011 → PULSE-VIZ-012
```
**Deliverable:** Interactive timeline component with graph filtering

### Sprint 4: Semantic Zoom (7 hrs)
```
PULSE-VIZ-013 → PULSE-VIZ-014 → PULSE-VIZ-015 → PULSE-VIZ-016
```
**Deliverable:** Zoom-dependent detail levels (overview → detail)

### Sprint 5: Entity Panel (6 hrs)
```
PULSE-VIZ-017 → PULSE-VIZ-018 → PULSE-VIZ-019
```
**Deliverable:** Rich entity detail panel with activity sparkline

### Sprint 6: Path Finding (4.5 hrs)
```
PULSE-VIZ-020 → PULSE-VIZ-021 → PULSE-VIZ-022
```
**Deliverable:** Visual path discovery between entities

---

## Files to Modify by Feature

| Feature ID | Files |
|------------|-------|
| PULSE-VIZ-001 | `static/js/pulse-dashboard.js` (Sigma.js renderer settings) |
| PULSE-VIZ-001.5 | `static/js/pulse-dashboard.js` (enterNode/leaveNode event handlers) |
| PULSE-VIZ-001.6 | `static/js/pulse-dashboard.js` (tooltip click handler), `templates/dashboard.html` (sources panel HTML), `static/css/sigint-theme.css` (sources panel styling) |
| PULSE-VIZ-001.7 | `static/js/pulse-dashboard.js` (clickNode/clickStage event handlers) |
| PULSE-VIZ-002 | `templates/dashboard.html` |
| PULSE-VIZ-003 | `static/js/pulse-dashboard.js` |
| PULSE-VIZ-004 | `static/js/pulse-dashboard.js` |
| PULSE-VIZ-005 | `app/scripts/migrate_entity_temporal.py` (new), `app/models/entities.py` |
| PULSE-VIZ-006 | `app/scripts/migrate_entity_temporal.py`, `app/models/entities.py` |
| PULSE-VIZ-007 | `app/scripts/migrate_entity_temporal.py` |
| PULSE-VIZ-008 | `app/api/v1/network/routes.py` |
| PULSE-VIZ-009 | `templates/dashboard.html`, `static/css/sigint-theme.css` |
| PULSE-VIZ-010 | `static/js/pulse-dashboard.js` |
| PULSE-VIZ-011 | `static/js/pulse-dashboard.js` |
| PULSE-VIZ-012 | `static/js/pulse-dashboard.js` |
| PULSE-VIZ-013 | `app/api/v1/network/routes.py` |
| PULSE-VIZ-014 | `static/js/pulse-dashboard.js` |
| PULSE-VIZ-015 | `static/js/pulse-dashboard.js` |
| PULSE-VIZ-016 | `static/js/pulse-dashboard.js` |
| PULSE-VIZ-017 | `templates/dashboard.html`, `static/css/sigint-theme.css` |
| PULSE-VIZ-018 | `static/js/pulse-dashboard.js` |
| PULSE-VIZ-019 | `static/js/pulse-dashboard.js` |
| PULSE-VIZ-020 | `static/js/pulse-dashboard.js` |
| PULSE-VIZ-021 | `static/js/pulse-dashboard.js` |
| PULSE-VIZ-022 | `static/js/pulse-dashboard.js`, `templates/dashboard.html` |

---

## Next Steps

1. **Create detailed specs** for Sprint 1 features (PULSE-VIZ-001 through PULSE-VIZ-004)
2. **Implement Sprint 1** to resolve immediate UX blockers
3. **Validate** bug fixes with user before proceeding to temporal features

---

*Generated: 2026-01-15*
*Parent: [entity-graph-visualization-soa-2026-01.md](../docs/research/entity-graph-visualization-soa-2026-01.md)*
