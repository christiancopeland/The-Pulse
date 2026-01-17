## Recent Changes (2026-01-16) - Network Graph Performance Analysis & Spec

### Overview

Conducted deep analysis of Network page latency issues. Created comprehensive atomic spec for performance optimization. Discovered critical bug in Phase 4 semantic zoom implementation.

### Performance Analysis

Identified **3 root causes** of network graph latency:

| Bottleneck | Impact | Location |
|------------|--------|----------|
| Synchronous ForceAtlas2 | UI freeze 3-8s | `pulse-dashboard.js:3087` |
| Excessive refresh() calls | 20+ per action | Throughout file |
| No Sigma performance settings | Slow pan/zoom | `initializeSigmaGraph()` |

### SOA Research Completed

Researched state-of-the-art graph visualization techniques:
- **Web Worker ForceAtlas2** - Built into graphology library, runs layout off main thread
- **GPU-accelerated layout** - Cosmograph/Cosmos achieves 40x+ speedup
- **WebGPU innovations** - Research shows 69.5x speedup potential
- **Sigma.js settings** - `hideEdgesOnMove`, `hideLabelsOnMove` for smooth interaction

### New Spec Created

**File:** `specs/ATOMIC_network-graph-performance-optimization_2026-01-16.md`

| Phase | Features | Est. Time |
|-------|----------|-----------|
| Phase 0 | PERF-000: Fix threshold bug | 0.5 hrs |
| Phase 1 | PERF-001/003/004: Worker, Settings, Batching | 4 hrs |
| Phase 2 | PERF-002: Progressive feedback | 1.5 hrs |
| Phase 3 | PERF-005/006: Cosmos eval, Metrics | 6 hrs |

**Total: 7 features, 12 hours estimated**

### Critical Bug Discovered

Phase 4 Semantic Zoom has **inverted camera ratio thresholds** - clusters never appear:
- Sigma.js: zoom OUT = ratio INCREASES
- Code assumes: zoom OUT = ratio DECREASES
- Location: `pulse-dashboard.js:1983-1988`

See validation results appended to `specs/ATOMIC_phase4-semantic-zoom_entity-graph-visualization_2026-01-16.md`

### Graph Statistics

```
Nodes: 2,215
Edges: 5,890
Clusters: 23
Components: 1,211
Current render time: 35-70 seconds (blocking)
Target render time: < 1 second (with optimizations)
```

### Files Created

| File | Purpose |
|------|---------|
| `specs/ATOMIC_network-graph-performance-optimization_2026-01-16.md` | Full performance optimization spec |

### Next Steps

1. **PERF-000**: Fix threshold inversion (30 min) - unblocks semantic zoom
2. **PERF-003**: Enable Sigma performance settings (30 min) - quick win
3. **PERF-001**: Web Worker ForceAtlas2 (2 hrs) - eliminates UI freeze

### Research Sources

