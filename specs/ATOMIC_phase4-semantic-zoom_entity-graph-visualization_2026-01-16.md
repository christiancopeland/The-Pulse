# Atomic Implementation Plan: Phase 4 - Semantic Zoom

**Created:** 2026-01-16
**Parent Document:** [specs/ATOMIC_entity-graph-visualization-soa_2026-01-15.md](./ATOMIC_entity-graph-visualization-soa_2026-01-15.md)
**Status:** Ready for Implementation

---

## Overview

Phase 4 implements semantic zoom for the entity graph, following Shneiderman's "Overview first, zoom and filter, then details-on-demand" mantra. At low zoom levels, the graph shows cluster super-nodes representing groups of related entities. As the user zooms in, more detail appears until individual entities are visible.

**Phase 4 Features:**
- PULSE-VIZ-013: Cluster Data API — **ALREADY COMPLETE** (via `include_clusters` param)
- PULSE-VIZ-014: Cluster Super-Nodes
- PULSE-VIZ-014a: Cluster Node Styling
- PULSE-VIZ-014b: Cluster Expand/Collapse
- PULSE-VIZ-015: Camera Zoom Handler Enhancement
- PULSE-VIZ-016: Detail Level Switching
- PULSE-VIZ-016a: Smooth Level Transitions

**Total Estimated Time:** 8.5 hours (reduced from 7 since VIZ-013 is done, but refined estimates)

---

## Prerequisites

### Phase 1-3 Complete ✓

| Dependency | Status | Notes |
|------------|--------|-------|
| PULSE-VIZ-003: ForceAtlas2 Integration | **COMPLETE** | Graph layout working |
| Phase 2: Temporal Backend | **COMPLETE** | `first_seen`/`last_seen` available |
| Phase 3: Timeline UI | **COMPLETE** | Time filtering working |

### Existing Infrastructure

The codebase already has partial semantic zoom support:

**Backend (`app/services/network_mapper/graph_service.py:802-866`):**
```python
def get_clusters_for_visualization(self, min_size: int = 3) -> List[Dict]:
    """
    Returns: cluster_id, size, members, representative, representative_name,
             label, dominant_type, type_distribution
    """
```

**API (`app/api/v1/network/routes.py:137-182`):**
```
GET /api/v1/network/graph?include_clusters=true
```
- Returns graph with `clusters` array containing cluster data
- Cluster centroids computed from member positions

**Frontend (`static/js/pulse-dashboard.js:1820-1837`):**
```javascript
setupSemanticZoom(sigma, graph) {
    sigma.on('cameraUpdated', () => {
        const ratio = sigma.getCamera().ratio;
        // Currently only adjusts labelDensity
    });
}
```

---

## Phase 4 Features

### PULSE-VIZ-013: Cluster Data API

**ID:** PULSE-VIZ-013
**Status:** ALREADY COMPLETE ✓

The API already supports `GET /api/v1/network/graph?include_clusters=true` which returns:

```json
{
  "nodes": [...],
  "edges": [...],
  "clusters": [
    {
      "cluster_id": "cluster_0",
      "size": 12,
      "members": ["uuid1", "uuid2", ...],
      "representative": "uuid1",
      "representative_name": "John Doe",
      "label": "John Doe +11",
      "dominant_type": "PERSON",
      "type_distribution": {"PERSON": 8, "ORG": 4},
      "position": {"x": 0.45, "y": 0.32}
    }
  ]
}
```

**No implementation needed.** Proceed to VIZ-014.

---

### PULSE-VIZ-014: Cluster Super-Nodes

**ID:** PULSE-VIZ-014
**Estimated Time:** 2 hours
**Dependencies:** PULSE-VIZ-013 (complete)

#### Description

Add cluster super-nodes to the graphology graph when in "overview" mode. These are special nodes that represent entire clusters, displayed at their centroid position with distinctive styling.

#### Files to Modify

| File | Changes |
|------|---------|
| `static/js/pulse-dashboard.js` | Add `addClusterNodes()`, `removeClusterNodes()` methods |

#### Implementation Contract

