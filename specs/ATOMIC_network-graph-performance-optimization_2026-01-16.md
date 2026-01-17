# Atomic Implementation Plan: Network Graph Performance Optimization

**Created:** 2026-01-16
**Parent Document:** SOA Research conducted in-session (no prior doc)
**Status:** CLIENT-SIDE COMPLETE (6/7 features) - Server bottleneck identified

---

## Implementation Progress (2026-01-16 - Final)

| Feature | Status | Notes |
|---------|--------|-------|
| **PERF-000** | DONE | Thresholds fixed in `setupSemanticZoom()` and `updateDetailLevel()` |
| **PERF-001** | DONE | FA2Layout bundled via esbuild, Web Worker working (5s layout, non-blocking) |
| **PERF-002** | DONE | Indicator HTML/CSS/JS complete, shows elapsed time |
| **PERF-003** | DONE | `hideEdgesOnMove`, `hideLabelsOnMove`, threshold=6 added |
| **PERF-004** | DONE | `scheduleRefresh()` method, 17 calls replaced |
| **PERF-005** | DEFERRED | Not needed - client-side layout is fast (5s) |
| **PERF-006** | DONE | Performance timing added to System Log |

### Measured Performance (2026-01-16)

```
⚡ API fetch: 54473ms      ← SERVER BOTTLENECK (54 seconds!)
⚡ Graph build: 32ms       ← Fast (adding nodes/edges to graphology)
⚡ Layout: 5017ms          ← Good (FA2 Web Worker, non-blocking)
⚡ Render total: 5055ms    ← Good
```

**Finding:** Client-side performance is now excellent. The 54-second delay is from the **server-side API endpoint** (`/api/v1/network/graph`), likely due to:
1. Community detection (Louvain) triggered by `include_clusters=true`
2. Server-side position computation triggered by `include_positions=true`
3. Database queries for 2215 nodes and 5890 edges

### Files Created for FA2Layout Bundle

| File | Purpose |
|------|---------|
| `build-fa2-worker.js` | esbuild script |
| `fa2-worker-entry.js` | Bundle entry point |
| `static/js/fa2layout.bundle.js` | Browser-compatible FA2Layout (40KB) |

To rebuild: `npm run build:fa2` or `node build-fa2-worker.js`

---

## Overview

This spec addresses critical latency issues in The Pulse's Network page rendering. The current implementation causes **35-70 second UI freezes** during graph layout computation due to synchronous ForceAtlas2 execution on the main thread.

**Current State:**
- 2,215 nodes, 5,890 edges
- Synchronous layout blocks UI for 3-8+ seconds
- 20+ direct `sigma.refresh()` calls cause excessive re-renders
- No performance settings enabled in Sigma.js
- Semantic zoom thresholds are inverted (critical bug)

**Target State:**
- Non-blocking layout computation via Web Worker
- < 1 second to visible graph (progressive rendering)
- Smooth 45-60 FPS during pan/zoom interactions
- Batched refresh calls (1 per frame max)
- GPU-accelerated layout evaluation path

---

## Prerequisites

### Hardware Context

User has a **5070 GPU** with:
- 12,000+ CUDA cores
- 12-16GB VRAM
- Excellent WebGL/WebGPU support

Current GPU utilization: **< 5%** (layout is CPU-bound)

### Dependencies

| Dependency | Status | Notes |
|------------|--------|-------|
| Sigma.js v2.4.0 | Installed | WebGL renderer |
| graphology v0.25.4 | Installed | Graph data structure |
| graphology-layout-forceatlas2 | Installed | Includes Web Worker version |
| ForceAtlas2 CDN | Loaded | `forceatlas2.min.js` |

### Related Specs

- [ATOMIC_phase4-semantic-zoom_entity-graph-visualization_2026-01-16.md](./ATOMIC_phase4-semantic-zoom_entity-graph-visualization_2026-01-16.md) - Contains PERF-000 bug details

---

## Phase 0: Critical Bug Fix (Blocker)

### PERF-000: Fix Semantic Zoom Threshold Inversion

**ID:** PERF-000
**Estimated Time:** 0.5 hours
**Dependencies:** None
**Priority:** P0 - Blocks semantic zoom functionality

#### Problem

The camera ratio threshold comparisons in `updateDetailLevel()` are inverted. In Sigma.js:
- Zoom **IN** = ratio **decreases** (camera moves closer)
- Zoom **OUT** = ratio **increases** (camera moves farther)

Current code assumes the opposite, so clusters never appear.

#### Location

`static/js/pulse-dashboard.js` lines 1983-1988

#### Current Code (Broken)

