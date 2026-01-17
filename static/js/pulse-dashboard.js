/**
 * The Pulse - Intelligence Dashboard
 * Main JavaScript controller for the SIGINT-themed dashboard
 */

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
}

class PulseDashboard {
    constructor() {
        // API endpoints
        this.apiBase = '/api/v1';

        // WebSocket connection
        this.ws = null;
        this.wsReconnectAttempts = 0;
        this.maxReconnectAttempts = 5;
        this.wsReconnectDelay = 2000;

        // State
        this.currentView = 'briefing';
        this.currentBriefing = null;
        this.collectors = [];
        this.entities = [];
        this.newsItems = [];
        this.activityLog = [];

        // Local Government state
        this.watchAreas = [];
        this.localAlerts = [];
        this.localStats = null;

        // Sigma.js graph instances
        this.graph = null;
        this.sigma = null;
        this.graphMini = null;
        this.sigmaMini = null;
        this.graphFullscreen = null;
        this.sigmaFullscreen = null;
        this.clusters = [];  // For semantic zoom
        this._refreshScheduled = false;  // PERF-004: Batch refresh flag

        // Entity list state
        this.entityListState = {
            page: 1,
            perPage: 50,
            sortBy: 'mentions',
            typeFilter: '',
            searchQuery: '',
            selected: new Set(),
            total: 0
        };

        // Graph state
        this.graphDepth = 1;
        this.graphSearchTimeout = null;
        this.focusedEntityId = null;  // For filter-on-double-click

        // Audio
        this.audioElement = null;
        this.isPlaying = false;

        // Initialize
        this.init();
    }

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

    async init() {
        this.log('info', 'Initializing The Pulse Dashboard...');

        // Set up UI
        this.setupEventListeners();
        this.startClock();

        // Connect WebSocket
        this.connectWebSocket();

        // Load initial data (entities and graph loaded on-demand in Entities view)
        await Promise.all([
            this.loadCollectorStatus(),
            this.loadLatestBriefing(),
            this.loadRecentItems(),
            this.loadStats(),
            this.loadBriefingArchive(),
            this.loadLocalAlerts(),
            this.loadWatchAreas(),
            this.loadLocalStats(),
            this.loadRecentActivity()  // Populate timeline on init
        ]);

        this.log('success', 'Dashboard initialized successfully');
    }

    // =============================================
    // WEBSOCKET CONNECTION
    // =============================================