```javascript
// Add to PulseDashboard class

/**
 * PULSE-VIZ-014: Add cluster super-nodes to graph for overview mode
 * Called when zoom level is low enough to show clusters instead of entities
 */
addClusterNodes() {
    if (!this.currentGraph || !this.clusters || this.clusters.length === 0) {
        this.log('warning', 'Cannot add clusters: no graph or cluster data');
        return;
    }

    // Track which cluster nodes we've added
    this.clusterNodeIds = new Set();

    this.clusters.forEach(cluster => {
        // Skip small clusters (already filtered by API, but double-check)
        if (cluster.size < 3) return;

        const nodeId = cluster.cluster_id;

        // Skip if already added
        if (this.currentGraph.hasNode(nodeId)) return;

        // Calculate size based on cluster member count
        // Base size 15, scales up logarithmically
        const size = 15 + Math.log2(cluster.size) * 8;

        // Get position from cluster data or compute from members
        let x = 0, y = 0;
        if (cluster.position) {
            x = cluster.position.x;
            y = cluster.position.y;
        } else if (cluster.members && cluster.members.length > 0) {
            // Compute centroid from member positions
            let count = 0;
            cluster.members.forEach(memberId => {
                if (this.currentGraph.hasNode(memberId)) {
                    const attrs = this.currentGraph.getNodeAttributes(memberId);
                    x += attrs.x || 0;
                    y += attrs.y || 0;
                    count++;
                }
            });
            if (count > 0) {
                x /= count;
                y /= count;
            }
        }

        // Add cluster super-node
        this.currentGraph.addNode(nodeId, {
            label: cluster.label,
            x: x,
            y: y,
            size: size,
            color: this.getClusterColor(cluster.dominant_type),
            type: 'cluster',  // Mark as cluster for special handling
            isCluster: true,
            clusterData: cluster,
            // Visual styling
            borderColor: '#ffffff',
            borderWidth: 2
        });

        this.clusterNodeIds.add(nodeId);
    });

    this.log('info', `Added ${this.clusterNodeIds.size} cluster super-nodes`);
}

/**
 * Get cluster color based on dominant entity type
 */
getClusterColor(dominantType) {
    const colors = {
        'PERSON': '#4a9eff',      // Blue
        'ORG': '#ff6b6b',         // Red
        'LOCATION': '#51cf66',    // Green
        'EVENT': '#ffd43b',       // Yellow
        'unknown': '#868e96'      // Gray
    };
    return colors[dominantType] || colors['unknown'];
}

/**
 * Remove cluster super-nodes from graph (when zooming into detail view)
 */
removeClusterNodes() {
    if (!this.currentGraph || !this.clusterNodeIds) return;

    this.clusterNodeIds.forEach(nodeId => {
        if (this.currentGraph.hasNode(nodeId)) {
            this.currentGraph.dropNode(nodeId);
        }
    });

    this.clusterNodeIds.clear();
    this.log('info', 'Removed cluster super-nodes');
}
```

#### Acceptance Criteria

- [ ] `addClusterNodes()` creates nodes for each cluster with size >= 3
- [ ] Cluster nodes positioned at centroid of members
- [ ] Cluster node size scales with member count (logarithmic)
- [ ] Cluster node color reflects dominant entity type
- [ ] Cluster nodes have `isCluster: true` attribute
- [ ] `removeClusterNodes()` cleanly removes all cluster nodes
- [ ] No duplicate cluster nodes on repeated calls

---

### PULSE-VIZ-014a: Cluster Node Styling

**ID:** PULSE-VIZ-014a
**Estimated Time:** 1 hour
**Dependencies:** PULSE-VIZ-014

#### Description

Enhance Sigma.js rendering to display cluster nodes distinctively: hexagonal shape (or circular with border), glow effect, and member count badge.

#### Files to Modify

| File | Changes |
|------|---------|
| `static/js/pulse-dashboard.js` | Add `clusterNodeReducer` and custom draw program |
| `static/css/sigint-theme.css` | Add cluster node CSS variables |

#### Implementation Contract

```javascript
// Add to Sigma settings in loadNetworkGraph()

// Custom node reducer for cluster styling
const clusterNodeReducer = (node, data) => {
    const res = { ...data };

    if (data.isCluster) {
        // Cluster-specific styling
        res.type = 'cluster';  // Use custom program
        res.borderColor = '#ffffff';
        res.borderSize = 3;

        // Pulsing glow effect via increased size when highlighted
        if (data.highlighted) {
            res.size = data.size * 1.2;
        }
    }

    return res;
};

// In Sigma initialization:
const sigma = new Sigma(graph, container, {
    // ... existing settings ...
    nodeReducer: clusterNodeReducer,
    nodeProgramClasses: {
        cluster: ClusterNodeProgram  // Custom WebGL program
    }
});
```