```javascript
updateDetailLevel(ratio) {
    let targetLevel;
    if (ratio < 0.3) {           // WRONG: expects zoomed out = low ratio
        targetLevel = 'overview';
    } else if (ratio < 1.0) {
        targetLevel = 'partial';
    } else {
        targetLevel = 'full';    // Default - always triggers
    }
    // ...
}
```

#### Corrected Code

```javascript
updateDetailLevel(ratio) {
    let targetLevel;
    if (ratio > 3.0) {           // Zoomed out far (ratio increases)
        targetLevel = 'overview';
    } else if (ratio > 1.5) {    // Zoomed out some
        targetLevel = 'partial';
    } else {
        targetLevel = 'full';    // Default / zoomed in
    }
    // ...
}
```

#### Also Fix Label Density Thresholds

Same file, `setupSemanticZoom()` method (~line 1832-1844):

```javascript
// CURRENT (inverted):
if (ratio < 0.3) {
    sigma.setSetting('labelDensity', 0.02);
} else if (ratio < 0.6) {
    sigma.setSetting('labelDensity', 0.04);
// ...

// CORRECTED:
if (ratio > 3.0) {
    sigma.setSetting('labelDensity', 0.02);  // Few labels when zoomed out
} else if (ratio > 2.0) {
    sigma.setSetting('labelDensity', 0.04);
} else if (ratio > 1.0) {
    sigma.setSetting('labelDensity', 0.07);
} else {
    sigma.setSetting('labelDensity', 0.15);  // More labels when zoomed in
}
```

#### Acceptance Criteria

- [ ] Zooming out (15 clicks) triggers overview mode with cluster super-nodes
- [ ] Zooming to medium level shows partial mode (clusters + top entities)
- [ ] Zooming in shows full detail mode (all entities)
- [ ] All 23 clusters appear when fully zoomed out
- [ ] Console logs show "Switching detail level: full → overview" when zooming out

#### Test Commands

```bash
# Start server
uvicorn app.main:app --reload

# Open dashboard, navigate to Network tab
# Use zoom out button 15 times
# Verify clusters appear in graph
```

---

## Phase 1: Immediate Performance Wins

These three features can be implemented in parallel after PERF-000.

### PERF-001: Web Worker ForceAtlas2

**ID:** PERF-001
**Estimated Time:** 2 hours
**Dependencies:** PERF-000
**Priority:** P0 - Main performance impact

#### Description

Replace synchronous `forceAtlas2.assign()` with async `FA2Layout` Web Worker. Layout computation runs in background thread, keeping UI responsive.

#### Files to Modify

| File | Changes |
|------|---------|
| `templates/dashboard.html` | Add Web Worker script tag |
| `static/js/pulse-dashboard.js` | Replace layout code, add worker management |

#### Implementation Contract

**dashboard.html - Add Script:**

```html
<!-- After existing ForceAtlas2 script -->
<script src="https://cdn.jsdelivr.net/npm/graphology-layout-forceatlas2@0.10.1/worker.min.js"></script>
```

**pulse-dashboard.js - Add to PulseDashboard class:**

```javascript
/**
 * PERF-001: Initialize ForceAtlas2 Web Worker for non-blocking layout
 */
initLayoutWorker() {
    // Clean up existing worker
    if (this.layoutWorker) {
        this.layoutWorker.kill();
        this.layoutWorker = null;
    }

    if (!this.currentGraph || typeof FA2Layout === 'undefined') {
        this.log('warning', 'Cannot init layout worker: missing graph or FA2Layout');
        return;
    }

    this.layoutWorker = new FA2Layout(this.currentGraph, {
        settings: {
            linLogMode: true,           // Critical for cluster separation
            scalingRatio: 10,           // Expand overall spacing
            gravity: 0.5,               // Moderate centering force
            barnesHutOptimize: true,    // O(n log n) vs O(n²)
            barnesHutTheta: 0.5,
            strongGravityMode: false,
            slowDown: 1,
            outboundAttractionDistribution: false
        }
    });

    this.log('info', 'ForceAtlas2 Web Worker initialized');
}

/**
 * PERF-001: Run layout asynchronously with timeout
 * @param {number} maxDuration - Maximum layout duration in ms
 * @returns {Promise<void>}
 */
async runLayoutAsync(maxDuration = 5000) {
    if (!this.layoutWorker) {
        this.initLayoutWorker();
    }

    if (!this.layoutWorker) {
        this.log('error', 'Layout worker not available');
        return;
    }

    const startTime = performance.now();
    this.log('info', 'Starting async ForceAtlas2 layout...');

    // Start worker
    this.layoutWorker.start();

    // Refresh periodically to show progress
    const progressInterval = setInterval(() => {
        this.scheduleRefresh();
    }, 200);

    // Wait for duration or manual stop
    return new Promise(resolve => {
        setTimeout(() => {
            this.layoutWorker.stop();
            clearInterval(progressInterval);
            this.scheduleRefresh();

            const duration = performance.now() - startTime;
            this.log('success', `Async layout completed in ${duration.toFixed(0)}ms`);
            resolve();
        }, maxDuration);
    });
}

/**
 * PERF-001: Clean up layout worker
 */
destroyLayoutWorker() {
    if (this.layoutWorker) {
        this.layoutWorker.kill();
        this.layoutWorker = null;
        this.log('info', 'Layout worker destroyed');
    }
}
```

