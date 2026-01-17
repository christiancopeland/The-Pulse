# Atomic Implementation Plan: Phase 3 - Timeline UI Component

**Created:** 2026-01-16
**Completed:** 2026-01-16
**Parent Document:** [specs/ATOMIC_entity-graph-visualization-soa_2026-01-15.md](./ATOMIC_entity-graph-visualization-soa_2026-01-15.md)
**Status:** COMPLETE (6/6 features)

---

## Overview

Phase 3 builds an interactive timeline component below the entity graph that enables temporal filtering and visualization. Users can see when entities were most active and filter the graph to specific time ranges.

**Phase 3 Features (Refined):**
- [x] PULSE-VIZ-009: Timeline Container HTML/CSS
- [x] PULSE-VIZ-010a: TimelineRenderer Core
- [x] PULSE-VIZ-010b: Timeline Bar Rendering
- [x] PULSE-VIZ-010c: Timeline Data Integration
- [x] PULSE-VIZ-011: Time Range Filter
- [x] PULSE-VIZ-012: Timeline-Graph Sync

**Estimated Time:** 9.5 hours
**Actual Time:** ~2 hours (implemented in single session)

---

## Prerequisites: Phase 2 Complete

Phase 3 depends on Phase 2 backend infrastructure:

| Dependency | Status | Notes |
|------------|--------|-------|
| PULSE-VIZ-005: Entity Temporal Schema | **COMPLETE** | Migration ran 2026-01-16 |
| PULSE-VIZ-007: Backfill Temporal Data | **COMPLETE** | Data backfilled |
| PULSE-VIZ-008: Timeline API Endpoint | **COMPLETE** | `GET /api/v1/network/timeline` |

**Verification (run to test):**
```bash
# Verify API works
curl http://localhost:8000/api/v1/network/timeline?period=day&days=30
```

---

## Phase 3 Features

### PULSE-VIZ-009: Timeline Container HTML/CSS

**ID:** PULSE-VIZ-009
**Estimated Time:** 1 hour
**Dependencies:** None

#### Description

Add the HTML structure and CSS styling for the timeline component. The timeline will appear below the entity graph and include:
- A canvas element for the activity visualization
- A range slider for selecting time windows
- Date display labels showing the selected range
- Reset button and period selector

#### Files to Modify

| File | Changes |
|------|---------|
| `templates/dashboard.html` | Add `#entity-timeline-container` below graph |
| `static/css/sigint-theme.css` | Add timeline styling with SIGINT theme |

#### Implementation Contract

```html
<!-- Add inside #view-entities, below .entity-graph-container -->
<div class="entity-timeline-container" id="entity-timeline-container">
    <div class="timeline-header">
        <h4 class="timeline-title">
            <i class="fas fa-clock"></i> Entity Activity Timeline
        </h4>
        <div class="timeline-controls">
            <button class="btn btn-sm timeline-btn" id="timeline-reset" title="Reset to full range">
                <i class="fas fa-undo"></i>
            </button>
            <select class="timeline-period-select" id="timeline-period-select">
                <option value="day">Daily</option>
                <option value="week">Weekly</option>
            </select>
        </div>
    </div>

    <div class="timeline-date-display">
        <span id="timeline-start-date">--</span>
        <span class="timeline-date-separator">to</span>
        <span id="timeline-end-date">--</span>
    </div>

    <div class="timeline-canvas-wrapper">
        <canvas id="entity-timeline-canvas"></canvas>
    </div>

    <div class="timeline-slider-wrapper">
        <input type="range"
               id="timeline-range-start"
               class="timeline-range-slider"
               min="0" max="100" value="0">
        <input type="range"
               id="timeline-range-end"
               class="timeline-range-slider"
               min="0" max="100" value="100">
    </div>

    <div class="timeline-legend">
        <span class="legend-item">
            <span class="legend-bar low"></span> Low Activity
        </span>
        <span class="legend-item">
            <span class="legend-bar medium"></span> Medium
        </span>
        <span class="legend-item">
            <span class="legend-bar high"></span> High Activity
        </span>
    </div>
</div>
```