For simplicity, use CSS-based approach with HTML overlay for cluster badges:

```javascript
/**
 * PULSE-VIZ-014a: Update cluster node badges on render
 * Shows member count on cluster nodes
 */
updateClusterBadges() {
    const container = this.currentSigma?.getContainer();
    if (!container) return;

    // Remove existing badges
    container.querySelectorAll('.cluster-badge').forEach(el => el.remove());

    if (!this.clusterNodeIds || this.clusterNodeIds.size === 0) return;

    this.clusterNodeIds.forEach(nodeId => {
        if (!this.currentGraph.hasNode(nodeId)) return;

        const attrs = this.currentGraph.getNodeAttributes(nodeId);
        const cluster = attrs.clusterData;
        if (!cluster) return;

        // Get screen position
        const pos = this.currentSigma.graphToViewport({
            x: attrs.x,
            y: attrs.y
        });

        // Create badge element
        const badge = document.createElement('div');
        badge.className = 'cluster-badge';
        badge.textContent = cluster.size;
        badge.style.cssText = `
            position: absolute;
            left: ${pos.x + attrs.size / 2}px;
            top: ${pos.y - attrs.size / 2}px;
            background: #ff6b00;
            color: white;
            font-size: 10px;
            font-weight: bold;
            padding: 2px 5px;
            border-radius: 8px;
            font-family: var(--font-mono);
            pointer-events: none;
            z-index: 100;
        `;

        container.appendChild(badge);
    });
}
```

#### Acceptance Criteria

- [ ] Cluster nodes visually distinct from regular nodes (border, size)
- [ ] Member count badge displays on cluster nodes
- [ ] Badges update on camera move/zoom
- [ ] Badges removed when clusters removed
- [ ] Colors match dominant entity type

---

### PULSE-VIZ-014b: Cluster Expand/Collapse

**ID:** PULSE-VIZ-014b
**Estimated Time:** 1.5 hours
**Dependencies:** PULSE-VIZ-014

#### Description

Double-clicking a cluster node expands it to show individual members. The cluster node is replaced by its member nodes, positioned around the cluster centroid.

#### Files to Modify

| File | Changes |
|------|---------|
| `static/js/pulse-dashboard.js` | Add `expandCluster()`, `collapseCluster()`, double-click handler |

#### Implementation Contract

```javascript
// Add to PulseDashboard class

/**
 * PULSE-VIZ-014b: Expand a cluster to show individual members
 */
expandCluster(clusterId) {
    if (!this.currentGraph?.hasNode(clusterId)) return;

    const attrs = this.currentGraph.getNodeAttributes(clusterId);
    if (!attrs.isCluster || !attrs.clusterData) return;

    const cluster = attrs.clusterData;
    const centroid = { x: attrs.x, y: attrs.y };

    this.log('info', `Expanding cluster ${cluster.label} (${cluster.size} members)`);

    // Track expanded cluster
    this.expandedClusters = this.expandedClusters || new Set();
    this.expandedClusters.add(clusterId);

    // Show member nodes (they're hidden in overview mode)
    cluster.members.forEach((memberId, index) => {
        if (this.currentGraph.hasNode(memberId)) {
            // Position in circle around centroid
            const angle = (2 * Math.PI * index) / cluster.members.length;
            const radius = Math.sqrt(cluster.size) * 0.1;

            this.currentGraph.setNodeAttribute(memberId, 'hidden', false);
            this.currentGraph.setNodeAttribute(memberId, 'x', centroid.x + Math.cos(angle) * radius);
            this.currentGraph.setNodeAttribute(memberId, 'y', centroid.y + Math.sin(angle) * radius);

            // Mark as part of expanded cluster
            this.currentGraph.setNodeAttribute(memberId, 'expandedFromCluster', clusterId);
        }
    });

    // Show edges between members
    this.currentGraph.forEachEdge((edgeId, edgeAttrs, source, target) => {
        const sourceInCluster = cluster.members.includes(source);
        const targetInCluster = cluster.members.includes(target);
        if (sourceInCluster && targetInCluster) {
            this.currentGraph.setEdgeAttribute(edgeId, 'hidden', false);
        }
    });

    // Hide the cluster super-node
    this.currentGraph.setNodeAttribute(clusterId, 'hidden', true);

    // Update badge
    this.updateClusterBadges();

    this.currentSigma?.refresh();
}

/**
 * Collapse an expanded cluster back to super-node
 */
collapseCluster(clusterId) {
    if (!this.expandedClusters?.has(clusterId)) return;

    const attrs = this.currentGraph.getNodeAttributes(clusterId);
    const cluster = attrs.clusterData;

    this.log('info', `Collapsing cluster ${cluster.label}`);

    // Hide member nodes
    cluster.members.forEach(memberId => {
        if (this.currentGraph.hasNode(memberId)) {
            this.currentGraph.setNodeAttribute(memberId, 'hidden', true);
            this.currentGraph.removeNodeAttribute(memberId, 'expandedFromCluster');
        }
    });

    // Hide inter-cluster edges
    this.currentGraph.forEachEdge((edgeId, edgeAttrs, source, target) => {
        const sourceInCluster = cluster.members.includes(source);
        const targetInCluster = cluster.members.includes(target);
        if (sourceInCluster || targetInCluster) {
            this.currentGraph.setEdgeAttribute(edgeId, 'hidden', true);
        }
    });

    // Show the cluster super-node
    this.currentGraph.setNodeAttribute(clusterId, 'hidden', false);

    this.expandedClusters.delete(clusterId);
    this.updateClusterBadges();
    this.currentSigma?.refresh();
}

// Add double-click handler in setupSigmaEvents():
sigma.on('doubleClickNode', ({ node }) => {
    const attrs = graph.getNodeAttributes(node);

    if (attrs.isCluster) {
        this.expandCluster(node);
    } else if (attrs.expandedFromCluster) {
        this.collapseCluster(attrs.expandedFromCluster);
    }
});
```