**pulse-dashboard.js - Modify renderNetworkGraph():**

```javascript
/**
 * Render graph data using Sigma.js with ASYNC ForceAtlas2 layout
 * PERF-001: Replaced synchronous layout with Web Worker
 */
async renderNetworkGraph(elements, clusters, isFullscreen = false) {
    if (!elements) return;

    const graph = isFullscreen ? this.graphFullscreen : (this.graph || this.graphMini);
    const sigma = isFullscreen ? this.sigmaFullscreen : (this.sigma || this.sigmaMini);

    if (!graph || !sigma) {
        console.warn('Graph not initialized yet');
        return;
    }

    // Clear existing graph and worker
    graph.clear();
    this.destroyLayoutWorker();

    // Track disconnected nodes for PULSE-VIZ-004
    const nodeIds = new Set();
    const connectedNodes = new Set();

    // Add nodes with initial random positions
    for (const node of elements.nodes) {
        const nodeData = node.data;
        nodeIds.add(nodeData.id);

        const nodeSize = Math.max(5, Math.min(20, 5 + (nodeData.size || 15) / 3));
        graph.addNode(nodeData.id, {
            x: Math.random() * 1000 - 500,
            y: Math.random() * 1000 - 500,
            size: nodeSize,
            originalSize: nodeSize,
            label: nodeData.label || nodeData.name || nodeData.id,
            color: this.getNodeColor(nodeData.type || nodeData.entity_type),
            entityType: (nodeData.type || nodeData.entity_type || 'custom').toLowerCase(),
            firstSeen: nodeData.first_seen || nodeData.created_at,
            lastSeen: nodeData.last_seen || nodeData.created_at,
            originalData: nodeData
        });
    }

    // Add edges and track connected nodes
    for (const edge of elements.edges) {
        const edgeData = edge.data;
        const source = edgeData.source;
        const target = edgeData.target;

        if (graph.hasNode(source) && graph.hasNode(target)) {
            try {
                graph.addEdge(source, target, {
                    size: Math.max(1, Math.min(5, (edgeData.weight || 1))),
                    color: this.getEdgeColor(edgeData.type || edgeData.relationship_type),
                    edgeType: edgeData.type || edgeData.relationship_type || 'associated_with',
                    originalData: edgeData
                });
                connectedNodes.add(source);
                connectedNodes.add(target);
            } catch (e) {
                // Edge may already exist
            }
        }
    }

    // Show graph immediately with random positions
    this.scheduleRefresh();
    this.log('info', `Showing ${graph.order} nodes (layout computing...)`);

    // PERF-001: Run layout asynchronously in Web Worker
    if (typeof FA2Layout !== 'undefined' && graph.order > 1) {
        this.currentGraph = graph;
        await this.runLayoutAsync(5000);
    } else if (typeof forceAtlas2 !== 'undefined' && graph.order > 1) {
        // Fallback to synchronous if worker not available
        this.log('warning', 'FA2 Worker not loaded, using synchronous layout');
        const settings = forceAtlas2.inferSettings(graph);
        settings.linLogMode = true;
        settings.barnesHutOptimize = graph.order > 100;
        forceAtlas2.assign(graph, { settings, iterations: 200 });
    }

    // Position orphan nodes
    const disconnectedNodes = [...nodeIds].filter(id => !connectedNodes.has(id));
    if (disconnectedNodes.length > 0) {
        this.positionOrphanNodes(graph, disconnectedNodes);
    }

    this.scheduleRefresh();
    this.log('success', `Rendered ${graph.order} nodes, ${graph.size} edges`);
}
```

#### Acceptance Criteria

- [ ] UI does not freeze during layout computation
- [ ] Graph nodes visible within 500ms of load (random positions)
- [ ] Nodes animate into final positions over ~5 seconds
- [ ] System Log shows "Starting async ForceAtlas2 layout..."
- [ ] System Log shows "Async layout completed in Xms"
- [ ] Layout quality matches previous (clusters separated)
- [ ] Worker cleaned up on page navigation (no memory leak)
- [ ] Fallback to sync layout if worker unavailable

---

### PERF-003: Sigma.js Performance Settings

**ID:** PERF-003
**Estimated Time:** 0.5 hours
**Dependencies:** None
**Priority:** P0 - Quick win