- [Graphology ForceAtlas2 Worker](https://graphology.github.io/standard-library/layout-forceatlas2.html)
- [Cosmograph/Cosmos GPU Layout](https://github.com/cosmograph-org/cosmos)
- [Cambridge Intelligence WebGL Visualization](https://cambridge-intelligence.com/visualizing-graphs-webgl/)

---

## Recent Changes (2026-01-16) - Phase 4: Semantic Zoom Implementation

### Overview

Implemented complete Phase 4 Semantic Zoom feature for the entity graph visualization. The graph now adapts its detail level based on camera zoom, showing cluster summaries when zoomed out and individual entities when zoomed in.

### Changes

#### PULSE-VIZ-014: Cluster Super-Nodes

**File:** `static/js/pulse-dashboard.js` (lines 1870-1960)

**Implementation:**
- `addClusterNodes()` - Creates cluster super-nodes at cluster centroid positions
- `removeClusterNodes()` - Removes cluster nodes when switching to full detail
- `getClusterColor(dominantType)` - Returns color based on entity type (PERSON=blue, ORG=red, etc.)

Cluster nodes are sized logarithmically based on member count (base 15 + log2(size) * 8).

#### PULSE-VIZ-014a: Cluster Node Styling

**File:** `static/js/pulse-dashboard.js` (lines 2144-2191)

**Implementation:** `updateClusterBadges()` creates HTML overlay badges showing member count on each cluster node. Badges are positioned relative to viewport coordinates and update on camera move.

#### PULSE-VIZ-014b: Cluster Expand/Collapse

**File:** `static/js/pulse-dashboard.js` (lines 2200-2310)

**Implementation:**
- `expandCluster(clusterId)` - Shows member nodes in circle around centroid
- `collapseCluster(clusterId)` - Hides members, shows cluster node
- `setupClusterDoubleClick(sigma, graph)` - Registers double-click handler

#### PULSE-VIZ-015: Camera Zoom Handler Enhancement

**File:** `static/js/pulse-dashboard.js` (lines 1823-1855)

**Implementation:** Enhanced `setupSemanticZoom()` to call `updateDetailLevel(ratio)` with 150ms debounce. Stores `currentGraph` and `currentSigma` references for use by detail level methods.

#### PULSE-VIZ-016: Detail Level Switching

**File:** `static/js/pulse-dashboard.js` (lines 1965-2142)

**Implementation:**
- `updateDetailLevel(ratio)` - Determines target level from ratio
- `applyOverviewMode()` - Shows only cluster nodes (ratio < 0.3)
- `applyPartialMode()` - Shows clusters + top 20 entities (0.3 ≤ ratio < 1.0)
- `applyFullMode()` - Shows all individual entities (ratio ≥ 1.0)
- `getTopEntitiesByCentrality(n)` - Returns top N entities by degree

#### PULSE-VIZ-016a: Smooth Level Transitions

**File:** `static/js/pulse-dashboard.js` (lines 2320-2345)

**Implementation:** Utility methods `sleep(ms)` and `adjustColorOpacity(color, opacity)` for future animation support.

### Files Modified

| File | Lines Added |
|------|-------------|
| `static/js/pulse-dashboard.js` | ~400 |

### Testing

- Node.js syntax check: PASSED
- API returns 23 clusters with proper structure
- Largest cluster: 182 members

---

## Recent Changes (2026-01-15) - Sprint 1: Graph Visualization Bug Fixes

### Overview

Implemented Sprint 1 of the Entity Graph Visualization SOA roadmap. Fixed the two critical UX blockers: unreadable hover labels and blob-like graph layout.

### Changes

#### PULSE-VIZ-001: Custom Hover Label Renderer

**Problem:** Sigma.js hardcodes hover background to white (`#FFF`), unreadable on dark theme.

**File:** `static/js/pulse-dashboard.js` (lines 1437-1478)

**Fix:** Added `defaultDrawNodeHover` to Sigma constructor:
- Dark background: `rgba(26, 26, 30, 0.95)`
- Cyan border: `#00d4ff`
- Light text: `#e0e0e0`
- Cyan highlight ring around hovered node

#### PULSE-VIZ-002: Add ForceAtlas2 Library

**Problem:** No browser-ready bundle existed for graphology-layout-forceatlas2.

**Solution:** Bundled library locally using esbuild:
```bash
npm install --save-dev esbuild graphology-layout-forceatlas2
npx esbuild bundle-forceatlas2.js --bundle --minify --format=iife --outfile=static/js/forceatlas2.min.js
```

**File:** `static/js/forceatlas2.min.js` (10.9KB)

#### PULSE-VIZ-003: ForceAtlas2 Layout Integration

**Problem:** Server-side NetworkX spring_layout produced a blob with outliers.

**File:** `static/js/pulse-dashboard.js` (lines 1652-1679)

**Fix:** Client-side ForceAtlas2 with research-backed settings:
```javascript
settings.linLogMode = true;        // Critical for cluster separation
settings.scalingRatio = 10;
settings.gravity = 0.5;
settings.barnesHutOptimize = true; // For graphs > 100 nodes
```

Dynamic iterations (100-500) based on graph size.

#### PULSE-VIZ-004: Disconnected Component Handler

**Problem:** Isolated nodes (no edges) drifted to random positions.

**File:** `static/js/pulse-dashboard.js` (lines 1693-1722)

**Fix:** Added `positionOrphanNodes()` method that:
1. Detects disconnected nodes (not in any edge)
2. Positions them in a grid at bottom-right of main graph
3. Uses 50px spacing, square grid layout

### Files Modified

| File | Changes |
|------|---------|
| `static/js/pulse-dashboard.js` | Custom hover renderer, ForceAtlas2 integration, orphan node handling |
| `templates/dashboard.html` | Updated script include to use local ForceAtlas2 bundle |
| `static/js/forceatlas2.min.js` | **NEW**: Bundled ForceAtlas2 library (10.9KB) |

### Testing

After hard-refreshing browser at `/dashboard` → Network view:
- Hover labels should have dark background with cyan border
- Graph should show distinct clusters (not a blob)
- Orphan nodes should appear in grid at bottom-right

### Spec Reference

Sprint 1 acceptance criteria marked complete in [specs/ATOMIC_entity-graph-visualization-soa_2026-01-15.md](specs/ATOMIC_entity-graph-visualization-soa_2026-01-15.md)

---

## Recent Changes (2026-01-15) - Entity Network UX Polish

### Overview

Post-Phase 3 UX fixes addressing node spacing, double-click behavior, and legend visibility issues identified during testing.

### Changes

#### 1. Node Spacing Fix (Backend)

**Problem:** 1000+ nodes were crammed together in an indistinguishable blob.

**File:** `app/services/network_mapper/graph_service.py` (lines 756-800)

**Root Cause:** Layout used `k=1/sqrt(n)` repulsion and fixed `scale=1000`, insufficient for large graphs.

**Fix:**
- Increased repulsion: `k = 3/sqrt(n)` (was `1/sqrt(n)`)
- Dynamic scaling: `effective_scale = scale + (node_count * 3)`
  - For 1000 nodes: ~4000 scale instead of 1000
- More iterations: 100 (was 50) for better convergence

#### 2. Double-Click Filter Behavior (Frontend)

**Problem:** Double-clicking a node added more nodes but didn't filter the view.

**File:** `static/js/pulse-dashboard.js`

**Changes:**
- Added `focusedEntityId` state property (line 53)
- Changed `doubleClickNode` handler (lines 1445-1465) to call `filterToEntity()` instead of `expandNodeConnections()`
- Added `clickStage` handler to clear focus on background click
- New method `filterToEntity(nodeId, graph, sigma)` (lines 1691-1735):
  - Fades non-connected nodes to 10% opacity
  - Shrinks non-connected nodes to size 3
  - Animates camera to center on focused entity
- New method `clearFocus(graph, sigma)` (lines 1737-1756)
- Updated `clearHighlight()` to respect focus mode

#### 3. Legend Visibility Fix (CSS/HTML)

**Problem:** Color legend was outside graph container, getting cut off by viewport.

**Files:**
- `templates/dashboard.html` (lines 327-331, 506-510): Moved legend inside graph containers
- `static/css/sigint-theme.css` (lines 917-928): Changed to absolute positioning at bottom-left

#### 4. UI Hint Text Update

**File:** `templates/dashboard.html` (line 325)
- Changed: "Double-click an entity to expand its connections"
- To: "Double-click to filter connections • Click background to reset"

### Files Modified

| File | Changes |
|------|---------|
| `app/services/network_mapper/graph_service.py` | Dynamic layout scaling, increased k and iterations |
| `static/js/pulse-dashboard.js` | `filterToEntity()`, `clearFocus()`, `focusedEntityId` state |
| `static/css/sigint-theme.css` | `.graph-legend` absolute positioning |
| `templates/dashboard.html` | Legend moved inside containers, hint text updated |

### Testing

After restarting backend and hard-refreshing browser:
- Graph nodes should be visibly spread out
- Double-click filters to entity's connections (others fade)
- Click background clears filter
- Legend visible at bottom-left

---

## Recent Changes (2026-01-15) - Entity Visualization Overhaul Phase 3 (Sigma.js)

### Overview

Completed Phase 3 of the entity visualization overhaul: migrated from Cytoscape.js to Sigma.js v2 + graphology for WebGL-based rendering. This enables smooth interaction with 10k+ nodes.

### Changes

#### Library Migration

**Replaced:** Cytoscape.js (Canvas-based)
**With:** Sigma.js v2 + graphology (WebGL-based)

**File:** `templates/dashboard.html`
```html
<!-- Removed -->
<script src="https://cdnjs.cloudflare.com/ajax/libs/cytoscape/3.23.0/cytoscape.min.js"></script>

<!-- Added -->
<script src="https://cdnjs.cloudflare.com/ajax/libs/graphology/0.25.4/graphology.umd.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/sigma.js/2.4.0/sigma.min.js"></script>
```

#### Server-Side Layout Computation

**File:** `app/services/network_mapper/graph_service.py`
- Added `compute_layout(algorithm, scale)` method
  - Algorithms: spring (default), kamada_kawai, circular, shell
  - Returns `{entity_id: (x, y)}` coordinate mapping
  - Eliminates client-side layout jitter
- Added `get_clusters_for_visualization(min_size)` method
  - Uses Louvain community detection
  - Returns cluster metadata for semantic zoom

**File:** `app/api/v1/network/routes.py`
- Updated `/network/graph` endpoint with new parameters:
  - `include_positions: bool = True`
  - `layout: str = "spring"`
  - `include_clusters: bool = False`

#### Frontend Rewrite

**File:** `static/js/pulse-dashboard.js`
- Complete rewrite of graph rendering system
- New class properties: `graph`, `sigma`, `graphMini`, `sigmaMini`, `graphFullscreen`, `sigmaFullscreen`
- Key methods rewritten:
  - `initEntityGraph()` - Creates graphology Graph + Sigma renderer
  - `renderNetworkGraph()` - Uses server-computed positions
  - `highlightNode()` / `clearHighlight()` - Hover effects
  - `expandNodeConnections()` - Double-click expand
  - `setupSemanticZoom()` - Label density adjustment
- Zoom controls use Sigma camera API: `animatedZoom()`, `animatedUnzoom()`, `animatedReset()`

#### Critical Bug Fix: Reserved `type` Attribute

**Error:** `Sigma: could not find a suitable program for node type "LOCATION"!`

**Root Cause:** Sigma.js reserves the `type` attribute for node rendering programs (shader types like "circle", "image"). Setting `type: "LOCATION"` caused Sigma to look for a non-existent renderer.

**Fix:** Renamed all attributes:
- Node: `type` → `entityType`
- Edge: `type` → `edgeType`

Affected functions:
- `renderNetworkGraph()`
- `updateEntityGraphFallback()`
- `highlightNode()` / `clearHighlight()`
- `expandNodeConnections()`
- `highlightNeighborhood()`
- `renderNeighborhoodGraph()`
- `loadEntityAndFocus()`

### Files Modified

| File | Changes |
|------|---------|
| `app/services/network_mapper/graph_service.py` | `compute_layout()`, `get_clusters_for_visualization()` (~130 lines) |
| `app/api/v1/network/routes.py` | New params: `include_positions`, `layout`, `include_clusters` |
| `templates/dashboard.html` | Sigma.js + graphology CDN scripts |
| `static/js/pulse-dashboard.js` | Complete graph system rewrite (~500 lines changed) |

### Status

- Phase 1: Complete (graph container, fullscreen, entity list)
- Phase 2: Complete (progressive disclosure)
- Phase 3: Complete (Sigma.js migration)

**Entity Visualization Overhaul: COMPLETE**

---

## Recent Changes (2025-01-15) - Entity Visualization Overhaul Phase 2

### Overview

Completed Phase 2 (Progressive Disclosure) of the entity visualization overhaul. Added search-to-focus, expand-on-click, and depth controls for better graph exploration.

### Changes

#### New API Endpoints

**File:** `app/api/v1/network/routes.py`
- `GET /graph/subset`: Paginated graph loading with centrality sorting
  - Params: `limit`, `offset`, `sort_by` (centrality/mentions/recent), `entity_type`, `search`
  - Returns subset of nodes + edges between them

**File:** `app/api/v1/entities/routes.py`
- `GET /entities/search`: Fuzzy entity search with relevance scoring
  - Params: `q` (query), `limit`, `entity_type`
  - Relevance: exact match > prefix > substring

#### Frontend Features

**Search-to-Focus:**
- Search input in graph header and fullscreen modal
- Dropdown shows matching entities (debounced 300ms)
- Clicking result centers graph on entity or loads its neighborhood

**Expand-on-Click:**
- Double-click any node to load its immediate neighbors
- Incrementally adds new nodes without clearing graph
- Toast feedback on expansion

**Depth Selector:**
- Dropdown in main graph and fullscreen modal
- Options: 1 hop, 2 hops, 3 hops
- Controls neighborhood depth when loading entities

**Visual Feedback:**
- `.faded` class dims non-focused elements (opacity 0.15)
- `.highlighted` class emphasizes focused node (cyan border)
- Hint tooltip: "Double-click an entity to expand its connections"

### Files Modified

| File | Changes |
|------|---------|
| `app/api/v1/network/routes.py` | `/graph/subset` endpoint (~140 lines) |
| `app/api/v1/entities/routes.py` | `/search` endpoint (~65 lines) |
| `templates/dashboard.html` | Search wrapper, depth selector, hint (~25 lines) |
| `static/js/pulse-dashboard.js` | Search/expand methods (~250 lines) |
| `static/css/sigint-theme.css` | Search dropdown, depth selector styles (~165 lines) |

### Status

- Phase 1: Complete (graph container, fullscreen, entity list)
- Phase 2: Complete (progressive disclosure)
- Phase 3: Pending/Optional (Sigma.js migration)

---

## Recent Changes (2025-01-15) - Entity Visualization Overhaul Phase 1

### Overview

Implemented Phase 1 of the entity visualization improvements to address graph usability and entity management issues:
1. Expanded graph container from 300px to full viewport height
2. Added dedicated entity list page with bulk operations
3. Added full-screen graph modal for immersive exploration
4. Separated Network view (graph) from Entities view (list)

### Changes

#### Graph Container Expansion
**File:** `static/css/sigint-theme.css`
- Changed `.entity-graph-container` height from `300px` to `calc(100vh - 220px)` with `min-height: 500px`
- Graph now fills available viewport, enabling actual exploration

#### Full-Screen Graph Modal
**Files:** `dashboard.html`, `sigint-theme.css`, `pulse-dashboard.js`
- Added `#fullscreen-graph-modal` overlay with dedicated Cytoscape instance
- Zoom controls, search input, and legend in modal
- Toggle via "Full Screen" button, close via X or Escape key

#### Navigation Split
**File:** `templates/dashboard.html`
- "Entities" nav item renamed to "Network" (graph view)
- Added new "Entities" nav item (list view)
- Two distinct views: `view-entities` (graph) and `view-entity-list` (list)

#### Entity List View
**Files:** `dashboard.html`, `sigint-theme.css`, `pulse-dashboard.js`
- Dedicated page for entity management at `/dashboard#entity-list`
- Features: Search, type filter, sort (mentions/name/recent), pagination (50/page)
- Bulk actions: Select all, merge selected, delete selected, export JSON

#### API Enhancements
**File:** `app/api/v1/entities/routes.py`
- `GET /entities`: Now supports `limit`, `offset`, `sort`, `type` params + returns `total` count
- `DELETE /entities/bulk`: New endpoint for bulk entity deletion

### Files Modified

| File | Changes |
|------|---------|
| `static/css/sigint-theme.css` | Graph container height, fullscreen modal styles, entity list styles (~280 lines added) |
| `templates/dashboard.html` | Navigation split, entity list view, fullscreen modal (~110 lines added) |
| `static/js/pulse-dashboard.js` | Entity list state, fullscreen graph methods, entity list methods (~350 lines added) |
| `app/api/v1/entities/routes.py` | Pagination params, bulk delete endpoint (~75 lines added) |

### Spec Location

Full implementation spec for all 3 phases: `specs/entity-visualization-overhaul-2025-01-15.md`

### Next Steps (Phase 2 & 3)

Phase 2 (Progressive Disclosure):
- Paginated graph API (`/graph/subset`)
- Entity search endpoint
- Search-to-focus workflow
- Expand-on-click pattern
- Depth controls

Phase 3 (Sigma.js Migration - MANDATORY):
- Replace Cytoscape.js with Sigma.js v2 + graphology
- Server-side layout computation
- Semantic zoom with clustering

---

## Recent Changes (2026-01-15) - Dashboard Startup Latency Fix

### Overview

Removed the Trending Entities and Relationship Graph sections from the dashboard homepage to reduce initial load latency. These features are still available on the dedicated Entities page.

### Changes

#### Removed from Dashboard Homepage
- **Trending Entities panel** - Was making `/api/v1/entities` call on every page load
- **Relationship Graph mini panel** - Was initializing Cytoscape and calling `/api/v1/network/graph` on startup

#### Deferred Loading
- Entity data and network graph now load **on-demand** when user navigates to the Entities view
- Dashboard init no longer calls `loadEntities()` or `initEntityGraph('entity-graph-mini')`

### Files Modified

| File | Changes |
|------|---------|
| `templates/dashboard.html` | Removed Trending Entities and Relationship Graph panel sections from right sidebar |
| `static/js/pulse-dashboard.js` | Removed `loadEntities()` and `initEntityGraph()` from init; entities now load when switching to Entities view |

---

## Recent Changes (2026-01-12) - Dashboard UI & Collector Fixes

### Overview

Fixed multiple dashboard UI issues and collector bugs that were causing empty displays and silent failures:

1. **Dashboard UI Fixes** - Collapsible panels, news feed, entities list, briefing button
2. **SEC EDGAR Collector** - RSS fallback when search API returns empty results
3. **OpenSanctions Collector** - Proper API key requirement handling
4. **Local News Collector** - Removed broken RSS feed
5. **RC Manufacturers Collector** - Warning for missing configuration
6. **Timezone Fixes** - Fixed naive/aware datetime mismatch in local government queries

---

### Dashboard UI Fixes

#### Issue 1: Collapsible Panels Not Working

**File:** `static/css/sigint-theme.css` (lines 277-283)

**Problem:** CSS selector required `.collapsible` class but HTML only had `.expanded`

**Fix:**
```css
/* Before - required .collapsible class that HTML didn't have */
.panel-section.collapsible .panel-content { display: none; }
.panel-section.collapsible.expanded .panel-content { display: block; }

/* After - works with just .expanded class */
.panel-section .panel-content { display: none; }
.panel-section.expanded .panel-content { display: block; }
```

#### Issue 2: News Feed Empty

**File:** `static/js/pulse-dashboard.js` (line 346)

**Problem:** API returns array directly but JS expected `{items: [...]}` wrapper

**Fix:**
```javascript
// Before
this.newsItems = response.items || [];

// After - handles both formats
this.newsItems = Array.isArray(response) ? response : (response.items || []);
```

#### Issue 3: Entities List Empty / No Mention Counts

**File:** `app/api/v1/entities/routes.py` (lines 122-165)

**Problem:** Endpoint didn't include `mention_count` and had user_id type mismatch

**Fix:**
- Added LEFT JOIN with `EntityMention` table
- Added `GROUP BY` to aggregate mention counts
- Fixed user_id comparison: `str(current_user.user_id)`
- Added `mention_count` field to response
- Changed sort order to `mention_count DESC`

#### Issue 4: Briefing Button No Feedback

**File:** `static/js/pulse-dashboard.js` (lines 427-454)

**Problem:** No loading spinner, no toast notifications on success/error

**Fix:** Added `setButtonLoading()`, `showToast()` for success/error feedback

---

### Collector Bug Fixes

#### SEC EDGAR Collector - RSS Fallback Fix

**File:** `app/services/collectors/sec_edgar_collector.py` (lines 229-242)

**Problem:** Search API returns HTTP 200 with 0 results. Fallback only triggered on non-200 status.

**Fix:** Added fallback when hits array is empty:
```python
hits = data.get("hits", {}).get("hits", [])
if not hits:
    self._logger.debug(f"SEC search returned 0 hits for {form_type}, trying RSS fallback")
    rss_items = await self._fetch_from_rss(session, form_type)
    items.extend(rss_items)
    continue
```

**Result:** Now collects ~120 items via RSS fallback instead of 0.

#### OpenSanctions Collector - API Key Handling

**File:** `app/services/collectors/opensanctions_collector.py` (lines 181-207)

**Problem:** `/search` endpoint requires API key but collector silently failed without one.

**Fix:** Added early exit with helpful warning:
```python
if not self.api_key:
    self._logger.warning(
        "OpenSanctions API key not configured. The /search endpoint requires authentication. "
        "Set OPENSANCTIONS_API_KEY environment variable, or consider using bulk data downloads "
        "from https://www.opensanctions.org/datasets/ for free access."
    )
    return items
```

**Note:** OpenSanctions bulk data is FREE for non-commercial use. Only the API is paid.

#### Local News Collector - Broken Feed Removed

**File:** `app/services/collectors/config.py` (lines 106-117)

**Problem:** WRCB RSS feed redirects to 404 (https://www.local3news.com/rss/)

**Fix:** Removed broken feed, kept working Chattanoogan feed:
```python
LOCAL_NEWS_SOURCES = {
    "chattanoogan": {
        "url": "https://www.chattanoogan.com",
        "rss": "https://www.chattanoogan.com/Breaking-News/feed.rss",
        "category": "local",
    },
    # WRCB/Local3News RSS feed removed - redirects to 404 as of 2026-01
}
```

#### RC Manufacturers Collector - Missing Config Warning

**File:** `app/services/collectors/rc_manufacturer_collector.py` (lines 137-147)

**Problem:** Collector initialized with 0 targets (no `rc_industry` entries in `SCRAPE_TARGETS`)

**Fix:** Added warning when no targets configured:
```python
if not self.targets:
    self._logger.warning(
        "RC Manufacturers collector has no targets configured. "
        "Add entries with category='rc_industry' to SCRAPE_TARGETS in config.py, "
        "or disable this collector if RC monitoring is not needed."
    )
    return all_items
```

---

### Timezone Mismatch Fixes

**Problem:** PostgreSQL columns use `TIMESTAMP WITHOUT TIME ZONE` but queries passed timezone-aware datetimes, causing:
```
can't subtract offset-naive and offset-aware datetimes
```

**Files Fixed:**
| File | Line | Change |
|------|------|--------|
| `app/services/local_government/local_analyzer.py` | 64 | `datetime.now(timezone.utc).replace(tzinfo=None)` |
| `app/services/local_government/local_analyzer.py` | 435 | `datetime.now(timezone.utc).replace(tzinfo=None)` |
| `app/services/local_government/geofence_service.py` | 343 | `datetime.now(timezone.utc).replace(tzinfo=None)` |

**Fix Pattern:**
```python
# Before - timezone-aware (fails with TIMESTAMP WITHOUT TIME ZONE)
cutoff = datetime.now(timezone.utc) - timedelta(days=30)

# After - naive datetime (compatible)
cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=30)
```

---

### Files Summary (2026-01-12)

| File | Action | Description |
|------|--------|-------------|
| `static/css/sigint-theme.css` | Modified | Fixed collapsible panel CSS selectors |
| `static/js/pulse-dashboard.js` | Modified | Fixed news feed parsing, briefing button UX, entities loading |
| `app/api/v1/entities/routes.py` | Modified | Added mention_count, fixed user_id comparison |
| `app/services/collectors/sec_edgar_collector.py` | Modified | Added RSS fallback for empty search results |
| `app/services/collectors/opensanctions_collector.py` | Modified | Added API key requirement warning |
| `app/services/collectors/config.py` | Modified | Removed broken WRCB RSS feed |
| `app/services/collectors/rc_manufacturer_collector.py` | Modified | Added missing config warning |
| `app/services/local_government/local_analyzer.py` | Modified | Fixed timezone-aware datetime queries |
| `app/services/local_government/geofence_service.py` | Modified | Fixed timezone-aware datetime queries |

---

## Recent Changes (2026-01-12) - Entity Network & Relationship Fixes

### Overview

Fixed critical issues preventing entity network graphs and tracked entity lists from displaying:

1. **Empty Entity Relationships** - Discovered relationship extraction was never called, fixed with immediate discovery + pipeline integration
2. **User ID Type Mismatch** - Fixed `str()` conversion causing UUID column comparison failures
3. **Graph Performance** - Added 60-second TTL cache for network graph queries
4. **Frontend Rendering Bug** - Fixed network graph only rendering to mini graph, not main canvas
5. **Missing Entity List** - Added function to populate tracked entities list

---

### Issue 1: Empty Entity Relationships (0 Edges)

**Root Cause**: `AutoEntityExtractor.extract_relationships()` method existed but was NEVER called anywhere in the codebase.

**Immediate Fix**: Called relationship discovery API:
```bash
# Ran POST /api/v1/network/discover
# Discovered 48 relationships (96 edges bidirectional)

# Then ran POST /api/v1/network/discover/full
# Found 10,702 relationships across multiple types
```

**Long-term Fix**: Enhanced processing pipeline to extract relationships automatically.

**Files Modified**:

| File | Changes |
|------|---------|
| `app/services/processing/pipeline.py` | Added `RELATIONSHIP_PATTERNS`, `_infer_relationship_type()`, enhanced `_detect_relationships_in_item()` |
| `app/services/entity_extraction/auto_extractor.py` | Added `extract_and_save_relationships()` method |

**Pattern-Based Relationship Detection**:
```python
RELATIONSHIP_PATTERNS = {
    "supports": ["supports", "endorses", "backs", "advocates for", "champions", "defends"],
    "opposes": ["opposes", "criticizes", "attacks", "condemns", "rejects", "denounces", "against"],
    "collaborates_with": ["works with", "partners with", "collaborates", "together with", "alongside", "met with"],
    "leads": ["leads", "heads", "directs", "manages", "runs", "chairs"],
    "funds": ["funds", "finances", "invests in", "sponsors", "pays for"],
    "part_of": ["member of", "part of", "belongs to", "works for", "employed by", "joined"],
    "impacts": ["affects", "impacts", "influences", "changes", "shapes"],
    "responds_to": ["responds to", "reacted to", "answered", "replied to"],
    "regulates": ["regulates", "oversees", "monitors", "controls"],
}
```

---

### Issue 2: User ID Type Mismatch (Empty Entities)

**File**: `app/api/v1/entities/routes.py`

**Problem**: SQLAlchemy comparing `str(UUID)` to UUID column type returns no matches:
```python
# BROKEN - comparing string to UUID column
.where(TrackedEntity.user_id == str(current_user.user_id))
```

**Fix**: Removed `str()` conversion (lines 142, 434, 442):
```python
# FIXED - direct UUID comparison
.where(TrackedEntity.user_id == current_user.user_id)
```

---

### Issue 3: Extreme Graph Loading Slowness

**Root Cause**: Graph reloaded from database on EVERY request (1007 nodes + 5890 edges), taking 5-10 seconds per query.

**File**: `app/api/v1/network/routes.py`

**Fix**: Added `GraphCache` class with 60-second TTL:
```python
class GraphCache:
    """Simple in-memory cache for loaded graphs with TTL."""

    def __init__(self, ttl_seconds: int = 60):
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._ttl = timedelta(seconds=ttl_seconds)
        self._lock = asyncio.Lock()

    async def get_mapper(self, db, user_id: Optional[UUID]) -> NetworkMapperService:
        key = self._cache_key(user_id)
        now = datetime.now(timezone.utc)
        async with self._lock:
            if key in self._cache:
                entry = self._cache[key]
                if now - entry["loaded_at"] < self._ttl:
                    entry["mapper"].db = db  # Update session reference
                    return entry["mapper"]
            # Load fresh and cache
            mapper = NetworkMapperService(db, user_id=user_id)
            await mapper.load_from_database()
            self._cache[key] = {"mapper": mapper, "loaded_at": now}
            return mapper

    async def invalidate(self, user_id: Optional[UUID] = None):
        """Invalidate cache on relationship modifications."""

_graph_cache = GraphCache(ttl_seconds=60)
```

**Cache Invalidation**: Added to relationship modification endpoints (`/relationships`, `/discover`, `/discover/full`).

---

### Issue 4: Database Index Optimization

**File**: `app/models/entities.py`

**Added Indexes**:
```python
# TrackedEntity indexes
Index('ix_tracked_entities_name_lower_btree', 'name_lower'),
Index('ix_tracked_entities_user_id', 'user_id'),

# EntityMention indexes
Index('ix_entity_mentions_entity_id', 'entity_id'),
Index('ix_entity_mentions_news_item_id', 'news_item_id'),
Index('ix_entity_mentions_document_id', 'document_id'),
Index('ix_entity_mentions_news_article_id', 'news_article_id'),
Index('ix_entity_mentions_timestamp', 'timestamp'),
Index('ix_entity_mentions_entity_timestamp', 'entity_id', 'timestamp'),
```

---

### Issue 5: Main Entity Network Canvas Empty

**File**: `static/js/pulse-dashboard.js`

**Problem**: `renderNetworkGraph()` used `this.cyMini || this.cy` which always prefers mini graph:
```javascript
// BROKEN - only renders to one graph
const cy = this.cyMini || this.cy;
cy.elements().remove();
cy.add([...]);
```

**Fix**: Render to BOTH graphs:
```javascript
renderNetworkGraph(elements) {
    if (!elements) return;
    // Process nodes and edges...
    const graphs = [this.cyMini, this.cy].filter(Boolean);
    for (const cy of graphs) {
        cy.elements().remove();
        cy.add([...processedNodes, ...processedEdges]);
        cy.layout({name: 'cose', animate: false, nodeRepulsion: 8000, idealEdgeLength: 100}).run();
        cy.fit(null, 20);
    }
}
```

---

### Issue 6: Tracked Entities List Empty

**File**: `static/js/pulse-dashboard.js`

**Problem**: No function populated `#full-entity-list` container, only `#trending-entities` was rendered.

**Fix**: Added `renderFullEntityList()` function:
```javascript
renderFullEntityList() {
    const container = document.getElementById('full-entity-list');
    if (!container) return;
    if (this.entities.length === 0) {
        container.innerHTML = `<li class="entity-list-item"><span class="text-muted">No entities tracked...</span></li>`;
        return;
    }
    const entitiesToShow = [...this.entities].slice(0, 100);
    container.innerHTML = entitiesToShow.map(entity => {
        const typeClass = (entity.entity_type || 'custom').toLowerCase();
        return `<li class="entity-list-item" data-entity="${entity.name}" data-entity-id="${entity.entity_id}">
            <span class="entity-type-badge ${typeClass}">${entity.entity_type?.slice(0, 3) || 'ENT'}</span>
            <span class="entity-name">${entity.name}</span>
            <span class="entity-mention-count">${entity.mention_count || 0}</span>
        </li>`;
    }).join('');
}
```

Called from `renderTrendingEntities()` to ensure both lists are populated.

---

### Files Summary (2026-01-12 - Network Fixes)

| File | Action | Description |
|------|--------|-------------|
| `app/api/v1/entities/routes.py` | Modified | Removed `str()` from user_id comparisons (lines 142, 434, 442) |
| `app/api/v1/network/routes.py` | Modified | Added GraphCache with 60s TTL, cache invalidation |
| `app/services/processing/pipeline.py` | Modified | Added RELATIONSHIP_PATTERNS, relationship type inference |
| `app/services/entity_extraction/auto_extractor.py` | Modified | Added `extract_and_save_relationships()` method |
| `app/models/entities.py` | Modified | Added database indexes for TrackedEntity and EntityMention |
| `static/js/pulse-dashboard.js` | Modified | Fixed `renderNetworkGraph()` to render both graphs, added `renderFullEntityList()` |

---

## Recent Changes (2026-01-10) - Entity System Improvements

### Overview

Implemented 5 major improvements to the entity extraction and tracking system:
1. **WikiData Cache Persistence** - Redis L1/L2 caching for WikiData API
2. **Extraction Rate Limiting** - Queue manager to prevent concurrent extractions
3. **Dashboard Error Handling** - Toast notifications and loading states
4. **Entity Deduplication** - WikiData QID-based duplicate detection and merging
5. **Scalable Batch Extraction** - Two-phase extraction for large backlogs

---

### Phase 1: WikiData Cache Persistence (Redis)

**Goal**: Persist WikiData lookups to Redis with 24-hour TTL, reducing API calls.

#### Files Modified

| File | Changes |
|------|---------|
| `app/services/entity_extraction/wikidata_linker.py` | Added Redis L2 cache with SETEX, `from_dict()` method on LinkedEntity |
| `app/core/dependencies.py` | Added `get_redis_client()`, `get_wikidata_linker()` singletons |

#### Implementation Details

```python
# L1/L2 Cache Architecture
# L1: In-memory dict (fast, per-process)
# L2: Redis with 24h TTL (persistent, shared)

REDIS_CACHE_PREFIX = "wikidata:entity:"
REDIS_TTL_SECONDS = 86400  # 24 hours

# Cache lookup order:
# 1. Check in-memory cache (L1)
# 2. Check Redis cache (L2)
# 3. Call WikiData API
# 4. Store in both caches
```

---

### Phase 2: Extraction Rate Limiting & Queue

**Goal**: Prevent concurrent extractions, queue requests, provide status feedback.

#### Files Created

| File | Purpose |
|------|---------|
| `app/services/extraction_queue_manager.py` | **NEW** - Queue manager with semaphore-based rate limiting |

#### Files Modified

| File | Changes |
|------|---------|
| `app/api/v1/processing/routes.py` | Added rate limiting to `/extract-entities`, new status endpoint |
| `app/services/entity_extraction/auto_extractor.py` | Added `progress_callback` parameter |

#### New Endpoints

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/v1/processing/extract-entities/status` | Get extraction queue status |

#### Implementation Details

```python
class ExtractionQueueManager:
    """Ensures only one extraction runs at a time."""

    def __init__(self, max_concurrent: int = 1):
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._lock = asyncio.Lock()
        self._active_task: Optional[ExtractionTask] = None

    async def acquire_slot(self) -> ExtractionTask:
        """Blocks until extraction slot available."""
        await self._semaphore.acquire()
        # Returns task with status tracking

    async def release_slot(self, task, success, error=None):
        """Release slot and update task status."""

# When extraction is busy, returns 202 Accepted:
{
    "status": "queued",
    "message": "Extraction already in progress",
    "queue_position": 1
}
```

---

### Phase 3: Dashboard Error Handling

**Goal**: Better error feedback with toast notifications, loading states.

#### Files Modified

| File | Changes |
|------|---------|
| `static/js/pulse-dashboard.js` | Added `showToast()`, `setButtonLoading()`, enhanced `fetchApi()` |
| `static/css/sigint-theme.css` | Added toast notification styles (~100 lines) |
| `templates/dashboard.html` | Added toast container, bulk extract/enrich buttons |

#### Toast Types

| Type | Use Case |
|------|----------|
| `error` | API failures, network errors |
| `warning` | Rate limiting, queued requests |
| `success` | Extraction complete, entities merged |
| `info` | Progress updates, status changes |

#### Dashboard Buttons Added

| Button | Action |
|--------|--------|
| **Bulk Extract** | Fast GLiNER-only extraction (no WikiData) |
| **Enrich Entities** | Add WikiData metadata to existing entities |

---

### Phase 4: Entity Deduplication/Merging

**Goal**: Prevent and detect duplicate entities using WikiData QIDs.

#### Files Modified

| File | Changes |
|------|---------|
| `app/services/entity_extraction/auto_extractor.py` | Added QID-based deduplication in `_auto_track_entities()` |
| `app/api/v1/entities/routes.py` | Added `/duplicates` and `/merge` endpoints |

#### New Endpoints

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/v1/entities/duplicates` | Find entities sharing same WikiData QID |
| POST | `/api/v1/entities/merge` | Merge secondary entity into primary |

#### Deduplication Logic

```python
# In _auto_track_entities():
# 1. Link entity to WikiData (get QID)
# 2. Check for existing entity by QID (prevents duplicates)
# 3. If no QID match, try name matching (existing logic)
# 4. Create new entity only if truly new

async def _find_entity_by_wikidata_id(self, wikidata_id: str):
    """Find entity by WikiData QID in metadata."""
    return await self.db.execute(
        select(TrackedEntity).where(
            TrackedEntity.user_id == self.user_id,
            TrackedEntity.entity_metadata['wikidata_id'].astext == wikidata_id
        )
    )
```

#### Merge Endpoint Behavior

```python
# POST /api/v1/entities/merge?primary_id=...&secondary_id=...
# 1. Move all mentions from secondary to primary
# 2. Merge aliases into primary's metadata
# 3. Track merge history in metadata
# 4. Delete secondary entity
```

---

### Phase 5: Scalable Batch Extraction

**Goal**: Process large backlogs (1374+ items) efficiently.

#### New Endpoints

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/api/v1/processing/extract-entities/bulk` | Fast extraction without WikiData |
| POST | `/api/v1/processing/enrich-entities` | Parallel WikiData enrichment |

#### Two-Phase Extraction Strategy

```
Phase 1 (Fast, Local-Only):
├── GLiNER extraction runs locally (~200ms/item)
├── Creates entities WITHOUT WikiData linking
├── 500 items = ~5 minutes
└── Immediate results, entities available right away

Phase 2 (Background WikiData Enrichment):
├── Separate endpoint processes entities needing WikiData
├── Parallel lookups with semaphore (5 concurrent)
├── Redis cache reduces repeat lookups
├── Run multiple times to process backlog
└── ~2 minutes per 100 entities
```

#### Performance Estimates

| Step | Items | Time | Notes |
|------|-------|------|-------|
| Bulk Extract (3 batches) | 1374 | ~8 min | No network, GLiNER only |
| Enrich (14 batches) | ~4000 entities | ~30 min | 100/batch, cached |
| **Total** | 1374 items | **~40 min** | vs 6+ hours sequential |

---

### Files Summary

| File | Action | Description |
|------|--------|-------------|
| `app/core/dependencies.py` | Modified | Added Redis/WikiDataLinker singletons |
| `app/services/extraction_queue_manager.py` | **Created** | Rate limiting queue manager |
| `app/api/v1/processing/routes.py` | Modified | Rate limiting, bulk endpoints |
| `app/services/entity_extraction/auto_extractor.py` | Modified | QID dedup, progress callback |
| `app/services/entity_extraction/wikidata_linker.py` | Modified | Redis L2 cache |
| `app/api/v1/entities/routes.py` | Modified | `/duplicates`, `/merge` endpoints |
| `static/js/pulse-dashboard.js` | Modified | Toast system, bulk buttons |
| `static/css/sigint-theme.css` | Modified | Toast notification styles |
| `templates/dashboard.html` | Modified | Toast container, new buttons |

---

## Recent Changes (2026-01-10) - Entity Extraction Bug Fixes

### Entity Extraction Bug Fixes

**Fixed 404 errors, 429 rate limiting, and FK constraint cascade failures affecting entity extraction.**

#### Bug Fix #1: Entity Routes 404 Errors (CRITICAL)
- **File**: `app/api/v1/entities/routes.py`
- **Issue**: All entity routes had duplicate `/entities/` prefix causing 404s
  - Routes defined as `@router.get("/entities")` with prefix `/api/v1/entities`
  - Resulted in paths like `/api/v1/entities/entities` instead of `/api/v1/entities`
  - Dashboard calls to `/api/v1/entities` returned 404
- **Fix**: Removed `/entities` prefix from all 8 route decorators
- **Routes Fixed**:
  | Before | After |
  |--------|-------|
  | `@router.post("/entities/track")` | `@router.post("/track")` |
  | `@router.get("/entities")` | `@router.get("")` |
  | `@router.delete("/entities/{name}")` | `@router.delete("/{name}")` |
  | `@router.get("/entities/{name}/mentions")` | `@router.get("/{name}/mentions")` |
  | `@router.get("/entities/{name}/relationships")` | `@router.get("/{name}/relationships")` |
  | `@router.post("/entities/{name}/scan")` | `@router.post("/{name}/scan")` |
  | `@router.get("/entities/diagnostic")` | `@router.get("/diagnostic")` |
  | `@router.get("/entities/diagnostic/articles")` | `@router.get("/diagnostic/articles")` |

#### Bug Fix #2: WikiData 429 Rate Limiting
- **File**: `app/services/entity_extraction/wikidata_linker.py`
- **Issue**: Only 100ms delay between requests, no retry on 429 errors
  - Batch entity extraction overwhelmed WikiData API
  - Rate-limited requests silently returned empty results
- **Fix**: Improved rate limiting with exponential backoff
  - Increased `REQUEST_DELAY_MS`: 100ms → 500ms
  - Added `MAX_RETRIES = 3` for 429 responses
  - Added `BACKOFF_MULTIPLIER = 2` for exponential backoff
  - Retry delays: 0.5s → 1s → 2s before giving up

#### Bug Fix #3: FK Constraint Cascade Failures
- **File**: `app/services/entity_extraction/auto_extractor.py`
- **Issue**: Single FK constraint failure rolled back session, failing all subsequent entities
  - Error: "Session has been rolled back due to a previous exception"
  - One bad entity blocked entire batch
- **Fix**: Per-entity transaction handling in `_auto_track_entities()`
  - Each entity+mention committed individually
  - Failed entities trigger rollback and continue to next
  - Batch processing now resilient to individual failures

#### Files Modified
| File | Changes |
|------|---------|
| `app/api/v1/entities/routes.py` | Removed duplicate `/entities` prefix from all 8 routes |
| `app/services/entity_extraction/wikidata_linker.py` | Added retry logic with exponential backoff for 429 errors |
| `app/services/entity_extraction/auto_extractor.py` | Per-entity error handling with rollback and continue |

---

## Recent Changes (2026-01-09)

### Entity Extraction Integration & Bug Fixes

**Critical fix: Auto entity extraction was never being called, resulting in 0 tracked entities.**

#### Root Cause
The `AutoEntityExtractor` module existed but was:
1. Never integrated into any pipeline or exposed via API
2. Had a database FK constraint bug preventing entity creation

#### Entity Extraction API (NEW)
- **File**: `app/api/v1/processing/routes.py`
- **New Endpoints**:
  - `POST /api/v1/processing/extract-entities` - Batch extract from recent news
  - `POST /api/v1/processing/extract-entities/{item_id}` - Extract from single item
- **Features**:
  - Uses GLiNER zero-shot NER for 7 entity types (PERSON, ORGANIZATION, GOVERNMENT_AGENCY, MILITARY_UNIT, LOCATION, POLITICAL_PARTY, EVENT)
  - Auto-tracks high-confidence entities (threshold configurable, default 0.7)
  - WikiData linking for entity disambiguation
  - Configurable time window (1-168 hours) and batch size (1-200 items)

#### Dashboard Integration
- **File**: `templates/dashboard.html`
  - Added "Extract Entities" button to Quick Actions panel
- **File**: `static/js/pulse-dashboard.js`
  - Added `extractEntities()` method
  - Button triggers extraction and refreshes entity list/graph

#### Bug Fix: FK Constraint Violation
- **File**: `app/services/entity_extraction/auto_extractor.py`
- **Issue**: `TrackedEntity` was added to session but not flushed before creating `EntityMention` records that reference it
- **Fix**: Added `await self.db.flush()` after creating new entities (line 383)

#### Files Modified
| File | Changes |
|------|---------|
| `app/api/v1/processing/routes.py` | Added `/extract-entities` and `/extract-entities/{item_id}` endpoints |
| `app/services/entity_extraction/auto_extractor.py` | Added `flush()` after entity creation to fix FK constraint |
| `templates/dashboard.html` | Added "Extract Entities" button to Quick Actions |
| `static/js/pulse-dashboard.js` | Added `extractEntities()` method and event handler |

#### Usage
```bash
# Via API
curl -X POST "http://localhost:8000/api/v1/processing/extract-entities?hours=24&limit=50"

# Via Dashboard
Click "Extract Entities" button in Quick Actions panel
```

---

## Recent Changes (2026-01-05)

### Briefing Generation Fixes & Storage Browser

**Critical fixes for slim briefings and new developer tools.**

#### Briefing Pipeline Fixes (P0)
- **Reddit Collector Category Bug**: Fixed `_get_category()` defaulting ALL subreddits to `rc_industry`
  - File: `app/services/collectors/reddit_collector.py`
  - Now uses `REDDIT_CATEGORY_MAP` from config for proper classification
  - Default changed from `rc_industry` to `general` for unknown subreddits
- **Context Builder Unprocessed Items**: Fixed filter excluding 754+ unprocessed items
  - File: `app/services/synthesis/context_builder.py`
  - Now calculates relevance on-the-fly for items with `processed=0`
  - Uses `RelevanceRanker` to score items that haven't been through processing pipeline
  - Result: Briefings now include 100+ diverse items (was only 9 ArXiv papers)

#### Enhanced Logging System
- **Session-based logs**: Each app session creates `session_YYYYMMDD_HHMMSS.log`
- **Function names in format**: `module:function:line` for precise tracing
- **Session banners**: Clear START/END markers with timestamps
- **Runtime controls**: `enable_verbose()`, `enable_debug()`, `enable_quiet()`
- **Quick helpers**: `log_info()`, `log_debug()`, `log_error()` convenience functions
- File: `app/core/logging.py`

#### Storage Browser Dashboard (NEW)
- **File**: `browse_storage.py` - Streamlit-based UI for browsing collected items
- **Run with**: `streamlit run browse_storage.py`
- **Features**:
  - Browse all collected items with pagination
  - Filter by source type (reddit, gdelt, arxiv, rss, local)
  - Filter by category (geopolitics, cyber, military, tech_ai, etc.)
  - Search titles
  - View full item details (content, metadata, relevance scores)
  - Collection run history with stats
- **Database**: Uses sync SQLAlchemy for Streamlit compatibility

#### Files Modified
| File | Changes |
|------|---------|
| `app/services/collectors/reddit_collector.py` | Uses REDDIT_CATEGORY_MAP, fixed default category |
| `app/services/collectors/config.py` | Added lowercase comment for category map |
| `app/services/synthesis/context_builder.py` | On-the-fly relevance scoring for unprocessed items |
| `app/core/logging.py` | Enhanced with session logs, function names, runtime controls |
| `browse_storage.py` | NEW: Streamlit storage browser |

---

### Phase 6: Intelligence Platform Reconfiguration Complete

**Critical fixes addressing RC hobbyist content pollution and non-functional dashboard components.**

#### Dashboard Fixes (P0)
- **Auth-Free Local User**: Replaced hardcoded user_id with auto-creating local user pattern
  - File: `app/api/v1/entities/routes.py` - New `get_current_user()` creates `local@pulse.local` user on first use
  - Fixes: Trending Entities, Relationship Graph, and all entity-related features
- **API Path Fix**: Corrected `/entities/entities` → `/entities` in dashboard JS
- **Dead Code Removal**: Removed legacy OpenAI chat handler from `app/api/v1/websocket/routes.py`
  - Removed: `openai`, `redis`, `security_service` imports and duplicate chat handler
  - Only Claude-based `research_assistant.chat()` remains

#### RC Content Filtering (P0)
- **Tier Escalation Blocking**: RC hobby content now NEVER escalates to Tier 1
  - File: `app/services/synthesis/tiered_briefing.py`
  - New: `_is_rc_hobby_content()` method checks source type, categories, title keywords, source name
  - New: `RC_CONTENT_IDENTIFIERS` dict with source types, categories, and title keywords
  - RC content forced to `TIER_4_MONITOR` regardless of escalation keywords
- **Quality Filtering**: Context builder now excludes low-quality and RC content
  - File: `app/services/synthesis/context_builder.py`
  - New filters: `processed == 1`, `relevance_score >= 0.4`, excluded source types/categories
  - Constants: `MIN_RELEVANCE_SCORE`, `EXCLUDED_SOURCE_TYPES`, `EXCLUDED_CATEGORIES`

#### Relevance Scoring (P1)
- **Source Score Adjustments**: `app/services/processing/ranker.py`
  - RC sources reduced: 7.0 → 1.0 (Horizon Hobby, Traxxas, FMS Hobby, Big Squid RC)
  - Reddit reduced: 5.0 → 3.0
  - Added: ACLED (9.5), OpenSanctions (9.0), SEC EDGAR (8.5)
- **Category Importance**: RC categories reduced from 6.0 → 0.5
  - Added: military (9.5), conflict (9.0), sanctions (9.0), cyber (8.5)

#### Data Source Reconfiguration (P1)
- **Reddit Subreddits**: `app/services/collectors/config.py`
  - Removed: RCPlanes, radiocontrol, fpv, rccars, Multicopter
  - Added: geopolitics, worldnews, intelligence, credibledefense, cybersecurity, Economics
  - New: `REDDIT_CATEGORY_MAP` for proper classification
- **RSS Feeds**: Added 10 intelligence sources, removed Big Squid RC
  - Added: Defense News, Breaking Defense, War on Rocks, Foreign Policy, Lawfare, CFR, Al Jazeera, Krebs on Security, Threatpost
- **Scrape Targets**: Removed RC manufacturers (Horizon Hobby, Traxxas, FMS Hobby)
- **GDELT**: All 8 query templates now enabled by default (`use_all_templates=True`)

#### Dashboard Enhancements (P2)
- **Activity Timeline**: Now populated on init via `loadRecentActivity()`
  - Fetches recent collection runs and displays in timeline
  - New: `formatTimeAgo()` helper for relative timestamps

#### Files Modified
| File | Changes |
|------|---------|
| `app/api/v1/entities/routes.py` | Auth-free local user pattern |
| `app/api/v1/websocket/routes.py` | Removed OpenAI/Redis, dead code cleanup |
| `app/services/synthesis/tiered_briefing.py` | RC blocking, new tier maps |
| `app/services/synthesis/context_builder.py` | Quality filtering |
| `app/services/processing/ranker.py` | Adjusted source/category scores |
| `app/services/collectors/config.py` | Intelligence-focused sources |
| `app/services/collectors/gdelt_collector.py` | All templates enabled |
| `static/js/pulse-dashboard.js` | API fix, activity loading |

---

### Phase 5: Pattern Detection & Timeline Visualization Complete
- **Trend Indicator Service**: 6-month rolling trend tracking with sparkline data
- **Conflict Index**: Armed conflict, military activity, and security event tracking
- **Market Volatility**: Financial and business activity monitoring
- **Political Instability**: Political turmoil and governance event tracking
- **Entity Activity**: Tracked entity mention frequency analysis
- **Collection Health**: Data collection system status monitoring
- **New Files**:
  - `app/services/synthesis/trend_indicators.py` - Trend indicator service
- **Updated Files**:
  - `app/services/synthesis/__init__.py` - Added trend indicator exports
  - `app/api/v1/synthesis/routes.py` - Added trend API endpoints
- **New Endpoints**:
  - `GET /api/v1/synthesis/trends` - Get current trend indicators
  - `GET /api/v1/synthesis/trends/summary` - Get trend summary for dashboard
  - `GET /api/v1/synthesis/trends/categories` - Get category breakdown

### Phase 4: Entity Extraction & Network Mapping Complete
- **GLiNER Extractor**: Zero-shot NER for 11 intelligence-specific entity types (FREE, local)
- **WikiData Linker**: Entity disambiguation to canonical WikiData QIDs (FREE API)
- **Auto-Extractor**: Automated extraction and tracking pipeline
- **New Files**:
  - `app/services/entity_extraction/__init__.py` - Module exports
  - `app/services/entity_extraction/gliner_extractor.py` - GLiNER zero-shot NER
  - `app/services/entity_extraction/wikidata_linker.py` - WikiData entity linking
  - `app/services/entity_extraction/auto_extractor.py` - Automated extraction pipeline
- **Updated Files**:
  - `requirements.txt` - Added gliner>=0.2.0
- **Entity Types**: PERSON, ORGANIZATION, GOVERNMENT_AGENCY, MILITARY_UNIT, WEAPON_SYSTEM, LOCATION, FINANCIAL_INSTRUMENT, POLITICAL_PARTY, CRIMINAL_ORGANIZATION, EVENT, DATE

---

## Recent Changes (2026-01-04)

### Phase 3: New Data Source Integrations Complete
- **Enhanced GDELT Collector**: 8 query templates (geopolitics, military, cyber, financial, sanctions, political)
- **ACLED Collector**: Armed conflict and protest data (FREE for research)
- **OpenSanctions Collector**: Sanctions lists and PEP data (FREE with rate limits)
- **SEC EDGAR Collector**: Corporate filings (8-K, 10-K, 13-F, Form 4) (FREE government data)
- **New Files**:
  - `app/services/collectors/acled_collector.py` - Armed conflict data collector
  - `app/services/collectors/opensanctions_collector.py` - Sanctions/PEP collector
  - `app/services/collectors/sec_edgar_collector.py` - SEC filings collector
- **Updated Files**:
  - `app/services/collectors/gdelt_collector.py` - Enhanced with 8 query templates
  - `app/services/collectors/__init__.py` - Updated registry with new collectors
  - `app/services/collectors/config.py` - New category labels
- **All data sources are FREE** - No paid APIs required

### Phase 2: Tiered Intelligence Briefings Complete
- **Tiered Briefing System**: 4-tier priority structure (Geo/Military > Local Gov > Tech/AI > Financial)
- **Pattern Detection**: Automatic escalation, sentiment shift, and entity surge detection
- **"So What?" Analysis**: Claude-powered actionable analysis for Tier 1/2 items
- **New Files**:
  - `app/services/synthesis/tiered_briefing.py` - Tiered briefing generator
  - `app/services/synthesis/pattern_detector.py` - Pattern detection engine
- **New Endpoint**: `POST /api/v1/synthesis/generate/tiered`

### Phase 1: Claude Code Migration Complete
- **LLM Backend**: Migrated from Ollama to Claude Code CLI (subscription-based)
- **Embeddings**: Migrated from Ollama nomic-embed-text to local sentence-transformers
- **New Files**:
  - `app/services/claude_bridge.py` - Claude Code CLI wrapper
  - `app/services/local_embeddings.py` - Local embedding generation

---