#### Acceptance Criteria

- [ ] Double-clicking cluster expands to show member nodes
- [ ] Members positioned in circle around cluster centroid
- [ ] Edges between members become visible
- [ ] Cluster super-node hides during expansion
- [ ] Double-clicking expanded member collapses back to cluster
- [ ] Track which clusters are expanded
- [ ] Visual feedback during expand/collapse

---

### PULSE-VIZ-015: Camera Zoom Handler Enhancement

**ID:** PULSE-VIZ-015
**Estimated Time:** 1 hour
**Dependencies:** PULSE-VIZ-003 (complete)

#### Description

Enhance the existing `setupSemanticZoom()` to call `updateDetailLevel()` when zoom ratio changes. Currently it only adjusts label density.

#### Files to Modify

| File | Changes |
|------|---------|
| `static/js/pulse-dashboard.js` | Enhance `setupSemanticZoom()` method |

#### Implementation Contract

```javascript
// Replace existing setupSemanticZoom() method

/**
 * PULSE-VIZ-015: Enhanced semantic zoom with detail level switching
 */
setupSemanticZoom(sigma, graph) {
    // Store current detail level to avoid redundant updates
    this.currentDetailLevel = 'full';  // 'overview' | 'partial' | 'full'

    sigma.on('cameraUpdated', () => {
        const ratio = sigma.getCamera().ratio;

        // Adjust label density based on zoom level (existing behavior)
        if (ratio < 0.3) {
            sigma.setSetting('labelDensity', 0.02);
        } else if (ratio < 0.6) {
            sigma.setSetting('labelDensity', 0.04);
        } else if (ratio < 1.0) {
            sigma.setSetting('labelDensity', 0.07);
        } else {
            sigma.setSetting('labelDensity', 0.15);
        }

        // PULSE-VIZ-015: Update detail level (debounced)
        clearTimeout(this._zoomTimeout);
        this._zoomTimeout = setTimeout(() => {
            this.updateDetailLevel(ratio);
        }, 150);  // 150ms debounce for smooth interaction
    });

    this.log('info', 'Semantic zoom initialized');
}
```

#### Acceptance Criteria

- [ ] `cameraUpdated` listener calls `updateDetailLevel(ratio)`
- [ ] Detail level updates are debounced (150ms)
- [ ] Existing label density adjustment preserved
- [ ] `currentDetailLevel` tracks state to prevent redundant updates
- [ ] No performance degradation during zoom

---

### PULSE-VIZ-016: Detail Level Switching

**ID:** PULSE-VIZ-016
**Estimated Time:** 2 hours
**Dependencies:** PULSE-VIZ-014, PULSE-VIZ-015

#### Description

