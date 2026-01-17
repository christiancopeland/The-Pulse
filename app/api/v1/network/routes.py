"""
Network Mapper API routes for The Pulse.

Provides endpoints for:
- Graph analysis (paths, centrality, communities)
- Relationship discovery
- Entity network visualization
- Graph statistics
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional, List, Dict, Any, Literal
from uuid import UUID
from pydantic import BaseModel, Field
from datetime import datetime, timezone, timedelta
from sqlalchemy import text
import asyncio
import logging
import time

from app.core.dependencies import get_db, get_local_user, LocalUser
from app.services.network_mapper import NetworkMapperService, RelationshipDiscoveryService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/network", tags=["network"])


# ==================== Graph Cache ====================

class GraphCache:
    """Simple in-memory cache for loaded graphs with TTL."""

    def __init__(self, ttl_seconds: int = 60):
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._ttl = timedelta(seconds=ttl_seconds)
        self._lock = asyncio.Lock()

    def _cache_key(self, user_id: UUID) -> str:
        return str(user_id) if user_id else "default"

    async def get_mapper(
        self,
        db,
        user_id: Optional[UUID]
    ) -> NetworkMapperService:
        """Get or create a cached NetworkMapperService."""
        key = self._cache_key(user_id)
        now = datetime.now(timezone.utc)

        async with self._lock:
            # Check if we have a valid cached entry
            if key in self._cache:
                entry = self._cache[key]
                if now - entry["loaded_at"] < self._ttl:
                    logger.debug(f"Graph cache hit for user {key}")
                    # Update db session reference
                    entry["mapper"].db = db
                    return entry["mapper"]
                else:
                    logger.debug(f"Graph cache expired for user {key}")

            # Create new mapper and load from database
            logger.info(f"Loading graph from database for user {key}")
            mapper = NetworkMapperService(db, user_id=user_id)
            await mapper.load_from_database()

            # Cache it
            self._cache[key] = {
                "mapper": mapper,
                "loaded_at": now
            }

            return mapper

    async def invalidate(self, user_id: Optional[UUID] = None):
        """Invalidate cache for a user or all users."""
        async with self._lock:
            if user_id:
                key = self._cache_key(user_id)
                if key in self._cache:
                    del self._cache[key]
                    logger.info(f"Invalidated graph cache for user {key}")
            else:
                self._cache.clear()
                logger.info("Invalidated all graph caches")


# SERV-007: Global cache instance with 5-minute TTL (was 60 seconds)
_graph_cache = GraphCache(ttl_seconds=300)


# ==================== Layout Cache (SERV-002) ====================

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
    ) -> Optional[Dict[str, tuple]]:
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
        positions: Dict[str, tuple]
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
                if keys_to_delete:
                    logger.info(f"Invalidated {len(keys_to_delete)} layout cache entries")
            else:
                self._cache.clear()
                logger.info("Invalidated all layout caches")


# Global layout cache with 5-minute TTL
_layout_cache = LayoutCache(ttl_seconds=300)


# ==================== Cluster Cache (SERV-003) ====================

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
                    logger.debug(f"Cluster cache expired for {key}")
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
                if keys_to_delete:
                    logger.info(f"Invalidated {len(keys_to_delete)} cluster cache entries")
            else:
                self._cache.clear()
                logger.info("Invalidated all cluster caches")


# Global cluster cache with 10-minute TTL
_cluster_cache = ClusterCache(ttl_seconds=600)


# ==================== Pydantic Models ====================

class PathRequest(BaseModel):
    """Request model for path finding."""
    source_id: str = Field(..., description="Source entity ID")
    target_id: str = Field(..., description="Target entity ID")
    max_depth: int = Field(6, ge=1, le=10, description="Maximum path length")


class RelationshipRequest(BaseModel):
    """Request model for adding relationships."""
    source_id: str = Field(..., description="Source entity ID")
    target_id: str = Field(..., description="Target entity ID")
    relationship_type: str = Field(..., description="Type of relationship")
    confidence: float = Field(0.5, ge=0, le=1, description="Confidence score")
    description: Optional[str] = None


class DiscoveryRequest(BaseModel):
    """Request model for relationship discovery."""
    min_co_occurrences: int = Field(2, ge=1, description="Minimum co-occurrences")
    time_window_days: int = Field(30, ge=1, description="Time window in days")
    use_llm: bool = Field(True, description="Use LLM for relationship inference")


# ==================== Graph Endpoints ====================

@router.get("/status")
async def get_network_status(
    db=Depends(get_db),
    current_user: LocalUser = Depends(get_local_user)
):
    """Get network graph status and statistics."""
    mapper = await _graph_cache.get_mapper(db, user_id=current_user.user_id)

    return {
        "status": "loaded",
        "stats": mapper.get_graph_stats()
    }


@router.get("/graph")
async def get_full_graph(
    include_isolated: bool = Query(False, description="Include nodes without edges"),
    include_positions: bool = Query(True, description="Include pre-computed layout positions"),
    layout: str = Query("spring", description="Layout algorithm: spring, kamada_kawai, circular, shell"),
    include_clusters: bool = Query(False, description="Include cluster data for semantic zoom"),
    db=Depends(get_db),
    current_user: LocalUser = Depends(get_local_user)
):
    """
    Get full entity graph in Sigma.js/graphology format.

    With include_positions=True (default), nodes come with pre-computed
    x,y coordinates eliminating client-side layout computation and jitter.

    For large graphs, use include_clusters=True to get cluster data for
    semantic zoom (show clusters at overview, entities at detail).

    Performance optimizations (SERV-000 through SERV-003):
    - Timing instrumentation in response._timings
    - Layout positions cached for 5 minutes
    - Cluster data cached for 10 minutes
    - Fixed double layout computation bug
    """
    timings = {}
    total_start = time.perf_counter()

    # SERV-000: Time graph loading
    t0 = time.perf_counter()
    mapper = await _graph_cache.get_mapper(db, user_id=current_user.user_id)
    timings["graph_load_ms"] = round((time.perf_counter() - t0) * 1000, 1)

    node_count = mapper.graph.number_of_nodes()

    # SERV-000: Time export
    t0 = time.perf_counter()
    elements = mapper.export_cytoscape(include_isolated=include_isolated)
    timings["export_cytoscape_ms"] = round((time.perf_counter() - t0) * 1000, 1)

    # SERV-002: Layout positions with caching
    # SERV-009: Skip server-side layout for large graphs (>500 nodes)
    # Client FA2 Web Worker handles layout non-blocking, so server computation
    # is unnecessary overhead for large graphs
    SKIP_LAYOUT_THRESHOLD = 500
    positions = {}

    if include_positions and node_count <= SKIP_LAYOUT_THRESHOLD:
        # Check layout cache first
        positions = await _layout_cache.get_positions(
            current_user.user_id, layout, node_count
        )

        if positions is None:
            t0 = time.perf_counter()
            positions = mapper.compute_layout(algorithm=layout)
            timings["compute_layout_ms"] = round((time.perf_counter() - t0) * 1000, 1)
            timings["layout_cache"] = "miss"

            # Store in cache
            await _layout_cache.set_positions(
                current_user.user_id, layout, node_count, positions
            )
        else:
            timings["compute_layout_ms"] = 0
            timings["layout_cache"] = "hit"

        # Apply positions to nodes
        for node in elements["nodes"]:
            node_id = node["data"]["id"]
            if node_id in positions:
                x, y = positions[node_id]
                node["position"] = {"x": x, "y": y}
    elif include_positions:
        # Large graph - skip server layout, client FA2 will handle it
        timings["compute_layout_ms"] = 0
        timings["layout_cache"] = "skipped"
        timings["layout_skip_reason"] = f"node_count ({node_count}) > threshold ({SKIP_LAYOUT_THRESHOLD})"
        logger.info(f"Skipping server-side layout for {node_count} nodes (threshold: {SKIP_LAYOUT_THRESHOLD})")

    response = {
        "elements": elements,
        "stats": mapper.get_graph_stats()
    }

    # SERV-003: Cluster data with caching
    if include_clusters:
        # Check cluster cache first
        clusters = await _cluster_cache.get_clusters(
            current_user.user_id, 3, node_count  # min_size=3
        )

        if clusters is None:
            t0 = time.perf_counter()
            clusters = mapper.get_clusters_for_visualization(min_size=3)
            timings["compute_clusters_ms"] = round((time.perf_counter() - t0) * 1000, 1)
            timings["cluster_cache"] = "miss"

            await _cluster_cache.set_clusters(
                current_user.user_id, 3, node_count, clusters
            )
        else:
            timings["compute_clusters_ms"] = 0
            timings["cluster_cache"] = "hit"

        # SERV-001: Use already-computed positions for centroids (FIX - was computing twice!)
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

    timings["total_ms"] = round((time.perf_counter() - total_start) * 1000, 1)

    # Log timing breakdown
    logger.info(f"Network graph API: {timings}")

    # Include timings in response for debugging
    response["_timings"] = timings

    return response


@router.get("/graph/subset")
async def get_graph_subset(
    limit: int = Query(50, ge=10, le=200, description="Maximum entities to return"),
    offset: int = Query(0, ge=0, description="Skip first N entities"),
    sort_by: str = Query("centrality", description="Sort by: centrality, mentions, recent"),
    entity_type: Optional[str] = Query(None, description="Filter by entity type"),
    search: Optional[str] = Query(None, description="Filter by name (prefix match)"),
    include_relationships: bool = Query(True, description="Include edges between returned nodes"),
    db=Depends(get_db),
    current_user: LocalUser = Depends(get_local_user)
):
    """
    Load a subset of entities with their immediate relationships.

    Does NOT load entire graph - only requested nodes + their edges.
    Designed for progressive loading and large graphs.

    Args:
        limit: Maximum number of entities to return
        offset: Skip first N entities (for pagination)
        sort_by: Sort order (centrality, mentions, recent)
        entity_type: Filter by entity type (person, org, location)
        search: Filter by name prefix
        include_relationships: Whether to include edges

    Returns:
        Subset of graph with stats and pagination info
    """
    mapper = await _graph_cache.get_mapper(db, user_id=current_user.user_id)
    stats = mapper.get_graph_stats()

    # Get all nodes with their centrality scores
    if stats["nodes"] == 0:
        return {
            "elements": {"nodes": [], "edges": []},
            "stats": {"returned": 0, "total_entities": 0, "total_relationships": 0},
            "pagination": {"limit": limit, "offset": offset, "has_more": False}
        }

    # Calculate centrality for sorting
    import networkx as nx
    centrality_scores = {}

    if sort_by == "centrality" and mapper.graph.number_of_nodes() > 0:
        try:
            centrality_scores = nx.degree_centrality(mapper.graph)
        except Exception:
            # Fallback to degree if centrality fails
            centrality_scores = {n: d for n, d in mapper.graph.degree()}

    # Collect all nodes with their data
    nodes_data = []
    for node_id, data in mapper.graph.nodes(data=True):
        # Apply entity_type filter
        if entity_type:
            node_type = data.get("entity_type", "").lower()
            if node_type != entity_type.lower():
                continue

        # Apply search filter (prefix match)
        if search:
            node_name = data.get("name", "").lower()
            if not node_name.startswith(search.lower()):
                continue

        nodes_data.append({
            "id": node_id,
            "data": data,
            "centrality": centrality_scores.get(node_id, 0),
            "degree": mapper.graph.degree(node_id)
        })

    # Sort nodes
    if sort_by == "centrality":
        nodes_data.sort(key=lambda x: x["centrality"], reverse=True)
    elif sort_by == "mentions":
        nodes_data.sort(key=lambda x: x["degree"], reverse=True)
    elif sort_by == "recent":
        nodes_data.sort(
            key=lambda x: x["data"].get("created_at", ""),
            reverse=True
        )

    total_filtered = len(nodes_data)

    # Apply pagination
    paginated_nodes = nodes_data[offset:offset + limit]
    node_ids = set(n["id"] for n in paginated_nodes)

    # Build Cytoscape elements
    elements = {
        "nodes": [
            {
                "data": {
                    "id": n["id"],
                    "label": n["data"].get("name", "Unknown"),
                    "type": n["data"].get("entity_type", "unknown").lower(),
                    "size": min(40, max(15, 15 + n["degree"] * 2)),
                    "centrality": n["centrality"],
                    **{k: v for k, v in n["data"].items()
                       if k not in ("created_at", "metadata") and not isinstance(v, (dict, list))}
                }
            }
            for n in paginated_nodes
        ],
        "edges": []
    }

    # Add edges between the selected nodes (if requested)
    if include_relationships:
        for u, v, k, d in mapper.graph.edges(keys=True, data=True):
            if u in node_ids and v in node_ids:
                elements["edges"].append({
                    "data": {
                        "id": f"{u}-{v}-{k}",
                        "source": u,
                        "target": v,
                        "type": d.get("relationship_type", "associated_with"),
                        "weight": min(5, max(1, d.get("weight", 1))),
                        "confidence": d.get("confidence", 0.5)
                    }
                })

    return {
        "elements": elements,
        "stats": {
            "returned": len(paginated_nodes),
            "total_entities": stats["nodes"],
            "total_relationships": stats["edges"],
            "filtered_entities": total_filtered
        },
        "pagination": {
            "limit": limit,
            "offset": offset,
            "has_more": offset + limit < total_filtered
        }
    }


@router.get("/neighborhood/{entity_id}")
async def get_entity_neighborhood(
    entity_id: str,
    depth: int = Query(1, ge=1, le=3, description="Hops from center entity"),
    relationship_types: Optional[str] = Query(None, description="Comma-separated relationship types"),
    db=Depends(get_db),
    current_user: LocalUser = Depends(get_local_user)
):
    """Get neighborhood of an entity up to N hops."""
    mapper = await _graph_cache.get_mapper(db, user_id=current_user.user_id)

    rel_types = relationship_types.split(",") if relationship_types else None

    neighborhood = mapper.get_neighborhood(
        entity_id=entity_id,
        depth=depth,
        relationship_types=rel_types
    )

    if not neighborhood.get("center"):
        raise HTTPException(status_code=404, detail="Entity not found in graph")

    return neighborhood


@router.get("/neighborhood/by-name/{entity_name}")
async def get_entity_neighborhood_by_name(
    entity_name: str,
    depth: int = Query(1, ge=1, le=3),
    db=Depends(get_db),
    current_user: LocalUser = Depends(get_local_user)
):
    """Get neighborhood of an entity by name."""
    mapper = await _graph_cache.get_mapper(db, user_id=current_user.user_id)

    # Find entity by name
    entity = mapper.get_entity_by_name(entity_name)
    if not entity:
        raise HTTPException(status_code=404, detail=f"Entity '{entity_name}' not found")

    return mapper.get_neighborhood(entity_id=entity["id"], depth=depth)


# ==================== Path Finding ====================

@router.post("/path")
async def find_path_between_entities(
    request: PathRequest,
    db=Depends(get_db),
    current_user: LocalUser = Depends(get_local_user)
):
    """Find shortest path between two entities."""
    mapper = await _graph_cache.get_mapper(db, user_id=current_user.user_id)

    path = mapper.find_path(
        source_id=request.source_id,
        target_id=request.target_id,
        max_depth=request.max_depth
    )

    if not path:
        return {
            "found": False,
            "path": [],
            "message": "No path found between entities"
        }

    return {
        "found": True,
        "path": path,
        "length": len(path)
    }


@router.post("/paths/all")
async def find_all_paths(
    request: PathRequest,
    limit: int = Query(10, ge=1, le=50),
    db=Depends(get_db),
    current_user: LocalUser = Depends(get_local_user)
):
    """Find all paths between two entities."""
    mapper = await _graph_cache.get_mapper(db, user_id=current_user.user_id)

    paths = mapper.find_all_paths(
        source_id=request.source_id,
        target_id=request.target_id,
        max_depth=request.max_depth,
        limit=limit
    )

    return {
        "count": len(paths),
        "paths": paths
    }


# ==================== Centrality Analysis ====================

@router.get("/centrality/degree")
async def get_degree_centrality(
    limit: int = Query(20, ge=1, le=100),
    db=Depends(get_db),
    current_user: LocalUser = Depends(get_local_user)
):
    """Get most connected entities by degree centrality."""
    mapper = await _graph_cache.get_mapper(db, user_id=current_user.user_id)

    return {
        "entities": mapper.get_most_connected(n=limit),
        "metric": "degree_centrality"
    }


@router.get("/centrality/betweenness")
async def get_betweenness_centrality(
    limit: int = Query(20, ge=1, le=100),
    db=Depends(get_db),
    current_user: LocalUser = Depends(get_local_user)
):
    """Get entities that bridge different communities."""
    mapper = await _graph_cache.get_mapper(db, user_id=current_user.user_id)

    return {
        "entities": mapper.get_betweenness_centrality(n=limit),
        "metric": "betweenness_centrality"
    }


@router.get("/centrality/pagerank")
async def get_pagerank(
    limit: int = Query(20, ge=1, le=100),
    db=Depends(get_db),
    current_user: LocalUser = Depends(get_local_user)
):
    """Get entities ranked by PageRank importance."""
    mapper = await _graph_cache.get_mapper(db, user_id=current_user.user_id)

    return {
        "entities": mapper.get_pagerank(n=limit),
        "metric": "pagerank"
    }


# ==================== Community Detection ====================

@router.get("/communities")
async def detect_communities(
    db=Depends(get_db),
    current_user: LocalUser = Depends(get_local_user)
):
    """Detect communities/clusters in the entity network."""
    mapper = await _graph_cache.get_mapper(db, user_id=current_user.user_id)

    communities = mapper.detect_communities()

    return {
        "count": len(communities),
        "communities": communities
    }


# ==================== Timeline ====================

@router.get("/timeline/{entity_id}")
async def get_relationship_timeline(
    entity_id: str,
    db=Depends(get_db),
    current_user: LocalUser = Depends(get_local_user)
):
    """Get timeline of relationship development for an entity."""
    mapper = await _graph_cache.get_mapper(db, user_id=current_user.user_id)

    timeline = mapper.get_relationship_timeline(entity_id)

    return {
        "entity_id": entity_id,
        "relationships": timeline
    }


@router.get("/timeline")
async def get_entity_activity_timeline(
    period: Literal["day", "week"] = Query("day", description="Aggregation period"),
    days: int = Query(90, ge=7, le=365, description="Number of days to include"),
    entity_type: Optional[str] = Query(None, description="Filter by entity type (person, org, location)"),
    db=Depends(get_db),
    current_user: LocalUser = Depends(get_local_user)
):
    """
    VIZ-008: Get entity activity timeline for visualization.

    Returns aggregated counts of:
    - entity_count: Total entities active in this period
    - mention_count: Total mentions in this period
    - new_entities: Entities first seen in this period

    Args:
        period: Aggregation granularity ('day' or 'week')
        days: How far back to look (default 90 days)
        entity_type: Optional filter by entity type

    Returns:
        Timeline data with date-indexed activity counts
    """
    end_date = datetime.now(timezone.utc)
    start_date = end_date - timedelta(days=days)

    # Determine date truncation based on period
    trunc_expr = "date_trunc('day', timestamp::timestamptz)" if period == "day" else "date_trunc('week', timestamp::timestamptz)"
    trunc_first_seen = "date_trunc('day', first_seen)" if period == "day" else "date_trunc('week', first_seen)"

    # Build entity type filter clause
    type_filter = ""
    if entity_type:
        type_filter = "AND LOWER(te.entity_type) = :entity_type"

    query = text(f"""
        WITH mention_activity AS (
            SELECT
                {trunc_expr} as period_date,
                COUNT(DISTINCT em.entity_id) as entity_count,
                COUNT(*) as mention_count
            FROM entity_mentions em
            JOIN tracked_entities te ON te.entity_id = em.entity_id
            WHERE em.timestamp ~ '^\\d{{4}}-\\d{{2}}-\\d{{2}}'
            AND em.timestamp::timestamptz >= :start_date
            AND em.timestamp::timestamptz <= :end_date
            AND te.user_id = :user_id
            {type_filter}
            GROUP BY period_date
        ),
        new_entities AS (
            SELECT
                {trunc_first_seen} as period_date,
                COUNT(*) as new_entities
            FROM tracked_entities te
            WHERE te.first_seen >= :start_date
            AND te.first_seen <= :end_date
            AND te.user_id = :user_id
            {type_filter.replace('te.', '')}
            GROUP BY period_date
        )
        SELECT
            COALESCE(m.period_date, n.period_date) as period_date,
            COALESCE(m.entity_count, 0) as entity_count,
            COALESCE(m.mention_count, 0) as mention_count,
            COALESCE(n.new_entities, 0) as new_entities
        FROM mention_activity m
        FULL OUTER JOIN new_entities n ON m.period_date = n.period_date
        WHERE COALESCE(m.period_date, n.period_date) IS NOT NULL
        ORDER BY period_date ASC
    """)

    params = {
        "start_date": start_date,
        "end_date": end_date,
        "user_id": current_user.user_id
    }
    if entity_type:
        params["entity_type"] = entity_type.lower()

    result = await db.execute(query, params)

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
        "entity_type": entity_type,
        "data": data
    }


# ==================== Relationship Management ====================

@router.post("/relationships")
async def add_relationship(
    request: RelationshipRequest,
    db=Depends(get_db),
    current_user: LocalUser = Depends(get_local_user)
):
    """Manually add a relationship between entities."""
    mapper = await _graph_cache.get_mapper(db, user_id=current_user.user_id)

    is_new = mapper.add_relationship(
        source_id=request.source_id,
        target_id=request.target_id,
        relationship_type=request.relationship_type,
        confidence=request.confidence,
        properties={"description": request.description} if request.description else {}
    )

    # Save to database
    await mapper.save_to_database()

    # SERV-004: Invalidate ALL caches since relationships changed
    await _graph_cache.invalidate(current_user.user_id)
    await _layout_cache.invalidate(current_user.user_id)
    await _cluster_cache.invalidate(current_user.user_id)

    return {
        "created": is_new,
        "message": "Relationship created" if is_new else "Relationship updated"
    }


@router.get("/relationships/types")
async def get_relationship_types():
    """Get available relationship types."""
    from app.models.entities import RELATIONSHIP_TYPES
    return {"types": RELATIONSHIP_TYPES}


# ==================== Discovery ====================

@router.post("/discover")
async def discover_relationships(
    request: DiscoveryRequest,
    db=Depends(get_db),
    current_user: LocalUser = Depends(get_local_user)
):
    """Run relationship discovery from co-mentions."""
    discovery = RelationshipDiscoveryService(
        db_session=db,
        ollama_client=None,  # TODO: Inject Ollama client
        user_id=current_user.user_id
    )

    relationships = await discovery.discover_from_co_mentions(
        min_co_occurrences=request.min_co_occurrences,
        time_window_days=request.time_window_days,
        use_llm=request.use_llm
    )

    # SERV-004: Invalidate ALL caches since new relationships were discovered
    if relationships:
        await _graph_cache.invalidate(current_user.user_id)
        await _layout_cache.invalidate(current_user.user_id)
        await _cluster_cache.invalidate(current_user.user_id)

    return {
        "discovered": len(relationships),
        "relationships": [r.to_dict() for r in relationships]
    }


@router.post("/discover/full")
async def run_full_discovery(
    min_confidence: float = Query(0.3, ge=0, le=1),
    db=Depends(get_db),
    current_user: LocalUser = Depends(get_local_user)
):
    """Run full relationship discovery across all entities."""
    discovery = RelationshipDiscoveryService(
        db_session=db,
        user_id=current_user.user_id
    )

    results = await discovery.discover_all_relationships(
        min_confidence=min_confidence
    )

    # SERV-004: Invalidate ALL caches since new relationships were discovered
    if results.get("relationships_found", 0) > 0:
        await _graph_cache.invalidate(current_user.user_id)
        await _layout_cache.invalidate(current_user.user_id)
        await _cluster_cache.invalidate(current_user.user_id)

    return results


@router.get("/discover/stats")
async def get_discovery_stats(
    db=Depends(get_db),
    current_user: LocalUser = Depends(get_local_user)
):
    """Get relationship discovery statistics."""
    discovery = RelationshipDiscoveryService(
        db_session=db,
        user_id=current_user.user_id
    )

    return await discovery.get_relationship_stats()


# ==================== Export ====================

@router.get("/export/cytoscape")
async def export_cytoscape_format(
    include_isolated: bool = Query(False),
    db=Depends(get_db),
    current_user: LocalUser = Depends(get_local_user)
):
    """Export graph in Cytoscape.js format."""
    mapper = await _graph_cache.get_mapper(db, user_id=current_user.user_id)

    return mapper.export_cytoscape(include_isolated=include_isolated)


@router.get("/export/json")
async def export_json_format(
    db=Depends(get_db),
    current_user: LocalUser = Depends(get_local_user)
):
    """Export graph as JSON."""
    mapper = await _graph_cache.get_mapper(db, user_id=current_user.user_id)

    return {
        "graph": mapper.export_json(),
        "stats": mapper.get_graph_stats()
    }


# ==================== Cache Management (SERV-008) ====================

@router.get("/cache/status")
async def get_cache_status(
    current_user: LocalUser = Depends(get_local_user)
):
    """
    SERV-008: Get cache status for debugging.

    Returns current state of all caches (graph, layout, cluster) for
    the current user. Useful for debugging performance issues.
    """
    user_id = str(current_user.user_id)

    graph_entries = [k for k in _graph_cache._cache if user_id in k]
    layout_entries = [k for k in _layout_cache._cache if user_id in k]
    cluster_entries = [k for k in _cluster_cache._cache if user_id in k]

    return {
        "user_id": user_id,
        "graph_cache": {
            "entries": len(graph_entries),
            "ttl_seconds": 300,
            "keys": graph_entries
        },
        "layout_cache": {
            "entries": len(layout_entries),
            "ttl_seconds": 300,
            "keys": layout_entries
        },
        "cluster_cache": {
            "entries": len(cluster_entries),
            "ttl_seconds": 600,
            "keys": cluster_entries
        }
    }


@router.post("/cache/invalidate")
async def invalidate_caches(
    current_user: LocalUser = Depends(get_local_user)
):
    """
    SERV-008: Manually invalidate all caches for current user.

    Forces next graph request to recompute everything fresh.
    Useful after bulk entity updates or for debugging.
    """
    await _graph_cache.invalidate(current_user.user_id)
    await _layout_cache.invalidate(current_user.user_id)
    await _cluster_cache.invalidate(current_user.user_id)

    return {
        "status": "invalidated",
        "user_id": str(current_user.user_id),
        "message": "All caches cleared. Next graph request will recompute."
    }