```css
/* Add to static/css/sigint-theme.css */

/* ============================================
   PULSE-VIZ-009: Entity Timeline Component
   ============================================ */

.entity-timeline-container {
    margin-top: var(--spacing-md);
    padding: var(--spacing-md);
    background: var(--bg-secondary);
    border: 1px solid var(--border-color);
    border-radius: 4px;
}

.timeline-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: var(--spacing-sm);
}

.timeline-title {
    margin: 0;
    font-size: 13px;
    font-weight: 600;
    color: var(--accent-cyan);
    font-family: var(--font-mono);
}

.timeline-title i {
    margin-right: var(--spacing-xs);
}

.timeline-controls {
    display: flex;
    align-items: center;
    gap: var(--spacing-sm);
}

.timeline-btn {
    padding: 4px 8px;
    font-size: 12px;
}

.timeline-period-select {
    background: var(--bg-tertiary);
    border: 1px solid var(--border-color);
    color: var(--text-primary);
    font-size: 11px;
    font-family: var(--font-mono);
    padding: 4px 8px;
    border-radius: 3px;
    cursor: pointer;
}

.timeline-period-select:hover {
    border-color: var(--accent-cyan);
}

.timeline-date-display {
    text-align: center;
    font-size: 12px;
    font-family: var(--font-mono);
    color: var(--text-secondary);
    margin-bottom: var(--spacing-sm);
}

.timeline-date-display span {
    color: var(--accent-cyan);
}

.timeline-date-separator {
    color: var(--text-muted) !important;
    margin: 0 var(--spacing-sm);
}

.timeline-canvas-wrapper {
    position: relative;
    height: 80px;
    background: var(--bg-primary);
    border: 1px solid var(--border-color);
    border-radius: 3px;
    margin-bottom: var(--spacing-sm);
}

.timeline-canvas-wrapper canvas {
    width: 100%;
    height: 100%;
}

.timeline-slider-wrapper {
    position: relative;
    height: 24px;
    margin-bottom: var(--spacing-sm);
}

.timeline-range-slider {
    position: absolute;
    width: 100%;
    height: 4px;
    background: transparent;
    -webkit-appearance: none;
    appearance: none;
    pointer-events: none;
}

.timeline-range-slider::-webkit-slider-thumb {
    -webkit-appearance: none;
    appearance: none;
    width: 16px;
    height: 16px;
    background: var(--accent-cyan);
    border-radius: 50%;
    cursor: pointer;
    pointer-events: auto;
    box-shadow: 0 0 8px rgba(0, 212, 255, 0.5);
}

.timeline-range-slider::-moz-range-thumb {
    width: 16px;
    height: 16px;
    background: var(--accent-cyan);
    border-radius: 50%;
    cursor: pointer;
    pointer-events: auto;
    border: none;
    box-shadow: 0 0 8px rgba(0, 212, 255, 0.5);
}

.timeline-range-slider::-webkit-slider-runnable-track {
    height: 4px;
    background: var(--border-color);
    border-radius: 2px;
}

.timeline-range-slider::-moz-range-track {
    height: 4px;
    background: var(--border-color);
    border-radius: 2px;
}

.timeline-legend {
    display: flex;
    justify-content: center;
    gap: var(--spacing-lg);
    font-size: 10px;
    color: var(--text-muted);
    font-family: var(--font-mono);
}

.timeline-legend .legend-item {
    display: flex;
    align-items: center;
    gap: var(--spacing-xs);
}

.timeline-legend .legend-bar {
    display: inline-block;
    width: 16px;
    height: 10px;
    border-radius: 2px;
}

.timeline-legend .legend-bar.low {
    background: rgba(0, 212, 255, 0.2);
}

.timeline-legend .legend-bar.medium {
    background: rgba(0, 212, 255, 0.5);
}

.timeline-legend .legend-bar.high {
    background: rgba(0, 212, 255, 0.9);
}
```

#### Acceptance Criteria

- [x] Timeline container visible below entity graph
- [x] SIGINT theme styling applied consistently
- [x] Range sliders visible and draggable (UI only, no functionality yet)
- [x] Date display shows placeholder text "--"
- [x] Legend shows activity levels with colored bars
- [x] Period selector dropdown shows day/week options
- [x] Reset button visible with undo icon

---

### PULSE-VIZ-010a: TimelineRenderer Core

**ID:** PULSE-VIZ-010a
**Estimated Time:** 1.5 hours
**Dependencies:** PULSE-VIZ-009

#### Description

Create the `TimelineRenderer` class with canvas infrastructure: setup, retina display scaling, resize handling, and empty state rendering. This provides the foundation for bar rendering.

#### Files to Modify

| File | Changes |
|------|---------|
| `static/js/pulse-dashboard.js` | Add `TimelineRenderer` class (core methods only) |

#### Implementation Contract

