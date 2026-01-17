# Atomic Implementation Plan: Server-Side Network API Optimization

**Created:** 2026-01-16
**Parent Document:** [ATOMIC_network-graph-performance-optimization_2026-01-16.md](./ATOMIC_network-graph-performance-optimization_2026-01-16.md)
**Status:** IMPLEMENTED - All 9 features complete

## Implementation Progress (2026-01-16 - Final)

| Feature | Status | Notes |
|---------|--------|-------|
| **SERV-000** | DONE | Timing instrumentation in `_timings` response field |
| **SERV-001** | DONE | Fixed double layout computation bug |
| **SERV-002** | DONE | Layout cache with 5-min TTL |
| **SERV-003** | DONE | Cluster cache with 10-min TTL |
| **SERV-004** | DONE | Cache invalidation on relationship changes |
| **SERV-005** | DONE | Dynamic iterations (30/50/100 based on size) |
| **SERV-006** | DONE | Label Propagation for graphs >1000 nodes |
| **SERV-007** | DONE | Graph cache TTL extended to 5 minutes |
| **SERV-008** | DONE | `/cache/status` and `/cache/invalidate` endpoints |
| **SERV-009** | DONE | Skip server layout for graphs >500 nodes (client FA2 handles it) |
| **CLIENT-FIX** | DONE | Fixed double API call in `switchView()` |

### Measured Performance (Final)

```
Before:  54,473ms total
After:   698ms total (77x faster!)

Breakdown:
⚡ graph_load_ms: 290ms
⚡ export_cytoscape_ms: 191ms
⚡ compute_layout_ms: 0 (skipped - client FA2 handles)
⚡ compute_clusters_ms: 118ms
⚡ total_ms: 698ms
```

---

---

## Overview

This spec addresses the **server-side bottleneck** discovered after completing client-side performance optimizations. The `/api/v1/network/graph` endpoint currently takes **54+ seconds** to respond, making the Network view unusable despite fast client-side rendering.

**Measured Performance (from parent spec):**

```
⚡ API fetch: 54473ms      ← THIS SPEC'S TARGET
⚡ Graph build: 32ms       ← Already fast (client)
⚡ Layout: 5017ms          ← Already fast (client async)
⚡ Render total: 5055ms    ← Already fast (client)
```

**Target:** Reduce API response time from 54s to < 2s for cached responses, < 5s for cold cache.

---

## Root Cause Analysis

### Code Locations

| File | Lines | Issue |
|------|-------|-------|
| `app/api/v1/network/routes.py` | 132-184 | `/graph` endpoint orchestration |
| `app/api/v1/network/routes.py` | 156 + 173 | **Double layout computation** |
| `app/services/network_mapper/graph_service.py` | 729-800 | `compute_layout()` - O(n²) |
| `app/services/network_mapper/graph_service.py` | 802-866 | `get_clusters_for_visualization()` |
| `app/api/v1/network/routes.py` | 29-88 | `GraphCache` - 60s TTL only |

### Identified Bottlenecks

#### 1. Double Layout Computation (Critical Bug)

When both `include_positions=True` AND `include_clusters=True`:

```python
# Line 156 - First layout call
if include_positions:
    positions = mapper.compute_layout(algorithm=layout)
    # ... apply positions to nodes ...

# Line 173 - SECOND layout call (identical!)
if include_clusters:
    clusters = mapper.get_clusters_for_visualization(min_size=3)
    if include_positions and clusters:
        positions = mapper.compute_layout(algorithm=layout)  # DUPLICATE!
```

This runs `spring_layout()` with 100 iterations TWICE on 2215 nodes.

#### 2. Expensive Layout Algorithm

`compute_layout()` uses NetworkX `spring_layout()`:
- 100 iterations (line 770)
- O(n²) per iteration for force calculations
- For 2215 nodes: ~4.9M force calculations × 100 = **490M operations**

#### 3. Community Detection Per-Request

`get_clusters_for_visualization()` runs `greedy_modularity_communities()`:
- Algorithm: O(n log² n) for sparse graphs
- For each cluster, also runs `nx.degree_centrality()` on subgraph
- **Not cached** - computed fresh on every request

#### 4. Insufficient Caching