Implement the core detail level switching logic. Based on camera ratio:
- **Overview** (ratio < 0.3): Show only cluster super-nodes
- **Partial** (0.3 <= ratio < 1.0): Show clusters + top-N entities by centrality
- **Full** (ratio >= 1.0): Show all individual entities

#### Files to Modify

| File | Changes |
|------|---------|
| `static/js/pulse-dashboard.js` | Add `updateDetailLevel()` method |

#### Implementation Contract

```javascript
// Add to PulseDashboard class

/**
 * PULSE-VIZ-016: Update graph detail level based on zoom ratio
 *
 * Detail levels:
 * - 'overview': ratio < 0.3 - clusters only
 * - 'partial':  0.3 <= ratio < 1.0 - clusters + top-20 by centrality
 * - 'full':     ratio >= 1.0 - all nodes
 */
updateDetailLevel(ratio) {
    // Determine target level
    let targetLevel;
    if (ratio < 0.3) {
        targetLevel = 'overview';
    } else if (ratio < 1.0) {
        targetLevel = 'partial';
    } else {
        targetLevel = 'full';
    }

    // Skip if no change
    if (targetLevel === this.currentDetailLevel) return;

    this.log('info', `Switching detail level: ${this.currentDetailLevel} → ${targetLevel} (ratio: ${ratio.toFixed(2)})`);

    const previousLevel = this.currentDetailLevel;
    this.currentDetailLevel = targetLevel;

    // Apply visibility based on new level
    switch (targetLevel) {
        case 'overview':
            this.applyOverviewMode();
            break;
        case 'partial':
            this.applyPartialMode();
            break;
        case 'full':
            this.applyFullMode();
            break;
    }

    // Refresh render
    this.currentSigma?.refresh();
}

/**
 * Overview mode: Show only cluster super-nodes
 */
applyOverviewMode() {
    const graph = this.currentGraph;
    if (!graph) return;

    // Ensure cluster nodes exist
    if (!this.clusterNodeIds || this.clusterNodeIds.size === 0) {
        this.addClusterNodes();
    }

    // Hide all regular (non-cluster) nodes
    graph.forEachNode((nodeId, attrs) => {
        if (!attrs.isCluster) {
            graph.setNodeAttribute(nodeId, 'hidden', true);
        } else {
            graph.setNodeAttribute(nodeId, 'hidden', false);
        }
    });

    // Hide all edges (clusters don't have inter-cluster edges yet)
    graph.forEachEdge((edgeId) => {
        graph.setEdgeAttribute(edgeId, 'hidden', true);
    });

    this.updateClusterBadges();
    this.log('info', `Overview mode: showing ${this.clusterNodeIds?.size || 0} clusters`);
}

/**
 * Partial mode: Show clusters + top entities by centrality
 */
applyPartialMode() {
    const graph = this.currentGraph;
    if (!graph) return;

    // Ensure cluster nodes exist
    if (!this.clusterNodeIds || this.clusterNodeIds.size === 0) {
        this.addClusterNodes();
    }

    // Get top-20 entities by centrality (from graph data)
    const topEntities = this.getTopEntitiesByCentrality(20);
    const topEntityIds = new Set(topEntities.map(e => e.id));

    // Show cluster nodes
    this.clusterNodeIds?.forEach(nodeId => {
        graph.setNodeAttribute(nodeId, 'hidden', false);
    });

    // Show top entities, hide others
    graph.forEachNode((nodeId, attrs) => {
        if (attrs.isCluster) return;  // Already handled

        const isTopEntity = topEntityIds.has(nodeId);
        graph.setNodeAttribute(nodeId, 'hidden', !isTopEntity);
    });

    // Show edges only between visible nodes
    graph.forEachEdge((edgeId, attrs, source, target) => {
        const sourceVisible = !graph.getNodeAttribute(source, 'hidden');
        const targetVisible = !graph.getNodeAttribute(target, 'hidden');
        graph.setEdgeAttribute(edgeId, 'hidden', !sourceVisible || !targetVisible);
    });

    this.updateClusterBadges();
    this.log('info', `Partial mode: showing clusters + ${topEntityIds.size} top entities`);
}

/**
 * Full mode: Show all individual entities
 */
applyFullMode() {
    const graph = this.currentGraph;
    if (!graph) return;

    // Remove cluster super-nodes
    this.removeClusterNodes();

    // Show all regular nodes (unless filtered by time range)
    graph.forEachNode((nodeId) => {
        // Respect time filter if active
        if (this.timeFilterRange) {
            // Time filter logic already handles visibility
            return;
        }
        graph.setNodeAttribute(nodeId, 'hidden', false);
    });

    // Show all edges (unless filtered)
    graph.forEachEdge((edgeId, attrs, source, target) => {
        const sourceVisible = !graph.getNodeAttribute(source, 'hidden');
        const targetVisible = !graph.getNodeAttribute(target, 'hidden');
        graph.setEdgeAttribute(edgeId, 'hidden', !sourceVisible || !targetVisible);
    });

    this.log('info', `Full mode: showing ${graph.order} entities`);
}

/**
 * Get top N entities by degree centrality from graph
 */
getTopEntitiesByCentrality(n = 20) {
    const graph = this.currentGraph;
    if (!graph) return [];

    const entities = [];

    graph.forEachNode((nodeId, attrs) => {
        if (attrs.isCluster) return;  // Skip clusters

        const degree = graph.degree(nodeId);
        entities.push({
            id: nodeId,
            name: attrs.label,
            degree: degree
        });
    });

    // Sort by degree descending
    entities.sort((a, b) => b.degree - a.degree);

    return entities.slice(0, n);
}
```