```javascript
// Add to pulse-dashboard.js (before PulseDashboard class)

/**
 * PULSE-VIZ-010a: Timeline Canvas Renderer - Core Setup
 * Handles canvas infrastructure, scaling, and empty state
 */
class TimelineRenderer {
    constructor(canvasId, options = {}) {
        this.canvas = document.getElementById(canvasId);
        if (!this.canvas) {
            console.warn(`TimelineRenderer: Canvas #${canvasId} not found`);
            return;
        }

        this.ctx = this.canvas.getContext('2d');
        this.data = [];
        this.selectedRange = { start: 0, end: 100 }; // percentage

        // Configuration
        this.options = {
            backgroundColor: '#12121a',
            barColor: 'rgba(0, 212, 255, 0.7)',
            selectionColor: 'rgba(0, 212, 255, 0.15)',
            padding: { top: 10, right: 10, bottom: 20, left: 10 },
            ...options
        };

        // Initialize
        this.setupCanvas();

        // Bind resize handler with debounce
        this._resizeTimeout = null;
        window.addEventListener('resize', () => {
            clearTimeout(this._resizeTimeout);
            this._resizeTimeout = setTimeout(() => this.setupCanvas(), 100);
        });
    }

    /**
     * Set up canvas dimensions with retina display support
     */
    setupCanvas() {
        if (!this.canvas) return;

        const rect = this.canvas.parentElement.getBoundingClientRect();
        const dpr = window.devicePixelRatio || 1;

        // Set actual canvas size (scaled for retina)
        this.canvas.width = rect.width * dpr;
        this.canvas.height = rect.height * dpr;

        // Set display size
        this.canvas.style.width = rect.width + 'px';
        this.canvas.style.height = rect.height + 'px';

        // Scale context for retina
        this.ctx.scale(dpr, dpr);

        // Store logical dimensions
        this.width = rect.width;
        this.height = rect.height;

        // Re-render if we have data
        if (this.data.length > 0) {
            this.render();
        } else {
            this.renderEmptyState();
        }
    }

    /**
     * Store data for rendering (actual rendering in VIZ-010b)
     */
    setData(data) {
        this.data = data || [];

        if (this.data.length > 0) {
            // Calculate max values for normalization
            this.maxMentions = Math.max(...this.data.map(d => d.mention_count || 0), 1);
            this.maxEntities = Math.max(...this.data.map(d => d.entity_count || 0), 1);
        }

        this.render();
    }

    /**
     * Set selected range for highlight rendering
     */
    setSelectedRange(startPercent, endPercent) {
        this.selectedRange = {
            start: Math.min(startPercent, endPercent),
            end: Math.max(startPercent, endPercent)
        };
        this.render();
    }

    /**
     * Main render entry point
     */
    render() {
        if (!this.ctx) return;

        const { ctx, width, height, options } = this;

        // Clear canvas with background
        ctx.fillStyle = options.backgroundColor;
        ctx.fillRect(0, 0, width, height);

        if (this.data.length === 0) {
            this.renderEmptyState();
            return;
        }

        // Bar rendering implemented in VIZ-010b
        this.renderBars();
    }

    /**
     * Render empty state message
     */
    renderEmptyState() {
        const { ctx, width, height, options } = this;

        ctx.fillStyle = options.backgroundColor;
        ctx.fillRect(0, 0, width, height);

        ctx.fillStyle = 'rgba(255, 255, 255, 0.3)';
        ctx.font = '12px "JetBrains Mono", monospace';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText('No activity data available', width / 2, height / 2);
    }

    /**
     * Placeholder for bar rendering (implemented in VIZ-010b)
     */
    renderBars() {
        // Implemented in PULSE-VIZ-010b
        console.log('TimelineRenderer: renderBars() - implement in VIZ-010b');
    }

    /**
     * Get data point at x position (for hover/click handling in VIZ-012)
     */
    getDateAtPosition(x) {
        if (!this.data.length) return null;

        const { padding } = this.options;
        const chartWidth = this.width - padding.left - padding.right;
        const percent = (x - padding.left) / chartWidth;
        const index = Math.floor(percent * this.data.length);

        if (index >= 0 && index < this.data.length) {
            return this.data[index];
        }
        return null;
    }
}
```

#### Acceptance Criteria

- [x] `TimelineRenderer` class instantiates without errors
- [x] Canvas scales correctly for retina displays (devicePixelRatio)
- [x] Canvas resizes properly when window resizes (debounced)
- [x] Empty state shows "No activity data available" centered
- [x] `setData()` stores data and triggers render
- [x] `setSelectedRange()` stores selection range
- [x] `getDateAtPosition()` returns correct data point for x coordinate

---

### PULSE-VIZ-010b: Timeline Bar Rendering

**ID:** PULSE-VIZ-010b
**Estimated Time:** 2 hours
**Dependencies:** PULSE-VIZ-010a

#### Description

Implement the bar chart rendering with intensity-based colors, selection highlight overlay, axis labels, and new-entity indicators.

#### Files to Modify

| File | Changes |
|------|---------|
| `static/js/pulse-dashboard.js` | Implement `renderBars()` and helper methods in `TimelineRenderer` |

#### Implementation Contract

```javascript
// Replace renderBars() placeholder and add these methods to TimelineRenderer class

/**
 * PULSE-VIZ-010b: Render activity bars with intensity coloring
 */