Current `GraphCache`:
- Only caches the loaded NetworkMapperService (graph structure)
- TTL: 60 seconds (too short for stable data)
- Does NOT cache:
  - Layout positions (most expensive)
  - Cluster data (second most expensive)
  - Cytoscape export format

---

## Implementation Plan

### Phase 0: Instrumentation

#### SERV-000: Server-Side Timing

**Priority:** P0 (Prerequisite)
**Estimated Time:** 0.5 hours
**Dependencies:** None

Add timing instrumentation to identify exact bottleneck durations.

**File:** `app/api/v1/network/routes.py`

**Implementation:**

```python
import time

@router.get("/graph")
async def get_full_graph(
    include_isolated: bool = Query(False),
    include_positions: bool = Query(True),
    layout: str = Query("spring"),
    include_clusters: bool = Query(False),
    db=Depends(get_db),
    current_user: LocalUser = Depends(get_local_user)
):
    timings = {}
    total_start = time.perf_counter()

    # SERV-000: Time graph loading
    t0 = time.perf_counter()
    mapper = await _graph_cache.get_mapper(db, user_id=current_user.user_id)
    timings["graph_load"] = (time.perf_counter() - t0) * 1000

    # SERV-000: Time export
    t0 = time.perf_counter()
    elements = mapper.export_cytoscape(include_isolated=include_isolated)
    timings["export_cytoscape"] = (time.perf_counter() - t0) * 1000

    # SERV-000: Time layout
    if include_positions:
        t0 = time.perf_counter()
        positions = mapper.compute_layout(algorithm=layout)
        timings["compute_layout"] = (time.perf_counter() - t0) * 1000
        for node in elements["nodes"]:
            node_id = node["data"]["id"]
            if node_id in positions:
                x, y = positions[node_id]
                node["position"] = {"x": x, "y": y}

    response = {
        "elements": elements,
        "stats": mapper.get_graph_stats()
    }

    # SERV-000: Time clustering
    if include_clusters:
        t0 = time.perf_counter()
        clusters = mapper.get_clusters_for_visualization(min_size=3)
        timings["compute_clusters"] = (time.perf_counter() - t0) * 1000

        # Use already-computed positions for centroids (FIX for double layout)
        if include_positions and clusters and positions:
            for cluster in clusters:
                member_positions = [
                    positions[m] for m in cluster["members"] if m in positions
                ]
                if member_positions:
                    cx = sum(p[0] for p in member_positions) / len(member_positions)
                    cy = sum(p[1] for p in member_positions) / len(member_positions)
                    cluster["position"] = {"x": cx, "y": cy}
        response["clusters"] = clusters

    timings["total"] = (time.perf_counter() - total_start) * 1000

    # Log timing breakdown
    logger.info(f"Network graph API timings: {timings}")

    # Include timings in response (dev mode)
    response["_timings"] = timings

    return response
```

**Acceptance Criteria:**
- [ ] Server logs show timing breakdown for each phase
- [ ] Response includes `_timings` object with ms values
- [ ] Can identify which phase takes the most time

---

### Phase 1: Critical Bug Fixes

#### SERV-001: Fix Double Layout Computation

**Priority:** P0
**Estimated Time:** 0.5 hours
**Dependencies:** SERV-000

The code currently calls `compute_layout()` twice when both positions and clusters are requested. This is already fixed in SERV-000's implementation above - we reuse the `positions` variable.

**Current (Broken):**
```python
# Line 156
positions = mapper.compute_layout(algorithm=layout)

# Line 173 - CALLS IT AGAIN!
positions = mapper.compute_layout(algorithm=layout)
```

**Fixed:**
```python
# Compute once
positions = mapper.compute_layout(algorithm=layout) if include_positions else {}

# Reuse for cluster centroids
if include_clusters and positions:
    for cluster in clusters:
        # Use existing positions dict
```

**Acceptance Criteria:**
- [ ] `compute_layout()` called exactly ONCE per request
- [ ] Cluster centroids still computed correctly
- [ ] Response time reduced by ~50% for requests with both flags

---

### Phase 2: Caching Layer

#### SERV-002: Layout Position Cache

**Priority:** P0
**Estimated Time:** 1.5 hours
**Dependencies:** SERV-001