#### Description

Enable built-in Sigma.js performance optimizations that hide edges and labels during pan/zoom operations.

#### Files to Modify

| File | Changes |
|------|---------|
| `static/js/pulse-dashboard.js` | Update Sigma constructor settings |

#### Implementation Contract

**Modify initializeSigmaGraph() - Sigma constructor:**

```javascript
// Create Sigma renderer with WebGL
const sigma = new Sigma(graph, container, {
    // Existing settings
    renderEdgeLabels: false,
    defaultNodeColor: '#9966ff',
    defaultEdgeColor: '#3a3a4a',
    labelFont: 'JetBrains Mono, monospace',
    labelSize: 10,
    labelColor: { color: '#e0e0e0' },
    labelDensity: 0.07,
    labelGridCellSize: 60,
    minCameraRatio: 0.1,
    maxCameraRatio: 10,
    zoomDuration: 200,
    enableEdgeHoverEvents: true,
    allowInvalidContainer: true,
    renderLabels: true,
    labelRenderedSizeThreshold: 3,

    // PERF-003: Performance optimizations
    hideEdgesOnMove: true,          // Hide 5,890 edges during pan/zoom
    hideLabelsOnMove: true,         // Hide labels during pan/zoom
    labelRenderedSizeThreshold: 6,  // Only show labels on nodes >= size 6
});
```

#### Acceptance Criteria

- [ ] Pan operation feels smooth (no stutter)
- [ ] Zoom operation feels smooth (no stutter)
- [ ] Edges disappear during mouse drag, reappear on mouse up
- [ ] Labels disappear during mouse drag, reappear on mouse up
- [ ] Small nodes (size < 6) don't display labels until zoomed in
- [ ] Labels still visible on larger/important nodes at normal zoom

---

### PERF-004: Batched Refresh Calls

**ID:** PERF-004
**Estimated Time:** 1.5 hours
**Dependencies:** None
**Priority:** P1 - Reduces redundant work

#### Description

Create a `scheduleRefresh()` method that coalesces multiple `sigma.refresh()` calls into a single frame using `requestAnimationFrame`. Replace all direct refresh calls.

#### Files to Modify

| File | Changes |
|------|---------|
| `static/js/pulse-dashboard.js` | Add scheduleRefresh(), replace 20+ refresh calls |

#### Implementation Contract

**Add to PulseDashboard class:**

```javascript
/**
 * PERF-004: Batched refresh using requestAnimationFrame
 * Coalesces multiple refresh requests into a single frame
 */
scheduleRefresh() {
    if (this._refreshScheduled) return;
    this._refreshScheduled = true;

    requestAnimationFrame(() => {
        this._refreshScheduled = false;
        if (this.currentSigma) {
            this.currentSigma.refresh();
        }
    });
}
```

**Replace all instances of:**

| Pattern | Replacement |
|---------|-------------|
| `sigma.refresh();` | `this.scheduleRefresh();` |
| `this.currentSigma?.refresh();` | `this.scheduleRefresh();` |
| `this.sigma?.refresh();` | `this.scheduleRefresh();` |

**Locations to update (grep results):**

- Line ~2013: `applyOverviewMode()`
- Line ~2013: `applyPartialMode()`
- Line ~2013: `applyFullMode()`
- Line ~2247: `expandCluster()`
- Line ~2288: `collapseCluster()`
- Line ~2817: time range filter
- Line ~2853: time range clear
- Line ~3104: `renderNetworkGraph()`
- Line ~3168: `updateEntityGraphFallback()`
- Line ~3214: `highlightNode()`
- Line ~3240: `clearHighlight()`
- Line ~3285: `filterToEntity()`
- Line ~3310: `clearFocus()`
- Line ~3385: neighborhood filter
- Line ~3484: `highlightNeighborhood()`
- Line ~3551: `clearNeighborhoodHighlight()`
- Line ~3609: `highlightPath()`
- Line ~4371: fullscreen sync
- Line ~4581: entity highlight

#### Acceptance Criteria

- [ ] `scheduleRefresh()` method exists and uses `requestAnimationFrame`
- [ ] Grep for `\.refresh\(\)` shows only `scheduleRefresh` implementation
- [ ] Multiple rapid hover in/out does not cause multiple renders per frame
- [ ] All graph operations still update correctly
- [ ] Console does not show "refresh" being called multiple times rapidly

#### Verification Command

```bash
# Should show only the scheduleRefresh implementation, not direct calls
grep -n "\.refresh()" static/js/pulse-dashboard.js | grep -v scheduleRefresh
```

---

## Phase 2: Enhanced Feedback

### PERF-002: Progressive Layout Feedback

