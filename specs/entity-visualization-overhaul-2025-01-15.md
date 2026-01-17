# Entity Visualization Overhaul Specification

**Created:** 2025-01-15
**Status:** Draft - Pending Approval
**Estimated Effort:** 3 phases over 2-4 weeks

---

## Problem Statement

The current entity visualization in The Pulse has three critical issues:

1. **Container too small**: The graph container is fixed at 300px height, making exploration impossible
2. **Performance/Latency**: The `/network/graph` endpoint loads ALL entities and relationships at once
3. **Wasted space**: Tracked Entities list occupies half the viewport on the same page as the graph

### Current State Evidence

```css
/* static/css/sigint-theme.css:818 */
.entity-graph-container {
    height: 300px;  /* FAR too small */
}
```

```javascript
/* static/js/pulse-dashboard.js:1448 */
async loadNetworkGraph() {
    const response = await this.fetchApi('/network/graph');  // Loads EVERYTHING
    this.renderNetworkGraph(response.elements);
}
```

---

## Solution Overview

### Three-Phase Approach

| Phase | Focus | Deliverable |
|-------|-------|-------------|
| **Phase 1** | Immediate UX fixes | Full-height graph, separate entity list page |
| **Phase 2** | Progressive disclosure | Search-to-focus, expand-on-click, pagination |
| **Phase 3** | Performance migration | Sigma.js + graphology, server-side layout |

---

## Phase 1: Immediate UX Fixes

**Goal:** Make the graph usable without changing the visualization library.

### 1.1 Expand Graph Container

**File:** `static/css/sigint-theme.css`

Change `.entity-graph-container` from 300px to dynamic height:

```css
.entity-graph-container {
    width: 100%;
    height: calc(100vh - 180px);  /* Full viewport minus header */
    min-height: 500px;
    background: var(--bg-primary);
    border: 1px solid var(--border-color);
    border-radius: 4px;
    position: relative;
}
```

### 1.2 Add Full-Screen Graph Modal

**Files:**
- `templates/dashboard.html` - Add modal HTML
- `static/css/sigint-theme.css` - Modal styles
- `static/js/pulse-dashboard.js` - Toggle logic

**HTML structure:**
```html
<div class="modal-overlay hidden" id="graph-fullscreen-modal">
    <div class="fullscreen-graph-container">
        <div class="fullscreen-graph-header">
            <h2><i class="fas fa-project-diagram"></i> Entity Network</h2>
            <button class="btn btn-close" id="btn-close-fullscreen-graph">
                <i class="fas fa-times"></i>
            </button>
        </div>
        <div class="fullscreen-graph-controls">
            <input type="text" id="graph-search" placeholder="Search entities...">
            <button class="btn" id="btn-graph-zoom-in"><i class="fas fa-plus"></i></button>
            <button class="btn" id="btn-graph-zoom-out"><i class="fas fa-minus"></i></button>
            <button class="btn" id="btn-graph-fit"><i class="fas fa-compress-arrows-alt"></i></button>
        </div>
        <div id="fullscreen-entity-graph"></div>
        <div class="graph-legend">
            <span class="legend-item person"><span class="legend-dot"></span> Person</span>
            <span class="legend-item org"><span class="legend-dot"></span> Organization</span>
            <span class="legend-item location"><span class="legend-dot"></span> Location</span>
        </div>
    </div>
</div>
```

### 1.3 Create Dedicated Entity List View

**Rationale:** Separate the graph exploration from entity management.

**Changes:**
1. Add new nav item: "Entity List"
2. Create `view-entity-list` container with:
   - Search/filter controls
   - Sortable table: Name, Type, Mentions, WikiData status
   - **Bulk actions from Phase 1:**
     - Checkbox selection (select all, select visible)
     - Merge selected (requires 2+ entities of same type)
     - Delete selected (with confirmation)
     - Export selected (JSON)
   - Pagination (50 per page)

**Bulk merge workflow:**
1. User selects 2+ entities
2. Click "Merge" button
3. Modal shows selected entities, user picks primary (keeper)
4. POST `/entities/merge` with primary_id + secondary_ids
5. Refresh list