Layout positions are deterministic (we use `seed=42`). Cache them separately with longer TTL.

**File:** `app/api/v1/network/routes.py`

**Implementation:**

```python
class LayoutCache:
    """Cache for computed layout positions with longer TTL."""

    def __init__(self, ttl_seconds: int = 300):  # 5 minute TTL
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._ttl = timedelta(seconds=ttl_seconds)
        self._lock = asyncio.Lock()

    def _cache_key(self, user_id: UUID, algorithm: str, node_count: int) -> str:
        """Cache key includes algorithm and node count for invalidation."""
        return f"{user_id}:{algorithm}:{node_count}"

    async def get_positions(
        self,
        user_id: UUID,
        algorithm: str,
        node_count: int
    ) -> Optional[Dict[str, Tuple[float, float]]]:
        """Get cached positions if valid."""
        key = self._cache_key(user_id, algorithm, node_count)
        now = datetime.now(timezone.utc)

        async with self._lock:
            if key in self._cache:
                entry = self._cache[key]
                if now - entry["computed_at"] < self._ttl:
                    logger.debug(f"Layout cache hit for {key}")
                    return entry["positions"]
                else:
                    logger.debug(f"Layout cache expired for {key}")
                    del self._cache[key]
        return None

    async def set_positions(
        self,
        user_id: UUID,
        algorithm: str,
        node_count: int,
        positions: Dict[str, Tuple[float, float]]
    ):
        """Store computed positions in cache."""
        key = self._cache_key(user_id, algorithm, node_count)
        async with self._lock:
            self._cache[key] = {
                "positions": positions,
                "computed_at": datetime.now(timezone.utc)
            }
            logger.info(f"Cached layout positions for {key} ({len(positions)} nodes)")

    async def invalidate(self, user_id: Optional[UUID] = None):
        """Invalidate cache for a user or all users."""
        async with self._lock:
            if user_id:
                keys_to_delete = [k for k in self._cache if k.startswith(str(user_id))]
                for key in keys_to_delete:
                    del self._cache[key]
            else:
                self._cache.clear()


# Global layout cache with 5-minute TTL
_layout_cache = LayoutCache(ttl_seconds=300)
```

**Update `/graph` endpoint:**

```python
@router.get("/graph")
async def get_full_graph(...):
    # ... existing code ...

    positions = {}
    if include_positions:
        node_count = mapper.graph.number_of_nodes()

        # SERV-002: Check layout cache first
        positions = await _layout_cache.get_positions(
            current_user.user_id, layout, node_count
        )

        if positions is None:
            t0 = time.perf_counter()
            positions = mapper.compute_layout(algorithm=layout)
            timings["compute_layout"] = (time.perf_counter() - t0) * 1000
            timings["layout_cache"] = "miss"

            # Store in cache
            await _layout_cache.set_positions(
                current_user.user_id, layout, node_count, positions
            )
        else:
            timings["layout_cache"] = "hit"
            timings["compute_layout"] = 0

        # Apply positions to nodes
        for node in elements["nodes"]:
            node_id = node["data"]["id"]
            if node_id in positions:
                x, y = positions[node_id]
                node["position"] = {"x": x, "y": y}
```

**Acceptance Criteria:**
- [ ] First request computes layout (shows `layout_cache: "miss"`)
- [ ] Subsequent requests within 5 min use cache (shows `layout_cache: "hit"`)
- [ ] Cached response time < 1 second
- [ ] Cache invalidated when relationships change
- [ ] Different algorithms cached separately

---

#### SERV-003: Cluster Data Cache

**Priority:** P1
**Estimated Time:** 1 hour
**Dependencies:** SERV-002

Community detection is expensive and clusters don't change unless entities/relationships are added.

**File:** `app/api/v1/network/routes.py`

**Implementation:**