**ID:** PERF-002
**Estimated Time:** 1.5 hours
**Dependencies:** PERF-001
**Priority:** P1 - User experience improvement

#### Description

Show nodes immediately with random positions, then animate to final layout positions. Add visual indicator during layout computation. User sees progress instead of frozen UI.

#### Files to Modify

| File | Changes |
|------|---------|
| `templates/dashboard.html` | Add layout indicator HTML |
| `static/css/sigint-theme.css` | Add indicator styles |
| `static/js/pulse-dashboard.js` | Add indicator show/hide methods |

#### Implementation Contract

**dashboard.html - Add inside `#main-entity-graph` container:**

```html
<div id="main-entity-graph" class="entity-graph-container">
    <!-- Existing content -->

    <!-- PERF-002: Layout progress indicator -->
    <div id="layout-progress-indicator" class="layout-indicator" style="display: none;">
        <div class="layout-spinner"></div>
        <span class="layout-text">Computing layout...</span>
    </div>
</div>
```

**sigint-theme.css - Add styles:**

```css
/* PERF-002: Layout Progress Indicator */
.layout-indicator {
    position: absolute;
    bottom: 10px;
    left: 10px;
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 8px 12px;
    background: rgba(26, 26, 30, 0.95);
    border: 1px solid var(--accent-cyan);
    border-radius: 4px;
    font-family: var(--font-mono);
    font-size: 11px;
    color: var(--accent-cyan);
    z-index: 100;
    pointer-events: none;
}

.layout-spinner {
    width: 12px;
    height: 12px;
    border: 2px solid var(--accent-cyan);
    border-top-color: transparent;
    border-radius: 50%;
    animation: layout-spin 1s linear infinite;
}

@keyframes layout-spin {
    to { transform: rotate(360deg); }
}

.layout-indicator.complete {
    border-color: var(--status-success);
    color: var(--status-success);
}

.layout-indicator.complete .layout-spinner {
    display: none;
}

.layout-indicator.complete::before {
    content: '✓';
    margin-right: 4px;
}
```

**pulse-dashboard.js - Add methods:**

```javascript
/**
 * PERF-002: Show/hide layout progress indicator
 * @param {boolean} show - Whether to show indicator
 * @param {string} message - Optional message to display
 */
showLayoutIndicator(show, message = 'Computing layout...') {
    const indicator = document.getElementById('layout-progress-indicator');
    if (!indicator) return;

    if (show) {
        indicator.style.display = 'flex';
        indicator.classList.remove('complete');
        const textEl = indicator.querySelector('.layout-text');
        if (textEl) textEl.textContent = message;
    } else {
        indicator.style.display = 'none';
    }
}

/**
 * PERF-002: Show completion state briefly
 * @param {number} duration - Duration to show completion message
 */
showLayoutComplete(duration = 1500) {
    const indicator = document.getElementById('layout-progress-indicator');
    if (!indicator) return;

    indicator.style.display = 'flex';
    indicator.classList.add('complete');
    const textEl = indicator.querySelector('.layout-text');
    if (textEl) textEl.textContent = 'Layout complete';

    setTimeout(() => {
        indicator.style.display = 'none';
        indicator.classList.remove('complete');
    }, duration);
}
```

**Modify runLayoutAsync() to use indicator:**

```javascript
async runLayoutAsync(maxDuration = 5000) {
    if (!this.layoutWorker) {
        this.initLayoutWorker();
    }

    if (!this.layoutWorker) {
        this.log('error', 'Layout worker not available');
        return;
    }

    const startTime = performance.now();
    this.log('info', 'Starting async ForceAtlas2 layout...');

    // PERF-002: Show progress indicator
    this.showLayoutIndicator(true, 'Computing layout...');

    this.layoutWorker.start();

    const progressInterval = setInterval(() => {
        this.scheduleRefresh();
        // Update indicator with elapsed time
        const elapsed = ((performance.now() - startTime) / 1000).toFixed(1);
        this.showLayoutIndicator(true, `Computing layout... ${elapsed}s`);
    }, 200);

    return new Promise(resolve => {
        setTimeout(() => {
            this.layoutWorker.stop();
            clearInterval(progressInterval);
            this.scheduleRefresh();

            const duration = performance.now() - startTime;
            this.log('success', `Async layout completed in ${duration.toFixed(0)}ms`);

            // PERF-002: Show completion briefly
            this.showLayoutComplete(1500);

            resolve();
        }, maxDuration);
    });
}
```

#### Acceptance Criteria

- [ ] "Computing layout..." indicator appears during layout
- [ ] Indicator shows elapsed time (e.g., "Computing layout... 2.3s")
- [ ] Spinner animates smoothly
- [ ] "Layout complete" with checkmark appears briefly when done
- [ ] Indicator disappears after 1.5 seconds
- [ ] User can still pan/zoom while indicator is visible
- [ ] Indicator positioned in bottom-left, doesn't obscure graph