**Bulk delete workflow:**
1. User selects 1+ entities
2. Click "Delete" button
3. Confirmation modal: "Delete X entities? This cannot be undone."
4. DELETE `/entities/bulk` with entity_ids
5. Refresh list

**Navigation update in `dashboard.html`:**
```html
<a href="#entities" class="nav-item" data-view="entities">
    <i class="fas fa-project-diagram"></i> Network
</a>
<a href="#entity-list" class="nav-item" data-view="entity-list">
    <i class="fas fa-list"></i> Entities
</a>
```

### 1.4 Remove Tracked Entities from Graph View

**File:** `templates/dashboard.html`

Remove the `full-entity-list` section from `view-entities`. The graph view should contain only:
- Graph container (now full-height)
- Graph controls (zoom, fit, search)
- Entity detail panel (shows on node click)

---

## Phase 2: Progressive Disclosure

**Goal:** Never load the entire graph. User intent drives what's visible.

### 2.1 Paginated Graph API

**File:** `app/api/v1/network/routes.py`

Add new endpoint for paginated/filtered graph loading:

```python
@router.get("/graph/subset")
async def get_graph_subset(
    limit: int = Query(50, ge=10, le=200),
    offset: int = Query(0, ge=0),
    sort_by: str = Query("centrality"),  # centrality, mentions, recent
    entity_type: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    include_relationships: bool = Query(True),
    db=Depends(get_db),
    current_user: LocalUser = Depends(get_local_user)
):
    """
    Load a subset of entities with their immediate relationships.
    Does NOT load entire graph - only requested nodes + depth-1 edges.
    """
```

**Response format:**
```json
{
    "elements": {
        "nodes": [...],
        "edges": [...]
    },
    "stats": {
        "returned": 50,
        "total_entities": 2847,
        "total_relationships": 12453
    },
    "pagination": {
        "limit": 50,
        "offset": 0,
        "has_more": true
    }
}
```

### 2.2 Search-to-Focus Workflow

**File:** `static/js/pulse-dashboard.js`

Add entity search that centers the graph:

```javascript
async searchAndFocusEntity(query) {
    // 1. Search API for matching entities
    const results = await this.fetchApi(`/entities/search?q=${encodeURIComponent(query)}&limit=10`);

    // 2. If single match, center on it
    if (results.length === 1) {
        await this.loadEntityNeighborhood(results[0].entity_id, depth=1);
        this.centerOnEntity(results[0].entity_id);
    } else {
        // Show search results dropdown
        this.showSearchResults(results);
    }
}

centerOnEntity(entityId) {
    const node = this.cy.getElementById(entityId);
    if (node.length) {
        this.cy.animate({
            center: { eles: node },
            zoom: 1.5
        }, { duration: 500 });

        // Highlight neighborhood, fade others
        const neighborhood = node.closedNeighborhood();
        this.cy.elements().not(neighborhood).style('opacity', 0.15);
        neighborhood.style('opacity', 1);
    }
}
```

### 2.3 Expand-on-Click Pattern

**File:** `static/js/pulse-dashboard.js`

Double-click a node to load its relationships:

```javascript
setupGraphInteractions() {
    this.cy.on('dbltap', 'node', async (e) => {
        const node = e.target;
        const entityId = node.data('id');

        // Load depth-1 neighborhood
        const neighborhood = await this.fetchApi(`/network/neighborhood/${entityId}?depth=1`);

        // Add new nodes/edges
        const newElements = this.processNeighborhoodResponse(neighborhood);
        this.cy.add(newElements);

        // Run incremental layout on new elements only
        this.cy.layout({
            name: 'fcose',
            eles: this.cy.elements(), // Or just new elements
            animate: true,
            animationDuration: 500
        }).run();
    });
}
```

### 2.4 Depth Controls

Add UI controls to limit relationship depth:

```html
<div class="graph-depth-control">
    <label>Depth:</label>
    <select id="graph-depth">
        <option value="1" selected>1 hop</option>
        <option value="2">2 hops</option>
        <option value="3">3 hops</option>
    </select>
</div>
```