#### Acceptance Criteria

- [ ] `updateDetailLevel(ratio)` correctly determines level from ratio
- [ ] Overview mode (ratio < 0.3) shows only cluster nodes
- [ ] Partial mode (0.3 - 1.0) shows clusters + top-20 entities
- [ ] Full mode (ratio >= 1.0) shows all individual entities
- [ ] Level changes are logged with ratio
- [ ] No redundant updates when level unchanged
- [ ] Time filter respected in full mode
- [ ] Edges visibility follows node visibility

---

### PULSE-VIZ-016a: Smooth Level Transitions

**ID:** PULSE-VIZ-016a
**Estimated Time:** 1 hour
**Dependencies:** PULSE-VIZ-016

#### Description

Add smooth visual transitions when switching between detail levels. Use opacity animation rather than instant hide/show for a polished experience.

#### Files to Modify

| File | Changes |
|------|---------|
| `static/js/pulse-dashboard.js` | Add transition animation logic |
| `static/css/sigint-theme.css` | Add transition CSS variables |

#### Implementation Contract

```javascript
// Add to PulseDashboard class

/**
 * PULSE-VIZ-016a: Animate node opacity during detail level transition
 */
async transitionDetailLevel(targetLevel) {
    const graph = this.currentGraph;
    const sigma = this.currentSigma;
    if (!graph || !sigma) return;

    // Capture nodes that will change visibility
    const hidingNodes = [];
    const showingNodes = [];

    graph.forEachNode((nodeId, attrs) => {
        const willBeHidden = this.nodeWillBeHiddenInLevel(nodeId, attrs, targetLevel);
        const currentlyHidden = attrs.hidden;

        if (!currentlyHidden && willBeHidden) {
            hidingNodes.push(nodeId);
        } else if (currentlyHidden && !willBeHidden) {
            showingNodes.push(nodeId);
        }
    });

    // Fade out hiding nodes
    const fadeOutDuration = 200;
    const fadeInDuration = 200;

    // Fade out
    for (let i = 0; i <= 10; i++) {
        const opacity = 1 - (i / 10);
        hidingNodes.forEach(nodeId => {
            graph.setNodeAttribute(nodeId, 'color',
                this.adjustColorOpacity(graph.getNodeAttribute(nodeId, 'baseColor') || graph.getNodeAttribute(nodeId, 'color'), opacity)
            );
        });
        sigma.refresh();
        await this.sleep(fadeOutDuration / 10);
    }

    // Apply actual visibility changes
    this.applyDetailLevelVisibility(targetLevel);

    // Fade in showing nodes
    for (let i = 0; i <= 10; i++) {
        const opacity = i / 10;
        showingNodes.forEach(nodeId => {
            if (!graph.getNodeAttribute(nodeId, 'hidden')) {
                graph.setNodeAttribute(nodeId, 'color',
                    this.adjustColorOpacity(graph.getNodeAttribute(nodeId, 'baseColor') || graph.getNodeAttribute(nodeId, 'color'), opacity)
                );
            }
        });
        sigma.refresh();
        await this.sleep(fadeInDuration / 10);
    }

    // Restore full opacity
    [...hidingNodes, ...showingNodes].forEach(nodeId => {
        const baseColor = graph.getNodeAttribute(nodeId, 'baseColor');
        if (baseColor) {
            graph.setNodeAttribute(nodeId, 'color', baseColor);
        }
    });

    sigma.refresh();
}

/**
 * Utility: Sleep for ms milliseconds
 */
sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

/**
 * Utility: Adjust color opacity
 */
adjustColorOpacity(color, opacity) {
    // Handle hex colors
    if (color.startsWith('#')) {
        const r = parseInt(color.slice(1, 3), 16);
        const g = parseInt(color.slice(3, 5), 16);
        const b = parseInt(color.slice(5, 7), 16);
        return `rgba(${r}, ${g}, ${b}, ${opacity})`;
    }
    // Handle rgba
    if (color.startsWith('rgba')) {
        return color.replace(/[\d.]+\)$/, `${opacity})`);
    }
    // Handle rgb
    if (color.startsWith('rgb(')) {
        return color.replace('rgb(', 'rgba(').replace(')', `, ${opacity})`);
    }
    return color;
}
```