renderBars() {
    const { ctx, width, height, data, options } = this;
    const { padding } = options;

    const chartWidth = width - padding.left - padding.right;
    const chartHeight = height - padding.top - padding.bottom;
    const barWidth = Math.max(2, (chartWidth / data.length) - 1);
    const barGap = 1;

    // Draw selection highlight first (behind bars)
    this.drawSelectionHighlight(chartWidth, chartHeight, padding);

    // Draw bars
    data.forEach((item, index) => {
        const x = padding.left + (index * (barWidth + barGap));
        const intensity = (item.mention_count || 0) / this.maxMentions;
        const barHeight = Math.max(2, intensity * chartHeight);
        const y = padding.top + (chartHeight - barHeight);

        // Bar color based on intensity
        ctx.fillStyle = this.getIntensityColor(intensity);
        ctx.fillRect(x, y, barWidth, barHeight);

        // New entity indicator (amber dot above bar)
        if (item.new_entities > 0) {
            ctx.fillStyle = '#ff6b00';
            ctx.beginPath();
            ctx.arc(x + barWidth / 2, y - 4, 2, 0, Math.PI * 2);
            ctx.fill();
        }
    });

    // Draw axis labels
    this.drawAxisLabels(chartWidth, chartHeight, padding);
}

/**
 * Get color based on activity intensity (0-1)
 */
getIntensityColor(intensity) {
    // Alpha ranges from 0.2 (low) to 0.95 (high)
    const alpha = 0.2 + (intensity * 0.75);
    return `rgba(0, 212, 255, ${alpha.toFixed(2)})`;
}

/**
 * Draw selection highlight overlay (dims areas outside selection)
 */
drawSelectionHighlight(chartWidth, chartHeight, padding) {
    const { ctx, selectedRange, options } = this;

    // Skip if full range selected
    if (selectedRange.start === 0 && selectedRange.end === 100) {
        return;
    }

    const startX = padding.left + (selectedRange.start / 100) * chartWidth;
    const endX = padding.left + (selectedRange.end / 100) * chartWidth;

    // Dim areas outside selection
    ctx.fillStyle = 'rgba(0, 0, 0, 0.5)';

    // Left dimmed area
    if (startX > padding.left) {
        ctx.fillRect(padding.left, padding.top, startX - padding.left, chartHeight);
    }

    // Right dimmed area
    const rightStart = endX;
    const rightWidth = (padding.left + chartWidth) - endX;
    if (rightWidth > 0) {
        ctx.fillRect(rightStart, padding.top, rightWidth, chartHeight);
    }

    // Selection border
    ctx.strokeStyle = options.barColor;
    ctx.lineWidth = 1;
    ctx.strokeRect(startX, padding.top, endX - startX, chartHeight);
}

/**
 * Draw x-axis date labels (first, middle, last)
 */
drawAxisLabels(chartWidth, chartHeight, padding) {
    const { ctx, data, height } = this;

    if (data.length === 0) return;

    ctx.fillStyle = 'rgba(255, 255, 255, 0.5)';
    ctx.font = '10px "JetBrains Mono", monospace';

    const formatDate = (dateStr) => {
        if (!dateStr) return '';
        const d = new Date(dateStr);
        return `${d.getMonth() + 1}/${d.getDate()}`;
    };

    const labelY = height - 4;

    // First date (left-aligned)
    ctx.textAlign = 'left';
    ctx.fillText(formatDate(data[0].date), padding.left, labelY);

    // Last date (right-aligned)
    ctx.textAlign = 'right';
    ctx.fillText(formatDate(data[data.length - 1].date), this.width - padding.right, labelY);

    // Middle date (center-aligned)
    if (data.length > 2) {
        const midIndex = Math.floor(data.length / 2);
        ctx.textAlign = 'center';
        ctx.fillText(formatDate(data[midIndex].date), this.width / 2, labelY);
    }
}

/**
 * Convert percentage position to date data
 */
percentToDate(percent) {
    if (!this.data.length) return null;

    const index = Math.floor((percent / 100) * (this.data.length - 1));
    const clampedIndex = Math.max(0, Math.min(index, this.data.length - 1));
    return this.data[clampedIndex];
}

/**
 * Convert date to percentage position
 */