---

## Phase 3: Advanced Optimization

### PERF-005: Cosmos GPU Layout Evaluation

**ID:** PERF-005
**Estimated Time:** 4 hours
**Dependencies:** PERF-001, PERF-002
**Priority:** P2 - Future optimization path

#### Description

Evaluate `@cosmograph/cosmos` for GPU-accelerated force layout. Create benchmark comparing performance against current ForceAtlas2 Worker approach. Document findings.

#### Why Cosmos?

From SOA research:
- Cosmos runs entire force simulation on GPU using WebGL shaders
- Capable of 1M+ nodes at interactive framerates
- 40x+ speedup over CPU implementations
- User has 5070 GPU (massively underutilized)

#### Files to Create

| File | Purpose |
|------|---------|
| `static/js/cosmos-benchmark.js` | Benchmark script |
| `docs/research/cosmos-evaluation-2026-01.md` | Findings document |

#### Implementation Contract

**cosmos-benchmark.js:**

```javascript
/**
 * PERF-005: Benchmark Cosmos GPU layout vs ForceAtlas2 Worker
 *
 * Usage: Run in browser console on Network page
 *   await benchmarkLayouts();
 */

async function benchmarkLayouts() {
    const results = {
        nodeCount: 0,
        edgeCount: 0,
        fa2Worker: { time: 0, iterations: 0 },
        cosmos: { time: 0, fps: 0 }
    };

    // Get current graph data
    const dashboard = window.dashboard;
    if (!dashboard || !dashboard.graph) {
        console.error('Dashboard not initialized');
        return;
    }

    const graph = dashboard.graph;
    results.nodeCount = graph.order;
    results.edgeCount = graph.size;

    console.log(`Benchmarking with ${results.nodeCount} nodes, ${results.edgeCount} edges`);

    // Prepare node/edge arrays for Cosmos
    const nodes = [];
    const links = [];

    graph.forEachNode((id, attrs) => {
        nodes.push({ id, x: attrs.x, y: attrs.y });
    });

    graph.forEachEdge((edge, attrs, source, target) => {
        links.push({ source, target });
    });

    // Benchmark 1: ForceAtlas2 Worker (current approach)
    console.log('Testing ForceAtlas2 Worker...');
    const testGraph1 = new graphology.Graph();
    nodes.forEach(n => testGraph1.addNode(n.id, { x: Math.random() * 1000, y: Math.random() * 1000 }));
    links.forEach(l => {
        try { testGraph1.addEdge(l.source, l.target); } catch(e) {}
    });

    const fa2Start = performance.now();
    const fa2Layout = new FA2Layout(testGraph1, {
        settings: { linLogMode: true, barnesHutOptimize: true }
    });
    fa2Layout.start();
    await new Promise(r => setTimeout(r, 5000));
    fa2Layout.stop();
    results.fa2Worker.time = performance.now() - fa2Start;
    fa2Layout.kill();
    console.log(`FA2 Worker: ${results.fa2Worker.time.toFixed(0)}ms`);

    // Benchmark 2: Cosmos GPU (if available)
    if (typeof Cosmos !== 'undefined') {
        console.log('Testing Cosmos GPU...');
        const cosmosContainer = document.createElement('div');
        cosmosContainer.style.cssText = 'width: 800px; height: 600px; position: absolute; left: -9999px;';
        document.body.appendChild(cosmosContainer);

        const cosmosStart = performance.now();
        const cosmos = new Cosmos.Graph(cosmosContainer, {
            nodeColor: () => '#9966ff',
            nodeSize: () => 5,
            simulation: { gravity: 0.5, repulsion: 1 }
        });
        cosmos.setData(nodes, links);
        await new Promise(r => setTimeout(r, 5000));
        results.cosmos.time = performance.now() - cosmosStart;
        cosmos.dispose();
        cosmosContainer.remove();
        console.log(`Cosmos GPU: ${results.cosmos.time.toFixed(0)}ms`);
    } else {
        console.log('Cosmos not loaded - skipping GPU benchmark');
        results.cosmos.time = -1;
    }

    // Report
    console.log('\n=== BENCHMARK RESULTS ===');
    console.table(results);

    if (results.cosmos.time > 0) {
        const speedup = results.fa2Worker.time / results.cosmos.time;
        console.log(`\nCosmos speedup: ${speedup.toFixed(1)}x`);

        if (speedup > 2) {
            console.log('RECOMMENDATION: Cosmos shows significant improvement. Consider integration.');
        } else {
            console.log('RECOMMENDATION: FA2 Worker is competitive. Cosmos integration not urgent.');
        }
    }

    return results;
}

// Export for module usage
if (typeof module !== 'undefined') {
    module.exports = { benchmarkLayouts };
}
```