#### Acceptance Criteria

- [ ] Nodes fade out before being hidden (200ms)
- [ ] Nodes fade in after being shown (200ms)
- [ ] Transitions don't block user interaction
- [ ] Transitions can be interrupted by rapid zoom
- [ ] Performance remains smooth during transitions

---

## Dependency Graph

```
Phase 1-3 (COMPLETE)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PULSE-VIZ-003 (ForceAtlas2) ───────────────────────────────────┐
                                                               │
Phase 4 (Semantic Zoom)                                        │
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━│━
                                                               │
PULSE-VIZ-013 ✓ ──────────────────────────────────────────┐    │
(Cluster API - DONE)                                      │    │
                                                          ▼    │
                                                    PULSE-VIZ-014
                                                    (Super-Nodes)
                                                          │
                              ┌────────────────┬──────────┤
                              ▼                ▼          ▼
                        VIZ-014a          VIZ-014b   VIZ-015 ◄──┘
                       (Styling)         (Expand)  (Zoom Handler)
                              │                │          │
                              └────────────────┴──────────┤
                                                          ▼
                                                    PULSE-VIZ-016
                                                   (Detail Switch)
                                                          │
                                                          ▼
                                                    VIZ-016a
                                                   (Transitions)
```

---

## Implementation Order

### Step 1: Cluster Super-Nodes (2 hours)
```
PULSE-VIZ-014
```
**Deliverable:** Cluster nodes can be added/removed from graph

### Step 2: Cluster Styling (1 hour)
```
PULSE-VIZ-014a
```
**Deliverable:** Clusters visually distinct with badges

### Step 3: Expand/Collapse (1.5 hours)
```
PULSE-VIZ-014b
```
**Deliverable:** Double-click expands/collapses clusters

### Step 4: Zoom Handler (1 hour)
```
PULSE-VIZ-015
```
**Deliverable:** Zoom triggers detail level evaluation

### Step 5: Detail Switching (2 hours)
```
PULSE-VIZ-016
```
**Deliverable:** Three detail levels working based on zoom

### Step 6: Smooth Transitions (1 hour)
```
PULSE-VIZ-016a
```
**Deliverable:** Polished fade transitions between levels

---

## Testing Commands

```bash
# Start server
uvicorn app.main:app --reload

# Test cluster API
curl "http://localhost:8000/api/v1/network/graph?include_clusters=true" | jq '.clusters | length'

# Check cluster structure
curl "http://localhost:8000/api/v1/network/graph?include_clusters=true" | jq '.clusters[0]'
```

**Manual Testing:**
1. Open dashboard → Network tab
2. Zoom out fully → should see only cluster nodes
3. Zoom to ~50% → should see clusters + top entities
4. Zoom in fully → should see all entities
5. Double-click cluster → should expand
6. Double-click member → should collapse

---

## Summary

| Metric | Value |
|--------|-------|
| **Total Features** | 6 (VIZ-013 already done) |
| **Total Estimated Time** | 8.5 hours |
| **Files to Modify** | 2 (`pulse-dashboard.js`, `sigint-theme.css`) |
| **API Dependencies** | 1 (already implemented) |

---

## Open Questions

- [ ] Should cluster-to-cluster edges be shown in overview mode? (Currently no)
- [ ] Should partially expanded state be allowed? (e.g., some clusters expanded, some collapsed)
- [ ] Should zoom level thresholds be configurable?