    connectWebSocket() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/api/v1/websocket/ws`;

        try {
            this.ws = new WebSocket(wsUrl);

            this.ws.onopen = () => {
                this.log('success', 'WebSocket connected');
                this.wsReconnectAttempts = 0;
                this.updateSystemHealth('healthy');
            };

            this.ws.onmessage = (event) => {
                this.handleWebSocketMessage(event.data);
            };

            this.ws.onclose = () => {
                this.log('warn', 'WebSocket disconnected');
                this.updateSystemHealth('warning');
                this.attemptReconnect();
            };

            this.ws.onerror = (error) => {
                this.log('error', 'WebSocket error');
                console.error('WebSocket error:', error);
            };
        } catch (error) {
            this.log('error', `Failed to connect: ${error.message}`);
            this.attemptReconnect();
        }
    }

    attemptReconnect() {
        if (this.wsReconnectAttempts < this.maxReconnectAttempts) {
            this.wsReconnectAttempts++;
            this.log('info', `Reconnecting... (${this.wsReconnectAttempts}/${this.maxReconnectAttempts})`);
            setTimeout(() => this.connectWebSocket(), this.wsReconnectDelay * this.wsReconnectAttempts);
        } else {
            this.log('error', 'Max reconnection attempts reached');
            this.updateSystemHealth('error');
        }
    }

    handleWebSocketMessage(data) {
        try {
            const message = JSON.parse(data);
            const { type, payload } = message;

            switch (type) {
                case 'collection.started':
                    this.log('info', `Collection started: ${payload.collector}`);
                    this.updateCollectorStatus(payload.collector, 'running');
                    break;

                case 'collection.completed':
                    this.log('success', `Collection completed: ${payload.collector} (${payload.new_items} new)`);
                    this.updateCollectorStatus(payload.collector, 'healthy');
                    this.addTimelineEvent('collection', `${payload.collector}: ${payload.new_items} new items`);
                    this.loadStats();
                    break;

                case 'collection.failed':
                    this.log('error', `Collection failed: ${payload.collector}`);
                    this.updateCollectorStatus(payload.collector, 'error');
                    break;

                case 'processing.completed':
                    this.log('success', `Processing completed: ${payload.processed} items`);
                    this.addTimelineEvent('processing', `Processed ${payload.processed} items`);
                    break;

                case 'briefing.started':
                    this.log('info', 'Briefing generation started');
                    break;

                case 'briefing.completed':
                    this.log('success', 'Briefing generated');
                    this.loadLatestBriefing();
                    this.addTimelineEvent('briefing', 'New briefing generated');
                    break;

                case 'entity.detected':
                    this.addTimelineEvent('entity', `Entity detected: ${payload.name}`);
                    break;

                case 'system.status':
                    this.updateSystemHealth(payload.status);
                    break;

                // Local Government events
                case 'local.alert':
                    this.handleLocalAlert(payload);
                    break;

                case 'local.watch_triggered':
                    this.log('info', `Watch area triggered: ${payload.area_name}`);
                    this.addTimelineEvent('local', `Activity in ${payload.area_name}: ${payload.type}`);
                    this.loadLocalAlerts();
                    break;

                case 'local.collection_completed':
                    this.log('success', `Local data collected: ${payload.source}`);
                    this.loadLocalStats();
                    break;

                default:
                    console.log('Unknown message type:', type, payload);
            }
        } catch (error) {
            console.error('Failed to parse WebSocket message:', error);
        }
    }

    // =============================================
    // API CALLS
    // =============================================

    async fetchApi(endpoint, options = {}) {
        try {
            const response = await fetch(`${this.apiBase}${endpoint}`, {
                ...options,
                headers: {
                    'Content-Type': 'application/json',
                    ...options.headers
                }
            });

            // Handle queued status (202)
            if (response.status === 202) {
                const data = await response.json();
                data._status = 202;
                return data;
            }

            if (!response.ok) {
                // Extract error detail from response
                let errorDetail;
                try {
                    const data = await response.json();
                    errorDetail = data.detail || data.message || `HTTP ${response.status}`;
                } catch {
                    errorDetail = `HTTP ${response.status}`;
                }

                // Create typed error
                const error = new Error(errorDetail);
                error.status = response.status;
                error.isApiError = true;
                throw error;
            }

            return await response.json();
        } catch (error) {
            if (!error.isApiError) {
                error.message = 'Network error - check connection';
                error.status = 0;
            }
            console.error(`API request failed: ${endpoint}`, error);
            throw error;
        }
    }

    // =============================================
    // TOAST NOTIFICATIONS
    // =============================================

    showToast(type, message, duration = 5000) {
        const container = document.getElementById('toast-container');
        if (!container) {
            // Fallback to console log if toast container doesn't exist
            console.log(`[${type.toUpperCase()}] ${message}`);
            return;
        }

        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;
        toast.innerHTML = `
            <i class="fas ${this.getToastIcon(type)}"></i>
            <span class="toast-message">${message}</span>
            <button class="toast-close" onclick="this.parentElement.remove()">
                <i class="fas fa-times"></i>
            </button>
        `;
        container.appendChild(toast);

        // Auto-dismiss
        setTimeout(() => {
            if (toast.parentElement) {
                toast.remove();
            }
        }, duration);
    }

    getToastIcon(type) {
        const icons = {
            error: 'fa-exclamation-circle',
            warning: 'fa-exclamation-triangle',
            success: 'fa-check-circle',
            info: 'fa-info-circle'
        };
        return icons[type] || icons.info;
    }

    getErrorMessage(error) {
        if (error.status === 429) return 'Rate limited - please wait before trying again';
        if (error.status === 404) return 'Resource not found';
        if (error.status === 0) return 'Connection failed - check network';
        if (error.status === 500) return error.message || 'Server error occurred';
        return error.message || 'An unexpected error occurred';
    }

    // =============================================
    // BUTTON LOADING STATES
    // =============================================

    setButtonLoading(buttonId, loading) {
        const button = document.getElementById(buttonId);
        if (!button) return;

        if (loading) {
            button.disabled = true;
            button.dataset.originalHtml = button.innerHTML;
            button.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Working...';
        } else {
            button.disabled = false;
            if (button.dataset.originalHtml) {
                button.innerHTML = button.dataset.originalHtml;
            }
        }
    }

    async loadCollectorStatus() {
        try {
            const status = await this.fetchApi('/collection/status');
            this.collectors = status.collectors || [];
            this.renderCollectorStatus();
        } catch (error) {
            this.log('error', 'Failed to load collector status');
        }
    }

    async loadLatestBriefing() {
        try {
            const briefing = await this.fetchApi('/synthesis/briefings/latest');
            this.currentBriefing = briefing;
            this.renderBriefing(briefing);
        } catch (error) {
            // No briefing available
            this.showBriefingEmpty();
        }
    }

    async loadEntities() {
        try {
            const response = await this.fetchApi('/entities');
            // API returns array directly, not wrapped in {entities: [...]}
            this.entities = Array.isArray(response) ? response : (response.entities || []);
            this.renderTrendingEntities();
            this.updateEntityGraph();
        } catch (error) {
            console.error('Failed to load entities:', error);
            this.entities = [];
            this.renderTrendingEntities();
        }
    }

    async loadRecentItems() {
        try {
            // Load all items with pagination (no time limit)
            // First request gets count and initial items
            const response = await this.fetchApi('/collection/items?limit=500');

            // Handle both array response (legacy) and paginated response
            if (Array.isArray(response)) {
                this.newsItems = response;
            } else {
                this.newsItems = response.items || [];

                // If there are more items, load additional pages
                if (response.has_more && response.total > 500) {
                    let offset = 500;
                    const maxItems = 2000; // Cap at 2000 items to prevent UI slowdown

                    while (offset < response.total && offset < maxItems) {
                        const nextPage = await this.fetchApi(`/collection/items?limit=500&offset=${offset}`);
                        if (nextPage.items && nextPage.items.length > 0) {
                            this.newsItems = this.newsItems.concat(nextPage.items);
                            offset += nextPage.items.length;
                        } else {
                            break;
                        }
                    }

                    console.log(`Loaded ${this.newsItems.length} of ${response.total} total items`);
                }
            }

            this.renderNewsFeed();
        } catch (error) {
            console.error('Failed to load recent items:', error);
        }
    }

    async loadStats() {
        try {
            const stats = await this.fetchApi('/collection/items/stats');
            this.renderStats(stats);
        } catch (error) {
            console.error('Failed to load stats:', error);
        }
    }

    async loadBriefingArchive() {
        try {
            const briefings = await this.fetchApi('/synthesis/briefings?limit=5');
            this.renderBriefingArchive(briefings.briefings || []);
        } catch (error) {
            console.error('Failed to load briefing archive:', error);
        }
    }

    async loadRecentActivity() {
        // Populate activity timeline with recent collection runs and events
        try {
            const runs = await this.fetchApi('/collection/runs?limit=10');
            const runsList = runs.runs || runs || [];

            // Add recent collection runs to timeline (most recent first)
            runsList.reverse().forEach(run => {
                if (run.status === 'completed') {
                    this.addTimelineEvent(
                        'collection',
                        `${run.collector_name}: ${run.items_new || 0} new items`,
                        run.completed_at ? `Completed ${this.formatTimeAgo(run.completed_at)}` : null
                    );
                } else if (run.status === 'failed') {
                    this.addTimelineEvent(
                        'error',
                        `${run.collector_name}: Collection failed`,
                        run.error_message ? run.error_message.substring(0, 50) : null
                    );
                }
            });

            // Render the populated timeline
            this.renderTimeline();
        } catch (error) {
            console.error('Failed to load recent activity:', error);
        }
    }

    formatTimeAgo(dateString) {
        const date = new Date(dateString);
        const now = new Date();
        const diffMs = now - date;
        const diffMins = Math.floor(diffMs / 60000);
        const diffHours = Math.floor(diffMins / 60);
        const diffDays = Math.floor(diffHours / 24);

        if (diffMins < 1) return 'just now';
        if (diffMins < 60) return `${diffMins}m ago`;
        if (diffHours < 24) return `${diffHours}h ago`;
        return `${diffDays}d ago`;
    }

    async runCollection(collectorName = null) {
        try {
            this.log('info', 'Starting collection...');
            const url = collectorName
                ? `/collection/run?collector_name=${encodeURIComponent(collectorName)}`
                : '/collection/run';
            await this.fetchApi(url, { method: 'POST' });
        } catch (error) {
            this.log('error', 'Failed to start collection');
        }
    }

    async generateBriefing() {
        const buttonId = 'btn-generate-briefing';
        const fallbackButtonId = 'btn-generate-first-briefing';
        this.setButtonLoading(buttonId, true);
        this.setButtonLoading(fallbackButtonId, true);

        try {
            this.log('info', 'Generating briefing...');
            this.showBriefingLoading();
            const briefing = await this.fetchApi('/synthesis/generate', {
                method: 'POST',
                body: JSON.stringify({
                    period_hours: 24,
                    include_audio: true
                })
            });
            this.currentBriefing = briefing;
            this.renderBriefing(briefing);
            this.log('success', 'Briefing generated successfully');
            this.showToast('success', 'Intelligence briefing generated successfully');
        } catch (error) {
            this.log('error', 'Failed to generate briefing');
            this.showToast('error', this.getErrorMessage(error) || 'Failed to generate briefing');
        } finally {
            this.setButtonLoading(buttonId, false);
            this.setButtonLoading(fallbackButtonId, false);
        }
    }

    async processItems() {
        try {
            this.log('info', 'Processing items...');
            await this.fetchApi('/processing/run', { method: 'POST' });
        } catch (error) {
            this.log('error', 'Failed to process items');
        }
    }

    async extractEntities() {
        const buttonId = 'btn-extract-entities';
        this.setButtonLoading(buttonId, true);

        try {
            this.log('info', 'Extracting entities from recent news...');
            const result = await this.fetchApi('/processing/extract-entities?hours=24&limit=50&auto_track=true', {
                method: 'POST'
            });

            // Handle queued response (202)
            if (result.status === 'queued' || result._status === 202) {
                const queuePos = result.queue_position || '?';
                this.showToast('info', `Extraction queued (position ${queuePos}). Another extraction is in progress.`);
                this.log('info', `Extraction queued at position ${queuePos}`);
                return;
            }

            // Handle success
            if (result.stats) {
                const { items_processed, unique_entities, new_entities_created, mentions_created } = result.stats;
                this.showToast('success', `Extracted ${unique_entities} entities from ${items_processed} items`);
                this.log('success', `Extracted ${unique_entities} unique entities from ${items_processed} items`);
                if (new_entities_created > 0) {
                    this.log('info', `Auto-tracked ${new_entities_created} new entities (${mentions_created} mentions)`);
                }
            }

            // Reload entities to show new ones
            await this.loadEntities();
            this.updateStats();

            // Refresh the entity graph if visible
            if (this.sigmaMini || this.sigma) {
                this.loadNetworkGraph();
            }

        } catch (error) {
            const message = this.getErrorMessage(error);
            this.showToast('error', message);
            this.log('error', 'Failed to extract entities: ' + message);
            console.error('Entity extraction failed:', error);
        } finally {
            this.setButtonLoading(buttonId, false);
        }
    }

    async bulkExtractEntities() {
        const buttonId = 'btn-bulk-extract';
        this.setButtonLoading(buttonId, true);

        try {
            this.log('info', 'Starting bulk entity extraction (no WikiData)...');
            const result = await this.fetchApi('/processing/extract-entities/bulk?hours=720&limit=500', {
                method: 'POST'
            });

            // Handle queued response
            if (result.status === 'queued' || result._status === 202) {
                this.showToast('info', `Bulk extraction queued. Another extraction is in progress.`);
                this.log('info', 'Bulk extraction queued');
                return;
            }

            if (result.stats) {
                const { items_processed, unique_entities, new_entities_created } = result.stats;
                this.showToast('success', `Extracted entities from ${items_processed} items (${new_entities_created} new)`);
                this.log('success', `Bulk extraction complete. Run "Enrich Entities" to add WikiData.`);
            }

            await this.loadEntities();
            this.updateStats();

        } catch (error) {
            const message = this.getErrorMessage(error);
            this.showToast('error', message);
            this.log('error', 'Bulk extraction failed: ' + message);
        } finally {
            this.setButtonLoading(buttonId, false);
        }
    }

    async enrichEntities() {
        const buttonId = 'btn-enrich-entities';
        this.setButtonLoading(buttonId, true);

        try {
            this.log('info', 'Enriching entities with WikiData...');
            const result = await this.fetchApi('/processing/enrich-entities?limit=100', {
                method: 'POST'
            });

            if (result.remaining > 0) {
                this.showToast('info', `Enriched ${result.enriched} entities. ${result.remaining} remaining.`);
                this.log('info', `${result.remaining} entities still need enrichment. Run again.`);
            } else {
                this.showToast('success', `All entities enriched with WikiData!`);
                this.log('success', 'All entities have WikiData metadata');
            }

            await this.loadEntities();

        } catch (error) {
            const message = this.getErrorMessage(error);
            this.showToast('error', message);
            this.log('error', 'Enrichment failed: ' + message);
        } finally {
            this.setButtonLoading(buttonId, false);
        }
    }

    async checkExtractionStatus() {
        try {
            const status = await this.fetchApi('/processing/extract-entities/status');
            if (status.is_active && status.active_task) {
                const { items_processed, items_total } = status.active_task;
                this.log('info', `Extraction in progress: ${items_processed}/${items_total} items`);
            } else {
                this.log('info', 'No extraction currently running');
            }
            return status;
        } catch (error) {
            this.log('error', 'Failed to check extraction status');
            return null;
        }
    }

    async semanticSearch(query) {
        try {
            const results = await this.fetchApi(`/processing/search?query=${encodeURIComponent(query)}&limit=20`);
            this.renderSearchResults(results.results || []);
        } catch (error) {
            console.error('Search failed:', error);
        }
    }

    // =============================================
    // LOCAL GOVERNMENT API CALLS
    // =============================================

    async loadLocalAlerts() {
        try {
            const response = await this.fetchApi('/local/alerts?unread_only=true&limit=10');
            this.localAlerts = response.alerts || [];
            this.renderLocalAlerts();
        } catch (error) {
            console.error('Failed to load local alerts:', error);
        }
    }

    async loadWatchAreas() {
        try {
            const response = await this.fetchApi('/local/watch-areas');
            this.watchAreas = response.watch_areas || [];
            this.renderWatchAreas();
        } catch (error) {
            console.error('Failed to load watch areas:', error);
        }
    }

    async loadLocalStats() {
        try {
            const stats = await this.fetchApi('/local/stats');
            this.localStats = stats;
            this.renderLocalStats();
        } catch (error) {
            console.error('Failed to load local stats:', error);
        }
    }

    async loadLocalBriefing() {
        try {
            this.log('info', 'Generating local briefing...');
            const briefing = await this.fetchApi('/local/briefing?days=7');
            this.renderLocalBriefing(briefing);
            this.log('success', 'Local briefing loaded');
        } catch (error) {
            this.log('error', 'Failed to load local briefing');
        }
    }

    async scanWatchAreas() {
        try {
            this.log('info', 'Scanning watch areas...');
            const result = await this.fetchApi('/local/scan?hours=24', { method: 'POST' });
            if (result.matches && result.matches.length > 0) {
                this.log('success', `Found ${result.matches.length} matches in watch areas`);
                this.loadLocalAlerts();
            } else {
                this.log('info', 'No new activity in watch areas');
            }
        } catch (error) {
            this.log('error', 'Failed to scan watch areas');
        }
    }

    async markAlertRead(alertId) {
        try {
            await this.fetchApi(`/local/alerts/${alertId}/read`, { method: 'POST' });
            this.loadLocalAlerts();
        } catch (error) {
            console.error('Failed to mark alert read:', error);
        }
    }

    async createWatchArea(name, latitude, longitude, radiusMiles = 1.0) {
        try {
            const response = await this.fetchApi('/local/watch-areas', {
                method: 'POST',
                body: JSON.stringify({
                    name,
                    latitude,
                    longitude,
                    radius_miles: radiusMiles,
                    alert_types: ['zoning', 'permits', 'property', 'court']
                })
            });
            this.log('success', `Created watch area: ${name}`);
            this.loadWatchAreas();
            return response;
        } catch (error) {
            this.log('error', 'Failed to create watch area');
            throw error;
        }
    }

    async createPredefinedWatchArea(areaKey) {
        try {
            const response = await this.fetchApi(`/local/watch-areas/predefined/${areaKey}`, {
                method: 'POST'
            });
            this.log('success', `Created watch area: ${response.name}`);
            this.loadWatchAreas();
            return response;
        } catch (error) {
            this.log('error', `Failed to create predefined watch area: ${areaKey}`);
            throw error;
        }
    }

    async deleteWatchArea(areaId) {
        try {
            await this.fetchApi(`/local/watch-areas/${areaId}`, { method: 'DELETE' });
            this.log('success', 'Watch area deleted');
            this.loadWatchAreas();
        } catch (error) {
            this.log('error', 'Failed to delete watch area');
        }
    }

    handleLocalAlert(payload) {
        this.log('info', `Local alert: ${payload.title}`);
        this.addTimelineEvent('local', payload.title, payload.summary);

        // Show notification if browser supports it
        if ('Notification' in window && Notification.permission === 'granted') {
            new Notification('The Pulse - Local Alert', {
                body: payload.title,
                icon: '/static/img/pulse-icon.png'
            });
        }

        this.loadLocalAlerts();
    }

    // =============================================
    // UI RENDERING
    // =============================================

    renderCollectorStatus() {
        const container = document.getElementById('collector-status');
        if (!container) return;

        if (this.collectors.length === 0) {
            container.innerHTML = `
                <li class="collector-item">
                    <span class="status-indicator inactive"></span>
                    <span class="collector-name">No collectors configured</span>
                </li>
            `;
            return;
        }

        container.innerHTML = this.collectors.map(collector => {
            const statusClass = collector.is_running ? 'running' :
                                collector.health === 'healthy' ? 'healthy' :
                                collector.health === 'degraded' ? 'warning' : 'inactive';

            const lastRun = collector.last_run
                ? this.formatRelativeTime(new Date(collector.last_run))
                : 'Never';

            return `
                <li class="collector-item">
                    <span class="status-indicator ${statusClass}"></span>
                    <span class="collector-name">${collector.name}</span>
                    <div class="collector-meta">
                        <span class="collector-time">${lastRun}</span>
                    </div>
                </li>
            `;
        }).join('');
    }

    updateCollectorStatus(name, status) {
        const items = document.querySelectorAll('.collector-item');
        items.forEach(item => {
            const nameEl = item.querySelector('.collector-name');
            if (nameEl && nameEl.textContent === name) {
                const indicator = item.querySelector('.status-indicator');
                indicator.className = `status-indicator ${status}`;
            }
        });
    }

    showBriefingLoading() {
        document.getElementById('briefing-loading')?.classList.remove('hidden');
        document.getElementById('briefing-empty')?.classList.add('hidden');
        document.getElementById('briefing-content')?.classList.add('hidden');
    }

    showBriefingEmpty() {
        document.getElementById('briefing-loading')?.classList.add('hidden');
        document.getElementById('briefing-empty')?.classList.remove('hidden');
        document.getElementById('briefing-content')?.classList.add('hidden');
    }

    renderBriefing(briefing) {
        if (!briefing) {
            this.showBriefingEmpty();
            return;
        }

        document.getElementById('briefing-loading')?.classList.add('hidden');
        document.getElementById('briefing-empty')?.classList.add('hidden');
        document.getElementById('briefing-content')?.classList.remove('hidden');

        // Title and metadata
        document.getElementById('briefing-title').textContent = briefing.title || 'Intelligence Briefing';
        document.getElementById('briefing-date').textContent = this.formatDate(briefing.generated_at);
        document.getElementById('briefing-period').textContent =
            `${briefing.period_hours || 24}h coverage`;
        document.getElementById('briefing-items-count').textContent =
            `${briefing.metadata?.items_analyzed || 0} items analyzed`;

        // Executive summary
        const summaryEl = document.getElementById('briefing-summary');
        if (summaryEl && briefing.executive_summary) {
            summaryEl.innerHTML = marked.parse(briefing.executive_summary);
        }

        // Sections
        const sectionsEl = document.getElementById('briefing-sections');
        if (sectionsEl && briefing.sections) {
            sectionsEl.innerHTML = briefing.sections.map(section => `
                <div class="briefing-section">
                    <h3 class="briefing-section-title">
                        <i class="fas fa-angle-right briefing-section-icon"></i>
                        ${section.title || 'Section'}
                    </h3>
                    <div class="briefing-text">
                        ${marked.parse(section.summary || section.content || '')}
                    </div>
                    ${section.key_developments ? `
                        <ul class="briefing-key-developments">
                            ${section.key_developments.map(dev => `<li>${dev}</li>`).join('')}
                        </ul>
                    ` : ''}
                    ${section.sources_used ? `
                        <div class="briefing-sources">
                            ${section.sources_used.map(src => `
                                <span class="briefing-source-tag">${src}</span>
                            `).join('')}
                        </div>
                    ` : ''}
                </div>
            `).join('');
        }

        // Audio
        if (briefing.audio_path) {
            document.getElementById('audio-player')?.classList.remove('hidden');
            this.setupAudioPlayer(briefing.id);
        } else {
            document.getElementById('audio-player')?.classList.add('hidden');
        }
    }

    renderTrendingEntities() {
        const container = document.getElementById('trending-entities');
        if (!container) return;

        if (this.entities.length === 0) {
            container.innerHTML = `
                <li class="entity-list-item">
                    <span class="text-muted">No entities tracked</span>
                </li>
            `;
            return;
        }

        // Sort by mention count (if available) and take top 10
        const sorted = [...this.entities].slice(0, 10);

        container.innerHTML = sorted.map(entity => {
            const typeClass = (entity.entity_type || 'custom').toLowerCase();
            return `
                <li class="entity-list-item" data-entity="${entity.name}">
                    <span class="entity-type-badge ${typeClass}">${entity.entity_type?.slice(0, 3) || 'ENT'}</span>
                    <span class="entity-name">${entity.name}</span>
                    <span class="entity-mention-count">${entity.mention_count || 0}</span>
                </li>
            `;
        }).join('');

        // Also render the full entity list on the entities page
        this.renderFullEntityList();
    }

    renderFullEntityList() {
        const container = document.getElementById('full-entity-list');
        if (!container) return;

        if (this.entities.length === 0) {
            container.innerHTML = `
                <li class="entity-list-item">
                    <span class="text-muted">No entities tracked. Use "Extract Entities" to discover entities from your news feed.</span>
                </li>
            `;
            return;
        }

        // Show all entities (or limit to reasonable number for performance)
        const entitiesToShow = [...this.entities].slice(0, 100);

        container.innerHTML = entitiesToShow.map(entity => {
            const typeClass = (entity.entity_type || 'custom').toLowerCase();
            return `
                <li class="entity-list-item" data-entity="${entity.name}" data-entity-id="${entity.entity_id}">
                    <span class="entity-type-badge ${typeClass}">${entity.entity_type?.slice(0, 3) || 'ENT'}</span>
                    <span class="entity-name">${entity.name}</span>
                    <span class="entity-mention-count">${entity.mention_count || 0}</span>
                </li>
            `;
        }).join('');
    }

    renderNewsFeed() {
        const container = document.getElementById('news-feed');
        const emptyState = document.getElementById('feed-empty');
        if (!container) return;

        if (this.newsItems.length === 0) {
            container.innerHTML = '';
            emptyState?.classList.remove('hidden');
            return;
        }

        emptyState?.classList.add('hidden');

        container.innerHTML = this.newsItems.map(item => {
            const relevancePercent = Math.round((item.relevance_score || 0) * 100);

            return `
                <li class="news-item" data-id="${item.id}">
                    <div class="news-item-title">
                        <a href="${item.url}" target="_blank" rel="noopener">${item.title}</a>
                    </div>
                    ${item.summary ? `<div class="news-item-summary">${item.summary}</div>` : ''}
                    <div class="news-item-meta">
                        <span class="news-item-source">${item.source_name}</span>
                        <span>${this.formatRelativeTime(new Date(item.published_at || item.collected_at))}</span>
                        ${item.categories?.length ? `
                            <span class="news-item-category">${item.categories[0]}</span>
                        ` : ''}
                        <span class="news-item-relevance">
                            <div class="relevance-bar">
                                <div class="relevance-fill" style="width: ${relevancePercent}%"></div>
                            </div>
                            ${relevancePercent}%
                        </span>
                    </div>
                </li>
            `;
        }).join('');
    }

    renderStats(stats) {
        if (!stats) return;

        document.getElementById('stat-items-today').textContent =
            stats.items_today?.toLocaleString() || '0';
        document.getElementById('stat-items-total').textContent =
            stats.total_items?.toLocaleString() || '0';
        document.getElementById('stat-entities').textContent =
            this.entities.length.toString();
        document.getElementById('stat-briefings').textContent =
            stats.briefing_count?.toString() || '0';
    }

    renderBriefingArchive(briefings) {
        const container = document.getElementById('briefing-archive');
        if (!container) return;

        if (briefings.length === 0) {
            container.innerHTML = `
                <li class="news-item">
                    <span class="text-muted">No archived briefings</span>
                </li>
            `;
            return;
        }

        container.innerHTML = briefings.map(b => `
            <li class="news-item" data-briefing-id="${b.id}">
                <div class="news-item-title">${b.title}</div>
                <div class="news-item-meta">
                    <span>${this.formatDate(b.generated_at)}</span>
                    <span>${b.metadata?.items_analyzed || 0} items</span>
                </div>
            </li>
        `).join('');

        // Add click handlers
        container.querySelectorAll('[data-briefing-id]').forEach(el => {
            el.addEventListener('click', () => {
                this.loadBriefingById(el.dataset.briefingId);
            });
        });
    }

    async loadBriefingById(id) {
        try {
            const briefing = await this.fetchApi(`/synthesis/briefings/${id}`);
            this.currentBriefing = briefing;
            this.renderBriefing(briefing);
            this.switchView('briefing');
        } catch (error) {
            this.log('error', 'Failed to load briefing');
        }
    }

    renderSearchResults(results) {
        const container = document.getElementById('search-results');
        if (!container) return;

        if (results.length === 0) {
            container.innerHTML = `
                <div class="empty-state">
                    <div class="empty-state-icon"><i class="fas fa-search"></i></div>
                    <div class="empty-state-text">No results found</div>
                </div>
            `;
            return;
        }

        container.innerHTML = `
            <ul class="news-list">
                ${results.map(result => `
                    <li class="news-item">
                        <div class="news-item-title">${result.title || 'Untitled'}</div>
                        <div class="news-item-summary">${result.content?.slice(0, 200)}...</div>
                        <div class="news-item-meta">
                            <span class="news-item-source">${result.source_name || 'Unknown'}</span>
                            <span>Score: ${(result.score * 100).toFixed(1)}%</span>
                        </div>
                    </li>
                `).join('')}
            </ul>
        `;
    }

    addTimelineEvent(type, content, details = null) {
        const timeline = document.getElementById('activity-timeline');
        if (!timeline) return;

        const now = new Date();
        const event = {
            type,
            content,
            details,
            time: now
        };

        this.activityLog.unshift(event);
        if (this.activityLog.length > 20) {
            this.activityLog.pop();
        }

        this.renderTimeline();
    }

    // =============================================
    // LOCAL GOVERNMENT RENDERING
    // =============================================

    renderLocalAlerts() {
        const container = document.getElementById('local-alerts');
        const badge = document.getElementById('local-alerts-badge');

        if (badge) {
            badge.textContent = this.localAlerts.length;
            badge.classList.toggle('hidden', this.localAlerts.length === 0);
        }

        if (!container) return;

        if (this.localAlerts.length === 0) {
            container.innerHTML = `
                <div class="empty-state-small">
                    <i class="fas fa-check-circle"></i>
                    <span>No unread alerts</span>
                </div>
            `;
            return;
        }

        container.innerHTML = this.localAlerts.map(alert => {
            const severityClass = {
                'critical': 'severity-critical',
                'high': 'severity-high',
                'medium': 'severity-medium',
                'low': 'severity-low',
                'info': 'severity-info'
            }[alert.severity] || 'severity-info';

            const typeIcon = {
                'zoning': 'fas fa-map-marked-alt',
                'permit': 'fas fa-hard-hat',
                'property': 'fas fa-home',
                'court': 'fas fa-gavel',
                'meeting': 'fas fa-users'
            }[alert.type] || 'fas fa-exclamation-circle';

            return `
                <div class="local-alert-item ${severityClass}" data-alert-id="${alert.id}">
                    <div class="alert-header">
                        <i class="${typeIcon}"></i>
                        <span class="alert-type">${alert.type?.toUpperCase() || 'ALERT'}</span>
                        <span class="alert-time">${this.formatRelativeTime(new Date(alert.created_at))}</span>
                    </div>
                    <div class="alert-title">${alert.title}</div>
                    ${alert.address ? `<div class="alert-address"><i class="fas fa-map-pin"></i> ${alert.address}</div>` : ''}
                    <div class="alert-actions">
                        <button class="btn btn-tiny" onclick="pulseDashboard.markAlertRead('${alert.id}')">
                            <i class="fas fa-check"></i> Mark Read
                        </button>
                        ${alert.source_url ? `
                            <a href="${alert.source_url}" target="_blank" class="btn btn-tiny">
                                <i class="fas fa-external-link-alt"></i> Source
                            </a>
                        ` : ''}
                    </div>
                </div>
            `;
        }).join('');
    }

    renderWatchAreas() {
        const container = document.getElementById('watch-areas-list');
        if (!container) return;

        if (this.watchAreas.length === 0) {
            container.innerHTML = `
                <div class="empty-state-small">
                    <i class="fas fa-map-marker-alt"></i>
                    <span>No watch areas configured</span>
                    <button class="btn btn-small" onclick="pulseDashboard.showAddWatchAreaModal()">
                        <i class="fas fa-plus"></i> Add Area
                    </button>
                </div>
            `;
            return;
        }

        container.innerHTML = this.watchAreas.map(area => `
            <div class="watch-area-item" data-area-id="${area.id}">
                <div class="watch-area-header">
                    <span class="watch-area-name">${area.name}</span>
                    <span class="watch-area-radius">${area.radius_miles} mi</span>
                </div>
                <div class="watch-area-meta">
                    <span class="watch-area-status ${area.is_active ? 'active' : 'inactive'}">
                        ${area.is_active ? 'Active' : 'Inactive'}
                    </span>
                    <span class="watch-area-triggers">
                        <i class="fas fa-bell"></i> ${area.trigger_count || 0}
                    </span>
                </div>
                <div class="watch-area-types">
                    ${(area.alert_types || []).map(t => `
                        <span class="alert-type-badge">${t}</span>
                    `).join('')}
                </div>
                <div class="watch-area-actions">
                    <button class="btn btn-tiny btn-danger" onclick="pulseDashboard.deleteWatchArea('${area.id}')">
                        <i class="fas fa-trash"></i>
                    </button>
                </div>
            </div>
        `).join('');
    }

    renderLocalStats() {
        const container = document.getElementById('local-stats');
        if (!container || !this.localStats) return;

        container.innerHTML = `
            <div class="local-stats-grid">
                <div class="local-stat-item">
                    <div class="local-stat-value">${this.localStats.meetings || 0}</div>
                    <div class="local-stat-label">Meetings</div>
                </div>
                <div class="local-stat-item">
                    <div class="local-stat-value">${this.localStats.zoning || 0}</div>
                    <div class="local-stat-label">Zoning</div>
                </div>
                <div class="local-stat-item">
                    <div class="local-stat-value">${this.localStats.permits || 0}</div>
                    <div class="local-stat-label">Permits</div>
                </div>
                <div class="local-stat-item">
                    <div class="local-stat-value">${this.localStats.property || 0}</div>
                    <div class="local-stat-label">Property</div>
                </div>
                <div class="local-stat-item">
                    <div class="local-stat-value">${this.localStats.court || 0}</div>
                    <div class="local-stat-label">Court</div>
                </div>
            </div>
        `;
    }

    renderLocalBriefing(briefing) {
        const container = document.getElementById('local-briefing-content');
        if (!container || !briefing) return;

        let html = `
            <div class="local-briefing-header">
                <span class="briefing-period">${briefing.period || 'Last 7 days'}</span>
                <span class="briefing-generated">${this.formatDate(new Date())}</span>
            </div>
        `;

        // Council meetings summary
        if (briefing.council_summary) {
            const council = briefing.council_summary;
            html += `
                <div class="local-section">
                    <h4><i class="fas fa-users"></i> Council Meetings</h4>
                    <p>Recent meetings: ${council.recent_meetings?.length || 0}</p>
                    <ul class="local-items-list">
                        ${(council.recent_meetings || []).slice(0, 3).map(m => `
                            <li>${m.jurisdiction}: ${m.body || 'Meeting'} - ${m.meeting_date || 'TBD'}</li>
                        `).join('')}
                    </ul>
                </div>
            `;
        }

        // Zoning summary
        if (briefing.zoning_summary) {
            const zoning = briefing.zoning_summary;
            html += `
                <div class="local-section">
                    <h4><i class="fas fa-map-marked-alt"></i> Zoning Activity</h4>
                    <p>New cases: ${zoning.new_cases || 0} | Pending: ${zoning.pending_count || 0}</p>
                </div>
            `;
        }

        // Permits summary
        if (briefing.permit_summary) {
            const permits = briefing.permit_summary;
            const value = permits.total_value ? `$${permits.total_value.toLocaleString()}` : 'N/A';
            html += `
                <div class="local-section">
                    <h4><i class="fas fa-hard-hat"></i> Building Permits</h4>
                    <p>Issued: ${permits.issued_count || 0} | Value: ${value}</p>
                </div>
            `;
        }

        // Property summary
        if (briefing.property_summary) {
            const prop = briefing.property_summary;
            const volume = prop.total_volume ? `$${prop.total_volume.toLocaleString()}` : 'N/A';
            html += `
                <div class="local-section">
                    <h4><i class="fas fa-home"></i> Property Transactions</h4>
                    <p>Transactions: ${prop.transaction_count || 0} | Volume: ${volume}</p>
                </div>
            `;
        }

        // Court summary
        if (briefing.court_summary) {
            const court = briefing.court_summary;
            html += `
                <div class="local-section">
                    <h4><i class="fas fa-gavel"></i> Court Activity</h4>
                    <p>New filings: ${court.new_filings || 0} | Active: ${court.active_count || 0}</p>
                </div>
            `;
        }

        container.innerHTML = html;
    }

    showAddWatchAreaModal() {
        const modal = document.getElementById('watch-area-modal');
        if (modal) {
            modal.classList.remove('hidden');
            this.loadPredefinedAreas();
        }
    }

    hideWatchAreaModal() {
        const modal = document.getElementById('watch-area-modal');
        if (modal) {
            modal.classList.add('hidden');
        }
    }

    async loadPredefinedAreas() {
        try {
            const response = await this.fetchApi('/local/watch-areas/predefined');
            const container = document.getElementById('predefined-areas-list');
            if (!container) return;

            container.innerHTML = Object.entries(response.areas || {}).map(([key, area]) => `
                <div class="predefined-area-item" onclick="pulseDashboard.createPredefinedWatchArea('${key}')">
                    <span class="area-name">${area.name}</span>
                    <span class="area-radius">${area.radius_miles} mi</span>
                </div>
            `).join('');
        } catch (error) {
            console.error('Failed to load predefined areas:', error);
        }
    }

    renderTimeline() {
        const timeline = document.getElementById('activity-timeline');
        if (!timeline) return;

        timeline.innerHTML = this.activityLog.map(event => `
            <div class="timeline-item ${event.type}">
                <div class="timeline-time">${this.formatTime(event.time)}</div>
                <div class="timeline-content">${event.content}</div>
                ${event.details ? `<div class="timeline-details">${event.details}</div>` : ''}
            </div>
        `).join('');
    }

    // =============================================
    // ENTITY GRAPH (Sigma.js + graphology Integration)
    // =============================================

    /**
     * Node color scheme by entity type
     */
    getNodeColor(type) {
        const colors = {
            person: '#00d4ff',
            org: '#ffb000',
            organization: '#ffb000',
            location: '#00ff88',
            custom: '#9966ff',
            default: '#9966ff'
        };
        return colors[type?.toLowerCase()] || colors.default;
    }

    /**
     * Edge color scheme by relationship type
     */
    getEdgeColor(type) {
        const colors = {
            supports: '#00ff88',
            opposes: '#ff3366',
            collaborates_with: '#00d4ff',
            associated_with: '#3a3a4a',
            default: '#3a3a4a'
        };
        return colors[type?.toLowerCase()] || colors.default;
    }

    /**
     * Initialize Sigma.js graph renderer
     */
    initEntityGraph(containerId) {
        console.log('[DEBUG] initEntityGraph called with:', containerId);
        const container = document.getElementById(containerId);
        console.log('[DEBUG] Container element:', container);
        console.log('[DEBUG] graphology defined:', typeof graphology !== 'undefined');
        console.log('[DEBUG] Sigma defined:', typeof Sigma !== 'undefined');

        if (!container) {
            console.error('[DEBUG] Container NOT FOUND:', containerId);
            this.log('error', `Graph container not found: ${containerId}`);
            return;
        }
        if (typeof graphology === 'undefined' || typeof Sigma === 'undefined') {
            console.error('[DEBUG] Sigma.js or graphology library not loaded!');
            this.log('error', 'Sigma.js or graphology library not loaded');
            return;
        }

        this.log('info', `Initializing Sigma graph in ${containerId}`);

        // Create graphology graph instance
        const graph = new graphology.Graph();

        // Create Sigma renderer with WebGL
        const sigma = new Sigma(graph, container, {
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
            // PULSE-VIZ-001: Disable default hover rendering - we use HTML tooltip instead
            // Sigma v2.4.0 doesn't support custom hover via settings, so we use DOM overlay
            renderLabels: true,
            // PERF-003: Performance optimizations for smooth pan/zoom
            hideEdgesOnMove: true,          // Hide edges during pan/zoom
            hideLabelsOnMove: true,         // Hide labels during pan/zoom
            labelRenderedSizeThreshold: 6   // Only show labels on nodes >= size 6
        });

        // PULSE-VIZ-001: Create HTML tooltip element for dark-theme hover labels
        this.createHoverTooltip(container, containerId);

        // PULSE-VIZ-001.7: Click Isolation Lock
        // Single click locks the hover isolation (hides non-connected nodes)
        // Click persists until user clicks the background
        sigma.on('clickNode', ({ node }) => {
            const nodeData = graph.getNodeAttributes(node);

            // If clicking the same node, toggle off
            if (this.focusedEntityId === node) {
                this.clearFocus(graph, sigma);
                return;
            }

            // Lock isolation on this node
            this.focusedEntityId = node;
            this.highlightNode(node, graph, sigma);
            this.log('info', `Locked focus on ${nodeData.label} - click background to restore`);

            // Also show entity details panel
            this.showEntityDetails({ id: node, ...nodeData });
        });

        // Click on background (stage) to clear focus
        sigma.on('clickStage', () => {
            if (this.focusedEntityId) {
                this.clearFocus(graph, sigma);
            }
        });

        // Set up edge click handler
        sigma.on('clickEdge', ({ edge }) => {
            const edgeData = graph.getEdgeAttributes(edge);
            this.showRelationshipDetails(edgeData);
        });

        // Hover effects with PULSE-VIZ-001 tooltip and PULSE-VIZ-001.5 isolation
        sigma.on('enterNode', ({ node }) => {
            const nodeData = graph.getNodeAttributes(node);
            // PULSE-VIZ-001: Show HTML tooltip with dark theme
            this.showHoverTooltip(node, nodeData, sigma, containerId);
            // PULSE-VIZ-001.5: Hide all non-connected nodes (only if not click-locked)
            // BUG-001 FIX: Don't override click-lock isolation on hover
            if (!this.focusedEntityId) {
                this.highlightNode(node, graph, sigma);
            }
        });

        sigma.on('leaveNode', () => {
            // PULSE-VIZ-001: Delayed hide to allow mouse transition to tooltip
            this.scheduleHideTooltip(containerId);
            // PULSE-VIZ-001.5: Restore all nodes (only if not click-locked)
            if (!this.focusedEntityId) {
                this.clearHighlight(graph, sigma);
            }
        });

        // Store references
        if (containerId === 'entity-graph-mini') {
            this.graphMini = graph;
            this.sigmaMini = sigma;
            console.log('[DEBUG] graphMini/sigmaMini assigned');
        } else if (containerId === 'fullscreen-entity-graph') {
            this.graphFullscreen = graph;
            this.sigmaFullscreen = sigma;
            console.log('[DEBUG] graphFullscreen/sigmaFullscreen assigned');
        } else {
            this.graph = graph;
            this.sigma = sigma;
            console.log('[DEBUG] this.graph/this.sigma assigned');
            this.log('success', 'Main Sigma graph instance created');
        }

        // Store cluster data for semantic zoom
        if (containerId === 'main-entity-graph') {
            this.clusters = [];
            this.setupSemanticZoom(sigma, graph);
            this.setupClusterDoubleClick(sigma, graph);  // PULSE-VIZ-014b
        }

        this.loadNetworkGraph(containerId === 'fullscreen-entity-graph');
    }

    /**
     * PULSE-VIZ-015: Enhanced semantic zoom with detail level switching
     * Set up semantic zoom - adjust label density and detail level based on zoom
     */
    setupSemanticZoom(sigma, graph) {
        // Store current detail level to avoid redundant updates
        this.currentDetailLevel = 'full';  // 'overview' | 'partial' | 'full'

        // Store references for semantic zoom methods
        this.currentGraph = graph;
        this.currentSigma = sigma;

        sigma.on('cameraUpdated', () => {
            const ratio = sigma.getCamera().ratio;

            // PERF-000: Fixed threshold direction - ratio INCREASES when zooming OUT
            // Adjust label density based on zoom level
            if (ratio > 3.0) {
                sigma.setSetting('labelDensity', 0.02);  // Few labels when zoomed out
            } else if (ratio > 2.0) {
                sigma.setSetting('labelDensity', 0.04);
            } else if (ratio > 1.0) {
                sigma.setSetting('labelDensity', 0.07);
            } else {
                sigma.setSetting('labelDensity', 0.15);  // More labels when zoomed in
            }

            // PULSE-VIZ-015: Update detail level (debounced)
            clearTimeout(this._zoomTimeout);
            this._zoomTimeout = setTimeout(() => {
                this.updateDetailLevel(ratio);
            }, 150);  // 150ms debounce for smooth interaction
        });

        this.log('info', 'Semantic zoom initialized');
    }

    // =============================================
    // PULSE-VIZ-014: CLUSTER SUPER-NODES
    // =============================================

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
        this.clusterNodeIds = this.clusterNodeIds || new Set();

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
                originalSize: size,
                color: this.getClusterColor(cluster.dominant_type),
                baseColor: this.getClusterColor(cluster.dominant_type),
                type: 'cluster',  // Mark as cluster for special handling
                isCluster: true,
                clusterData: cluster,
                entityType: cluster.dominant_type?.toLowerCase() || 'unknown'
            });

            this.clusterNodeIds.add(nodeId);
        });

        this.log('info', `Added ${this.clusterNodeIds.size} cluster super-nodes`);
    }

    /**
     * PULSE-VIZ-014: Get cluster color based on dominant entity type
     */
    getClusterColor(dominantType) {
        const colors = {
            'PERSON': '#4a9eff',      // Blue
            'ORG': '#ff6b6b',         // Red
            'LOCATION': '#51cf66',    // Green
            'EVENT': '#ffd43b',       // Yellow
            'GPE': '#51cf66',         // Green (geopolitical entity)
            'MONEY': '#20c997',       // Teal
            'LAW': '#cc5de8',         // Purple
            'unknown': '#868e96'      // Gray
        };
        const typeUpper = (dominantType || 'unknown').toUpperCase();
        return colors[typeUpper] || colors['unknown'];
    }

    /**
     * PULSE-VIZ-014: Remove cluster super-nodes from graph (when zooming into detail view)
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

    // =============================================
    // PULSE-VIZ-016: DETAIL LEVEL SWITCHING
    // =============================================

    /**
     * PULSE-VIZ-016: Update graph detail level based on zoom ratio
     * PERF-000: Fixed threshold direction - Sigma.js ratio INCREASES when zooming OUT
     *
     * Detail levels:
     * - 'overview': ratio > 3.0 - clusters only (zoomed out far)
     * - 'partial':  1.5 < ratio <= 3.0 - clusters + top-20 by centrality
     * - 'full':     ratio <= 1.5 - all nodes (zoomed in)
     */
    updateDetailLevel(ratio) {
        // Skip if no clusters available (semantic zoom not applicable)
        if (!this.clusters || this.clusters.length === 0) {
            return;
        }

        // Determine target level - ratio INCREASES when zooming OUT
        let targetLevel;
        if (ratio > 3.0) {
            targetLevel = 'overview';  // Zoomed out far
        } else if (ratio > 1.5) {
            targetLevel = 'partial';   // Zoomed out some
        } else {
            targetLevel = 'full';      // Default / zoomed in
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
        this.scheduleRefresh();
    }

    /**
     * PULSE-VIZ-016: Overview mode - Show only cluster super-nodes
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
     * PULSE-VIZ-016: Partial mode - Show clusters + top entities by centrality
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
     * PULSE-VIZ-016: Full mode - Show all individual entities
     */
    applyFullMode() {
        const graph = this.currentGraph;
        if (!graph) return;

        // Remove cluster super-nodes
        this.removeClusterNodes();

        // Show all regular nodes (unless filtered by time range)
        graph.forEachNode((nodeId, attrs) => {
            // Skip cluster nodes (they're being removed)
            if (attrs.isCluster) return;

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
     * PULSE-VIZ-016: Get top N entities by degree centrality from graph
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
            if (!cluster || attrs.hidden) return;

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
                top: ${pos.y - attrs.size / 2 - 8}px;
                background: #ff6b00;
                color: white;
                font-size: 10px;
                font-weight: bold;
                padding: 2px 5px;
                border-radius: 8px;
                font-family: var(--font-mono, 'JetBrains Mono', monospace);
                pointer-events: none;
                z-index: 100;
            `;