```python
class ClusterCache:
    """Cache for computed cluster data with longer TTL."""

    def __init__(self, ttl_seconds: int = 600):  # 10 minute TTL
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._ttl = timedelta(seconds=ttl_seconds)
        self._lock = asyncio.Lock()

    def _cache_key(self, user_id: UUID, min_size: int, node_count: int) -> str:
        return f"{user_id}:clusters:{min_size}:{node_count}"

    async def get_clusters(
        self,
        user_id: UUID,
        min_size: int,
        node_count: int
    ) -> Optional[List[Dict]]:
        """Get cached clusters if valid."""
        key = self._cache_key(user_id, min_size, node_count)
        now = datetime.now(timezone.utc)

        async with self._lock:
            if key in self._cache:
                entry = self._cache[key]
                if now - entry["computed_at"] < self._ttl:
                    logger.debug(f"Cluster cache hit for {key}")
                    return entry["clusters"]
                else:
                    del self._cache[key]
        return None

    async def set_clusters(
        self,
        user_id: UUID,
        min_size: int,
        node_count: int,
        clusters: List[Dict]
    ):
        """Store computed clusters in cache."""
        key = self._cache_key(user_id, min_size, node_count)
        async with self._lock:
            self._cache[key] = {
                "clusters": clusters,
                "computed_at": datetime.now(timezone.utc)
            }
            logger.info(f"Cached {len(clusters)} clusters for {key}")

    async def invalidate(self, user_id: Optional[UUID] = None):
        """Invalidate cache for a user or all users."""
        async with self._lock:
            if user_id:
                keys_to_delete = [k for k in self._cache if k.startswith(str(user_id))]
                for key in keys_to_delete:
                    del self._cache[key]
            else:
                self._cache.clear()


# Global cluster cache with 10-minute TTL
_cluster_cache = ClusterCache(ttl_seconds=600)
```

**Update `/graph` endpoint to use cluster cache:**

```python
if include_clusters:
    node_count = mapper.graph.number_of_nodes()

    # SERV-003: Check cluster cache first
    clusters = await _cluster_cache.get_clusters(
        current_user.user_id, 3, node_count  # min_size=3
    )

    if clusters is None:
        t0 = time.perf_counter()
        clusters = mapper.get_clusters_for_visualization(min_size=3)
        timings["compute_clusters"] = (time.perf_counter() - t0) * 1000
        timings["cluster_cache"] = "miss"

        await _cluster_cache.set_clusters(
            current_user.user_id, 3, node_count, clusters
        )
    else:
        timings["cluster_cache"] = "hit"
        timings["compute_clusters"] = 0

    # Add cluster centroids using cached positions
    if positions and clusters:
        for cluster in clusters:
            member_positions = [
                positions[m] for m in cluster["members"] if m in positions
            ]
            if member_positions:
                cx = sum(p[0] for p in member_positions) / len(member_positions)
                cy = sum(p[1] for p in member_positions) / len(member_positions)
                cluster["position"] = {"x": cx, "y": cy}

    response["clusters"] = clusters
```

**Acceptance Criteria:**
- [ ] Cluster computation cached for 10 minutes
- [ ] Cache key includes node count for automatic invalidation
- [ ] Response includes `cluster_cache: "hit"` or `"miss"`
- [ ] Invalidated when entities/relationships change

---

#### SERV-004: Cache Invalidation on Data Changes

**Priority:** P1
**Estimated Time:** 0.5 hours
**Dependencies:** SERV-002, SERV-003

Ensure caches are invalidated when data changes.

**Update existing invalidation points in `routes.py`:**

```python
@router.post("/relationships")
async def add_relationship(...):
    # ... existing code ...

    # Invalidate ALL caches since relationships changed
    await _graph_cache.invalidate(current_user.user_id)
    await _layout_cache.invalidate(current_user.user_id)  # SERV-004
    await _cluster_cache.invalidate(current_user.user_id)  # SERV-004

    return {...}


@router.post("/discover")
async def discover_relationships(...):
    # ... existing code ...

    if relationships:
        await _graph_cache.invalidate(current_user.user_id)
        await _layout_cache.invalidate(current_user.user_id)  # SERV-004
        await _cluster_cache.invalidate(current_user.user_id)  # SERV-004

    return {...}


@router.post("/discover/full")
async def run_full_discovery(...):
    # ... existing code ...

    if results.get("relationships_found", 0) > 0:
        await _graph_cache.invalidate(current_user.user_id)
        await _layout_cache.invalidate(current_user.user_id)  # SERV-004
        await _cluster_cache.invalidate(current_user.user_id)  # SERV-004

    return results
```