dateToPercent(dateStr) {
    if (!this.data.length) return 0;

    const targetDate = new Date(dateStr).getTime();
    const startDate = new Date(this.data[0].date).getTime();
    const endDate = new Date(this.data[this.data.length - 1].date).getTime();
    const range = endDate - startDate;

    if (range === 0) return 50;
    return ((targetDate - startDate) / range) * 100;
}
```

#### Acceptance Criteria

- [x] Bars render for each data point
- [x] Bar height reflects mention_count (normalized to max)
- [x] Bar color intensity reflects relative activity (0.2-0.95 alpha)
- [x] New entity indicator (amber dot) appears on bars with new_entities > 0
- [x] Selection highlight dims areas outside selected range
- [x] Selection has cyan border
- [x] Date labels appear: first (left), middle (center), last (right)
- [x] `percentToDate()` and `dateToPercent()` convert correctly

---

### PULSE-VIZ-010c: Timeline Data Integration

**ID:** PULSE-VIZ-010c
**Estimated Time:** 1 hour
**Dependencies:** PULSE-VIZ-010b, PULSE-VIZ-008

#### Description

Integrate `TimelineRenderer` with `PulseDashboard`: add initialization method, API data loading, date display updates, and period selector handling.

#### Files to Modify

| File | Changes |
|------|---------|
| `static/js/pulse-dashboard.js` | Add `initTimeline()`, `loadTimelineData()`, `updateDateDisplay()` to PulseDashboard |

#### Implementation Contract

```javascript
// Add these methods to PulseDashboard class

/**
 * PULSE-VIZ-010c: Initialize timeline component
 * Called during dashboard initialization when Network view loads
 */
async initTimeline() {
    const container = document.getElementById('entity-timeline-container');
    if (!container) {
        this.log('warning', 'Timeline container not found');
        return;
    }

    // Create timeline renderer instance
    this.timelineRenderer = new TimelineRenderer('entity-timeline-canvas');

    if (!this.timelineRenderer.canvas) {
        this.log('error', 'Failed to initialize TimelineRenderer');
        return;
    }

    // Load initial data
    await this.loadTimelineData();

    // Set up period selector change handler
    const periodSelect = document.getElementById('timeline-period-select');
    if (periodSelect) {
        periodSelect.addEventListener('change', () => {
            this.loadTimelineData();
        });
    }

    // Set up reset button (full functionality in VIZ-011)
    const resetBtn = document.getElementById('timeline-reset');
    if (resetBtn) {
        resetBtn.addEventListener('click', () => {
            this.resetTimelineSelection();
        });
    }

    this.log('success', 'Timeline initialized');
}

/**
 * Load timeline data from API
 */
async loadTimelineData() {
    try {
        const periodSelect = document.getElementById('timeline-period-select');
        const period = periodSelect?.value || 'day';

        this.log('info', `Loading timeline data (period: ${period})`);

        const response = await this.fetchApi(`/network/timeline?period=${period}&days=90`);

        if (response && response.data) {
            // Store data for filtering
            this.timelineData = response.data;

            // Update renderer
            this.timelineRenderer.setData(response.data);

            // Update date display
            this.updateDateDisplay(response.start_date, response.end_date);

            this.log('success', `Loaded ${response.data.length} timeline data points`);
        } else {
            this.log('warning', 'No timeline data returned from API');
            this.timelineRenderer.setData([]);
        }
    } catch (error) {
        this.log('error', `Failed to load timeline: ${error.message}`);
        this.timelineRenderer.setData([]);
    }
}

/**
 * Update the date display labels
 */
updateDateDisplay(startDate, endDate) {
    const startEl = document.getElementById('timeline-start-date');
    const endEl = document.getElementById('timeline-end-date');

    const formatDate = (dateStr) => {
        if (!dateStr) return '--';
        return new Date(dateStr).toLocaleDateString();
    };

    if (startEl) {
        startEl.textContent = formatDate(startDate);
    }
    if (endEl) {
        endEl.textContent = formatDate(endDate);
    }
}

/**
 * Reset timeline selection (placeholder - full implementation in VIZ-011)
 */
resetTimelineSelection() {
    // Reset sliders to full range
    const startSlider = document.getElementById('timeline-range-start');
    const endSlider = document.getElementById('timeline-range-end');

    if (startSlider) startSlider.value = 0;
    if (endSlider) endSlider.value = 100;

    // Reset renderer highlight
    if (this.timelineRenderer) {
        this.timelineRenderer.setSelectedRange(0, 100);
    }

    // Reset date display to full range
    if (this.timelineData && this.timelineData.length > 0) {
        this.updateDateDisplay(
            this.timelineData[0].date,
            this.timelineData[this.timelineData.length - 1].date
        );
    }

    this.log('info', 'Timeline selection reset');
}
```

#### Call initTimeline from Network View Initialization

```javascript
// In the method that initializes the Network view (e.g., showView or loadNetworkGraph)
// Add after graph initialization:

// Initialize timeline if not already done
if (!this.timelineRenderer) {
    await this.initTimeline();
}
```

#### Acceptance Criteria

- [x] `initTimeline()` creates TimelineRenderer instance
- [x] Timeline data loads from `/api/v1/network/timeline` on init
- [x] Period selector (day/week) triggers data reload
- [x] Date display shows start and end dates from API response
- [x] Reset button resets sliders to 0/100 and clears highlight
- [x] Error handling shows empty state on API failure
- [x] Log messages indicate timeline status

---

### PULSE-VIZ-011: Time Range Filter

**ID:** PULSE-VIZ-011
**Estimated Time:** 2 hours
**Dependencies:** PULSE-VIZ-010c

#### Description

Add `filterGraphToTimeRange(startDate, endDate)` method that filters the entity graph to only show nodes active within the selected time range. Nodes outside the range are hidden.

#### Files to Modify

| File | Changes |
|------|---------|
| `static/js/pulse-dashboard.js` | Add time range filtering methods to PulseDashboard |

#### Implementation Contract

```javascript
// Add these methods to PulseDashboard class