---

## Validation Results

**Validation Date:** 2026-01-16
**Validator:** Claude Code (automated Playwright testing)
**Test Duration:** ~70s graph render + interaction tests

### Summary

| Spec Status | Actual Status |
|-------------|---------------|
| Phase 4 COMPLETE (6/6) | **CRITICAL BUG** - Semantic zoom non-functional |

### Feature-by-Feature Validation

| Feature ID | Spec Claims | Test Result | Evidence |
|------------|-------------|-------------|----------|
| **PULSE-VIZ-014** Cluster Super-Nodes | COMPLETE | ❌ **NOT WORKING** | Code exists but never executes |
| **PULSE-VIZ-014a** Cluster Styling/Badges | COMPLETE | ⚠️ **UNTESTABLE** | Depends on VIZ-014 |
| **PULSE-VIZ-014b** Cluster Expand/Collapse | COMPLETE | ⚠️ **UNTESTABLE** | No clusters appear |
| **PULSE-VIZ-015** Camera Zoom Handler | COMPLETE | ✅ **WORKS** | Debounced handler fires |
| **PULSE-VIZ-016** Detail Level Switching | COMPLETE | ❌ **BUG** | Thresholds inverted |
| **PULSE-VIZ-016a** Utility Methods | COMPLETE | ✅ **CODE EXISTS** | `sleep()`, `adjustColorOpacity()` |

### Root Cause: Inverted Camera Ratio Thresholds

**Location:** `static/js/pulse-dashboard.js:1983-1988`

The threshold comparisons are inverted. In Sigma.js:
- Zoom **IN** = ratio **decreases** (camera closer)
- Zoom **OUT** = ratio **increases** (camera farther)

But the code assumes the opposite:

```javascript
// CURRENT (BROKEN):
if (ratio < 0.3) {           // Expects zoomed out = low ratio
    targetLevel = 'overview';
} else if (ratio < 1.0) {
    targetLevel = 'partial';
} else {
    targetLevel = 'full';    // Default
}
```

**Test Evidence:**

| Zoom State | Actual Ratio | Expected Mode | Actual Mode |
|------------|--------------|---------------|-------------|
| Initial | 1.0 | full | full ✅ |
| Zoomed OUT 15x | **10.0** | overview | full ❌ |

The ratio goes **UP** when zooming out, but code checks for `ratio < 0.3`.

### Proposed Fix

```javascript
// CORRECTED:
if (ratio > 3.0) {           // Zoomed out far
    targetLevel = 'overview';
} else if (ratio > 1.0) {    // Zoomed out some
    targetLevel = 'partial';
} else {
    targetLevel = 'full';    // Default / zoomed in
}
```

### What Was Verified Working

1. **Graph Rendering:** 1006 nodes, 5825 edges render correctly (~35-40s ForceAtlas2)
2. **Semantic Zoom Initialization:** System Log shows "Semantic zoom initialized" ✓
3. **Cluster Data Loading:** `dashboard.clusters.length = 23` (confirmed via JS injection)
4. **Cluster Double-Click Handler:** "Cluster double-click handler initialized" ✓
5. **Zoom Controls:** `#btn-graph-zoom-in` / `#btn-graph-zoom-out` work correctly
6. **Camera Events:** `cameraUpdated` fires and calls `updateDetailLevel()` (debounced)
7. **API Response:** Correct cluster data structure from `/api/v1/network/graph?include_clusters=true`

### What Could NOT Be Tested

Due to threshold bug preventing clusters from appearing:
- Cluster super-node visual appearance
- Cluster member count badges (orange badges)
- Double-click cluster expansion behavior
- Double-click member collapse behavior
- Detail level visual transitions

### Test Environment

```
Server: http://localhost:8000/dashboard (HTTP 200)
Graph Data: 1006 nodes, 5825 edges, 23 clusters
Method: Playwright automation (headless Chromium)
Wait Time: 70s for graph render
Validation Tool: capture_web.py v1.1 with --click-text and --capture-console
```

### Recommendation

**DO NOT mark Phase 4 as complete.** Fix the threshold inversion in `updateDetailLevel()` before proceeding. The implementation code appears correct - only the threshold comparison direction is wrong.

---

*Generated: 2026-01-16*
*Parent: [ATOMIC_entity-graph-visualization-soa_2026-01-15.md](./ATOMIC_entity-graph-visualization-soa_2026-01-15.md)*