**Acceptance Criteria:**
- [ ] Adding a relationship invalidates all caches
- [ ] Running discovery invalidates all caches
- [ ] Next graph request recomputes everything fresh

---

### Phase 3: Algorithm Optimization

#### SERV-005: Reduce Layout Iterations for Large Graphs

**Priority:** P1
**Estimated Time:** 0.5 hours
**Dependencies:** SERV-002

For large graphs (>1000 nodes), reduce iteration count. Quality tradeoff is acceptable since client does async refinement.

**File:** `app/services/network_mapper/graph_service.py`

**Update `compute_layout()`:**

```python
def compute_layout(
    self,
    algorithm: str = "spring",
    scale: float = 1000.0
) -> Dict[str, Tuple[float, float]]:
    """
    Compute node positions server-side using NetworkX layouts.
    """
    from math import sqrt

    if len(self.graph) == 0:
        return {}

    node_count = len(self.graph)

    # SERV-005: Dynamic iteration count based on graph size
    # Fewer iterations for large graphs (client refines with FA2 anyway)
    if node_count > 2000:
        iterations = 30  # Large graph: quick approximation
    elif node_count > 1000:
        iterations = 50  # Medium graph
    else:
        iterations = 100  # Small graph: full quality

    effective_scale = scale + (node_count * 3)

    if algorithm == "spring":
        k = 3 / sqrt(node_count) if node_count > 1 else 1
        pos = nx.spring_layout(
            self.graph,
            k=k,
            iterations=iterations,  # SERV-005: Dynamic
            seed=42
        )
    # ... rest of method unchanged
```

**Acceptance Criteria:**
- [ ] Graphs > 2000 nodes use 30 iterations
- [ ] Graphs > 1000 nodes use 50 iterations
- [ ] Layout computation time reduced by ~60% for large graphs
- [ ] Visual quality still acceptable (client FA2 refines)

---

#### SERV-006: Faster Community Detection

**Priority:** P2
**Estimated Time:** 1 hour
**Dependencies:** SERV-003

Use faster Label Propagation for initial clustering, fall back to Louvain only if needed.

**File:** `app/services/network_mapper/graph_service.py`

**Update `get_clusters_for_visualization()`:**

```python
def get_clusters_for_visualization(self, min_size: int = 3) -> List[Dict]:
    """
    Get clusters with aggregate data for super-node rendering.

    SERV-006: Uses Label Propagation (O(n)) for large graphs instead of
    greedy modularity (O(n log² n)).
    """
    if len(self.graph) == 0:
        return []

    undirected = self.graph.to_undirected()
    node_count = len(self.graph)

    try:
        # SERV-006: Use faster algorithm for large graphs
        if node_count > 1000:
            # Label Propagation: O(n) - much faster for large graphs
            from networkx.algorithms.community import label_propagation_communities
            communities = list(label_propagation_communities(undirected))
            logger.info(f"Used label_propagation for {node_count} nodes")
        else:
            # Greedy modularity: O(n log² n) - better quality for small graphs
            from networkx.algorithms.community import greedy_modularity_communities
            communities = list(greedy_modularity_communities(undirected))
            logger.info(f"Used greedy_modularity for {node_count} nodes")

    except Exception as e:
        logger.warning(f"Community detection failed: {e}")
        return []

    # ... rest of method unchanged (cluster building)
```

**Acceptance Criteria:**
- [ ] Graphs > 1000 nodes use Label Propagation
- [ ] Smaller graphs still use Greedy Modularity (better quality)
- [ ] Cluster computation time reduced by ~80% for large graphs
- [ ] Clusters still meaningful (entities grouped by relationships)

---

### Phase 4: Response Optimization

#### SERV-007: Extend Graph Cache TTL

**Priority:** P1
**Estimated Time:** 0.25 hours
**Dependencies:** None

The current 60-second TTL causes unnecessary database reloads. Entities don't change that frequently.

**File:** `app/api/v1/network/routes.py`

**Change:**

```python
# Current (line 88)
_graph_cache = GraphCache(ttl_seconds=60)

# Updated
_graph_cache = GraphCache(ttl_seconds=300)  # 5 minutes
```

**Acceptance Criteria:**
- [ ] Graph structure cached for 5 minutes
- [ ] Database load only happens every 5 minutes (or on invalidation)
- [ ] No stale data issues (invalidation still works)

