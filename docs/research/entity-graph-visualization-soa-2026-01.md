# Entity Graph Visualization: State of the Art Analysis

**Created:** 2026-01-15
**Author:** Claude Code Research Agent
**Purpose:** Comprehensive analysis of SOA network visualization techniques compared to The Pulse's current implementation

---

## Executive Summary

The Pulse's current entity graph visualization has made significant progress with the migration to Sigma.js + graphology (Phase 3 complete), but two critical UX issues remain:

1. **Label readability on hover**: The hover label background is hardcoded to white (`#FFF`) in Sigma.js, causing contrast issues on dark themes
2. **Node layout clustering**: The NetworkX spring_layout produces a dense "blob" with outliers—force-directed algorithms converge to local minima without proper cluster separation

Beyond these immediate issues, The Pulse is missing several state-of-the-art features that intelligence analysis tools like i2 Analyst's Notebook provide: **temporal visualization**, **semantic zoom**, **POLE data model**, and **multi-view analysis** (link charts + timelines).

This report provides a detailed comparison with SOA approaches and a prioritized roadmap for implementation.

---

## Table of Contents

1. [Current State Analysis](#current-state-analysis)
2. [Issue Deep-Dive](#issue-deep-dive)
3. [State of the Art Survey](#state-of-the-art-survey)
4. [Gap Analysis: The Pulse vs. SOA](#gap-analysis)
5. [Recommended Implementation Roadmap](#recommended-roadmap)
6. [Technical Specifications](#technical-specifications)
7. [Sources](#sources)

---

## Current State Analysis

### Technology Stack (Post-Phase 3)

| Component | Technology | Status |
|-----------|------------|--------|
| Graph Rendering | Sigma.js v2.4.0 + graphology v0.25.4 | Implemented |
| Layout Computation | NetworkX (server-side spring_layout) | Implemented |
| Data Store | PostgreSQL (TrackedEntity, EntityMention, EntityRelationship) | Implemented |
| Graph Analysis | NetworkX (centrality, communities, paths) | Implemented |

### Current Capabilities

**Working:**
- WebGL rendering via Sigma.js (handles 1000+ nodes)
- Server-side layout computation (eliminates client-side jitter)
- Double-click to filter entity's connections
- Hover highlighting of neighborhood
- Entity type color coding (Person=cyan, Org=amber, Location=green)
- Fullscreen modal, zoom controls, depth selector
- Community detection via NetworkX

**Problematic:**
- Hover label background unreadable on dark theme
- Node spacing produces central blob + distant outliers
- No temporal visualization
- No semantic zoom (cluster aggregation at low zoom)
- No timeline view

### Key Files

| File | Purpose | Lines |
|------|---------|-------|
| [graph_service.py](app/services/network_mapper/graph_service.py) | Server-side layout, clustering | 860 |
| [pulse-dashboard.js](static/js/pulse-dashboard.js) | Sigma.js initialization, interactions | 3000+ |
| [sigint-theme.css](static/css/sigint-theme.css) | Dark theme styling | 950+ |

---

## Issue Deep-Dive

### Issue 1: Hover Label Readability

**Symptom:** When hovering over a node, the label text becomes unreadable.

**Root Cause:** Sigma.js's default `drawHover` function uses a hardcoded white background (`#FFF`) for the hover label. On The Pulse's dark SIGINT theme, this creates:
- White background behind light text = poor contrast
- The highlight "blob" obscures the entity name

**Evidence from Sigma.js GitHub:**
> "The label background appears to be hardcoded in the default drawHover code to #FFF... The current workaround is overriding the whole drawHover function to change this color." — [Issue #1210](https://github.com/jacomyal/sigma.js/issues/1210)

**Solution:** Override the `defaultDrawNodeHover` setting with a custom function that uses a dark background color matching the theme.

### Issue 2: Node Layout Clustering

**Symptom:** The graph displays a dense blob in the center with two isolated nodes far away at the bottom.

**Root Cause Analysis:**

1. **Disconnected Components**: The two outlier nodes are likely isolated (no edges to the main component). Force-directed layouts naturally push disconnected components apart, but without bounds, they drift far away.

2. **Local Minimum Convergence**: NetworkX's `spring_layout` with `k=3/sqrt(n)` creates repulsion, but:
   - Doesn't differentiate between intra-cluster and inter-cluster edges
   - Converges to local minima where dense clusters stay compressed
   - The current parameters (`iterations=100`, `effective_scale = scale + (node_count * 3)`) don't provide enough separation

3. **Missing LinLog Mode**: The spring_layout lacks LinLog energy model, which research shows is critical for visual cluster separation:
   > "The LinLog energy model has a strong impact on the shape of the graph, making the clusters tighter and more visually distinct." — [ForceAtlas2 Paper](https://pmc.ncbi.nlm.nih.gov/articles/PMC4051631/)

**Solution Options:**

1. **Client-side ForceAtlas2**: Use `graphology-layout-forceatlas2` with `linLogMode: true` and tuned parameters
2. **Server-side improvement**: Switch from NetworkX spring_layout to ForceAtlas2 implementation
3. **Handle disconnected components**: Detect and position isolated nodes in a designated "orphan" area

---

## State of the Art Survey

### Intelligence Analysis Tools

#### i2 Analyst's Notebook (IBM)

The gold standard for investigative link analysis, used by law enforcement, military intelligence, and financial services.

**Key Features:**
- **Two chart types**: Relational Analysis (Link Charts) + Temporal Analysis (Timelines)
- **POLE data model**: People, Objects, Locations, Events—standardized entity taxonomy
- **Multi-view visualization**: Network view, timeline view, geographic view, histogram view
- **Social network analysis**: Centrality metrics surfaced in UI
- **Connected network visualization**: Automatic discovery of hidden connections

**Lessons for The Pulse:**
- Dual view paradigm (link chart + timeline) is essential for intelligence analysis
- POLE model provides clear ontology for entity types
- Multiple visualization modes (not just force-directed graph)

#### Link Analysis Methodology

> "By examining connections between suspects, victims, witnesses, and evidence, analysts can establish links and associations that help establish motives, identify accomplices, and gather critical intelligence. It provides a comprehensive overview of the relationships within a case, leading to actionable insights." — [i2 Group](https://i2group.com/articles/what-is-link-analysis-and-link-visualization)

### Academic Research (2023-2026)

#### Force-Directed Layout Community Detection

> "Real-world networks show community structures – groups of nodes that are densely intra-connected and sparsely inter-connected. FDA methods can achieve higher accuracy than classical methods, albeit their effectiveness depends on the chosen setting – with distance-based clustering algorithms leading over density-based ones." — [Springer Research](https://link.springer.com/chapter/10.1007/978-3-642-40285-2_36)

**Key Insight:** Force-directed algorithms can reveal communities, but require careful parameter tuning.

#### Modularity Clustering = Force-Directed Layout

> "Two natural and widely used representations for the community structure of networks are clusterings, which partition the vertex set into disjoint subsets, and layouts, which assign the vertices to positions in a metric space. The LinLog model introduces an alternative energy model that prevents the separation of nodes in different clusters." — [arXiv:0807.4052](https://arxiv.org/abs/0807.4052)

**Key Insight:** LinLog mode is theoretically grounded for cluster visualization.

### Temporal Network Visualization

#### Methods for Visualizing Dynamic Networks

> "Visualization techniques improve the understanding of network dynamics and lead to more reliable and faster pattern identification and decision making. Common approaches include animation-based layouts (evolving node-link diagrams) and timeline-based approaches." — [Cambridge Intelligence](https://cambridge-intelligence.com/methods-visualizing-dynamic-networks/)

**Approaches:**

| Method | Description | Use Case |
|--------|-------------|----------|
| **Animation** | Smooth interpolation as graph evolves | Entity relationship changes over time |
| **Time Slicing** | Convert dynamic network to series of snapshots | Before/after analysis |
| **Storyline** | Metro-map metaphor for entity trajectories | Tracking entity activity over time |
| **Timeline Bar** | Interactive timeline control below graph | Filter graph to time window |

#### Tools

- **KronoGraph** (Cambridge Intelligence): Toolkit for interactive timeline visualizations
- **NDTV** (R package): Renders temporal networks as movies/animations
- **TGX** (Python): Analysis of temporal networks with TEA/TET plots

### Semantic Zoom

> "The semantic zooming approach separates information into three layers with discrete levels of detail: 1) Topological Layer, 2) Aggregation Layer, 3) Visual Appearance Layer. User studies confirm an increase in readability, visual clarity, and information clarity." — [Wiens et al., 2017](https://dl.acm.org/doi/10.1145/3148011.3148015)

**Implementation Pattern:**

```javascript
sigma.on('cameraUpdated', () => {
    const ratio = sigma.getCamera().ratio;

    if (ratio < 0.3) {
        // Overview: Show only cluster super-nodes
        showClustersOnly();
    } else if (ratio < 1) {
        // Region: Show clusters + top entities by centrality
        showClustersAndTopEntities();
    } else {
        // Detail: Show all entities in viewport
        showAllInViewport();
    }
});
```

**Shneiderman's Mantra:**
> "Overview first, zoom and filter, then details-on-demand"

### Network Visualization Tools (2025)

| Tool | Type | Strengths |
|------|------|-----------|
| **InfraNodus** | Online | Text analysis, knowledge graphs |
| **Sigma.js** | Library | WebGL, 10k+ nodes |
| **Cytoscape.js** | Library | Rich ecosystem, cola/cose layouts |
| **Neo4j Bloom** | Enterprise | Graph database native, codeless exploration |
| **KeyLines/ReGraph** | Commercial | Enterprise-grade, temporal support |
| **Gephi** | Desktop | Academic standard, ForceAtlas2 origin |

---

## Gap Analysis

### The Pulse vs. State of the Art

| Feature | SOA (i2/Research) | The Pulse | Gap |
|---------|-------------------|-----------|-----|
| **Force-directed layout** | ForceAtlas2 with LinLog | NetworkX spring_layout | Missing LinLog mode |
| **Temporal visualization** | Timeline + animation | None | Major gap |
| **Semantic zoom** | 3-layer detail levels | None | Major gap |
| **Hover customization** | Themeable | Hardcoded white | Bug |
| **Dual view (chart + timeline)** | Standard in i2 | Graph only | Major gap |
| **POLE taxonomy** | Standardized | Custom (Person/Org/Location) | Minor gap |
| **Entity cards** | Rich metadata | Basic labels | Enhancement |
| **Path analysis UI** | Interactive | API only | Enhancement |
| **Geographic view** | Heat maps, overlays | None | Future consideration |

### Priority Matrix

| Issue | Impact | Effort | Priority |
|-------|--------|--------|----------|
| Hover label readability | High (UX blocker) | Low (1-2 hours) | **P0** |
| Node spacing/clustering | High (UX blocker) | Medium (4-8 hours) | **P0** |
| Temporal visualization | High (SOA feature) | High (1-2 weeks) | **P1** |
| Semantic zoom | Medium (scale preparation) | Medium (1 week) | **P2** |
| Entity cards/detail panel | Medium (UX enhancement) | Low (2-4 hours) | **P2** |
| Timeline view | High (intelligence analysis core) | High (2-3 weeks) | **P1** |

---

## Recommended Roadmap

### Phase 0: Immediate Bug Fixes (1-2 days)

#### 0.1 Fix Hover Label Background

**File:** `static/js/pulse-dashboard.js`

Override `defaultDrawNodeHover` with a custom function:

```javascript
const sigma = new Sigma(graph, container, {
    // ... existing settings ...
    defaultDrawNodeHover: (context, data, settings) => {
        const size = data.size + 3;
        const fontSize = settings.labelSize || 14;
        const font = settings.labelFont || 'sans-serif';
        const label = data.label;

        // Draw node glow
        context.beginPath();
        context.arc(data.x, data.y, size, 0, Math.PI * 2);
        context.fillStyle = data.color || '#9966ff';
        context.fill();

        // Draw label background (DARK for theme)
        if (label) {
            context.font = `${fontSize}px ${font}`;
            const textWidth = context.measureText(label).width;
            const bgPadding = 4;

            // Dark background matching theme
            context.fillStyle = 'rgba(26, 26, 30, 0.95)';  // var(--bg-primary)
            context.fillRect(
                data.x + size + 3 - bgPadding,
                data.y - fontSize / 2 - bgPadding,
                textWidth + bgPadding * 2,
                fontSize + bgPadding * 2
            );

            // Border
            context.strokeStyle = '#00d4ff';  // Cyan accent
            context.lineWidth = 1;
            context.strokeRect(
                data.x + size + 3 - bgPadding,
                data.y - fontSize / 2 - bgPadding,
                textWidth + bgPadding * 2,
                fontSize + bgPadding * 2
            );

            // Label text
            context.fillStyle = '#e0e0e0';
            context.fillText(label, data.x + size + 3, data.y + fontSize / 3);
        }
    }
});
```

#### 0.2 Fix Node Layout Clustering

**Option A: Client-Side ForceAtlas2 (Recommended)**

Add `graphology-layout-forceatlas2` and run layout client-side:

```html
<script src="https://cdn.jsdelivr.net/npm/graphology-layout-forceatlas2@0.10.1/dist/graphology-layout-forceatlas2.min.js"></script>
```

```javascript
import forceAtlas2 from 'graphology-layout-forceatlas2';

// After loading graph data, run ForceAtlas2
const settings = forceAtlas2.inferSettings(graph);
settings.linLogMode = true;      // Critical for cluster separation
settings.scalingRatio = 10;      // Expand spacing
settings.gravity = 0.5;          // Allow clusters to spread
settings.barnesHutOptimize = true;  // Performance for large graphs

forceAtlas2.assign(graph, {
    settings,
    iterations: 200
});
```

**Option B: Server-Side Improvement**

Replace `spring_layout` with a Python ForceAtlas2 implementation:

```bash
pip install fa2
```

```python
# In graph_service.py
from fa2 import ForceAtlas2

def compute_layout(self, algorithm: str = "forceatlas2", scale: float = 1000.0):
    if algorithm == "forceatlas2":
        forceatlas2 = ForceAtlas2(
            outboundAttractionDistribution=True,
            linLogMode=True,
            scalingRatio=2.0,
            gravity=1.0,
            strongGravityMode=False,
            jitterTolerance=1.0,
            barnesHutOptimize=True,
            verbose=False
        )
        pos = forceatlas2.forceatlas2_networkx_layout(
            self.graph,
            pos=None,
            iterations=200
        )
    # ... scale and return
```

**Option C: Handle Disconnected Components**

Detect and position isolated nodes:

```python
def compute_layout_with_islands(self):
    components = list(nx.connected_components(self.graph.to_undirected()))
    positions = {}

    for i, component in enumerate(components):
        subgraph = self.graph.subgraph(component)
        sub_pos = self._compute_component_layout(subgraph)

        # Offset each component
        offset_x = (i % 3) * 1500
        offset_y = (i // 3) * 1500

        for node, (x, y) in sub_pos.items():
            positions[node] = (x + offset_x, y + offset_y)

    return positions
```

### Phase 1: Temporal Visualization (2-3 weeks)

#### 1.1 Timeline Data Model

Add temporal metadata to entity mentions:

```python
# Already exists: EntityMention.timestamp
# Need to expose via API
```

#### 1.2 Timeline View Component

Add a timeline panel below the graph:

```html
<div id="entity-timeline" class="timeline-container">
    <div class="timeline-controls">
        <input type="range" id="timeline-range" min="0" max="100">
        <span id="timeline-date-display"></span>
    </div>
    <canvas id="timeline-canvas"></canvas>
</div>
```

**Libraries to consider:**
- [vis-timeline](https://visjs.github.io/vis-timeline/docs/timeline/) - Full-featured timeline
- [KronoGraph](https://cambridge-intelligence.com/time/) - Commercial, integrated with graph
- Custom Canvas implementation for lightweight solution

#### 1.3 Time-Filtered Graph

Filter graph to show only entities/relationships within a time window:

```javascript
filterGraphToTimeRange(startDate, endDate) {
    graph.forEachNode((node, attrs) => {
        const nodeDate = new Date(attrs.firstSeen);
        const inRange = nodeDate >= startDate && nodeDate <= endDate;

        graph.setNodeAttribute(node, 'hidden', !inRange);
    });

    sigma.refresh();
}
```

### Phase 2: Semantic Zoom (1-2 weeks)

#### 2.1 Cluster Super-Nodes

Already have `get_clusters_for_visualization()` in backend. Frontend implementation:

```javascript
// Zoom-dependent rendering
sigma.on('cameraUpdated', () => {
    const ratio = sigma.getCamera().ratio;
    updateDetailLevel(ratio);
});

function updateDetailLevel(ratio) {
    if (ratio < 0.3) {
        // Show clusters only
        graph.forEachNode((node, attrs) => {
            if (attrs.type !== 'cluster') {
                graph.setNodeAttribute(node, 'hidden', true);
            }
        });
        showClusterNodes();
    } else if (ratio < 1.0) {
        // Show clusters + high-centrality nodes
        showClustersAndTopN(20);
    } else {
        // Show all
        graph.forEachNode((node) => {
            graph.setNodeAttribute(node, 'hidden', false);
        });
    }
    sigma.refresh();
}
```

### Phase 3: Enhanced Entity Interaction (1 week)

#### 3.1 Entity Detail Panel

On node click, show rich entity card:

```html
<div class="entity-detail-panel">
    <div class="entity-header">
        <span class="entity-type-badge">PERSON</span>
        <h3 class="entity-name">Robert Mueller</h3>
        <span class="confidence-score">94%</span>
    </div>
    <div class="entity-stats">
        <div class="stat">
            <span class="stat-value">23</span>
            <span class="stat-label">Mentions</span>
        </div>
        <div class="stat">
            <span class="stat-value">8</span>
            <span class="stat-label">Connections</span>
        </div>
    </div>
    <div class="entity-relationships">
        <!-- List of connected entities -->
    </div>
    <div class="entity-timeline-mini">
        <!-- Sparkline of activity over time -->
    </div>
</div>
```

#### 3.2 Path Finding UI

Add visual path finding between selected entities:

```javascript
async findAndHighlightPath(sourceId, targetId) {
    const response = await this.fetchApi('/network/path', {
        method: 'POST',
        body: JSON.stringify({ source: sourceId, target: targetId })
    });

    if (response.path) {
        // Highlight path nodes and edges
        const pathNodes = new Set(response.path);

        graph.forEachNode((node, attrs) => {
            const onPath = pathNodes.has(node);
            graph.setNodeAttribute(node, 'color',
                onPath ? '#ff0066' : '#333333'
            );
            graph.setNodeAttribute(node, 'size',
                onPath ? attrs.originalSize * 1.5 : attrs.originalSize * 0.5
            );
        });

        sigma.refresh();
    }
}
```

---

## Technical Specifications

### ForceAtlas2 Parameters for The Pulse

Based on research, recommended settings:

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| `linLogMode` | `true` | Critical for cluster separation |
| `scalingRatio` | `10-20` | Expand overall graph size |
| `gravity` | `0.3-0.5` | Allow clusters to spread, prevent extreme drift |
| `barnesHutOptimize` | `true` | Performance for 500+ nodes |
| `outboundAttractionDistribution` | `true` | Better for directed graphs |
| `strongGravityMode` | `false` | Avoid over-centering |
| `iterations` | `200-500` | More iterations for better convergence |

### Sigma.js Settings Enhancement

```javascript
const sigma = new Sigma(graph, container, {
    // Current settings...
    renderEdgeLabels: false,
    defaultNodeColor: '#9966ff',
    defaultEdgeColor: '#3a3a4a',
    labelFont: 'JetBrains Mono, monospace',
    labelSize: 10,
    labelColor: { color: '#e0e0e0' },

    // Enhanced settings
    labelDensity: 0.1,          // Slightly more labels visible
    labelGridCellSize: 80,      // Larger cells for less overlap
    labelRenderedSizeThreshold: 6,  // Hide labels for small nodes

    // Custom hover renderer (see Phase 0.1)
    defaultDrawNodeHover: customDrawNodeHover,

    // Zoom settings
    minCameraRatio: 0.05,       // Allow zooming out further for overview
    maxCameraRatio: 15,         // Allow more zoom-in for details

    // Performance
    hideEdgesOnMove: true,      // Smoother panning on large graphs
    hideLabelsOnMove: true,
});
```

### Database Schema Additions (Future)

For full temporal support:

```sql
-- Add first_seen/last_seen to entities
ALTER TABLE tracked_entities ADD COLUMN first_seen TIMESTAMP;
ALTER TABLE tracked_entities ADD COLUMN last_seen TIMESTAMP;

-- Add temporal metadata to relationships
ALTER TABLE entity_relationships ADD COLUMN first_observed TIMESTAMP;
ALTER TABLE entity_relationships ADD COLUMN last_observed TIMESTAMP;
ALTER TABLE entity_relationships ADD COLUMN observation_count INTEGER DEFAULT 1;
```

---

## Sources

### Graph Visualization Research

- [i2 Analyst's Notebook](https://i2group.com/solutions/i2-analysts-notebook) - Gold standard for intelligence link analysis
- [What is Link Analysis and Link Visualization?](https://i2group.com/articles/what-is-link-analysis-and-link-visualization) - i2 Group methodology
- [Graph Drawing 2025 Symposium](https://graphdrawing.github.io/gd2025/) - Academic conference
- [Network Visualization Roadmap Survey](https://pmc.ncbi.nlm.nih.gov/articles/PMC10947241/) - PMC comprehensive review

### Sigma.js / Graphology

- [Sigma.js Official](https://www.sigmajs.org/) - Library documentation
- [Graphology Standard Library](https://graphology.github.io/) - Graph data structure
- [ForceAtlas2 in Graphology](https://graphology.github.io/standard-library/layout-forceatlas2.html) - Layout algorithm
- [Sigma.js Customization](https://www.sigmajs.org/docs/advanced/customization/) - Hover/label customization
- [GitHub Issue #1210](https://github.com/jacomyal/sigma.js/issues/1210) - Hover background color discussion

### Layout Algorithms

- [ForceAtlas2 Paper (PMC)](https://pmc.ncbi.nlm.nih.gov/articles/PMC4051631/) - Original algorithm description
- [Modularity Clustering is Force-Directed Layout](https://arxiv.org/abs/0807.4052) - LinLog theoretical foundation
- [Force-Directed Layout Community Detection](https://link.springer.com/chapter/10.1007/978-3-642-40285-2_36) - Research on FDA accuracy

### Temporal Visualization

- [Dynamic Network Visualization Methods](https://cambridge-intelligence.com/methods-visualizing-dynamic-networks/) - Cambridge Intelligence guide
- [The Time Bar for Visualizing Dynamic Networks](https://cambridge-intelligence.com/time/) - KronoGraph
- [Temporal Network Analysis with R](https://programminghistorian.org/en/lessons/temporal-network-analysis-with-r) - Programming Historian tutorial

### Semantic Zoom

- [Semantic Zooming for Ontology Graph Visualizations](https://dl.acm.org/doi/10.1145/3148011.3148015) - Wiens et al. 2017
- [Multi-Level Tree Based Approach](https://arxiv.org/abs/1906.05996v1) - ZMLT algorithm

### Tools Comparison

- [Best Network Visualization Tools 2025](https://infranodus.com/docs/network-visualization-software) - InfraNodus comparison

---

## Appendix: i2 Analyst's Notebook Feature Comparison

| i2 Feature | The Pulse Equivalent | Implementation Status |
|------------|---------------------|----------------------|
| Link Charts | Entity Network view | Implemented |
| Timelines | - | Not implemented |
| POLE entities | Person/Org/Location | Partial (missing Object, Event) |
| Heat maps | - | Not implemented |
| Social Network Analysis | Centrality/Communities API | Backend only, not in UI |
| Geographic view | - | Not implemented |
| Entity search | Graph search bar | Implemented |
| Path finding | /network/path API | Backend only |
| Histograms | - | Not implemented |
| Connected network discovery | Relationship discovery | Implemented |

---

*Document generated: 2026-01-15*
*For: The Pulse Entity Visualization Enhancement*