#### Acceptance Criteria

- [ ] Benchmark script runs in browser console
- [ ] Results show layout times for both approaches
- [ ] Speedup ratio calculated and displayed
- [ ] Recommendation provided based on results
- [ ] Findings documented in research doc with:
  - Hardware specs
  - Graph size
  - Timing results
  - Visual quality comparison (screenshots)
  - Recommendation (proceed or defer Cosmos integration)

---

### PERF-006: Performance Metrics Dashboard

**ID:** PERF-006
**Estimated Time:** 2 hours
**Dependencies:** PERF-001, PERF-003, PERF-004
**Priority:** P2 - Observability

#### Description

Add performance instrumentation to track layout duration, render FPS, and refresh counts. Display metrics in System Log panel for debugging.

#### Files to Modify

| File | Changes |
|------|---------|
| `static/js/pulse-dashboard.js` | Add metrics collection and logging |

#### Implementation Contract

```javascript
/**
 * PERF-006: Performance metrics collection
 */
initPerformanceMetrics() {
    this.perfMetrics = {
        layoutStartTime: 0,
        layoutDuration: 0,
        refreshCount: 0,
        fps: 0,
        lastFpsUpdate: 0
    };

    // FPS counter
    let frameCount = 0;
    let lastFpsTime = performance.now();

    const measureFps = () => {
        frameCount++;
        const now = performance.now();

        if (now - lastFpsTime >= 1000) {
            this.perfMetrics.fps = frameCount;
            frameCount = 0;
            lastFpsTime = now;
        }

        requestAnimationFrame(measureFps);
    };

    measureFps();
}

/**
 * PERF-006: Log performance metric to System Log
 */
logPerfMetric(metric, value, unit = 'ms') {
    this.log('info', `⚡ ${metric}: ${value.toFixed(1)}${unit}`);
}

/**
 * PERF-006: Get performance summary
 */
getPerformanceSummary() {
    return {
        layoutTime: this.perfMetrics.layoutDuration,
        refreshCount: this.perfMetrics.refreshCount,
        currentFps: this.perfMetrics.fps
    };
}
```

**Update scheduleRefresh() to track count:**

```javascript
scheduleRefresh() {
    if (this._refreshScheduled) return;
    this._refreshScheduled = true;

    requestAnimationFrame(() => {
        this._refreshScheduled = false;
        if (this.currentSigma) {
            this.currentSigma.refresh();
            // PERF-006: Track refresh count
            if (this.perfMetrics) {
                this.perfMetrics.refreshCount++;
            }
        }
    });
}
```

**Update runLayoutAsync() to log metrics:**

```javascript
// At end of runLayoutAsync():
const duration = performance.now() - startTime;
this.perfMetrics.layoutDuration = duration;
this.logPerfMetric('Layout time', duration);
this.logPerfMetric('Refresh count', this.perfMetrics.refreshCount, '');
```

#### Acceptance Criteria

- [ ] System Log shows "⚡ Layout time: 3245.2ms" after layout
- [ ] Refresh count tracked and logged
- [ ] FPS counter running in background
- [ ] `dashboard.getPerformanceSummary()` returns metrics object
- [ ] Metrics help identify regressions in future changes

---

## Dependency Graph

```
                    ┌─────────────────────────────────────────────┐
                    │           PHASE 0: BUG FIX                  │
                    │                                             │
                    │  PERF-000: Fix Semantic Zoom Thresholds     │
                    │  (0.5 hrs) - BLOCKER                        │
                    └─────────────────────┬───────────────────────┘
                                          │
        ┌─────────────────────────────────┼─────────────────────────────────┐
        │                                 │                                 │
        ▼                                 ▼                                 ▼
┌───────────────────┐          ┌───────────────────┐          ┌───────────────────┐
│   PERF-001        │          │   PERF-003        │          │   PERF-004        │
│   Web Worker FA2  │          │   Sigma Settings  │          │   Batch Refresh   │
│   (2 hrs)         │          │   (0.5 hrs)       │          │   (1.5 hrs)       │
│                   │          │                   │          │                   │
│   Main perf win   │          │   Quick win       │          │   Reduces work    │
└─────────┬─────────┘          └───────────────────┘          └───────────────────┘
          │
          ▼
┌───────────────────┐
│   PERF-002        │
│   Progressive     │
│   Feedback        │
│   (1.5 hrs)       │
└─────────┬─────────┘
          │
          ├─────────────────────────────────┐
          │                                 │
          ▼                                 ▼
┌───────────────────┐          ┌───────────────────┐
│   PERF-005        │          │   PERF-006        │
│   Cosmos Eval     │          │   Metrics         │
│   (4 hrs)         │          │   (2 hrs)         │
│                   │          │                   │
│   Future path     │          │   Observability   │
└───────────────────┘          └───────────────────┘
```