---

#### SERV-008: Add Cache Status Endpoint

**Priority:** P2
**Estimated Time:** 0.5 hours
**Dependencies:** SERV-002, SERV-003

Add endpoint to monitor cache status for debugging.

**File:** `app/api/v1/network/routes.py`

**Implementation:**

```python
@router.get("/cache/status")
async def get_cache_status(
    current_user: LocalUser = Depends(get_local_user)
):
    """Get cache status for debugging."""
    user_id = str(current_user.user_id)

    graph_entries = [k for k in _graph_cache._cache if user_id in k]
    layout_entries = [k for k in _layout_cache._cache if user_id in k]
    cluster_entries = [k for k in _cluster_cache._cache if user_id in k]

    return {
        "graph_cache": {
            "entries": len(graph_entries),
            "ttl_seconds": 300
        },
        "layout_cache": {
            "entries": len(layout_entries),
            "ttl_seconds": 300
        },
        "cluster_cache": {
            "entries": len(cluster_entries),
            "ttl_seconds": 600
        }
    }


@router.post("/cache/invalidate")
async def invalidate_caches(
    current_user: LocalUser = Depends(get_local_user)
):
    """Manually invalidate all caches for current user."""
    await _graph_cache.invalidate(current_user.user_id)
    await _layout_cache.invalidate(current_user.user_id)
    await _cluster_cache.invalidate(current_user.user_id)

    return {"status": "invalidated", "user_id": str(current_user.user_id)}
```

**Acceptance Criteria:**
- [ ] `/api/v1/network/cache/status` returns cache state
- [ ] `/api/v1/network/cache/invalidate` clears all caches
- [ ] Useful for debugging cache issues

---

## Dependency Graph

```
                    ┌─────────────────────────────────────────────┐
                    │           PHASE 0: INSTRUMENTATION          │
                    │                                             │
                    │  SERV-000: Server-Side Timing (0.5 hrs)     │
                    └─────────────────────┬───────────────────────┘
                                          │
                                          ▼
                    ┌─────────────────────────────────────────────┐
                    │           PHASE 1: BUG FIXES                │
                    │                                             │
                    │  SERV-001: Fix Double Layout (0.5 hrs)      │
                    └─────────────────────┬───────────────────────┘
                                          │
        ┌─────────────────────────────────┼─────────────────────────────────┐
        │                                 │                                 │
        ▼                                 ▼                                 ▼
┌───────────────────┐          ┌───────────────────┐          ┌───────────────────┐
│   SERV-002        │          │   SERV-007        │          │   SERV-005        │
│   Layout Cache    │          │   Extend Graph    │          │   Reduce Layout   │
│   (1.5 hrs)       │          │   Cache TTL       │          │   Iterations      │
│                   │          │   (0.25 hrs)      │          │   (0.5 hrs)       │
└─────────┬─────────┘          └───────────────────┘          └───────────────────┘
          │
          ▼
┌───────────────────┐
│   SERV-003        │
│   Cluster Cache   │
│   (1 hr)          │
└─────────┬─────────┘
          │
          ├─────────────────────────────────┐
          │                                 │
          ▼                                 ▼
┌───────────────────┐          ┌───────────────────┐
│   SERV-004        │          │   SERV-006        │
│   Cache Invalidate│          │   Faster Clusters │
│   (0.5 hrs)       │          │   (1 hr)          │
└───────────────────┘          └───────────────────┘
                                          │
                                          ▼
                               ┌───────────────────┐
                               │   SERV-008        │
                               │   Cache Status    │
                               │   Endpoint        │
                               │   (0.5 hrs)       │
                               └───────────────────┘
```

---

## Summary

| Metric | Value |
|--------|-------|
| **Total Features** | 9 |
| **Total Estimated Time** | 6.75 hours |
| **Phases** | 5 (0-4) |
| **Files to Modify** | 2 primary |
| **Critical Path** | SERV-000 → SERV-001 → SERV-002 → SERV-003 |

### Implementation Order