/**
 * PULSE-VIZ-011: Filter graph to show only entities active in time range
 * @param {Date|string} startDate - Start of time range
 * @param {Date|string} endDate - End of time range
 */
filterGraphToTimeRange(startDate, endDate) {
    const graph = this.currentGraph;
    const sigma = this.currentSigma;

    if (!graph || !sigma) {
        this.log('warning', 'Cannot filter: Graph not initialized');
        return;
    }

    const start = new Date(startDate).getTime();
    const end = new Date(endDate).getTime();

    this.log('info', `Filtering graph: ${new Date(start).toLocaleDateString()} - ${new Date(end).toLocaleDateString()}`);

    // Determine which entities are active in this time range
    const activeEntityIds = new Set();

    graph.forEachNode((nodeId, attrs) => {
        // Get temporal bounds for this entity
        const firstSeen = attrs.firstSeen ? new Date(attrs.firstSeen).getTime() : 0;
        const lastSeen = attrs.lastSeen ? new Date(attrs.lastSeen).getTime() : Date.now();

        // Entity is visible if its activity window overlaps with selection
        // Overlap: entity was seen before selection ends AND last seen after selection starts
        const overlaps = (firstSeen <= end) && (lastSeen >= start);

        if (overlaps) {
            activeEntityIds.add(nodeId);
        }
    });

    // Apply visibility to nodes
    graph.forEachNode((nodeId) => {
        const isActive = activeEntityIds.has(nodeId);
        graph.setNodeAttribute(nodeId, 'hidden', !isActive);
    });

    // Hide edges where either endpoint is hidden
    graph.forEachEdge((edgeId, attrs, source, target) => {
        const sourceVisible = activeEntityIds.has(source);
        const targetVisible = activeEntityIds.has(target);
        graph.setEdgeAttribute(edgeId, 'hidden', !sourceVisible || !targetVisible);
    });

    // Refresh render
    sigma.refresh();

    // Log stats
    const visibleCount = activeEntityIds.size;
    const totalCount = graph.order;
    this.log('info', `Showing ${visibleCount}/${totalCount} entities in time range`);

    // Store current filter state
    this.timeFilterRange = { start: startDate, end: endDate };
}

/**
 * Clear time range filter and show all entities
 */
clearTimeRangeFilter() {
    const graph = this.currentGraph;
    const sigma = this.currentSigma;

    if (!graph || !sigma) return;

    // Don't clear if there's a click-locked focus (respect isolation)
    if (this.focusedEntityId) {
        this.log('info', 'Time filter clear skipped: entity focus is active');
        return;
    }

    // Show all nodes
    graph.forEachNode((nodeId) => {
        graph.setNodeAttribute(nodeId, 'hidden', false);
    });

    // Show all edges
    graph.forEachEdge((edgeId) => {
        graph.setEdgeAttribute(edgeId, 'hidden', false);
    });

    sigma.refresh();

    this.timeFilterRange = null;
    this.log('info', 'Time range filter cleared - showing all entities');
}

/**
 * Enhanced reset that clears filter and restores full view
 */
resetTimelineSelection() {
    // Reset sliders
    const startSlider = document.getElementById('timeline-range-start');
    const endSlider = document.getElementById('timeline-range-end');

    if (startSlider) startSlider.value = 0;
    if (endSlider) endSlider.value = 100;

    // Clear graph filter
    this.clearTimeRangeFilter();

    // Reset timeline highlight
    if (this.timelineRenderer) {
        this.timelineRenderer.setSelectedRange(0, 100);
    }

    // Reset date display to full range
    if (this.timelineData && this.timelineData.length > 0) {
        this.updateDateDisplay(
            this.timelineData[0].date,
            this.timelineData[this.timelineData.length - 1].date
        );
    }

    this.log('info', 'Timeline selection reset to full range');
}
```

#### Ensure Graph Nodes Have Temporal Attributes

The graph data must include `firstSeen` and `lastSeen` on nodes. Update the graph loading code:

```javascript
// In loadNetworkGraph() or wherever nodes are added to the graph:

// When processing node data from API:
graph.addNode(nodeId, {
    label: nodeData.name,
    entityType: nodeData.entity_type,
    // ... other attributes ...

    // Temporal attributes for filtering
    firstSeen: nodeData.first_seen || nodeData.created_at,
    lastSeen: nodeData.last_seen || nodeData.created_at
});
```

#### Acceptance Criteria

- [x] `filterGraphToTimeRange(start, end)` hides nodes outside date range
- [x] Nodes with overlapping activity window remain visible
- [x] Edges are hidden when either endpoint is hidden
- [x] `clearTimeRangeFilter()` shows all nodes/edges
- [x] Filter respects existing focus isolation (doesn't override click-lock)
- [x] `resetTimelineSelection()` clears filter and resets UI
- [x] Stats logged: "Showing X/Y entities in time range"

---

### PULSE-VIZ-012: Timeline-Graph Sync

**ID:** PULSE-VIZ-012
**Estimated Time:** 2 hours
**Dependencies:** PULSE-VIZ-011

#### Description

Wire the timeline slider controls to the graph filter. When users drag the range sliders, the graph filters in real-time. Clicking a bar on the timeline should center the selection on that period.

#### Files to Modify

| File | Changes |
|------|---------|
| `static/js/pulse-dashboard.js` | Add event handlers for slider and canvas interactions |

#### Implementation Contract

```javascript
// Add to PulseDashboard class

/**
 * PULSE-VIZ-012: Set up timeline-graph synchronization
 * Call this at the end of initTimeline()
 */
setupTimelineSync() {
    const startSlider = document.getElementById('timeline-range-start');
    const endSlider = document.getElementById('timeline-range-end');
    const canvas = document.getElementById('entity-timeline-canvas');

    if (!startSlider || !endSlider) {
        this.log('warning', 'Timeline sliders not found');
        return;
    }

    // Slider change handler
    const handleSliderChange = () => {
        let startPercent = parseInt(startSlider.value);
        let endPercent = parseInt(endSlider.value);

        // Enforce start <= end
        if (startPercent > endPercent) {
            if (document.activeElement === startSlider) {
                endSlider.value = startPercent;
                endPercent = startPercent;
            } else {
                startSlider.value = endPercent;
                startPercent = endPercent;
            }
        }

        this.onTimelineRangeChange(startPercent, endPercent);
    };

    // Real-time updates on slider drag
    startSlider.addEventListener('input', handleSliderChange);
    endSlider.addEventListener('input', handleSliderChange);

    // Canvas click - center selection on clicked position
    if (canvas) {
        canvas.addEventListener('click', (e) => {
            const rect = canvas.getBoundingClientRect();
            const x = e.clientX - rect.left;
            const clickPercent = (x / rect.width) * 100;

            // Center a ~15% window (roughly 2 weeks in 90 days)
            const windowSize = 15;
            const newStart = Math.max(0, clickPercent - windowSize / 2);
            const newEnd = Math.min(100, clickPercent + windowSize / 2);

            startSlider.value = newStart;
            endSlider.value = newEnd;

            this.onTimelineRangeChange(newStart, newEnd);
        });

        // Canvas hover - show date/count tooltip
        canvas.addEventListener('mousemove', (e) => {
            if (!this.timelineRenderer) return;

            const rect = canvas.getBoundingClientRect();
            const x = e.clientX - rect.left;
            const data = this.timelineRenderer.getDateAtPosition(x);

            if (data) {
                const date = new Date(data.date).toLocaleDateString();
                canvas.title = `${date}: ${data.mention_count} mentions, ${data.entity_count} entities`;
            } else {
                canvas.title = '';
            }
        });

        // Clear tooltip on mouse leave
        canvas.addEventListener('mouseleave', () => {
            canvas.title = '';
        });
    }

    this.log('info', 'Timeline-graph sync initialized');
}

/**
 * Handle timeline range changes from sliders or clicks
 */
onTimelineRangeChange(startPercent, endPercent) {
    if (!this.timelineData || this.timelineData.length === 0) {
        return;
    }

    // Update timeline highlight
    if (this.timelineRenderer) {
        this.timelineRenderer.setSelectedRange(startPercent, endPercent);
    }

    // Convert percentages to data indices
    const dataLength = this.timelineData.length;
    const startIndex = Math.floor((startPercent / 100) * (dataLength - 1));
    const endIndex = Math.ceil((endPercent / 100) * (dataLength - 1));

    // Get dates from data
    const startData = this.timelineData[Math.max(0, startIndex)];
    const endData = this.timelineData[Math.min(dataLength - 1, endIndex)];

    const startDate = startData?.date;
    const endDate = endData?.date;

    // Update date display
    this.updateDateDisplay(startDate, endDate);

    // Debounce graph filter updates for performance
    clearTimeout(this._timelineFilterTimeout);
    this._timelineFilterTimeout = setTimeout(() => {
        if (startDate && endDate) {
            this.filterGraphToTimeRange(startDate, endDate);
        }
    }, 100);
}
```

#### Update initTimeline to call setupTimelineSync

```javascript
async initTimeline() {
    // ... existing code ...

    // PULSE-VIZ-012: Set up timeline-graph sync (add at end)
    this.setupTimelineSync();
}
```

#### Acceptance Criteria

- [x] Dragging start slider updates graph filter in real-time
- [x] Dragging end slider updates graph filter in real-time
- [x] Sliders cannot cross (start <= end enforced)
- [x] Date display updates as sliders move
- [x] Clicking timeline canvas centers a ~2-week window on that position
- [x] Hovering timeline shows tooltip: "date: X mentions, Y entities"
- [x] Filter updates are debounced (100ms) for smooth performance
- [x] Mouse leave clears tooltip

---

## Dependency Graph

```
PULSE-VIZ-008 (API - Phase 2 Backend) ─────────────────────────┐
                                                               │