            container.appendChild(badge);
        });
    }

    // =============================================
    // PULSE-VIZ-014b: CLUSTER EXPAND/COLLAPSE
    // =============================================

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
                const radius = Math.sqrt(cluster.size) * 30;

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

        this.scheduleRefresh();
    }

    /**
     * PULSE-VIZ-014b: Collapse an expanded cluster back to super-node
     */
    collapseCluster(clusterId) {
        if (!this.expandedClusters?.has(clusterId)) return;
        if (!this.currentGraph?.hasNode(clusterId)) return;

        const attrs = this.currentGraph.getNodeAttributes(clusterId);
        const cluster = attrs.clusterData;

        this.log('info', `Collapsing cluster ${cluster.label}`);

        // Hide member nodes
        cluster.members.forEach(memberId => {
            if (this.currentGraph.hasNode(memberId)) {
                this.currentGraph.setNodeAttribute(memberId, 'hidden', true);
                try {
                    this.currentGraph.removeNodeAttribute(memberId, 'expandedFromCluster');
                } catch (e) {
                    // Attribute may not exist
                }
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
        this.scheduleRefresh();
    }

    /**
     * PULSE-VIZ-014b: Set up double-click handler for cluster expand/collapse
     * Called after Sigma is initialized
     */
    setupClusterDoubleClick(sigma, graph) {
        sigma.on('doubleClickNode', ({ node }) => {
            const attrs = graph.getNodeAttributes(node);

            if (attrs.isCluster) {
                this.expandCluster(node);
            } else if (attrs.expandedFromCluster) {
                this.collapseCluster(attrs.expandedFromCluster);
            }
        });

        this.log('info', 'Cluster double-click handler initialized');
    }

    // =============================================
    // PULSE-VIZ-016a: SMOOTH LEVEL TRANSITIONS
    // =============================================

    /**
     * PULSE-VIZ-016a: Utility - Sleep for ms milliseconds
     */
    sleep(ms) {
        return new Promise(resolve => setTimeout(resolve, ms));
    }

    /**
     * PULSE-VIZ-016a: Utility - Adjust color opacity
     */
    adjustColorOpacity(color, opacity) {
        if (!color) return `rgba(100, 100, 100, ${opacity})`;

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

    /**
     * PULSE-VIZ-001: Create HTML tooltip element for dark-theme hover labels
     * PULSE-VIZ-001.6: Tooltip is now clickable to show sources
     */
    createHoverTooltip(container, containerId) {
        // Create tooltip element if it doesn't exist
        const tooltipId = `hover-tooltip-${containerId}`;
        let tooltip = document.getElementById(tooltipId);

        if (!tooltip) {
            tooltip = document.createElement('div');
            tooltip.id = tooltipId;
            tooltip.className = 'entity-hover-tooltip';
            tooltip.style.cssText = `
                position: absolute;
                display: none;
                padding: 8px 12px;
                background: rgba(26, 26, 30, 0.95);
                border: 1.5px solid #00d4ff;
                border-radius: 4px;
                color: #e0e0e0;
                font-family: 'JetBrains Mono', monospace;
                font-size: 12px;
                white-space: nowrap;
                cursor: pointer;
                z-index: 10000;
                box-shadow: 0 4px 12px rgba(0, 0, 0, 0.5);
                transition: border-color 0.15s ease, box-shadow 0.15s ease;
            `;
            container.style.position = 'relative';
            container.appendChild(tooltip);

            // PULSE-VIZ-001.6: Click handler to show sources panel
            tooltip.addEventListener('click', (e) => {
                e.stopPropagation();
                if (this.hoveredEntityName) {
                    this.showSourcesPanel(this.hoveredEntityName);
                }
            });

            // Hover effect for clickability hint + keep tooltip visible
            tooltip.addEventListener('mouseenter', () => {
                // Cancel any scheduled hide - user is on the tooltip
                this.cancelHideTooltip(containerId);
                tooltip.style.borderColor = '#00ffff';
                tooltip.style.boxShadow = '0 4px 16px rgba(0, 212, 255, 0.4)';
            });
            tooltip.addEventListener('mouseleave', () => {
                // Hide immediately when leaving tooltip
                this.hideHoverTooltip(containerId);
                tooltip.style.borderColor = '#00d4ff';
                tooltip.style.boxShadow = '0 4px 12px rgba(0, 0, 0, 0.5)';
            });
        }

        // Store reference
        if (!this.hoverTooltips) this.hoverTooltips = {};
        this.hoverTooltips[containerId] = tooltip;
    }

    /**
     * PULSE-VIZ-001: Show hover tooltip with entity info
     * PULSE-VIZ-001.6: Store entity name for sources panel click
     */
    showHoverTooltip(nodeId, nodeData, sigma, containerId) {
        const tooltip = this.hoverTooltips?.[containerId];
        if (!tooltip) return;

        // PULSE-VIZ-001.6: Store entity name for click handler
        this.hoveredEntityName = nodeData.label || nodeId;

        // Get node viewport position
        const viewportPos = sigma.graphToViewport({
            x: nodeData.x,
            y: nodeData.y
        });

        // Build tooltip content
        const entityType = (nodeData.entityType || 'entity').toUpperCase();
        const typeColor = this.getNodeColor(nodeData.entityType);
        const neighborCount = this.getNeighborCount(nodeId, containerId);

        tooltip.innerHTML = `
            <div style="display: flex; align-items: center; gap: 8px;">
                <span style="
                    background: ${typeColor};
                    color: #1a1a1e;
                    padding: 2px 6px;
                    border-radius: 3px;
                    font-size: 10px;
                    font-weight: bold;
                ">${entityType}</span>
                <span style="font-weight: bold;">${this.hoveredEntityName}</span>
            </div>
            <div style="margin-top: 4px; color: #888; font-size: 10px;">
                ${neighborCount} connection${neighborCount !== 1 ? 's' : ''} • <span style="color: #00d4ff;">Click for sources</span>
            </div>
        `;

        // Position tooltip to the right of the node
        const nodeSize = nodeData.size || 6;
        tooltip.style.left = `${viewportPos.x + nodeSize + 10}px`;
        tooltip.style.top = `${viewportPos.y - tooltip.offsetHeight / 2}px`;
        tooltip.style.display = 'block';
    }

    /**
     * PULSE-VIZ-001: Hide hover tooltip
     */
    hideHoverTooltip(containerId) {
        const tooltip = this.hoverTooltips?.[containerId];
        if (tooltip) {
            tooltip.style.display = 'none';
        }
    }

    /**
     * Schedule tooltip hide with delay to allow mouse transition to tooltip
     */
    scheduleHideTooltip(containerId) {
        // Initialize timeout storage
        if (!this.tooltipHideTimeouts) this.tooltipHideTimeouts = {};

        // Clear any existing timeout
        if (this.tooltipHideTimeouts[containerId]) {
            clearTimeout(this.tooltipHideTimeouts[containerId]);
        }

        // Schedule hide after 150ms - enough time to move to tooltip
        this.tooltipHideTimeouts[containerId] = setTimeout(() => {
            this.hideHoverTooltip(containerId);
        }, 150);
    }

    /**
     * Cancel scheduled tooltip hide (called when entering tooltip)
     */
    cancelHideTooltip(containerId) {
        if (this.tooltipHideTimeouts?.[containerId]) {
            clearTimeout(this.tooltipHideTimeouts[containerId]);
            this.tooltipHideTimeouts[containerId] = null;
        }
    }

    /**
     * PULSE-VIZ-001.6: Show sources panel with entity mentions
     */
    async showSourcesPanel(entityName) {
        const panel = document.getElementById('entity-sources-panel');
        const titleEl = document.getElementById('sources-panel-title');
        const contentEl = document.getElementById('sources-panel-content');

        if (!panel || !contentEl) {
            this.log('warning', 'Sources panel elements not found');
            return;
        }

        // BUG-003 fix: Stop click propagation to prevent Sigma.js clickStage from clearing isolation
        // Only add listener once
        if (!panel._clickHandlerAdded) {
            panel.addEventListener('click', (e) => {
                e.stopPropagation();
            });
            panel.addEventListener('mousedown', (e) => {
                e.stopPropagation();
            });
            panel._clickHandlerAdded = true;
        }

        // Show panel with loading state
        titleEl.textContent = `Sources: ${entityName}`;
        contentEl.innerHTML = `
            <div class="sources-loading">
                <i class="fas fa-spinner"></i>
                <div>Loading sources...</div>
            </div>
        `;
        panel.classList.remove('hidden');

        try {
            // Fetch entity mentions from API
            const response = await this.fetchApi(`/entities/${encodeURIComponent(entityName)}/mentions`);
            const mentions = response.mentions || [];

            if (mentions.length === 0) {
                contentEl.innerHTML = `
                    <div class="sources-empty">
                        <i class="fas fa-folder-open"></i>
                        <div>No sources found for this entity</div>
                    </div>
                `;
                return;
            }

            // Render source items
            contentEl.innerHTML = mentions.map(mention => {
                const sourceType = mention.document_id ? 'document' : 'news';
                const sourceId = mention.document_id || mention.news_article_id || mention.news_item_id || '';
                const sourceTitle = mention.source_title || mention.document_name || 'Unknown Source';
                const date = mention.timestamp ? new Date(mention.timestamp).toLocaleDateString() : '';
                const context = this.highlightEntityInContext(mention.context || '', entityName);

                return `
                    <div class="source-item" onclick="pulseDashboard.openSource('${sourceType}', '${sourceId}')">
                        <div class="source-item-header">
                            <span class="source-type-badge ${sourceType}">${sourceType}</span>
                        </div>
                        <div class="source-item-title">${this.escapeHtml(sourceTitle)}</div>
                        ${date ? `<div class="source-item-date">${date}</div>` : ''}
                        <div class="source-item-context">${context}</div>
                    </div>
                `;
            }).join('');

            this.log('success', `Loaded ${mentions.length} sources for ${entityName}`);

        } catch (error) {
            this.log('error', `Failed to load sources: ${error.message}`);
            contentEl.innerHTML = `
                <div class="sources-empty">
                    <i class="fas fa-exclamation-triangle"></i>
                    <div>Failed to load sources</div>
                </div>
            `;
        }
    }

    /**
     * PULSE-VIZ-001.6: Hide the sources panel
     */
    hideSourcesPanel() {
        const panel = document.getElementById('entity-sources-panel');
        if (panel) {
            panel.classList.add('hidden');
        }
    }

    /**
     * PULSE-VIZ-001.6: Highlight entity name in context text
     */
    highlightEntityInContext(context, entityName) {
        if (!context || !entityName) return context;
        const escaped = this.escapeHtml(context);
        const regex = new RegExp(`(${entityName.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`, 'gi');
        return escaped.replace(regex, '<mark>$1</mark>');
    }

    /**
     * PULSE-VIZ-001.6: Open a source document or article
     */
    openSource(sourceType, sourceId) {
        if (!sourceId) return;

        if (sourceType === 'document') {
            // TODO: Navigate to document view
            this.log('info', `Opening document: ${sourceId}`);
        } else if (sourceType === 'news') {
            // TODO: Navigate to news article view
            this.log('info', `Opening news article: ${sourceId}`);
        }
    }

    /**
     * Escape HTML to prevent XSS
     */
    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    /**
     * Get neighbor count for a node (helper for tooltip)
     */
    getNeighborCount(nodeId, containerId) {
        let graph;
        if (containerId === 'entity-graph-mini') {
            graph = this.graphMini;
        } else if (containerId === 'fullscreen-entity-graph') {
            graph = this.graphFullscreen;
        } else {
            graph = this.graph;
        }

        if (!graph || !graph.hasNode(nodeId)) return 0;
        return graph.neighbors(nodeId).length;
    }

    // =============================================
    // PULSE-VIZ-010c: TIMELINE INTEGRATION
    // =============================================

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

        // Set up reset button
        const resetBtn = document.getElementById('timeline-reset');
        if (resetBtn) {
            resetBtn.addEventListener('click', () => {
                this.resetTimelineSelection();
            });
        }

        // PULSE-VIZ-012: Set up timeline-graph sync
        this.setupTimelineSync();

        this.log('success', 'Timeline initialized');
    }

    /**
     * PULSE-VIZ-010c: Load timeline data from API
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
     * PULSE-VIZ-010c: Update the date display labels
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
     * PULSE-VIZ-010c/011: Reset timeline selection (full implementation with graph filter)
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

    // =============================================
    // PULSE-VIZ-011: TIME RANGE FILTERING
    // =============================================

    /**
     * PULSE-VIZ-011: Filter graph to show only entities active in time range
     * @param {Date|string} startDate - Start of time range
     * @param {Date|string} endDate - End of time range
     */
    filterGraphToTimeRange(startDate, endDate) {
        const graph = this.graph;
        const sigma = this.sigma;

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
        this.scheduleRefresh();

        // Log stats
        const visibleCount = activeEntityIds.size;
        const totalCount = graph.order;
        this.log('info', `Showing ${visibleCount}/${totalCount} entities in time range`);

        // Store current filter state
        this.timeFilterRange = { start: startDate, end: endDate };
    }

    /**
     * PULSE-VIZ-011: Clear time range filter and show all entities
     */
    clearTimeRangeFilter() {
        const graph = this.graph;
        const sigma = this.sigma;

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

        this.scheduleRefresh();

        this.timeFilterRange = null;
        this.log('info', 'Time range filter cleared - showing all entities');
    }

    // =============================================
    // PULSE-VIZ-012: TIMELINE-GRAPH SYNC
    // =============================================

    /**
     * PULSE-VIZ-012: Set up timeline-graph synchronization
     * Called at the end of initTimeline()
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
     * PULSE-VIZ-012: Handle timeline range changes from sliders or clicks
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

    /**
     * Load network graph data from API with pre-computed positions
     * PERF-006: Added performance timing
     */
    async loadNetworkGraph(isFullscreen = false) {
        const perfStart = performance.now();
        try {
            // PERF-006: Time API fetch
            const fetchStart = performance.now();
            const response = await this.fetchApi('/network/graph?include_positions=true&include_clusters=true');
            const fetchTime = performance.now() - fetchStart;
            this.log('info', `⚡ API fetch: ${fetchTime.toFixed(0)}ms`);

            // PERF-006: Time render
            const renderStart = performance.now();
            await this.renderNetworkGraph(response.elements, response.clusters, isFullscreen);
            const renderTime = performance.now() - renderStart;
            this.log('info', `⚡ Render total: ${renderTime.toFixed(0)}ms`);

            this.updateNetworkStats(response.stats);

            // Store clusters for semantic zoom
            if (response.clusters) {
                this.clusters = response.clusters;
            }

            const totalTime = performance.now() - perfStart;
            this.log('success', `⚡ Network graph loaded in ${totalTime.toFixed(0)}ms`);
        } catch (error) {
            console.error('Failed to load network graph:', error);
            this.updateEntityGraphFallback(isFullscreen);
        }
    }

    // =============================================
    // PERF-001: WEB WORKER FORCEATLAS2 LAYOUT
    // =============================================

    /**
     * PERF-001: Initialize ForceAtlas2 Web Worker for non-blocking layout
     */
    initLayoutWorker() {
        // Clean up existing worker
        if (this.layoutWorker) {
            this.layoutWorker.kill();
            this.layoutWorker = null;
        }

        // Check for bundled FA2Layout (window.FA2Layout) or global
        const FA2LayoutClass = window.FA2Layout || (typeof FA2Layout !== 'undefined' ? FA2Layout : undefined);

        if (!this.currentGraph || !FA2LayoutClass) {
            this.log('warning', 'Cannot init layout worker: missing graph or FA2Layout');
            return;
        }

        this.layoutWorker = new FA2LayoutClass(this.currentGraph, {
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
     * PERF-002: Shows progress indicator during layout
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

        // PERF-002: Show progress indicator
        this.showLayoutIndicator(true, 'Computing layout...');

        // Start worker
        this.layoutWorker.start();

        // Refresh periodically to show progress and update indicator
        const progressInterval = setInterval(() => {
            this.scheduleRefresh();
            // PERF-002: Update indicator with elapsed time
            const elapsed = ((performance.now() - startTime) / 1000).toFixed(1);
            this.showLayoutIndicator(true, `Computing layout... ${elapsed}s`);
        }, 200);

        // Wait for duration or manual stop
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

    /**
     * Render graph data using Sigma.js with ASYNC ForceAtlas2 layout
     * PERF-001: Replaced synchronous layout with Web Worker
     * PERF-006: Added granular performance timing
     * PULSE-VIZ-003: Replaced server-side spring_layout with client-side ForceAtlas2
     */
    async renderNetworkGraph(elements, clusters, isFullscreen = false) {
        if (!elements) return;

        // Get appropriate graph/sigma instances
        const graph = isFullscreen ? this.graphFullscreen : (this.graph || this.graphMini);
        const sigma = isFullscreen ? this.sigmaFullscreen : (this.sigma || this.sigmaMini);

        if (!graph || !sigma) {
            console.warn('Graph not initialized yet');
            return;
        }

        // PERF-006: Time graph building
        const buildStart = performance.now();

        // Clear existing graph
        graph.clear();

        // Track disconnected nodes for PULSE-VIZ-004
        const nodeIds = new Set();
        const connectedNodes = new Set();

        // Add nodes with initial random positions (ForceAtlas2 will optimize)
        for (const node of elements.nodes) {
            const nodeData = node.data;
            nodeIds.add(nodeData.id);

            const nodeSize = Math.max(5, Math.min(20, 5 + (nodeData.size || 15) / 3));
            graph.addNode(nodeData.id, {
                x: Math.random() * 1000 - 500,
                y: Math.random() * 1000 - 500,
                size: nodeSize,
                originalSize: nodeSize, // PULSE-VIZ-001.5: Store for hover restore
                label: nodeData.label || nodeData.name || nodeData.id,
                color: this.getNodeColor(nodeData.type || nodeData.entity_type),
                entityType: (nodeData.type || nodeData.entity_type || 'custom').toLowerCase(),
                // PULSE-VIZ-011: Temporal attributes for time range filtering
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

            // Only add edge if both nodes exist
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
                    // Edge may already exist (multi-edge)
                    console.debug('Edge already exists:', source, target);
                }
            }
        }

        const buildTime = performance.now() - buildStart;
        this.log('info', `⚡ Graph build: ${buildTime.toFixed(0)}ms (${graph.order} nodes, ${graph.size} edges)`);

        // PERF-001: Show graph immediately with random positions
        this.scheduleRefresh();
        this.log('info', `Showing ${graph.order} nodes (layout computing...)`);

        // PERF-001: Clean up existing worker and run async layout
        this.destroyLayoutWorker();

        // PERF-006: Time layout computation
        const layoutStart = performance.now();

        // PERF-001: Check for bundled FA2Layout (window.FA2Layout) or global FA2Layout
        const FA2LayoutClass = window.FA2Layout || (typeof FA2Layout !== 'undefined' ? FA2Layout : undefined);

        if (FA2LayoutClass && graph.order > 1) {
            // Use Web Worker for non-blocking layout
            this.currentGraph = graph;
            this.log('info', '🔧 Using FA2Layout Web Worker (non-blocking)');
            await this.runLayoutAsync(5000);
        } else if (typeof forceAtlas2 !== 'undefined' && graph.order > 1) {
            // Fallback to synchronous if worker not available
            this.log('warning', 'FA2 Worker not loaded, using synchronous layout (UI will freeze)');
            const settings = forceAtlas2.inferSettings(graph);
            settings.linLogMode = true;
            settings.barnesHutOptimize = true;  // Always use Barnes-Hut for O(n log n)
            settings.barnesHutTheta = 0.5;
            // Reduce iterations for faster layout - 100 is usually enough for good separation
            forceAtlas2.assign(graph, { settings, iterations: 100 });
        } else if (graph.order <= 1) {
            console.debug('Skipping layout: graph too small');
        }

        const layoutTime = performance.now() - layoutStart;
        this.log('info', `⚡ Layout: ${layoutTime.toFixed(0)}ms`);

        // PULSE-VIZ-004: Position disconnected nodes in "orphan area" at bottom-right
        const disconnectedNodes = [...nodeIds].filter(id => !connectedNodes.has(id));
        if (disconnectedNodes.length > 0) {
            this.positionOrphanNodes(graph, disconnectedNodes);
        }

        // Refresh the renderer
        this.scheduleRefresh();

        this.log('success', `Rendered ${graph.order} nodes, ${graph.size} edges`);
    }

    /**
     * PULSE-VIZ-004: Position orphan nodes (no edges) in a grid at bottom-right
     */
    positionOrphanNodes(graph, orphanIds) {
        if (orphanIds.length === 0) return;

        // Find the bounding box of connected nodes
        let maxX = -Infinity, maxY = -Infinity;
        graph.forEachNode((node, attrs) => {
            if (!orphanIds.includes(node)) {
                maxX = Math.max(maxX, attrs.x);
                maxY = Math.max(maxY, attrs.y);
            }
        });

        // Position orphans in a grid below and to the right
        const gridCols = Math.ceil(Math.sqrt(orphanIds.length));
        const spacing = 50;
        const startX = maxX + spacing * 2;
        const startY = maxY + spacing * 2;

        orphanIds.forEach((nodeId, i) => {
            const col = i % gridCols;
            const row = Math.floor(i / gridCols);
            graph.setNodeAttribute(nodeId, 'x', startX + col * spacing);
            graph.setNodeAttribute(nodeId, 'y', startY + row * spacing);
        });

        this.log('info', `Positioned ${orphanIds.length} orphan nodes`);
    }

    /**
     * Fallback when network graph fails to load
     */
    updateEntityGraphFallback(isFullscreen = false) {
        const graph = isFullscreen ? this.graphFullscreen : (this.graph || this.graphMini);
        const sigma = isFullscreen ? this.sigmaFullscreen : (this.sigma || this.sigmaMini);

        if (!graph || !sigma) return;

        graph.clear();

        // Add nodes for entities in a circle layout
        const entities = this.entities.slice(0, 15);
        const radius = 400;
        const angleStep = (2 * Math.PI) / Math.max(1, entities.length);

        entities.forEach((entity, i) => {
            const angle = i * angleStep;
            graph.addNode(entity.entity_id || entity.name, {
                x: radius * Math.cos(angle),
                y: radius * Math.sin(angle),
                size: 8,
                label: entity.name,
                color: this.getNodeColor(entity.entity_type),
                entityType: (entity.entity_type || 'custom').toLowerCase()
            });
        });

        this.scheduleRefresh();
    }

    /**
     * Refresh graph data
     */
    updateEntityGraph() {
        this.loadNetworkGraph();
    }

    /**
     * PULSE-VIZ-001.5: Hover Isolation Mode
     * When hovering over a node, HIDE all non-connected nodes and edges
     * This reveals the subnetwork structure at a glance
     */
    highlightNode(nodeId, graph, sigma) {
        const neighbors = new Set(graph.neighbors(nodeId));
        neighbors.add(nodeId);

        // PULSE-VIZ-001.5: Hide non-neighbors completely (not just dim)
        graph.forEachNode((node, attrs) => {
            const isNeighbor = neighbors.has(node);
            const originalColor = this.getNodeColor(attrs.entityType);

            // Hide non-neighbors, show neighbors with original color
            graph.setNodeAttribute(node, 'hidden', !isNeighbor);
            if (isNeighbor) {
                graph.setNodeAttribute(node, 'color', originalColor);
                // Enlarge the hovered node for emphasis
                if (node === nodeId) {
                    graph.setNodeAttribute(node, 'size', (attrs.originalSize || attrs.size || 6) * 1.5);
                }
            }
        });

        // Hide edges not connecting to the neighborhood
        graph.forEachEdge((edge, attrs, source, target) => {
            const connected = neighbors.has(source) && neighbors.has(target);
            const originalColor = this.getEdgeColor(attrs.edgeType);

            graph.setEdgeAttribute(edge, 'hidden', !connected);
            if (connected) {
                graph.setEdgeAttribute(edge, 'color', originalColor);
            }
        });

        this.scheduleRefresh();
    }

    /**
     * Clear highlight effects and restore all nodes/edges
     */
    clearHighlight(graph, sigma) {
        // Don't clear if we're in focus mode
        if (this.focusedEntityId) return;

        // Restore all nodes - unhide and reset colors
        graph.forEachNode((node, attrs) => {
            graph.setNodeAttribute(node, 'hidden', false);
            graph.setNodeAttribute(node, 'color', this.getNodeColor(attrs.entityType));
            // Restore original size if it was enlarged
            if (attrs.originalSize) {
                graph.setNodeAttribute(node, 'size', attrs.originalSize);
            }
        });

        // Restore all edges - unhide and reset colors
        graph.forEachEdge((edge, attrs) => {
            graph.setEdgeAttribute(edge, 'hidden', false);
            graph.setEdgeAttribute(edge, 'color', this.getEdgeColor(attrs.edgeType));
        });

        this.scheduleRefresh();
    }

    /**
     * Filter graph to show only an entity and its direct connections
     * Non-connected nodes fade to 10% visibility
     */
    filterToEntity(nodeId, graph, sigma) {
        const neighbors = new Set(graph.neighbors(nodeId));
        neighbors.add(nodeId);

        // Fade non-connected nodes to very low visibility
        graph.forEachNode((node, attrs) => {
            const isConnected = neighbors.has(node);
            const originalColor = this.getNodeColor(attrs.entityType);

            if (isConnected) {
                graph.setNodeAttribute(node, 'color', originalColor);
                graph.setNodeAttribute(node, 'size', node === nodeId ? 15 : 8);
            } else {
                // Fade to 10% opacity (dark gray)
                graph.setNodeAttribute(node, 'color', 'rgba(60, 60, 60, 0.1)');
                graph.setNodeAttribute(node, 'size', 3);
            }
        });

        // Fade non-connected edges
        graph.forEachEdge((edge, attrs, source, target) => {
            const connected = neighbors.has(source) && neighbors.has(target);
            const originalColor = this.getEdgeColor(attrs.edgeType);

            if (connected) {
                graph.setEdgeAttribute(edge, 'color', originalColor);
            } else {
                graph.setEdgeAttribute(edge, 'color', 'rgba(40, 40, 40, 0.05)');
            }
        });

        // Animate camera to center on the focused node
        const nodeAttrs = graph.getNodeAttributes(nodeId);
        sigma.getCamera().animate(
            { x: nodeAttrs.x, y: nodeAttrs.y, ratio: 0.5 },
            { duration: 400 }
        );

        this.scheduleRefresh();
        this.showToast('info', `Showing connections for ${nodeAttrs.label || nodeId}. Click background to reset.`);
    }

    /**
     * Clear focus filter and restore full graph visibility
     */
    clearFocus(graph, sigma) {
        this.focusedEntityId = null;

        // PULSE-VIZ-001.7: Restore all nodes - unhide, restore colors and sizes
        graph.forEachNode((node, attrs) => {
            graph.setNodeAttribute(node, 'hidden', false);
            graph.setNodeAttribute(node, 'color', this.getNodeColor(attrs.entityType));
            // Restore original size if stored, otherwise default to 6
            const size = attrs.originalSize || 6;
            graph.setNodeAttribute(node, 'size', size);
        });

        // Restore all edges - unhide and restore colors
        graph.forEachEdge((edge, attrs) => {
            graph.setEdgeAttribute(edge, 'hidden', false);
            graph.setEdgeAttribute(edge, 'color', this.getEdgeColor(attrs.edgeType));
        });

        this.scheduleRefresh();
        this.log('info', 'Focus cleared - showing full graph');
    }

    /**
     * Expand node connections by loading its neighborhood
     */
    async expandNodeConnections(nodeId, isFullscreen = false) {
        try {
            const graph = isFullscreen ? this.graphFullscreen : this.graph;
            const sigma = isFullscreen ? this.sigmaFullscreen : this.sigma;

            if (!graph || !sigma) return;

            const neighborhood = await this.fetchApi(`/network/neighborhood/${nodeId}?depth=${this.graphDepth}`);

            if (!neighborhood || !neighborhood.nodes) {
                this.showToast('info', 'No additional connections found');
                return;
            }

            // Find nodes not already in graph
            const existingNodes = new Set();
            graph.forEachNode(node => existingNodes.add(node));

            const newNodes = neighborhood.nodes.filter(n => !existingNodes.has(n.id));

            if (newNodes.length === 0) {
                this.showToast('info', 'All connections already visible');
                return;
            }

            // Get position of clicked node to position new nodes nearby
            const centerAttrs = graph.getNodeAttributes(nodeId);
            const centerX = centerAttrs.x || 0;
            const centerY = centerAttrs.y || 0;

            // Add new nodes in a circle around the center node
            const radius = 150;
            const angleStep = (2 * Math.PI) / newNodes.length;

            newNodes.forEach((node, i) => {
                const angle = i * angleStep;
                graph.addNode(node.id, {
                    x: centerX + radius * Math.cos(angle),
                    y: centerY + radius * Math.sin(angle),
                    size: 6,
                    label: node.name,
                    color: this.getNodeColor(node.entity_type),
                    entityType: (node.entity_type || 'custom').toLowerCase(),
                    originalData: node
                });
            });

            // Add edges for new nodes
            const newNodeIds = new Set(newNodes.map(n => n.id));
            for (const edge of neighborhood.edges || []) {
                const source = edge.source;
                const target = edge.target;

                if (graph.hasNode(source) && graph.hasNode(target)) {
                    if (newNodeIds.has(source) || newNodeIds.has(target)) {
                        try {
                            graph.addEdge(source, target, {
                                size: Math.max(1, Math.min(5, edge.weight || 1)),
                                color: this.getEdgeColor(edge.relationship_type),
                                edgeType: edge.relationship_type || 'associated_with'
                            });
                        } catch (e) {
                            // Edge may already exist
                        }
                    }
                }
            }

            this.scheduleRefresh();
            this.log('success', `Added ${newNodes.length} connected entities`);

        } catch (error) {
            console.error('Failed to expand node:', error);
            this.showToast('error', 'Failed to load connections');
        }
    }

    updateNetworkStats(stats) {
        if (!stats) return;

        const statsEl = document.getElementById('network-stats');
        if (statsEl) {
            statsEl.innerHTML = `
                <span class="stat-item">Nodes: ${stats.nodes || 0}</span>
                <span class="stat-item">Edges: ${stats.edges || 0}</span>
                <span class="stat-item">Density: ${(stats.density || 0).toFixed(3)}</span>
            `;
        }

        document.getElementById('stat-entities').textContent = (stats.nodes || 0).toString();
    }

    showEntityDetails(nodeData) {
        this.log('info', `Selected entity: ${nodeData.label || nodeData.name}`);

        // Load neighborhood for this entity
        this.loadEntityNeighborhood(nodeData.id);

        // Update entity info panel if it exists
        const infoPanel = document.getElementById('entity-info');
        if (infoPanel) {
            infoPanel.innerHTML = `
                <div class="entity-detail-header">
                    <span class="entity-type-badge ${nodeData.type}">${nodeData.type?.toUpperCase() || 'ENT'}</span>
                    <h4>${nodeData.label || nodeData.name}</h4>
                </div>
                <div class="entity-detail-actions">
                    <button class="btn btn-small" onclick="pulseDashboard.exploreEntity('${nodeData.id}')">
                        <i class="fas fa-project-diagram"></i> Explore
                    </button>
                    <button class="btn btn-small" onclick="pulseDashboard.findPaths('${nodeData.id}')">
                        <i class="fas fa-route"></i> Find Paths
                    </button>
                </div>
            `;
            infoPanel.classList.remove('hidden');
        }
    }

    showRelationshipDetails(edgeData) {
        this.log('info', `Relationship: ${edgeData.type || 'associated_with'}`);

        const infoPanel = document.getElementById('relationship-info');
        if (infoPanel) {
            infoPanel.innerHTML = `
                <div class="relationship-detail">
                    <span class="relationship-type">${edgeData.type || 'associated_with'}</span>
                    <span class="relationship-confidence">Confidence: ${((edgeData.confidence || 0.5) * 100).toFixed(0)}%</span>
                </div>
            `;
        }
    }

    async loadEntityNeighborhood(entityId) {
        try {
            const neighborhood = await this.fetchApi(`/network/neighborhood/${entityId}?depth=1`);
            // Could highlight neighborhood in graph
            this.highlightNeighborhood(neighborhood);
        } catch (error) {
            console.error('Failed to load neighborhood:', error);
        }
    }

    /**
     * Highlight neighborhood nodes (Sigma.js version)
     */
    highlightNeighborhood(neighborhood) {
        const graph = this.graph || this.graphMini;
        const sigma = this.sigma || this.sigmaMini;
        if (!graph || !sigma || !neighborhood) return;

        // Get all node IDs in neighborhood
        const neighborhoodIds = new Set();
        if (neighborhood.center) {
            neighborhoodIds.add(neighborhood.center.id);
        }
        neighborhood.nodes?.forEach(node => neighborhoodIds.add(node.id));

        // Highlight by adjusting colors
        graph.forEachNode((node, attrs) => {
            if (neighborhoodIds.has(node)) {
                graph.setNodeAttribute(node, 'color', this.getNodeColor(attrs.entityType));
            } else {
                graph.setNodeAttribute(node, 'color', '#333333');
            }
        });

        this.scheduleRefresh();
    }

    async exploreEntity(entityId) {
        try {
            const neighborhood = await this.fetchApi(`/network/neighborhood/${entityId}?depth=2`);
            this.renderNeighborhoodGraph(neighborhood);
        } catch (error) {
            this.log('error', 'Failed to explore entity');
        }
    }

    /**
     * Render neighborhood graph (Sigma.js version)
     */
    renderNeighborhoodGraph(neighborhood) {
        const graph = this.graph || this.graphMini;
        const sigma = this.sigma || this.sigmaMini;
        if (!graph || !sigma || !neighborhood) return;

        graph.clear();

        // Add nodes in radial layout
        const centerNode = neighborhood.nodes.find(n => n.id === neighborhood.center?.id);
        const otherNodes = neighborhood.nodes.filter(n => n.id !== centerNode?.id);

        if (centerNode) {
            graph.addNode(centerNode.id, {
                x: 0,
                y: 0,
                size: 12,
                label: centerNode.name,
                color: this.getNodeColor(centerNode.entity_type),
                entityType: (centerNode.entity_type || 'custom').toLowerCase()
            });
        }

        const radius = 300;
        const angleStep = (2 * Math.PI) / Math.max(1, otherNodes.length);

        otherNodes.forEach((node, i) => {
            const angle = i * angleStep;
            graph.addNode(node.id, {
                x: radius * Math.cos(angle),
                y: radius * Math.sin(angle),
                size: 8,
                label: node.name,
                color: this.getNodeColor(node.entity_type),
                entityType: (node.entity_type || 'custom').toLowerCase()
            });
        });

        // Add edges
        neighborhood.edges.forEach(edge => {
            if (graph.hasNode(edge.source) && graph.hasNode(edge.target)) {
                try {
                    graph.addEdge(edge.source, edge.target, {
                        size: Math.max(1, (edge.confidence || 0.5) * 3),
                        color: this.getEdgeColor(edge.relationship_type),
                        edgeType: edge.relationship_type || 'associated_with'
                    });
                } catch (e) {
                    // Edge may already exist
                }
            }
        });

        this.scheduleRefresh();
    }

    async findPaths(entityId) {
        // Show path finder modal
        const modal = document.getElementById('path-finder-modal');
        if (modal) {
            modal.classList.remove('hidden');
            modal.dataset.sourceId = entityId;
        }
    }

    async searchPaths(sourceId, targetId) {
        try {
            const result = await this.fetchApi('/network/path', {
                method: 'POST',
                body: JSON.stringify({
                    source_id: sourceId,
                    target_id: targetId,
                    max_depth: 4
                })
            });

            if (result.found) {
                this.renderPath(result.path);
                this.log('success', `Found path with ${result.length} hops`);
            } else {
                this.log('warn', 'No path found between entities');
            }
        } catch (error) {
            this.log('error', 'Path search failed');
        }
    }

    /**
     * Render path between entities (Sigma.js version)
     */
    renderPath(path) {
        const graph = this.graph || this.graphMini;
        const sigma = this.sigma || this.sigmaMini;
        if (!graph || !sigma || !path) return;

        // Collect path node IDs
        const pathNodeIds = new Set();
        path.forEach(segment => {
            if (segment.from) pathNodeIds.add(segment.from.id);
            if (segment.to) pathNodeIds.add(segment.to.id);
        });

        // Highlight path nodes
        graph.forEachNode((node, attrs) => {
            if (pathNodeIds.has(node)) {
                graph.setNodeAttribute(node, 'color', '#ff66aa');
            } else {
                graph.setNodeAttribute(node, 'color', '#333333');
            }
        });

        this.scheduleRefresh();
    }

    async runRelationshipDiscovery() {
        try {
            this.log('info', 'Running relationship discovery...');
            const result = await this.fetchApi('/network/discover', {
                method: 'POST',
                body: JSON.stringify({
                    min_co_occurrences: 2,
                    time_window_days: 30,
                    use_llm: false
                })
            });

            this.log('success', `Discovered ${result.discovered} relationships`);
            this.loadNetworkGraph(); // Refresh graph
        } catch (error) {
            this.log('error', 'Relationship discovery failed');
        }
    }

    async loadCentralityAnalysis() {
        try {
            const [degree, betweenness, pagerank] = await Promise.all([
                this.fetchApi('/network/centrality/degree?limit=10'),
                this.fetchApi('/network/centrality/betweenness?limit=10'),
                this.fetchApi('/network/centrality/pagerank?limit=10')
            ]);

            this.renderCentralityAnalysis({ degree, betweenness, pagerank });
        } catch (error) {
            console.error('Centrality analysis failed:', error);
        }
    }

    renderCentralityAnalysis(data) {
        const container = document.getElementById('centrality-analysis');
        if (!container) return;

        container.innerHTML = `
            <div class="centrality-section">
                <h5>Most Connected</h5>
                <ul class="centrality-list">
                    ${data.degree.entities?.slice(0, 5).map(e => `
                        <li>
                            <span class="entity-name">${e.name}</span>
                            <span class="centrality-score">${e.connections} connections</span>
                        </li>
                    `).join('') || '<li>No data</li>'}
                </ul>
            </div>
            <div class="centrality-section">
                <h5>Bridge Entities</h5>
                <ul class="centrality-list">
                    ${data.betweenness.entities?.slice(0, 5).map(e => `
                        <li>
                            <span class="entity-name">${e.name}</span>
                            <span class="centrality-score">${(e.betweenness * 100).toFixed(1)}%</span>
                        </li>
                    `).join('') || '<li>No data</li>'}
                </ul>
            </div>
        `;
    }

    async detectCommunities() {
        try {
            const communities = await this.fetchApi('/network/communities');
            this.renderCommunities(communities.communities);
        } catch (error) {
            this.log('error', 'Community detection failed');
        }
    }

    renderCommunities(communities) {
        const container = document.getElementById('communities-list');
        if (!container) return;

        container.innerHTML = communities.map((c, i) => `
            <div class="community-item">
                <div class="community-header">
                    <span class="community-id">Community ${i + 1}</span>
                    <span class="community-size">${c.size} members</span>
                </div>
                <div class="community-members">
                    ${c.key_entities?.map(e => `
                        <span class="entity-tag">${e.name}</span>
                    `).join('') || ''}
                </div>
            </div>
        `).join('');
    }

    // =============================================
    // AUDIO PLAYER
    // =============================================

    setupAudioPlayer(briefingId) {
        this.audioElement = document.getElementById('audio-element');
        if (!this.audioElement) return;

        this.audioElement.src = `${this.apiBase}/synthesis/briefings/${briefingId}/audio`;

        this.audioElement.addEventListener('timeupdate', () => {
            this.updateAudioProgress();
        });

        this.audioElement.addEventListener('loadedmetadata', () => {
            document.getElementById('audio-duration').textContent =
                this.formatAudioTime(this.audioElement.duration);
        });

        this.audioElement.addEventListener('ended', () => {
            this.isPlaying = false;
            this.updatePlayButton();
        });
    }

    toggleAudioPlayback() {
        if (!this.audioElement) return;

        if (this.isPlaying) {
            this.audioElement.pause();
        } else {
            this.audioElement.play();
        }

        this.isPlaying = !this.isPlaying;
        this.updatePlayButton();
    }

    updatePlayButton() {
        const btn = document.getElementById('audio-play-btn');
        if (!btn) return;

        btn.innerHTML = this.isPlaying
            ? '<i class="fas fa-pause"></i>'
            : '<i class="fas fa-play"></i>';
    }

    updateAudioProgress() {
        if (!this.audioElement) return;

        const progress = (this.audioElement.currentTime / this.audioElement.duration) * 100;
        document.getElementById('audio-progress-fill').style.width = `${progress}%`;
        document.getElementById('audio-current-time').textContent =
            this.formatAudioTime(this.audioElement.currentTime);
    }

    formatAudioTime(seconds) {
        const mins = Math.floor(seconds / 60);
        const secs = Math.floor(seconds % 60);
        return `${mins}:${secs.toString().padStart(2, '0')}`;
    }

    // =============================================
    // VIEW MANAGEMENT
    // =============================================

    switchView(viewName) {
        // Update nav
        document.querySelectorAll('.nav-item').forEach(item => {
            item.classList.toggle('active', item.dataset.view === viewName);
        });

        // Update view containers
        document.querySelectorAll('.view-container').forEach(view => {
            view.classList.toggle('hidden', view.id !== `view-${viewName}`);
        });

        this.currentView = viewName;

        // Special handling for different views - load data on demand
        if (viewName === 'entities') {
            // FIX: Only initialize graph if not already done
            // initEntityGraph() calls loadNetworkGraph() internally, so no need to call it again
            if (!this.sigma) {
                this.initEntityGraph('main-entity-graph');
            } else {
                // Graph already initialized, just refresh data if needed
                this.loadNetworkGraph();
            }
            // PULSE-VIZ-010c: Initialize timeline if not already done
            if (!this.timelineRenderer) {
                this.initTimeline();
            }
        } else if (viewName === 'entity-list') {
            this.loadEntityList();
        }
    }

    // =============================================
    // EVENT LISTENERS
    // =============================================

    setupEventListeners() {
        // Navigation
        document.querySelectorAll('.nav-item[data-view]').forEach(item => {
            item.addEventListener('click', (e) => {
                e.preventDefault();
                this.switchView(item.dataset.view);
            });
        });

        // Panel collapsing
        document.querySelectorAll('.panel-header').forEach(header => {
            header.addEventListener('click', () => {
                header.closest('.panel-section').classList.toggle('expanded');
            });
        });

        // Quick action buttons
        document.getElementById('btn-run-collection')?.addEventListener('click', () => {
            this.runCollection();
        });

        document.getElementById('btn-extract-entities')?.addEventListener('click', () => {
            this.extractEntities();
        });

        document.getElementById('btn-bulk-extract')?.addEventListener('click', () => {
            this.bulkExtractEntities();
        });

        document.getElementById('btn-enrich-entities')?.addEventListener('click', () => {
            this.enrichEntities();
        });

        document.getElementById('btn-generate-briefing')?.addEventListener('click', () => {
            this.generateBriefing();
        });

        document.getElementById('btn-generate-first-briefing')?.addEventListener('click', () => {
            this.generateBriefing();
        });

        document.getElementById('btn-process-items')?.addEventListener('click', () => {
            this.processItems();
        });

        // Briefing actions
        document.getElementById('btn-play-audio')?.addEventListener('click', () => {
            const audioPlayer = document.getElementById('audio-player');
            audioPlayer.classList.toggle('hidden');
            if (!audioPlayer.classList.contains('hidden')) {
                this.toggleAudioPlayback();
            }
        });

        document.getElementById('audio-play-btn')?.addEventListener('click', () => {
            this.toggleAudioPlayback();
        });

        document.getElementById('btn-regenerate-briefing')?.addEventListener('click', () => {
            this.generateBriefing();
        });

        // Audio progress seeking
        document.getElementById('audio-progress-bar')?.addEventListener('click', (e) => {
            if (!this.audioElement) return;
            const rect = e.target.getBoundingClientRect();
            const percent = (e.clientX - rect.left) / rect.width;
            this.audioElement.currentTime = percent * this.audioElement.duration;
        });

        // Graph controls - main view
        const btnZoomIn = document.getElementById('btn-graph-zoom-in');
        const btnZoomOut = document.getElementById('btn-graph-zoom-out');
        const btnFit = document.getElementById('btn-graph-fit');
        const btnFullscreen = document.getElementById('btn-graph-fullscreen');

        console.log('[DEBUG] Button elements found:', {
            zoomIn: !!btnZoomIn,
            zoomOut: !!btnZoomOut,
            fit: !!btnFit,
            fullscreen: !!btnFullscreen
        });

        if (!btnZoomIn || !btnZoomOut || !btnFit || !btnFullscreen) {
            console.error('[DEBUG] Some graph control buttons NOT FOUND');
        }

        btnZoomIn?.addEventListener('click', () => {
            console.log('[DEBUG] Zoom In clicked, sigma:', this.sigma);
            if (this.sigma) {
                const camera = this.sigma.getCamera();
                camera.animatedZoom({ duration: 200 });
                this.log('info', 'Zoomed in');
            }
        });

        btnZoomOut?.addEventListener('click', () => {
            console.log('[DEBUG] Zoom Out clicked, sigma:', this.sigma);
            if (this.sigma) {
                const camera = this.sigma.getCamera();
                camera.animatedUnzoom({ duration: 200 });
                this.log('info', 'Zoomed out');
            }
        });

        btnFit?.addEventListener('click', () => {
            console.log('[DEBUG] Fit clicked, sigma:', this.sigma);
            if (this.sigma) {
                const camera = this.sigma.getCamera();
                camera.animatedReset({ duration: 200 });
                this.log('info', 'Graph fitted to view');
            }
        });

        btnFullscreen?.addEventListener('click', () => {
            console.log('[DEBUG] Fullscreen clicked');
            this.log('info', 'Opening fullscreen graph');
            this.openFullscreenGraph();
        });

        // Graph controls - fullscreen
        document.getElementById('btn-close-fullscreen-graph')?.addEventListener('click', () => {
            this.closeFullscreenGraph();
        });

        document.getElementById('btn-fullscreen-zoom-in')?.addEventListener('click', () => {
            if (this.sigmaFullscreen) {
                const camera = this.sigmaFullscreen.getCamera();
                camera.animatedZoom({ duration: 200 });
            }
        });

        document.getElementById('btn-fullscreen-zoom-out')?.addEventListener('click', () => {
            if (this.sigmaFullscreen) {
                const camera = this.sigmaFullscreen.getCamera();
                camera.animatedUnzoom({ duration: 200 });
            }
        });

        document.getElementById('btn-fullscreen-fit')?.addEventListener('click', () => {
            if (this.sigmaFullscreen) {
                const camera = this.sigmaFullscreen.getCamera();
                camera.animatedReset({ duration: 200 });
            }
        });

        // Graph search - main view
        const graphSearchInput = document.getElementById('graph-entity-search');
        console.log('[DEBUG] Graph search input element:', graphSearchInput);
        if (graphSearchInput) {
            graphSearchInput.addEventListener('input', (e) => {
                console.log('[DEBUG] Search input changed:', e.target.value);
                this.log('info', `Searching: "${e.target.value}"`);
                this.handleGraphSearch(e.target.value, 'graph-search-results');
            });
            graphSearchInput.addEventListener('keydown', (e) => {
                if (e.key === 'Enter') {
                    e.preventDefault();
                    console.log('[DEBUG] Enter pressed in search:', graphSearchInput.value);
                    this.log('info', `Search [Enter]: "${graphSearchInput.value}"`);
                    // Clear debounce and trigger immediate search
                    if (this.graphSearchTimeout) {
                        clearTimeout(this.graphSearchTimeout);
                    }
                    if (graphSearchInput.value.length >= 2) {
                        this.handleGraphSearch(graphSearchInput.value, 'graph-search-results');
                    }
                }
            });
            graphSearchInput.addEventListener('focus', () => {
                console.log('[DEBUG] Search input focused');
                if (graphSearchInput.value.length >= 2) {
                    document.getElementById('graph-search-results')?.classList.remove('hidden');
                }
            });
        } else {
            console.error('[DEBUG] Graph search input NOT FOUND');
        }

        // Graph search - fullscreen
        const fullscreenSearchInput = document.getElementById('fullscreen-graph-search');
        if (fullscreenSearchInput) {
            fullscreenSearchInput.addEventListener('input', (e) => {
                this.handleGraphSearch(e.target.value, 'fullscreen-search-results');
            });
            fullscreenSearchInput.addEventListener('focus', () => {
                if (fullscreenSearchInput.value.length >= 2) {
                    document.getElementById('fullscreen-search-results')?.classList.remove('hidden');
                }
            });
        }

        // Close search results when clicking outside
        document.addEventListener('click', (e) => {
            if (!e.target.closest('.graph-search-wrapper')) {
                document.getElementById('graph-search-results')?.classList.add('hidden');
                document.getElementById('fullscreen-search-results')?.classList.add('hidden');
            }
        });

        // Depth selector - main view
        const depthSelect = document.getElementById('graph-depth-select');
        console.log('[DEBUG] Depth select element:', depthSelect);
        if (depthSelect) {
            depthSelect.addEventListener('change', (e) => {
                const newDepth = parseInt(e.target.value);
                console.log('[DEBUG] Depth changed to:', newDepth);
                this.log('info', `Depth changed to ${newDepth} hops`);
                this.graphDepth = newDepth;
            });
        } else {
            console.error('[DEBUG] Depth select NOT FOUND');
        }

        // Depth selector - fullscreen
        const fullscreenDepthSelect = document.getElementById('fullscreen-depth-select');
        if (fullscreenDepthSelect) {
            fullscreenDepthSelect.addEventListener('change', (e) => {
                const newDepth = parseInt(e.target.value);
                console.log('[DEBUG] Fullscreen depth changed to:', newDepth);
                this.graphDepth = newDepth;
            });
        }

        // Escape key to close fullscreen modal
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && !document.getElementById('fullscreen-graph-modal')?.classList.contains('hidden')) {
                this.closeFullscreenGraph();
            }
        });

        // Entity list controls
        document.getElementById('entity-list-search-input')?.addEventListener('input', (e) => {
            this.filterEntityList(e.target.value);
        });

        document.getElementById('entity-list-type-filter')?.addEventListener('change', (e) => {
            this.entityListState.typeFilter = e.target.value;
            this.loadEntityList();
        });

        document.getElementById('entity-list-sort')?.addEventListener('change', (e) => {
            this.entityListState.sortBy = e.target.value;
            this.loadEntityList();
        });

        document.getElementById('entity-select-all')?.addEventListener('change', (e) => {
            this.toggleSelectAllEntities(e.target.checked);
        });

        document.getElementById('btn-entity-merge')?.addEventListener('click', () => {
            this.mergeSelectedEntities();
        });

        document.getElementById('btn-entity-delete')?.addEventListener('click', () => {
            this.deleteSelectedEntities();
        });

        document.getElementById('btn-entity-export')?.addEventListener('click', () => {
            this.exportSelectedEntities();
        });

        document.getElementById('btn-entity-prev')?.addEventListener('click', () => {
            if (this.entityListState.page > 1) {
                this.entityListState.page--;
                this.loadEntityList();
            }
        });

        document.getElementById('btn-entity-next')?.addEventListener('click', () => {
            this.entityListState.page++;
            this.loadEntityList();
        });

        // Feed tabs
        document.querySelectorAll('.tab[data-tab]').forEach(tab => {
            tab.addEventListener('click', () => {
                document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
                tab.classList.add('active');
                this.filterNewsFeed(tab.dataset.tab);
            });
        });

        // Search inputs
        document.getElementById('feed-search')?.addEventListener('input', (e) => {
            this.filterNewsFeed('all', e.target.value);
        });

        document.getElementById('semantic-search')?.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                this.semanticSearch(e.target.value);
            }
        });

        // Mobile menu
        document.getElementById('mobile-menu-toggle')?.addEventListener('click', () => {
            document.getElementById('left-sidebar')?.classList.toggle('mobile-open');
        });

        // Local Government buttons
        document.getElementById('btn-local-briefing')?.addEventListener('click', () => {
            this.loadLocalBriefing();
        });

        document.getElementById('btn-scan-watch-areas')?.addEventListener('click', () => {
            this.scanWatchAreas();
        });

        document.getElementById('btn-add-watch-area')?.addEventListener('click', () => {
            this.showAddWatchAreaModal();
        });

        document.getElementById('btn-close-watch-modal')?.addEventListener('click', () => {
            this.hideWatchAreaModal();
        });

        // Local government view switching
        document.querySelectorAll('[data-local-tab]').forEach(tab => {
            tab.addEventListener('click', () => {
                document.querySelectorAll('[data-local-tab]').forEach(t => t.classList.remove('active'));
                tab.classList.add('active');
                this.switchLocalView(tab.dataset.localTab);
            });
        });
    }

    switchLocalView(viewName) {
        document.querySelectorAll('.local-view-content').forEach(view => {
            view.classList.toggle('hidden', view.id !== `local-${viewName}`);
        });

        // Load specific data for each view
        switch (viewName) {
            case 'alerts':
                this.loadLocalAlerts();
                break;
            case 'watch':
                this.loadWatchAreas();
                break;
            case 'briefing':
                this.loadLocalBriefing();
                break;
            case 'zoning':
                this.loadZoningCases();
                break;
            case 'permits':
                this.loadBuildingPermits();
                break;
            case 'property':
                this.loadPropertyTransactions();
                break;
            case 'court':
                this.loadCourtCases();
                break;
        }
    }

    async loadZoningCases() {
        try {
            const response = await this.fetchApi('/local/zoning?limit=20');
            this.renderZoningCases(response.cases || []);
        } catch (error) {
            console.error('Failed to load zoning cases:', error);
        }
    }

    async loadBuildingPermits() {
        try {
            const response = await this.fetchApi('/local/permits?limit=20');
            this.renderBuildingPermits(response.permits || []);
        } catch (error) {
            console.error('Failed to load building permits:', error);
        }
    }

    async loadPropertyTransactions() {
        try {
            const response = await this.fetchApi('/local/property?limit=20');
            this.renderPropertyTransactions(response.transactions || []);
        } catch (error) {
            console.error('Failed to load property transactions:', error);
        }
    }

    async loadCourtCases() {
        try {
            const response = await this.fetchApi('/local/court?limit=20');
            this.renderCourtCases(response.cases || []);
        } catch (error) {
            console.error('Failed to load court cases:', error);
        }
    }

    renderZoningCases(cases) {
        const container = document.getElementById('local-zoning');
        if (!container) return;

        if (cases.length === 0) {
            container.innerHTML = '<div class="empty-state-small"><span>No zoning cases found</span></div>';
            return;
        }

        container.innerHTML = `
            <ul class="local-data-list">
                ${cases.map(c => `
                    <li class="local-data-item">
                        <div class="data-item-header">
                            <span class="case-number">${c.case_number || 'N/A'}</span>
                            <span class="case-status status-${(c.status || 'pending').toLowerCase()}">${c.status || 'Pending'}</span>
                        </div>
                        <div class="data-item-address">${c.address || 'No address'}</div>
                        <div class="data-item-meta">
                            <span>${c.jurisdiction}</span>
                            <span>${c.case_type || 'Zoning'}</span>
                            <span>${c.filed_date || ''}</span>
                        </div>
                    </li>
                `).join('')}
            </ul>
        `;
    }

    renderBuildingPermits(permits) {
        const container = document.getElementById('local-permits');
        if (!container) return;

        if (permits.length === 0) {
            container.innerHTML = '<div class="empty-state-small"><span>No permits found</span></div>';
            return;
        }

        container.innerHTML = `
            <ul class="local-data-list">
                ${permits.map(p => `
                    <li class="local-data-item">
                        <div class="data-item-header">
                            <span class="permit-number">${p.permit_number || 'N/A'}</span>
                            <span class="permit-type">${p.permit_type || 'Permit'}</span>
                        </div>
                        <div class="data-item-address">${p.address || 'No address'}</div>
                        <div class="data-item-meta">
                            <span>${p.jurisdiction}</span>
                            <span>${p.contractor || ''}</span>
                            <span class="permit-value">${p.estimated_value ? '$' + p.estimated_value.toLocaleString() : ''}</span>
                        </div>
                    </li>
                `).join('')}
            </ul>
        `;
    }

    renderPropertyTransactions(transactions) {
        const container = document.getElementById('local-property');
        if (!container) return;

        if (transactions.length === 0) {
            container.innerHTML = '<div class="empty-state-small"><span>No transactions found</span></div>';
            return;
        }

        container.innerHTML = `
            <ul class="local-data-list">
                ${transactions.map(t => `
                    <li class="local-data-item">
                        <div class="data-item-header">
                            <span class="sale-price">${t.sale_price ? '$' + t.sale_price.toLocaleString() : 'N/A'}</span>
                            <span class="sale-date">${t.sale_date || ''}</span>
                        </div>
                        <div class="data-item-address">${t.address || 'No address'}</div>
                        <div class="data-item-meta">
                            <span>From: ${t.grantor || 'Unknown'}</span>
                            <span>To: ${t.grantee || 'Unknown'}</span>
                        </div>
                    </li>
                `).join('')}
            </ul>
        `;
    }

    renderCourtCases(cases) {
        const container = document.getElementById('local-court');
        if (!container) return;

        if (cases.length === 0) {
            container.innerHTML = '<div class="empty-state-small"><span>No court cases found</span></div>';
            return;
        }

        container.innerHTML = `
            <ul class="local-data-list">
                ${cases.map(c => `
                    <li class="local-data-item">
                        <div class="data-item-header">
                            <span class="case-number">${c.case_number || 'N/A'}</span>
                            <span class="case-status status-${(c.status || 'active').toLowerCase()}">${c.status || 'Active'}</span>
                        </div>
                        <div class="data-item-title">${c.case_title || 'Case'}</div>
                        <div class="data-item-meta">
                            <span>${c.court}</span>
                            <span>${c.case_type || ''}</span>
                            <span>${c.filed_date || ''}</span>
                        </div>
                    </li>
                `).join('')}
            </ul>
        `;
    }

    filterNewsFeed(category, searchQuery = '') {
        const items = document.querySelectorAll('#news-feed .news-item');
        const query = searchQuery.toLowerCase();

        items.forEach(item => {
            const title = item.querySelector('.news-item-title')?.textContent.toLowerCase() || '';
            const categoryTag = item.querySelector('.news-item-category')?.textContent.toLowerCase() || '';

            const matchesSearch = !query || title.includes(query);

            // Special handling for tech_ai tab - match both tech_ai and tech_general
            let matchesCategory;
            if (category === 'tech_ai') {
                matchesCategory = categoryTag.includes('tech_ai') || categoryTag.includes('tech_general');
            } else {
                matchesCategory = category === 'all' || categoryTag.includes(category);
            }

            item.style.display = matchesSearch && matchesCategory ? '' : 'none';
        });
    }

    // =============================================
    // FULLSCREEN GRAPH (Sigma.js)
    // =============================================

    openFullscreenGraph() {
        const modal = document.getElementById('fullscreen-graph-modal');
        if (!modal) return;

        modal.classList.remove('hidden');
        document.body.style.overflow = 'hidden';

        // Initialize fullscreen graph if not already done
        if (!this.sigmaFullscreen) {
            this.initEntityGraph('fullscreen-entity-graph');
        } else {
            // Copy data from main graph to fullscreen
            this.copyGraphToFullscreen();
        }
    }

    /**
     * Copy main graph data to fullscreen graph
     */
    copyGraphToFullscreen() {
        if (!this.graph || !this.graphFullscreen || !this.sigmaFullscreen) return;

        this.graphFullscreen.clear();

        // Copy all nodes
        this.graph.forEachNode((node, attrs) => {
            this.graphFullscreen.addNode(node, { ...attrs });
        });

        // Copy all edges
        this.graph.forEachEdge((edge, attrs, source, target) => {
            try {
                this.graphFullscreen.addEdge(source, target, { ...attrs });
            } catch (e) {
                // Edge may already exist
            }
        });

        this.scheduleRefresh();

        // Fit view after a short delay
        setTimeout(() => {
            const camera = this.sigmaFullscreen.getCamera();
            camera.animatedReset({ duration: 200 });
        }, 100);
    }

    closeFullscreenGraph() {
        const modal = document.getElementById('fullscreen-graph-modal');
        if (!modal) return;

        modal.classList.add('hidden');
        document.body.style.overflow = '';
    }

    showEntityDetails(data) {
        // Log entity details and show in info panel
        console.log('Entity clicked:', data);
        this.log('info', `Selected entity: ${data.label || data.name || data.id}`);
    }

    // =============================================
    // GRAPH SEARCH AND EXPAND
    // =============================================

    async handleGraphSearch(query, resultsContainerId) {
        console.log('[DEBUG] handleGraphSearch called:', query, resultsContainerId);
        const resultsContainer = document.getElementById(resultsContainerId);
        if (!resultsContainer) {
            console.error('[DEBUG] Results container NOT FOUND:', resultsContainerId);
            return;
        }

        // Clear previous timeout
        if (this.graphSearchTimeout) {
            clearTimeout(this.graphSearchTimeout);
        }

        // Hide if query too short
        if (query.length < 2) {
            console.log('[DEBUG] Query too short, hiding results');
            resultsContainer.classList.add('hidden');
            return;
        }

        // Debounce the search
        this.graphSearchTimeout = setTimeout(async () => {
            console.log('[DEBUG] Executing search for:', query);
            try {
                const response = await this.fetchApi(`/entities/search?q=${encodeURIComponent(query)}&limit=10`);
                console.log('[DEBUG] Search response:', response);
                const results = response.results || [];

                if (results.length === 0) {
                    resultsContainer.innerHTML = `
                        <div class="graph-search-no-results">
                            No entities found matching "${this.escapeHtml(query)}"
                        </div>
                    `;
                } else {
                    resultsContainer.innerHTML = results.map(entity => `
                        <div class="graph-search-result-item"
                             data-entity-id="${entity.entity_id}"
                             onclick="window.pulseDashboard.searchAndFocusEntity('${entity.entity_id}', '${this.escapeHtml(entity.name)}')">
                            <span class="entity-type-badge ${(entity.entity_type || 'custom').toLowerCase()}">
                                ${(entity.entity_type || 'ENT').slice(0, 3).toUpperCase()}
                            </span>
                            <span class="entity-name">${this.escapeHtml(entity.name)}</span>
                        </div>
                    `).join('');
                }

                resultsContainer.classList.remove('hidden');
            } catch (error) {
                console.error('Graph search failed:', error);
                resultsContainer.innerHTML = `
                    <div class="graph-search-no-results">Search failed</div>
                `;
                resultsContainer.classList.remove('hidden');
            }
        }, 300);
    }

    /**
     * Search for entity and focus camera on it (Sigma.js version)
     */
    async searchAndFocusEntity(entityId, entityName) {
        // Hide search results
        document.getElementById('graph-search-results')?.classList.add('hidden');
        document.getElementById('fullscreen-search-results')?.classList.add('hidden');

        // Clear search inputs
        const searchInput = document.getElementById('graph-entity-search');
        const fullscreenSearch = document.getElementById('fullscreen-graph-search');
        if (searchInput) searchInput.value = entityName || '';
        if (fullscreenSearch) fullscreenSearch.value = entityName || '';

        // Determine which graph is active
        const isFullscreen = !document.getElementById('fullscreen-graph-modal')?.classList.contains('hidden');
        const graph = isFullscreen ? this.graphFullscreen : this.graph;
        const sigma = isFullscreen ? this.sigmaFullscreen : this.sigma;

        if (!graph || !sigma) return;

        // Check if entity exists in current graph
        if (graph.hasNode(entityId)) {
            // Entity already in graph - just focus on it
            this.centerOnEntity(entityId, isFullscreen);
        } else {
            // Entity not in graph - load its neighborhood
            await this.loadEntityAndFocus(entityId, isFullscreen);
        }
    }

    /**
     * Center camera on entity and highlight it (Sigma.js version)
     */
    centerOnEntity(entityId, isFullscreen = false) {
        const graph = isFullscreen ? this.graphFullscreen : this.graph;
        const sigma = isFullscreen ? this.sigmaFullscreen : this.sigma;

        if (!graph || !sigma || !graph.hasNode(entityId)) return;

        const nodeAttrs = graph.getNodeAttributes(entityId);

        // Highlight the node and its neighborhood
        this.highlightNode(entityId, graph, sigma);

        // Get node position and animate camera to center on it
        const camera = sigma.getCamera();
        camera.animate(
            { x: nodeAttrs.x, y: nodeAttrs.y, ratio: 0.3 },
            { duration: 500 }
        );

        this.log('info', `Focused on entity: ${nodeAttrs.label || entityId}`);
    }

    /**
     * Load entity neighborhood and focus on it (Sigma.js version)
     */
    async loadEntityAndFocus(entityId, isFullscreen = false) {
        try {
            this.log('info', 'Loading entity neighborhood...');

            const graph = isFullscreen ? this.graphFullscreen : this.graph;
            const sigma = isFullscreen ? this.sigmaFullscreen : this.sigma;

            if (!graph || !sigma) return;

            // Load neighborhood with current depth setting
            const neighborhood = await this.fetchApi(`/network/neighborhood/${entityId}?depth=${this.graphDepth}`);

            if (!neighborhood || !neighborhood.nodes || neighborhood.nodes.length === 0) {
                this.showToast('warning', 'Entity has no connections in the network');
                return;
            }

            // Clear graph and add neighborhood
            graph.clear();

            // Add nodes in a radial layout around the center entity
            const centerNode = neighborhood.nodes.find(n => n.id === neighborhood.center?.id) || neighborhood.nodes[0];
            const otherNodes = neighborhood.nodes.filter(n => n.id !== centerNode?.id);

            // Add center node at origin
            if (centerNode) {
                graph.addNode(centerNode.id, {
                    x: 0,
                    y: 0,
                    size: 12,
                    label: centerNode.name,
                    color: this.getNodeColor(centerNode.entity_type),
                    entityType: (centerNode.entity_type || 'custom').toLowerCase()
                });
            }

            // Add other nodes in a circle around center
            const radius = 300;
            const angleStep = (2 * Math.PI) / Math.max(1, otherNodes.length);

            otherNodes.forEach((node, i) => {
                const angle = i * angleStep;
                graph.addNode(node.id, {
                    x: radius * Math.cos(angle),
                    y: radius * Math.sin(angle),
                    size: 8,
                    label: node.name,
                    color: this.getNodeColor(node.entity_type),
                    entityType: (node.entity_type || 'custom').toLowerCase()
                });
            });

            // Add edges
            for (const edge of neighborhood.edges || []) {
                if (graph.hasNode(edge.source) && graph.hasNode(edge.target)) {
                    try {
                        graph.addEdge(edge.source, edge.target, {
                            size: Math.max(1, Math.min(5, edge.weight || 1)),
                            color: this.getEdgeColor(edge.relationship_type),
                            edgeType: edge.relationship_type || 'associated_with'
                        });
                    } catch (e) {
                        // Edge may already exist
                    }
                }
            }

            this.scheduleRefresh();

            // After a short delay, center on the target entity
            setTimeout(() => {
                this.centerOnEntity(entityId, isFullscreen);
            }, 100);

        } catch (error) {
            console.error('Failed to load entity neighborhood:', error);
            this.showToast('error', 'Failed to load entity connections');
        }
    }

    // =============================================
    // ENTITY LIST VIEW
    // =============================================

    async loadEntityList() {
        const { page, perPage, sortBy, typeFilter } = this.entityListState;

        try {
            // Build query params
            const params = new URLSearchParams({
                limit: perPage,
                offset: (page - 1) * perPage
            });

            if (sortBy) params.append('sort', sortBy);
            if (typeFilter) params.append('type', typeFilter);

            const response = await this.fetchApi(`/entities?${params}`);
            const entities = response.entities || response || [];

            // Get total count (may need separate API call or be included in response)
            this.entityListState.total = response.total || entities.length;

            this.renderEntityTable(entities);
            this.updateEntityPagination();
        } catch (error) {
            console.error('Failed to load entity list:', error);
            this.showToast('error', 'Failed to load entities');
        }
    }

    renderEntityTable(entities) {
        const tbody = document.getElementById('entity-table-body');
        if (!tbody) return;

        if (entities.length === 0) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="6" style="text-align: center; padding: 40px; color: var(--text-muted);">
                        No entities found
                    </td>
                </tr>
            `;
            return;
        }

        tbody.innerHTML = entities.map(entity => {
            const isSelected = this.entityListState.selected.has(entity.entity_id);
            const hasWikidata = entity.entity_metadata?.wikidata_id;
            const mentionCount = entity.mention_count || 0;
            const entityType = (entity.entity_type || 'unknown').toLowerCase();

            return `
                <tr data-entity-id="${entity.entity_id}">
                    <td class="entity-checkbox">
                        <input type="checkbox"
                            ${isSelected ? 'checked' : ''}
                            onchange="window.pulseDashboard.toggleEntitySelection('${entity.entity_id}', this.checked)">
                    </td>
                    <td class="entity-name">${this.escapeHtml(entity.name)}</td>
                    <td><span class="entity-type ${entityType}">${entityType}</span></td>
                    <td class="entity-mentions">${mentionCount}</td>
                    <td class="entity-wikidata">
                        ${hasWikidata
                            ? `<span class="linked"><i class="fas fa-check-circle"></i> ${entity.entity_metadata.wikidata_id}</span>`
                            : '<span class="unlinked"><i class="fas fa-times-circle"></i> Not linked</span>'
                        }
                    </td>
                    <td>
                        <button class="btn btn-sm" onclick="window.pulseDashboard.viewEntityInGraph('${entity.entity_id}')" title="View in Graph">
                            <i class="fas fa-project-diagram"></i>
                        </button>
                    </td>
                </tr>
            `;
        }).join('');
    }

    updateEntityPagination() {
        const { page, perPage, total } = this.entityListState;
        const start = (page - 1) * perPage + 1;
        const end = Math.min(page * perPage, total);

        document.getElementById('entity-page-start').textContent = total > 0 ? start : 0;
        document.getElementById('entity-page-end').textContent = end;
        document.getElementById('entity-total').textContent = total;

        document.getElementById('btn-entity-prev').disabled = page <= 1;
        document.getElementById('btn-entity-next').disabled = end >= total;
    }

    filterEntityList(query) {
        this.entityListState.searchQuery = query;
        // Simple client-side filtering for now
        const rows = document.querySelectorAll('#entity-table-body tr[data-entity-id]');
        const lowerQuery = query.toLowerCase();

        rows.forEach(row => {
            const name = row.querySelector('.entity-name')?.textContent.toLowerCase() || '';
            row.style.display = name.includes(lowerQuery) ? '' : 'none';
        });
    }

    toggleEntitySelection(entityId, selected) {
        if (selected) {
            this.entityListState.selected.add(entityId);
        } else {
            this.entityListState.selected.delete(entityId);
        }
        this.updateBulkActionButtons();
    }

    toggleSelectAllEntities(selectAll) {
        const checkboxes = document.querySelectorAll('#entity-table-body input[type="checkbox"]');
        checkboxes.forEach(checkbox => {
            const row = checkbox.closest('tr');
            const entityId = row?.dataset.entityId;
            if (entityId) {
                checkbox.checked = selectAll;
                if (selectAll) {
                    this.entityListState.selected.add(entityId);
                } else {
                    this.entityListState.selected.delete(entityId);
                }
            }
        });
        this.updateBulkActionButtons();
    }

    updateBulkActionButtons() {
        const count = this.entityListState.selected.size;

        document.getElementById('merge-count').textContent = count;
        document.getElementById('delete-count').textContent = count;

        document.getElementById('btn-entity-merge').disabled = count < 2;
        document.getElementById('btn-entity-delete').disabled = count === 0;
        document.getElementById('btn-entity-export').disabled = count === 0;
    }

    async mergeSelectedEntities() {
        const selected = Array.from(this.entityListState.selected);
        if (selected.length < 2) {
            this.showToast('warning', 'Select at least 2 entities to merge');
            return;
        }

        // For now, use first selected as primary
        const primaryId = selected[0];
        const secondaryIds = selected.slice(1);

        if (!confirm(`Merge ${selected.length} entities? The first selected entity will be kept.`)) {
            return;
        }

        try {
            // Merge entities one by one into primary
            for (const secondaryId of secondaryIds) {
                await this.fetchApi(`/entities/merge?primary_id=${primaryId}&secondary_id=${secondaryId}`, {
                    method: 'POST'
                });
            }

            this.showToast('success', `Merged ${selected.length} entities`);
            this.entityListState.selected.clear();
            this.loadEntityList();
        } catch (error) {
            console.error('Failed to merge entities:', error);
            this.showToast('error', 'Failed to merge entities');
        }
    }

    async deleteSelectedEntities() {
        const selected = Array.from(this.entityListState.selected);
        if (selected.length === 0) return;

        if (!confirm(`Delete ${selected.length} entities? This cannot be undone.`)) {
            return;
        }

        try {
            await this.fetchApi('/entities/bulk', {
                method: 'DELETE',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ entity_ids: selected })
            });

            this.showToast('success', `Deleted ${selected.length} entities`);
            this.entityListState.selected.clear();
            this.loadEntityList();
        } catch (error) {
            console.error('Failed to delete entities:', error);
            this.showToast('error', 'Failed to delete entities');
        }
    }

    exportSelectedEntities() {
        const selected = Array.from(this.entityListState.selected);
        if (selected.length === 0) return;

        // Get selected entities data from table
        const entities = selected.map(id => {
            const row = document.querySelector(`tr[data-entity-id="${id}"]`);
            if (!row) return null;
            return {
                entity_id: id,
                name: row.querySelector('.entity-name')?.textContent,
                type: row.querySelector('.entity-type')?.textContent
            };
        }).filter(Boolean);

        // Download as JSON
        const blob = new Blob([JSON.stringify(entities, null, 2)], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `entities-export-${new Date().toISOString().split('T')[0]}.json`;
        a.click();
        URL.revokeObjectURL(url);

        this.showToast('success', `Exported ${entities.length} entities`);
    }

    viewEntityInGraph(entityId) {
        // Switch to network view and focus on entity
        this.switchView('entities');
        setTimeout(() => {
            if (this.graph && this.sigma && this.graph.hasNode(entityId)) {
                // Center camera on entity
                this.centerOnEntity(entityId, false);
            } else if (this.graph && this.sigma) {
                // Entity not in graph - load its neighborhood
                this.loadEntityAndFocus(entityId, false);
            }
        }, 300);
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    // =============================================
    // UTILITY FUNCTIONS
    // =============================================

    startClock() {
        const updateClock = () => {
            const now = new Date();
            const timeStr = now.toLocaleTimeString('en-US', { hour12: false });
            const dateStr = now.toLocaleDateString('en-US', {
                weekday: 'short',
                month: 'short',
                day: 'numeric'
            });
            document.getElementById('current-time').textContent = `${dateStr} ${timeStr}`;
        };

        updateClock();
        setInterval(updateClock, 1000);
    }

    updateSystemHealth(status) {
        const indicator = document.querySelector('#system-health .status-indicator');
        const text = document.querySelector('#system-health span:last-child');

        if (indicator) {
            indicator.className = `status-indicator ${status}`;
        }

        if (text) {
            const statusText = {
                'healthy': 'System Healthy',
                'warning': 'System Degraded',
                'error': 'System Error'
            };
            text.textContent = statusText[status] || 'Unknown';
        }
    }

    log(level, message) {
        const logContainer = document.getElementById('system-log');
        if (!logContainer) return;

        const now = new Date();
        const timestamp = now.toLocaleTimeString('en-US', { hour12: false });

        const line = document.createElement('div');
        line.className = 'console-line';
        line.innerHTML = `
            <span class="console-timestamp">${timestamp}</span>
            <span class="console-level ${level}">${level.toUpperCase()}</span>
            <span class="console-message">${message}</span>
        `;

        logContainer.appendChild(line);
        logContainer.scrollTop = logContainer.scrollHeight;

        // Keep only last 50 lines
        while (logContainer.children.length > 50) {
            logContainer.removeChild(logContainer.firstChild);
        }
    }

    formatDate(dateStr) {
        if (!dateStr) return '--';
        const date = new Date(dateStr);
        return date.toLocaleDateString('en-US', {
            year: 'numeric',
            month: 'short',
            day: 'numeric'
        });
    }

    formatTime(date) {
        return date.toLocaleTimeString('en-US', {
            hour: '2-digit',
            minute: '2-digit',
            hour12: false
        });
    }

    formatRelativeTime(date) {
        const now = new Date();
        const diff = (now - date) / 1000; // seconds

        if (diff < 60) return 'just now';
        if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
        if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
        if (diff < 604800) return `${Math.floor(diff / 86400)}d ago`;

        return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
    }
}

// Initialize dashboard when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    window.pulseDashboard = new PulseDashboard();
});