| Order | ID | Name | Time | Cumulative |
|-------|-------|------|------|------------|
| 1 | SERV-000 | Server Timing | 0.5 hrs | 0.5 hrs |
| 2 | SERV-001 | Fix Double Layout | 0.5 hrs | 1.0 hrs |
| 3 | SERV-007 | Extend Graph TTL | 0.25 hrs | 1.25 hrs |
| 4 | SERV-002 | Layout Cache | 1.5 hrs | 2.75 hrs |
| 5 | SERV-003 | Cluster Cache | 1.0 hrs | 3.75 hrs |
| 6 | SERV-004 | Cache Invalidation | 0.5 hrs | 4.25 hrs |
| 7 | SERV-005 | Reduce Iterations | 0.5 hrs | 4.75 hrs |
| 8 | SERV-006 | Faster Clusters | 1.0 hrs | 5.75 hrs |
| 9 | SERV-008 | Cache Status | 0.5 hrs | 6.25 hrs |

### Expected Performance Improvement

| Scenario | Before | After (Cold) | After (Warm) |
|----------|--------|--------------|--------------|
| Full graph load | 54+ sec | < 5 sec | < 1 sec |
| With clusters | 54+ sec | < 6 sec | < 1 sec |
| Page reload | 54+ sec | < 1 sec | < 1 sec |
| After data change | 54+ sec | < 5 sec | - |

---

## Testing Strategy

### Manual Testing Checklist

```markdown
## SERV-000: Timing Instrumentation
- [ ] Response includes `_timings` object
- [ ] Server logs show timing breakdown
- [ ] Can identify slowest phase

## SERV-001: Double Layout Fix
- [ ] Only one "compute_layout" entry in timings
- [ ] Cluster centroids still computed correctly

## SERV-002: Layout Cache
- [ ] First request: `layout_cache: "miss"`
- [ ] Second request: `layout_cache: "hit"`, `compute_layout: 0`
- [ ] After 5 minutes: cache expires, recomputes

## SERV-003: Cluster Cache
- [ ] First request: `cluster_cache: "miss"`
- [ ] Second request: `cluster_cache: "hit"`, `compute_clusters: 0`

## SERV-004: Cache Invalidation
- [ ] Adding relationship invalidates caches
- [ ] Next request shows cache miss

## End-to-End
- [ ] Cold start: < 5 seconds
- [ ] Warm cache: < 1 second
- [ ] UI responsive during load
```

### Automated Validation

```bash
# Time cold start
time curl -s "http://localhost:8000/api/v1/network/graph?include_positions=true&include_clusters=true" | jq '._timings'

# Wait for cache warm
sleep 1

# Time warm cache
time curl -s "http://localhost:8000/api/v1/network/graph?include_positions=true&include_clusters=true" | jq '._timings'

# Check cache status
curl -s "http://localhost:8000/api/v1/network/cache/status" | jq
```

---

## Open Questions

- [ ] Should layout positions be persisted to database for cross-session stability?
- [ ] Should we add Redis caching for multi-instance deployments?
- [ ] Is Label Propagation quality acceptable for the UI? (may need tuning)
- [ ] Should there be a manual "recompute layout" button in the UI?

---

## User Feedback (2026-01-16)

**Issue:** Graph is fast but still unreadable at 1000+ nodes/5800+ edges.

**Related Specs:**
- [ATOMIC_phase4-semantic-zoom_entity-graph-visualization_2026-01-16.md](./ATOMIC_phase4-semantic-zoom_entity-graph-visualization_2026-01-16.md) - Cluster super-nodes for overview mode
- [entity-visualization-overhaul-2025-01-15.md](./entity-visualization-overhaul-2025-01-15.md) - Progressive disclosure

**Recommendation:** Test semantic zoom (zoom out far, should see clusters instead of individual nodes). If not working, debug `applyOverviewMode()` in pulse-dashboard.js.

---

## Sources

- Parent Spec: [ATOMIC_network-graph-performance-optimization_2026-01-16.md](./ATOMIC_network-graph-performance-optimization_2026-01-16.md)
- NetworkX Layout Algorithms: https://networkx.org/documentation/stable/reference/drawing.html
- NetworkX Community Detection: https://networkx.org/documentation/stable/reference/algorithms/community.html
- Label Propagation: O(m) time complexity for sparse graphs

---

*Generated: 2026-01-16*
*Session: Server-Side Network API Optimization*