### 2.5 Entity Search API

**File:** `app/api/v1/entities/routes.py`

Add search endpoint:

```python
@router.get("/search")
async def search_entities(
    q: str = Query(..., min_length=2),
    limit: int = Query(10, ge=1, le=50),
    entity_type: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: LocalUser = Depends(get_local_user)
):
    """
    Search entities by name with fuzzy matching.
    Uses PostgreSQL trigram similarity.
    """
    query = select(TrackedEntity).where(
        TrackedEntity.user_id == current_user.user_id,
        TrackedEntity.name.ilike(f"%{q}%")
    ).order_by(
        func.similarity(TrackedEntity.name, q).desc()
    ).limit(limit)

    result = await db.execute(query)
    return result.scalars().all()
```

---

## Phase 3: Performance Migration (Sigma.js) [MANDATORY]

**Goal:** WebGL-based rendering for 10k+ nodes with smooth interaction.

**Status:** This phase is mandatory, not conditional on Phase 2 results. The long-term architecture requires Sigma.js for the scale of data The Pulse will handle.

### 3.1 Library Migration

**Replace Cytoscape.js with Sigma.js v2 + graphology**

**New dependencies:**
```html
<!-- Remove cytoscape.min.js -->
<script src="https://cdnjs.cloudflare.com/ajax/libs/graphology/0.25.4/graphology.umd.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/sigma.js/2.4.0/sigma.min.js"></script>
```

### 3.2 Graph Initialization Pattern

```javascript
initSigmaGraph(containerId) {
    const container = document.getElementById(containerId);

    // Create graphology graph
    this.graph = new graphology.Graph();

    // Initialize Sigma renderer
    this.sigma = new Sigma(this.graph, container, {
        renderEdgeLabels: false,
        defaultNodeColor: '#9966ff',
        defaultEdgeColor: '#3a3a4a',
        labelRenderer: 'canvas',
        labelDensity: 0.07,
        labelGridCellSize: 60,
        minCameraRatio: 0.1,
        maxCameraRatio: 10,
    });

    // Node styling by type
    this.sigma.setSetting('nodeReducer', (node, data) => {
        const res = { ...data };
        switch (data.type) {
            case 'person': res.color = '#00d4ff'; break;
            case 'org': res.color = '#ffb000'; break;
            case 'location': res.color = '#00ff88'; break;
        }
        res.size = Math.max(5, Math.min(20, 5 + (data.degree || 0)));
        return res;
    });
}
```

### 3.3 Server-Side Layout Computation

**File:** `app/services/network_mapper/graph_service.py`

Add layout pre-computation using NetworkX:

```python
def compute_layout(self, algorithm: str = "spring") -> Dict[str, Tuple[float, float]]:
    """
    Compute node positions server-side.
    Returns: {entity_id: (x, y)} mapping
    """
    if algorithm == "spring":
        pos = nx.spring_layout(self.graph, k=1/sqrt(len(self.graph)), iterations=50)
    elif algorithm == "kamada_kawai":
        pos = nx.kamada_kawai_layout(self.graph)
    elif algorithm == "circular":
        pos = nx.circular_layout(self.graph)
    else:
        pos = nx.spring_layout(self.graph)

    # Scale to viewport coordinates
    return {str(node): (float(x) * 1000, float(y) * 1000) for node, (x, y) in pos.items()}
```

**Update export endpoint:**
```python
@router.get("/graph")
async def get_full_graph(
    include_positions: bool = Query(True),
    layout: str = Query("spring"),
    ...
):
    elements = mapper.export_cytoscape(include_isolated=include_isolated)

    if include_positions:
        positions = mapper.compute_layout(algorithm=layout)
        for node in elements["nodes"]:
            node_id = node["data"]["id"]
            if node_id in positions:
                node["position"] = {"x": positions[node_id][0], "y": positions[node_id][1]}

    return {"elements": elements, "stats": stats}
```

### 3.4 Clustering (Community Detection)

**File:** `app/services/network_mapper/graph_service.py`

Already implemented via `detect_communities()`. Enhance to return cluster metadata:

```python
def get_clusters_for_visualization(self, min_size: int = 3) -> List[Dict]:
    """
    Returns clusters with aggregate data for super-node rendering.
    """
    communities = list(nx.community.greedy_modularity_communities(self.graph.to_undirected()))

    clusters = []
    for i, community in enumerate(communities):
        if len(community) < min_size:
            continue

        # Get most central entity in cluster
        subgraph = self.graph.subgraph(community)
        centrality = nx.degree_centrality(subgraph)
        top_entity = max(centrality, key=centrality.get)

        clusters.append({
            "cluster_id": f"cluster_{i}",
            "size": len(community),
            "members": list(community),
            "representative": top_entity,
            "label": f"{self.graph.nodes[top_entity].get('name', 'Unknown')} +{len(community)-1}"
        })

    return clusters
```

### 3.5 Semantic Zoom

Implement zoom-dependent rendering:

```javascript
this.sigma.on('cameraUpdated', () => {
    const ratio = this.sigma.getCamera().ratio;

    if (ratio < 0.3) {
        // Overview: show only clusters
        this.showClustersOnly();
    } else if (ratio < 1) {
        // Region: show cluster + top entities
        this.showClustersAndTopEntities();
    } else {
        // Detail: show all visible entities
        this.showAllInViewport();
    }
});
```

---

## Files to Modify

### Phase 1
| File | Changes |
|------|---------|
| `static/css/sigint-theme.css` | Expand graph container, add fullscreen modal styles |
| `templates/dashboard.html` | Add fullscreen modal, add entity-list nav/view |
| `static/js/pulse-dashboard.js` | Modal toggle, view switching, entity list rendering |

### Phase 2
| File | Changes |
|------|---------|
| `app/api/v1/network/routes.py` | Add `/graph/subset` endpoint |
| `app/api/v1/entities/routes.py` | Add `/search` endpoint |
| `static/js/pulse-dashboard.js` | Search-to-focus, expand-on-click, depth controls |

### Phase 3
| File | Changes |
|------|---------|
| `templates/dashboard.html` | Replace Cytoscape with Sigma.js scripts |
| `static/js/pulse-dashboard.js` | Rewrite graph init/rendering for Sigma |
| `app/services/network_mapper/graph_service.py` | Add `compute_layout()`, enhance `get_clusters_for_visualization()` |
| `app/api/v1/network/routes.py` | Add `include_positions` and `layout` params |

---

## Acceptance Criteria

### Phase 1
- [ ] Graph container fills available viewport height (minimum 500px)
- [ ] Full-screen modal opens via button, closes via X or Escape
- [ ] Entity list is on dedicated page with search/filter/sort
- [ ] Graph view contains only graph + controls, no entity list

### Phase 2
- [ ] Graph loads top 50 entities by centrality on initial view
- [ ] Search box finds and centers on entity
- [ ] Double-click expands node's relationships
- [ ] Depth selector limits visible relationships
- [ ] Performance: <1 second load for paginated view

### Phase 3
- [ ] Sigma.js renders smoothly with 5000+ nodes
- [ ] Server-side layout positions nodes before rendering
- [ ] Semantic zoom shows clusters at overview, entities at detail
- [ ] No force simulation jitter on load

---

## Risk Assessment

| Risk | Mitigation |
|------|------------|
| Sigma.js learning curve | Phase 3 is optional; Phases 1-2 deliver most value with Cytoscape |
| Breaking existing functionality | Each phase is independently deployable |
| Layout algorithm performance | Server-side computation with caching (60s TTL already exists) |
| Mobile responsiveness | Full-screen modal works on mobile; entity list is mobile-friendly |

---

## Out of Scope

- Real-time collaborative editing
- 3D graph visualization
- Export to external tools (Gephi, Neo4j)
- Custom relationship creation UI (exists but not enhanced)

---

## Dependencies

- **Phase 1**: No new dependencies
- **Phase 2**: No new dependencies
- **Phase 3**:
  - `graphology` (npm/CDN)
  - `sigma` v2 (npm/CDN)
  - Optional: `graphology-layout` for additional algorithms