Phase 1 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━│━
                                                               │
PULSE-VIZ-009 ─────────────────────────────────────────────┐   │
(Container HTML/CSS)                                       │   │
                                                           ▼   │
Phase 2 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━│━━━│━
                                                           │   │
PULSE-VIZ-010a ──► PULSE-VIZ-010b ─────────────────────────┤   │
(Core Setup)       (Bar Rendering)                         │   │
                                                           ▼   │
Phase 3 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━│━━━│━
                                                           │   │
                   PULSE-VIZ-010c ◄────────────────────────┼───┘
                   (Data Integration)                      │
                          │                                │
                          ▼                                │
                   PULSE-VIZ-011 ──────────────────────────┤
                   (Time Range Filter)                     │
                                                           ▼
Phase 4 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━│━━━━
                                                           │
                   PULSE-VIZ-012 ◄─────────────────────────┘
                   (Timeline-Graph Sync)
```

---

## Implementation Order

### Step 1: HTML/CSS Setup (1 hour)
```
PULSE-VIZ-009
```
**Deliverable:** Timeline container visible below graph with SIGINT styling

### Step 2: Canvas Core (1.5 hours)
```
PULSE-VIZ-010a
```
**Deliverable:** TimelineRenderer class with canvas setup, retina support, empty state

### Step 3: Bar Rendering (2 hours)
```
PULSE-VIZ-010b
```
**Deliverable:** Activity bars render with intensity colors, selection highlight, axis labels

### Step 4: Data Integration (1 hour)
```
PULSE-VIZ-010c
```
**Deliverable:** Timeline loads data from API, period selector works, date display updates

### Step 5: Graph Filtering (2 hours)
```
PULSE-VIZ-011
```
**Deliverable:** `filterGraphToTimeRange()` hides/shows nodes based on temporal overlap

### Step 6: User Interaction (2 hours)
```
PULSE-VIZ-012
```
**Deliverable:** Sliders and clicks filter graph in real-time, hover tooltips work

---

## Testing Commands

```bash
# Ensure Phase 2 migration ran
psql -U postgres -d research_platform -c "SELECT COUNT(*) FROM tracked_entities WHERE first_seen IS NOT NULL"

# Test timeline API
curl http://localhost:8000/api/v1/network/timeline?period=day&days=30

# Test with weekly aggregation
curl http://localhost:8000/api/v1/network/timeline?period=week&days=90

# Check graph nodes have temporal data
curl http://localhost:8000/api/v1/network/graph | jq '.nodes[0] | {id, first_seen, last_seen}'
```

---

## Files to Modify Summary

| Feature | Files |
|---------|-------|
| PULSE-VIZ-009 | `templates/dashboard.html`, `static/css/sigint-theme.css` |
| PULSE-VIZ-010a | `static/js/pulse-dashboard.js` |
| PULSE-VIZ-010b | `static/js/pulse-dashboard.js` |
| PULSE-VIZ-010c | `static/js/pulse-dashboard.js` |
| PULSE-VIZ-011 | `static/js/pulse-dashboard.js` |
| PULSE-VIZ-012 | `static/js/pulse-dashboard.js` |

---

## Summary

| Metric | Value |
|--------|-------|
| **Total Features** | 6 |
| **Features Complete** | 6/6 (100%) |
| **Total Estimated Time** | 9.5 hours |
| **Actual Time** | ~2 hours |
| **Files Modified** | 3 |
| **API Dependencies** | 1 (PULSE-VIZ-008) |

---

## Implementation Order (Completed)

```
VIZ-009 → VIZ-010a → VIZ-010b → VIZ-010c → VIZ-011 → VIZ-012
   ✓         ✓          ✓           ✓          ✓         ✓
```

All features implemented in a single session on 2026-01-16.

---

*Generated: 2026-01-16*
*Completed: 2026-01-16*
*Refined with /atomic skill*
*Parent: [ATOMIC_entity-graph-visualization-soa_2026-01-15.md](./ATOMIC_entity-graph-visualization-soa_2026-01-15.md)*