---

## Summary

| Metric | Value |
|--------|-------|
| **Total Features** | 7 |
| **Total Estimated Time** | 12 hours |
| **Phases** | 4 (0-3) |
| **Files to Modify** | 3 primary |
| **Critical Path** | PERF-000 → PERF-001 → PERF-002 |

### Implementation Order

| Order | ID | Name | Time | Cumulative |
|-------|-------|------|------|------------|
| 1 | PERF-000 | Fix Threshold Bug | 0.5 hrs | 0.5 hrs |
| 2 | PERF-003 | Sigma Settings | 0.5 hrs | 1.0 hrs |
| 3 | PERF-004 | Batch Refresh | 1.5 hrs | 2.5 hrs |
| 4 | PERF-001 | Web Worker FA2 | 2.0 hrs | 4.5 hrs |
| 5 | PERF-002 | Progressive Feedback | 1.5 hrs | 6.0 hrs |
| 6 | PERF-006 | Metrics | 2.0 hrs | 8.0 hrs |
| 7 | PERF-005 | Cosmos Evaluation | 4.0 hrs | 12.0 hrs |

### Expected Performance Improvement

| Metric | Before | After Phase 1 | After Phase 2 |
|--------|--------|---------------|---------------|
| Time to visible | 35-70s | < 1s | < 500ms |
| UI freeze | Yes (3-8s) | No | No |
| Pan/zoom FPS | ~15 fps | ~45 fps | ~55 fps |
| Refresh calls/action | 3-5 | 1 | 1 |

---

## Testing Strategy

### Manual Testing Checklist

```markdown
## PERF-000: Threshold Fix
- [ ] Zoom out 15x → clusters appear
- [ ] Zoom to middle → clusters + top entities
- [ ] Zoom in → all entities visible
- [ ] Console: "Switching detail level: full → overview"

## PERF-001: Web Worker
- [ ] Page loads without freeze
- [ ] Nodes visible within 1 second
- [ ] Layout animates over ~5 seconds
- [ ] Console: "Starting async ForceAtlas2..."
- [ ] Console: "Async layout completed in Xms"

## PERF-003: Sigma Settings
- [ ] Pan feels smooth
- [ ] Zoom feels smooth
- [ ] Edges hide during drag
- [ ] Labels hide during drag

## PERF-004: Batch Refresh
- [ ] Rapid hover doesn't lag
- [ ] All operations still work
- [ ] No visual glitches

## PERF-002: Progressive Feedback
- [ ] Indicator appears during layout
- [ ] Shows elapsed time
- [ ] "Layout complete" appears briefly
- [ ] Indicator disappears after 1.5s
```

### Automated Validation

```bash
# Capture screenshots at key states
python ~/.claude/scripts/validation/interact_web.py http://localhost:8000/dashboard \
  --actions '[
    {"type": "click-text", "text": "NETWORK"},
    {"type": "wait-for-idle", "timeout": 10000},
    {"type": "screenshot", "name": "01-network-loading"},
    {"type": "wait", "ms": 6000},
    {"type": "screenshot", "name": "02-network-loaded"},
    {"type": "click", "selector": "#btn-graph-zoom-out"},
    {"type": "click", "selector": "#btn-graph-zoom-out"},
    {"type": "click", "selector": "#btn-graph-zoom-out"},
    {"type": "wait", "ms": 500},
    {"type": "screenshot", "name": "03-zoomed-out"}
  ]' \
  --output-dir ./perf-validation \
  --capture-console console.log
```

---

## Open Questions

- [ ] Should layout duration be configurable per graph size?
- [ ] Should we cache layout positions in localStorage for faster reload?
- [ ] What's the threshold node count for enabling Barnes-Hut? (currently 100)
- [ ] Should Cosmos integration be a separate spec if evaluation is positive?

---

## Sources

- [Graphology ForceAtlas2 Docs](https://graphology.github.io/standard-library/layout-forceatlas2.html)
- [Sigma.js Performance Issue #567](https://github.com/jacomyal/sigma.js/issues/567)
- [Cosmograph/Cosmos](https://github.com/cosmograph-org/cosmos)
- [How to Visualize a Graph with a Million Nodes](https://nightingaledvs.com/how-to-visualize-a-graph-with-a-million-nodes/)
- [Cambridge Intelligence: WebGL Visualization](https://cambridge-intelligence.com/visualizing-graphs-webgl/)

---

*Generated: 2026-01-16*
*Research Session: Network Graph Latency Deep Dive*
