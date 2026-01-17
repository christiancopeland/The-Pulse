"""
Network Mapper Service for entity relationship graph analysis.

Provides advanced graph operations using NetworkX including:
- Path finding (shortest path, all paths between entities)
- Centrality analysis (degree, betweenness, PageRank)
- Community detection (Louvain, greedy modularity)
- Neighborhood exploration
- Temporal analysis of relationship evolution
- Export to Cytoscape.js format for visualization
"""

import networkx as nx
from typing import List, Dict, Optional, Tuple, Any
from datetime import datetime, timezone
from dataclasses import dataclass, asdict
import json
import logging
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
from sqlalchemy.orm import selectinload

from app.models.entities import TrackedEntity, EntityMention, EntityRelationship

logger = logging.getLogger(__name__)


@dataclass
class GraphNode:
    """Represents a node in the entity graph."""
    id: str
    entity_type: str
    name: str
    properties: Dict[str, Any]


@dataclass
class GraphEdge:
    """Represents an edge (relationship) in the entity graph."""
    source_id: str
    target_id: str
    relationship_type: str
    properties: Dict[str, Any]
    first_seen: Optional[datetime]
    last_seen: Optional[datetime]
    weight: float


class NetworkMapperService:
    """
    Build and analyze entity relationship networks.

    Uses NetworkX for graph operations and provides methods for:
    - Loading graph from database
    - Path finding between entities
    - Centrality analysis
    - Community detection
    - Neighborhood exploration
    - Export for visualization
    """

    def __init__(self, db_session: AsyncSession, user_id: Optional[UUID] = None):
        """
        Initialize the network mapper service.

        Args:
            db_session: Async SQLAlchemy session
            user_id: Optional user ID to filter entities
        """
        self.db = db_session
        self.user_id = user_id
        self.graph = nx.MultiDiGraph()  # Directed graph with multiple edges
        self._loaded = False

    async def load_from_database(self) -> int:
        """
        Load graph from stored entities and relationships.

        Returns:
            Number of edges loaded
        """
        logger.info("Loading entity graph from database")

        # Clear existing graph
        self.graph.clear()

        # Load entities as nodes
        entity_query = select(TrackedEntity)
        if self.user_id:
            entity_query = entity_query.where(TrackedEntity.user_id == self.user_id)

        result = await self.db.execute(entity_query)
        entities = result.scalars().all()

        for entity in entities:
            self.graph.add_node(
                str(entity.entity_id),
                entity_type=entity.entity_type,
                name=entity.name,
                name_lower=entity.name_lower,
                created_at=entity.created_at,
                metadata=entity.entity_metadata or {}
            )

        logger.info(f"Loaded {len(entities)} entity nodes")

        # Load relationships as edges
        rel_query = select(EntityRelationship)
        if self.user_id:
            rel_query = rel_query.where(EntityRelationship.user_id == self.user_id)

        result = await self.db.execute(rel_query)
        relationships = result.scalars().all()

        for rel in relationships:
            self.graph.add_edge(
                str(rel.source_entity_id),
                str(rel.target_entity_id),
                relationship_type=rel.relationship_type,
                description=rel.description,
                first_seen=rel.first_seen,
                last_seen=rel.last_seen,
                weight=rel.mention_count or 1,
                confidence=rel.confidence or 0.5,
                key=str(rel.id)
            )

        logger.info(f"Loaded {len(relationships)} relationship edges")
        self._loaded = True

        return len(relationships)

    async def save_to_database(self) -> int:
        """
        Persist graph changes to database.

        Returns:
            Number of relationships saved/updated
        """
        saved_count = 0

        for source, target, key, data in self.graph.edges(keys=True, data=True):
            try:
                # Check if relationship exists
                existing = await self.db.execute(
                    select(EntityRelationship).where(
                        EntityRelationship.source_entity_id == UUID(source),
                        EntityRelationship.target_entity_id == UUID(target),
                        EntityRelationship.relationship_type == data.get('relationship_type', 'associated_with')
                    )
                )
                rel = existing.scalar_one_or_none()

                if rel:
                    # Update existing
                    rel.last_seen = datetime.now(timezone.utc)
                    rel.mention_count = data.get('weight', 1)
                    rel.confidence = data.get('confidence', 0.5)
                else:
                    # Create new
                    rel = EntityRelationship(
                        source_entity_id=UUID(source),
                        target_entity_id=UUID(target),
                        relationship_type=data.get('relationship_type', 'associated_with'),
                        description=data.get('description'),
                        confidence=data.get('confidence', 0.5),
                        user_id=self.user_id
                    )
                    self.db.add(rel)

                saved_count += 1

            except Exception as e:
                logger.error(f"Failed to save relationship {source} -> {target}: {e}")
                continue

        await self.db.commit()
        logger.info(f"Saved {saved_count} relationships to database")

        return saved_count

    def add_relationship(
        self,
        source_id: str,
        target_id: str,
        relationship_type: str,
        properties: Optional[Dict] = None,
        weight: float = 1.0,
        confidence: float = 0.5
    ) -> bool:
        """
        Add or update a relationship in the graph.

        Args:
            source_id: Source entity ID
            target_id: Target entity ID
            relationship_type: Type of relationship
            properties: Additional properties
            weight: Relationship strength
            confidence: Confidence score (0-1)

        Returns:
            True if new edge added, False if updated existing
        """
        # Check for existing edge of same type
        existing = self.graph.get_edge_data(source_id, target_id)

        if existing:
            for key, data in existing.items():
                if data.get('relationship_type') == relationship_type:
                    # Update existing
                    data['weight'] = data.get('weight', 0) + weight
                    data['last_seen'] = datetime.now(timezone.utc)
                    data['confidence'] = max(data.get('confidence', 0), confidence)
                    if properties:
                        data.setdefault('properties', {}).update(properties)
                    return False

        # Add new edge
        self.graph.add_edge(
            source_id,
            target_id,
            relationship_type=relationship_type,
            properties=properties or {},
            first_seen=datetime.now(timezone.utc),
            last_seen=datetime.now(timezone.utc),
            weight=weight,
            confidence=confidence
        )
        return True

    # ==================== PATH FINDING ====================

    def find_path(
        self,
        source_id: str,
        target_id: str,
        max_depth: int = 6
    ) -> List[Dict]:
        """
        Find shortest path between two entities.

        Args:
            source_id: Starting entity ID
            target_id: Destination entity ID
            max_depth: Maximum path length

        Returns:
            List of path segments with relationship details
        """
        try:
            # Use undirected view for path finding
            undirected = self.graph.to_undirected()
            path = nx.shortest_path(undirected, source_id, target_id)

            if len(path) - 1 > max_depth:
                return []

            # Build path with relationship details
            result = []
            for i in range(len(path) - 1):
                from_node = path[i]
                to_node = path[i + 1]

                # Get edge data (check both directions)
                edge_data = self.graph.get_edge_data(from_node, to_node)
                if not edge_data:
                    edge_data = self.graph.get_edge_data(to_node, from_node)

                result.append({
                    "from": self._get_node_info(from_node),
                    "to": self._get_node_info(to_node),
                    "relationships": list(edge_data.values()) if edge_data else []
                })

            return result

        except nx.NetworkXNoPath:
            return []
        except nx.NodeNotFound:
            return []

    def find_all_paths(
        self,
        source_id: str,
        target_id: str,
        max_depth: int = 4,
        limit: int = 10
    ) -> List[List[Dict]]:
        """
        Find all paths between entities up to max depth.

        Args:
            source_id: Starting entity ID
            target_id: Destination entity ID
            max_depth: Maximum path length
            limit: Maximum number of paths to return

        Returns:
            List of paths, each containing path segments
        """
        try:
            undirected = self.graph.to_undirected()
            paths = list(nx.all_simple_paths(
                undirected,
                source_id,
                target_id,
                cutoff=max_depth
            ))

            return [self._path_to_dict(p) for p in paths[:limit]]

        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return []

    # ==================== CENTRALITY ANALYSIS ====================

    def get_most_connected(self, n: int = 20) -> List[Dict]:
        """
        Get most connected entities by degree centrality.

        Args:
            n: Number of entities to return

        Returns:
            List of entities with their centrality scores
        """
        if len(self.graph) == 0:
            return []

        centrality = nx.degree_centrality(self.graph)
        sorted_nodes = sorted(
            centrality.items(),
            key=lambda x: x[1],
            reverse=True
        )[:n]

        return [
            {
                **self._get_node_info(node_id),
                "centrality": score,
                "connections": self.graph.degree(node_id)
            }
            for node_id, score in sorted_nodes
        ]

    def get_betweenness_centrality(self, n: int = 20) -> List[Dict]:
        """
        Find entities that bridge different communities.

        Entities with high betweenness centrality often control
        information flow between different groups.

        Args:
            n: Number of entities to return

        Returns:
            List of entities with their betweenness scores
        """
        if len(self.graph) == 0:
            return []

        centrality = nx.betweenness_centrality(self.graph)
        sorted_nodes = sorted(
            centrality.items(),
            key=lambda x: x[1],
            reverse=True
        )[:n]

        return [
            {
                **self._get_node_info(node_id),
                "betweenness": score
            }
            for node_id, score in sorted_nodes
        ]

    def get_pagerank(self, n: int = 20) -> List[Dict]:
        """
        Get entities ranked by PageRank importance.

        PageRank considers both the number and quality of
        connections to determine importance.

        Args:
            n: Number of entities to return

        Returns:
            List of entities with their PageRank scores
        """
        if len(self.graph) == 0:
            return []

        try:
            pagerank = nx.pagerank(self.graph, weight='weight')
        except:
            # Fallback if graph is not strongly connected
            pagerank = nx.pagerank(self.graph, weight='weight', max_iter=1000)

        sorted_nodes = sorted(
            pagerank.items(),
            key=lambda x: x[1],
            reverse=True
        )[:n]

        return [
            {
                **self._get_node_info(node_id),
                "pagerank": score
            }
            for node_id, score in sorted_nodes
        ]

    # ==================== COMMUNITY DETECTION ====================

    def detect_communities(self) -> List[Dict]:
        """
        Detect communities/clusters in the network.

        Uses greedy modularity optimization for community detection.

        Returns:
            List of communities with their members and statistics
        """
        if len(self.graph) == 0:
            return []

        # Convert to undirected for community detection
        undirected = self.graph.to_undirected()

        # Use greedy modularity communities
        from networkx.algorithms.community import greedy_modularity_communities

        try:
            communities = list(greedy_modularity_communities(undirected))
        except Exception as e:
            logger.warning(f"Community detection failed: {e}")
            return []

        # Group nodes by community
        result = []
        for i, community in enumerate(communities):
            members = [self._get_node_info(node) for node in community]

            # Calculate community statistics
            subgraph = undirected.subgraph(community)
            density = nx.density(subgraph) if len(community) > 1 else 0

            result.append({
                "community_id": i,
                "size": len(community),
                "density": density,
                "members": members[:20],  # Limit for display
                "key_entities": self._get_community_key_entities(community)
            })

        return sorted(result, key=lambda x: x['size'], reverse=True)

    def _get_community_key_entities(self, community_nodes: set) -> List[Dict]:
        """Get the most important entities in a community."""
        if len(community_nodes) == 0:
            return []

        subgraph = self.graph.subgraph(community_nodes)

        try:
            # Use PageRank on the subgraph
            pagerank = nx.pagerank(subgraph, weight='weight')
        except:
            # Fallback to degree if PageRank fails
            pagerank = {n: d for n, d in subgraph.degree()}

        top_nodes = sorted(
            pagerank.items(),
            key=lambda x: x[1],
            reverse=True
        )[:5]

        return [
            {
                **self._get_node_info(node_id),
                "importance": score
            }
            for node_id, score in top_nodes
        ]

    # ==================== NEIGHBORHOOD ====================

    def get_neighborhood(
        self,
        entity_id: str,
        depth: int = 1,
        relationship_types: Optional[List[str]] = None
    ) -> Dict:
        """
        Get all entities within N hops of an entity.

        Args:
            entity_id: Center entity ID
            depth: Number of hops to explore
            relationship_types: Optional filter for relationship types

        Returns:
            Dictionary with center node, neighbor nodes, and edges
        """
        if entity_id not in self.graph:
            return {"center": None, "nodes": [], "edges": []}

        # Get neighbors within depth
        undirected = self.graph.to_undirected()

        if depth == 1:
            neighbors = set(self.graph.predecessors(entity_id)) | \
                       set(self.graph.successors(entity_id))
            neighbors.add(entity_id)
        else:
            neighbors = set(nx.single_source_shortest_path_length(
                undirected, entity_id, cutoff=depth
            ).keys())

        # Build subgraph
        subgraph = self.graph.subgraph(neighbors)

        # Collect edges (filter by relationship type if specified)
        edges = []
        for u, v, k, data in subgraph.edges(keys=True, data=True):
            if relationship_types and data.get('relationship_type') not in relationship_types:
                continue
            edges.append({
                "source": u,
                "target": v,
                "key": k,
                **{k: v for k, v in data.items()
                   if k not in ('first_seen', 'last_seen') or v is None}
            })

        return {
            "center": self._get_node_info(entity_id),
            "nodes": [self._get_node_info(n) for n in neighbors],
            "edges": edges
        }

    # ==================== TEMPORAL ANALYSIS ====================

    def get_relationship_timeline(self, entity_id: str) -> List[Dict]:
        """
        Get timeline of when relationships were established.

        Args:
            entity_id: Entity ID to get timeline for

        Returns:
            List of relationships sorted by first_seen date
        """
        if entity_id not in self.graph:
            return []

        relationships = []

        # Outgoing relationships
        for neighbor in self.graph.successors(entity_id):
            edge_data = self.graph.get_edge_data(entity_id, neighbor)
            for key, data in edge_data.items():
                relationships.append({
                    "entity": self._get_node_info(neighbor),
                    "direction": "outgoing",
                    "relationship_type": data.get('relationship_type'),
                    "first_seen": data.get('first_seen'),
                    "last_seen": data.get('last_seen'),
                    "weight": data.get('weight', 1)
                })

        # Incoming relationships
        for neighbor in self.graph.predecessors(entity_id):
            edge_data = self.graph.get_edge_data(neighbor, entity_id)
            for key, data in edge_data.items():
                relationships.append({
                    "entity": self._get_node_info(neighbor),
                    "direction": "incoming",
                    "relationship_type": data.get('relationship_type'),
                    "first_seen": data.get('first_seen'),
                    "last_seen": data.get('last_seen'),
                    "weight": data.get('weight', 1)
                })

        # Sort by first_seen
        return sorted(
            relationships,
            key=lambda x: x['first_seen'] or datetime.min.replace(tzinfo=timezone.utc)
        )

    # ==================== EXPORT ====================

    def export_cytoscape(
        self,
        subgraph: Optional[nx.Graph] = None,
        include_isolated: bool = False
    ) -> Dict:
        """
        Export graph in Cytoscape.js format for visualization.

        Args:
            subgraph: Optional subgraph to export (defaults to full graph)
            include_isolated: Whether to include nodes with no edges

        Returns:
            Dictionary with nodes and edges in Cytoscape.js format
        """
        g = subgraph or self.graph

        # Filter out isolated nodes if requested
        if not include_isolated:
            connected_nodes = set()
            for u, v in g.edges():
                connected_nodes.add(u)
                connected_nodes.add(v)
        else:
            connected_nodes = set(g.nodes())

        elements = {
            "nodes": [
                {
                    "data": {
                        "id": node,
                        **{k: v for k, v in g.nodes[node].items()
                           if not isinstance(v, (datetime, dict))}
                    }
                }
                for node in connected_nodes if node in g.nodes
            ],
            "edges": [
                {
                    "data": {
                        "id": f"{u}-{v}-{k}",
                        "source": u,
                        "target": v,
                        **{key: val for key, val in d.items()
                           if not isinstance(val, (datetime, dict))}
                    }
                }
                for u, v, k, d in g.edges(keys=True, data=True)
            ]
        }

        return elements

    def export_json(self) -> str:
        """Export graph as JSON string."""
        return json.dumps({
            "nodes": [
                {"id": n, **self.graph.nodes[n]}
                for n in self.graph.nodes()
            ],
            "edges": [
                {"source": u, "target": v, **d}
                for u, v, d in self.graph.edges(data=True)
            ]
        }, default=str)

    def get_graph_stats(self) -> Dict:
        """Get summary statistics about the graph."""
        if len(self.graph) == 0:
            return {
                "nodes": 0,
                "edges": 0,
                "density": 0,
                "components": 0,
                "avg_degree": 0
            }

        undirected = self.graph.to_undirected()

        return {
            "nodes": self.graph.number_of_nodes(),
            "edges": self.graph.number_of_edges(),
            "density": nx.density(self.graph),
            "components": nx.number_connected_components(undirected),
            "avg_degree": sum(d for n, d in self.graph.degree()) / self.graph.number_of_nodes(),
            "relationship_types": list(set(
                d.get('relationship_type', 'unknown')
                for u, v, d in self.graph.edges(data=True)
            ))
        }

    # ==================== HELPERS ====================

    def _get_node_info(self, node_id: str) -> Dict:
        """Get node information as dictionary."""
        if node_id in self.graph:
            node_data = self.graph.nodes[node_id]
            return {
                "id": node_id,
                "name": node_data.get('name', 'Unknown'),
                "entity_type": node_data.get('entity_type', 'unknown'),
                "metadata": node_data.get('metadata', {})
            }
        return {"id": node_id, "name": "Unknown", "entity_type": "unknown"}

    def _path_to_dict(self, path: List[str]) -> List[Dict]:
        """Convert path to detailed dictionary representation."""
        result = []
        for i in range(len(path) - 1):
            from_node = path[i]
            to_node = path[i + 1]

            edge_data = self.graph.get_edge_data(from_node, to_node)
            if not edge_data:
                edge_data = self.graph.get_edge_data(to_node, from_node)

            result.append({
                "from": self._get_node_info(from_node),
                "to": self._get_node_info(to_node),
                "via": list(edge_data.values())[0] if edge_data else {}
            })
        return result

    def get_entity_by_name(self, name: str) -> Optional[Dict]:
        """Find entity by name (case-insensitive)."""
        name_lower = name.lower()
        for node_id, data in self.graph.nodes(data=True):
            if data.get('name_lower') == name_lower or data.get('name', '').lower() == name_lower:
                return self._get_node_info(node_id)
        return None

    # ==================== LAYOUT COMPUTATION ====================

    def compute_layout(
        self,
        algorithm: str = "spring",
        scale: float = 1000.0
    ) -> Dict[str, Tuple[float, float]]:
        """
        Compute node positions server-side using NetworkX layouts.

        Pre-computing layout eliminates client-side force simulation jitter
        and provides consistent, reproducible graph visualizations.

        Args:
            algorithm: Layout algorithm to use:
                - "spring" (default): Force-directed, good for most graphs
                - "kamada_kawai": Minimizes edge crossing, good for sparse graphs
                - "circular": Nodes in a circle, good for small graphs
                - "shell": Concentric circles by degree
            scale: Scale factor for coordinates (default 1000)

        Returns:
            Dictionary mapping entity_id -> (x, y) coordinates
        """
        from math import sqrt

        if len(self.graph) == 0:
            return {}

        node_count = len(self.graph)

        # Dynamic scale: more nodes need more space
        # Base 1000 + 3 pixels per node ensures readable spacing
        effective_scale = scale + (node_count * 3)

        # SERV-005: Dynamic iteration count based on graph size
        # Fewer iterations for large graphs (client FA2 refines anyway)
        if node_count > 2000:
            iterations = 30  # Large graph: quick approximation
        elif node_count > 1000:
            iterations = 50  # Medium graph
        else:
            iterations = 100  # Small graph: full quality

        logger.debug(f"compute_layout: {node_count} nodes, {iterations} iterations, algorithm={algorithm}")

        # Choose layout algorithm
        if algorithm == "spring":
            # k controls optimal distance between nodes
            # Using 3/sqrt(n) instead of 1/sqrt(n) for more repulsion
            k = 3 / sqrt(node_count) if node_count > 1 else 1
            pos = nx.spring_layout(
                self.graph,
                k=k,
                iterations=iterations,  # SERV-005: Dynamic iterations
                seed=42  # Reproducible layouts
            )
        elif algorithm == "kamada_kawai":
            try:
                pos = nx.kamada_kawai_layout(self.graph)
            except Exception:
                # Fallback to spring if kamada_kawai fails (disconnected graph)
                pos = nx.spring_layout(self.graph, seed=42)
        elif algorithm == "circular":
            pos = nx.circular_layout(self.graph)
        elif algorithm == "shell":
            # Group nodes by degree for shell layout
            undirected = self.graph.to_undirected()
            degrees = dict(undirected.degree())
            max_degree = max(degrees.values()) if degrees else 1
            shells = [[] for _ in range(min(5, max_degree + 1))]
            for node, deg in degrees.items():
                shell_idx = min(4, deg * 4 // (max_degree + 1))
                shells[shell_idx].append(node)
            shells = [s for s in shells if s]  # Remove empty shells
            pos = nx.shell_layout(self.graph, nlist=shells) if shells else nx.spring_layout(self.graph, seed=42)
        else:
            # Default to spring layout
            pos = nx.spring_layout(self.graph, seed=42)

        # Scale coordinates to viewport size
        return {
            str(node): (float(x) * effective_scale, float(y) * effective_scale)
            for node, (x, y) in pos.items()
        }

    def get_clusters_for_visualization(self, min_size: int = 3) -> List[Dict]:
        """
        Get clusters with aggregate data for super-node rendering.

        Used for semantic zoom - at low zoom levels, show clusters as
        single nodes instead of individual entities.

        SERV-006: Uses Label Propagation (O(m)) for large graphs instead of
        greedy modularity (O(n log² n)) for better performance.

        Args:
            min_size: Minimum cluster size to include

        Returns:
            List of cluster dictionaries with:
                - cluster_id: Unique identifier
                - size: Number of members
                - members: List of member entity IDs
                - representative: Most central entity in cluster
                - label: Display label (e.g., "John Doe +5")
                - position: Centroid position (x, y) if layout computed
        """
        if len(self.graph) == 0:
            return []

        undirected = self.graph.to_undirected()
        node_count = len(self.graph)

        try:
            # SERV-006: Use faster algorithm for large graphs
            if node_count > 1000:
                # Label Propagation: O(m) - much faster for large graphs
                from networkx.algorithms.community import label_propagation_communities
                communities = list(label_propagation_communities(undirected))
                logger.info(f"Used label_propagation for {node_count} nodes, found {len(communities)} communities")
            else:
                # Greedy modularity: O(n log² n) - better quality for small graphs
                from networkx.algorithms.community import greedy_modularity_communities
                communities = list(greedy_modularity_communities(undirected))
                logger.info(f"Used greedy_modularity for {node_count} nodes, found {len(communities)} communities")
        except Exception as e:
            logger.warning(f"Community detection failed: {e}")
            return []

        clusters = []
        for i, community in enumerate(communities):
            if len(community) < min_size:
                continue

            # Find most central entity in cluster
            subgraph = self.graph.subgraph(community)
            try:
                centrality = nx.degree_centrality(subgraph)
                top_entity = max(centrality, key=centrality.get)
            except Exception:
                top_entity = list(community)[0]

            top_entity_name = self.graph.nodes[top_entity].get('name', 'Unknown')

            # Get entity types distribution
            type_counts = {}
            for member in community:
                etype = self.graph.nodes[member].get('entity_type', 'unknown')
                type_counts[etype] = type_counts.get(etype, 0) + 1
            dominant_type = max(type_counts.items(), key=lambda x: x[1])[0] if type_counts else 'unknown'

            clusters.append({
                "cluster_id": f"cluster_{i}",
                "size": len(community),
                "members": [str(m) for m in community],
                "representative": str(top_entity),
                "representative_name": top_entity_name,
                "label": f"{top_entity_name} +{len(community) - 1}" if len(community) > 1 else top_entity_name,
                "dominant_type": dominant_type,
                "type_distribution": type_counts
            })

        return sorted(clusters, key=lambda x: x['size'], reverse=True)
