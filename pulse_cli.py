#!/usr/bin/env python3
"""
The Pulse CLI - Command line interface for The Pulse intelligence platform.

Phase 7: Local Government Monitor

Commands:
    generate    Generate an intelligence briefing
    status      Show system status
    collect     Run collection manually
    search      Search collected items
    graph       Generate entity relationship graph
    process     Run the processing pipeline
    network     Network analysis commands (status, centrality, communities, path, discover, export)
    local       Local government monitoring (briefing, stats, watch-areas, scan, alerts, collect)
"""
import asyncio
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
import json

import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.markdown import Markdown
from rich.syntax import Syntax
from rich import print as rprint

# Add the app directory to the path for imports
sys.path.insert(0, str(Path(__file__).parent))

app = typer.Typer(
    name="pulse",
    help="The Pulse - Personal Intelligence Platform CLI",
    add_completion=False,
)
console = Console()


def get_db_session():
    """Get an async database session."""
    from app.database import async_session
    return async_session()


async def init_services():
    """Initialize database and services."""
    from app.database import init_db
    await init_db()


# ============================================================================
# GENERATE Command - Generate intelligence briefings
# ============================================================================

@app.command()
def generate(
    period: int = typer.Option(24, "--period", "-p", help="Hours to include in briefing"),
    audio: bool = typer.Option(False, "--audio", "-a", help="Generate audio output"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Output file (markdown)"),
    topic: Optional[str] = typer.Option(None, "--topic", "-t", help="Focus on specific topic"),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="Suppress progress output"),
):
    """
    Generate an intelligence briefing.

    Creates a synthesized briefing from collected news items for the specified time period.

    Examples:
        pulse generate                    # Generate 24-hour briefing
        pulse generate -p 48 -a           # 48-hour briefing with audio
        pulse generate -t "AI research"   # Focus on AI research
        pulse generate -o briefing.md     # Save to file
    """
    async def _generate():
        await init_services()

        from app.services.synthesis.briefing_generator import BriefingGenerator

        async with get_db_session() as session:
            generator = BriefingGenerator(db_session=session)

            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
                disable=quiet,
            ) as progress:
                task = progress.add_task("Generating briefing...", total=None)

                if topic:
                    briefing = await generator.generate_focused_briefing(
                        topic=topic,
                        period_hours=period,
                        user_id="cli-user",
                    )
                else:
                    briefing = await generator.generate(
                        period_hours=period,
                        user_id="cli-user",
                        include_audio=audio,
                    )

                progress.update(task, description="Briefing complete!")

            # Output briefing
            if output:
                output_path = Path(output)
                output_path.write_text(briefing.to_markdown())
                console.print(f"[green]Briefing saved to {output}[/green]")
            else:
                console.print(Panel(
                    Markdown(briefing.to_markdown()),
                    title=briefing.title,
                    border_style="cyan",
                ))

            if briefing.audio_path:
                console.print(f"[green]Audio saved to {briefing.audio_path}[/green]")

            # Show stats
            console.print(f"\n[dim]Items analyzed: {briefing.metadata.get('items_analyzed', 0)}[/dim]")
            console.print(f"[dim]Sections: {len(briefing.sections)}[/dim]")

    asyncio.run(_generate())


# ============================================================================
# STATUS Command - Show system status
# ============================================================================

@app.command()
def status(
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show detailed status"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """
    Show system status.

    Displays the status of all collectors, processing pipeline, and storage systems.

    Examples:
        pulse status           # Basic status
        pulse status -v        # Detailed status
        pulse status --json    # JSON output
    """
    async def _status():
        await init_services()

        from app.services.collectors.scheduler import get_scheduler
        from app.services.broadcast import get_broadcast_manager

        scheduler = get_scheduler()
        status_data = scheduler.get_status()
        health = scheduler.get_health_summary()

        broadcast = get_broadcast_manager()
        broadcast_status = broadcast.get_status()

        if json_output:
            console.print_json(json.dumps({
                "scheduler": status_data,
                "health": health,
                "broadcast": broadcast_status,
            }))
            return

        # Header
        console.print(Panel(
            f"[bold cyan]THE PULSE[/bold cyan] - Intelligence Platform",
            subtitle=f"Status at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        ))

        # Health summary
        health_color = {
            "healthy": "green",
            "degraded": "yellow",
            "unhealthy": "red",
        }.get(health["overall"], "white")

        console.print(f"\n[bold]System Health:[/bold] [{health_color}]{health['overall'].upper()}[/{health_color}]")
        console.print(f"  Healthy: {health['healthy']} | Degraded: {health['degraded']} | Unhealthy: {health['unhealthy']}")
        console.print(f"  Scheduler: {'[green]Running[/green]' if status_data['is_running'] else '[red]Stopped[/red]'}")

        # Collectors table
        table = Table(title="\nCollectors", show_header=True)
        table.add_column("Name", style="cyan")
        table.add_column("Type", style="dim")
        table.add_column("Status")
        table.add_column("Last Run", style="dim")
        table.add_column("Errors", justify="right")

        for collector in status_data.get("collectors", []):
            health_icon = {
                "healthy": "[green]●[/green]",
                "degraded": "[yellow]●[/yellow]",
                "unhealthy": "[red]●[/red]",
            }.get(collector.get("health", "unknown"), "○")

            last_run = collector.get("last_run")
            if last_run:
                last_run = datetime.fromisoformat(last_run.replace("Z", "+00:00"))
                last_run_str = last_run.strftime("%H:%M:%S")
            else:
                last_run_str = "Never"

            table.add_row(
                collector["name"],
                collector["source_type"],
                f"{health_icon} {collector.get('health', 'unknown')}",
                last_run_str,
                str(collector.get("error_count", 0)),
            )

        console.print(table)

        # WebSocket connections
        console.print(f"\n[bold]WebSocket Connections:[/bold] {broadcast_status['active_connections']}")

        if verbose:
            # Show more details
            console.print("\n[bold]Recent Collection Runs:[/bold]")
            # Could add database query here for recent runs

    asyncio.run(_status())


# ============================================================================
# COLLECT Command - Run collection manually
# ============================================================================

@app.command()
def collect(
    all_collectors: bool = typer.Option(False, "--all", "-a", help="Run all collectors"),
    collector: Optional[str] = typer.Option(None, "--collector", "-c", help="Specific collector to run"),
    list_collectors: bool = typer.Option(False, "--list", "-l", help="List available collectors"),
):
    """
    Run collection manually.

    Triggers collection from news sources immediately.

    Examples:
        pulse collect --list           # List all collectors
        pulse collect --all            # Run all collectors
        pulse collect -c "RSS Feeds"   # Run specific collector
    """
    async def _collect():
        await init_services()

        from app.services.collectors.scheduler import get_scheduler
        from app.services.collectors import get_all_collectors

        if list_collectors:
            table = Table(title="Available Collectors")
            table.add_column("Name", style="cyan")
            table.add_column("Type", style="dim")
            table.add_column("Class")

            for c in get_all_collectors():
                table.add_row(c.name, c.source_type, c.__class__.__name__)

            console.print(table)
            return

        scheduler = get_scheduler()

        if not scheduler.collectors:
            console.print("[yellow]No collectors registered. Initialize scheduler first.[/yellow]")
            return

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            if all_collectors:
                task = progress.add_task("Running all collectors...", total=None)
                results = await scheduler.run_all_now()
                progress.update(task, description="Collection complete!")

                console.print(f"\n[green]Completed {len(results)} collection runs[/green]")

                for run in results:
                    status_icon = "[green]✓[/green]" if run.status == "completed" else "[red]✗[/red]"
                    console.print(
                        f"  {status_icon} {run.collector_name}: "
                        f"{run.items_new} new, {run.items_duplicate} duplicates"
                    )

            elif collector:
                if collector not in scheduler.collectors:
                    console.print(f"[red]Collector '{collector}' not found.[/red]")
                    console.print(f"Available: {', '.join(scheduler.collectors.keys())}")
                    return

                task = progress.add_task(f"Running {collector}...", total=None)
                run = await scheduler.run_collector_now(collector)
                progress.update(task, description="Collection complete!")

                if run:
                    console.print(f"\n[green]Collection complete:[/green]")
                    console.print(f"  Items collected: {run.items_collected}")
                    console.print(f"  New items: {run.items_new}")
                    console.print(f"  Duplicates: {run.items_duplicate}")
            else:
                console.print("[yellow]Specify --all or --collector <name>[/yellow]")

    asyncio.run(_collect())


# ============================================================================
# SEARCH Command - Search collected items
# ============================================================================

@app.command()
def search(
    query: str = typer.Argument(..., help="Search query"),
    semantic: bool = typer.Option(True, "--semantic/--keyword", help="Use semantic or keyword search"),
    limit: int = typer.Option(10, "--limit", "-n", help="Number of results"),
    source: Optional[str] = typer.Option(None, "--source", "-s", help="Filter by source type"),
    hours: int = typer.Option(168, "--hours", "-h", help="Search within last N hours"),
):
    """
    Search collected items.

    Performs semantic or keyword search across collected news items.

    Examples:
        pulse search "AI regulations"           # Semantic search
        pulse search "Ukraine" --keyword        # Keyword search
        pulse search "technology" -s rss -n 20  # Filter by source
    """
    async def _search():
        await init_services()

        from sqlalchemy import select, desc, or_
        from app.models.news_item import NewsItem
        from app.services.processing.embedder import NewsItemEmbedder

        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

        async with get_db_session() as session:
            if semantic:
                # Semantic search using embeddings
                embedder = NewsItemEmbedder()

                with Progress(
                    SpinnerColumn(),
                    TextColumn("[progress.description]{task.description}"),
                    console=console,
                ) as progress:
                    task = progress.add_task("Searching...", total=None)
                    results = await embedder.search(query, limit=limit)
                    progress.update(task, description="Search complete!")

                if not results:
                    console.print("[yellow]No results found.[/yellow]")
                    return

                table = Table(title=f"Search Results for '{query}'")
                table.add_column("Score", justify="right", style="cyan", width=6)
                table.add_column("Title", width=50)
                table.add_column("Source", style="dim", width=15)
                table.add_column("Date", style="dim", width=10)

                for result in results:
                    score = f"{result.get('score', 0):.2f}"
                    title = result.get('title', 'Untitled')[:48]
                    source_name = result.get('source_name', 'Unknown')[:13]
                    pub_date = result.get('published_at', '')[:10] if result.get('published_at') else ''

                    table.add_row(score, title, source_name, pub_date)

                console.print(table)

            else:
                # Keyword search in database
                query_filter = or_(
                    NewsItem.title.ilike(f"%{query}%"),
                    NewsItem.content.ilike(f"%{query}%"),
                    NewsItem.summary.ilike(f"%{query}%"),
                )

                stmt = (
                    select(NewsItem)
                    .where(NewsItem.collected_at >= cutoff)
                    .where(query_filter)
                    .order_by(desc(NewsItem.published_at))
                    .limit(limit)
                )

                if source:
                    stmt = stmt.where(NewsItem.source_type == source)

                result = await session.execute(stmt)
                items = result.scalars().all()

                if not items:
                    console.print("[yellow]No results found.[/yellow]")
                    return

                table = Table(title=f"Search Results for '{query}'")
                table.add_column("Title", width=50)
                table.add_column("Source", style="dim", width=15)
                table.add_column("Date", style="dim", width=10)
                table.add_column("URL", style="dim", width=30)

                for item in items:
                    title = (item.title or 'Untitled')[:48]
                    source_name = (item.source_name or 'Unknown')[:13]
                    pub_date = item.published_at.strftime('%Y-%m-%d') if item.published_at else ''
                    url = (item.url or '')[:28]

                    table.add_row(title, source_name, pub_date, url)

                console.print(table)

    asyncio.run(_search())


# ============================================================================
# GRAPH Command - Generate entity relationship graph
# ============================================================================

@app.command()
def graph(
    output: str = typer.Option("entity_graph.html", "--output", "-o", help="Output file"),
    entity: Optional[str] = typer.Option(None, "--entity", "-e", help="Focus on specific entity"),
    depth: int = typer.Option(2, "--depth", "-d", help="Relationship depth"),
    format_type: str = typer.Option("html", "--format", "-f", help="Output format: html, json, dot"),
):
    """
    Generate entity relationship graph.

    Creates a visualization of entity relationships from collected data.

    Examples:
        pulse graph                          # Full graph to HTML
        pulse graph -e "OpenAI"              # Focus on entity
        pulse graph -f json -o graph.json    # JSON format
    """
    async def _graph():
        await init_services()

        from app.services.entity_tracker import EntityTrackingService
        from app.services.document_processor import DocumentProcessor

        async with get_db_session() as session:
            doc_processor = DocumentProcessor()
            tracker = EntityTrackingService(session, doc_processor)

            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
            ) as progress:
                task = progress.add_task("Building entity graph...", total=None)

                # Get relationships data
                if entity:
                    relationships = await tracker.get_entity_relationships(entity)
                else:
                    # Get all tracked entities and their relationships
                    entities = await tracker.get_tracked_entities(user_id=None, limit=100)
                    relationships = {"nodes": [], "edges": []}

                    for e in entities:
                        rel = await tracker.get_entity_relationships(e.name)
                        if rel:
                            relationships["nodes"].extend(rel.get("nodes", []))
                            relationships["edges"].extend(rel.get("edges", []))

                progress.update(task, description="Graph complete!")

            if not relationships or not relationships.get("nodes"):
                console.print("[yellow]No entity relationships found.[/yellow]")
                return

            output_path = Path(output)

            if format_type == "json":
                output_path.write_text(json.dumps(relationships, indent=2))
            elif format_type == "dot":
                # Generate DOT format for Graphviz
                dot_content = "digraph EntityGraph {\n"
                dot_content += "  rankdir=LR;\n"
                dot_content += "  node [shape=box];\n"

                for node in relationships.get("nodes", []):
                    dot_content += f'  "{node["name"]}" [label="{node["name"]}"];\n'

                for edge in relationships.get("edges", []):
                    dot_content += f'  "{edge["source"]}" -> "{edge["target"]}" [label="{edge.get("relationship", "")}"];\n'

                dot_content += "}\n"
                output_path.write_text(dot_content)
            else:
                # Generate HTML with D3.js visualization
                html_content = generate_graph_html(relationships)
                output_path.write_text(html_content)

            console.print(f"[green]Graph saved to {output}[/green]")
            console.print(f"  Nodes: {len(relationships.get('nodes', []))}")
            console.print(f"  Edges: {len(relationships.get('edges', []))}")

    asyncio.run(_graph())


def generate_graph_html(data: dict) -> str:
    """Generate HTML with D3.js force-directed graph."""
    return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>The Pulse - Entity Graph</title>
    <script src="https://d3js.org/d3.v7.min.js"></script>
    <style>
        body {{
            font-family: 'Inter', sans-serif;
            background: #0a0a0f;
            color: #e0e0e0;
            margin: 0;
            padding: 20px;
        }}
        h1 {{
            color: #00d4ff;
            font-family: monospace;
        }}
        #graph {{
            width: 100%;
            height: 80vh;
            border: 1px solid #2a2a3a;
            border-radius: 8px;
        }}
        .node {{
            cursor: pointer;
        }}
        .node circle {{
            fill: #00d4ff;
            stroke: #0a0a0f;
            stroke-width: 2px;
        }}
        .node text {{
            fill: #e0e0e0;
            font-size: 12px;
        }}
        .link {{
            stroke: #2a2a3a;
            stroke-opacity: 0.6;
        }}
    </style>
</head>
<body>
    <h1>◆ The Pulse - Entity Graph</h1>
    <div id="graph"></div>
    <script>
        const data = {json.dumps(data)};

        const width = document.getElementById('graph').clientWidth;
        const height = document.getElementById('graph').clientHeight;

        const svg = d3.select('#graph')
            .append('svg')
            .attr('width', width)
            .attr('height', height);

        const simulation = d3.forceSimulation(data.nodes)
            .force('link', d3.forceLink(data.edges).id(d => d.id || d.name).distance(100))
            .force('charge', d3.forceManyBody().strength(-300))
            .force('center', d3.forceCenter(width / 2, height / 2));

        const link = svg.append('g')
            .selectAll('line')
            .data(data.edges)
            .join('line')
            .attr('class', 'link');

        const node = svg.append('g')
            .selectAll('g')
            .data(data.nodes)
            .join('g')
            .attr('class', 'node')
            .call(d3.drag()
                .on('start', dragstarted)
                .on('drag', dragged)
                .on('end', dragended));

        node.append('circle')
            .attr('r', 10);

        node.append('text')
            .attr('dx', 15)
            .attr('dy', 4)
            .text(d => d.name || d.id);

        simulation.on('tick', () => {{
            link
                .attr('x1', d => d.source.x)
                .attr('y1', d => d.source.y)
                .attr('x2', d => d.target.x)
                .attr('y2', d => d.target.y);

            node.attr('transform', d => `translate(${{d.x}},${{d.y}})`);
        }});

        function dragstarted(event, d) {{
            if (!event.active) simulation.alphaTarget(0.3).restart();
            d.fx = d.x;
            d.fy = d.y;
        }}

        function dragged(event, d) {{
            d.fx = event.x;
            d.fy = event.y;
        }}

        function dragended(event, d) {{
            if (!event.active) simulation.alphaTarget(0);
            d.fx = null;
            d.fy = null;
        }}
    </script>
</body>
</html>"""


# ============================================================================
# PROCESS Command - Run processing pipeline
# ============================================================================

@app.command()
def process(
    limit: int = typer.Option(100, "--limit", "-n", help="Number of items to process"),
    skip_validation: bool = typer.Option(False, "--skip-validation", help="Skip content validation"),
    skip_embedding: bool = typer.Option(False, "--skip-embedding", help="Skip vector embedding"),
):
    """
    Run the processing pipeline.

    Processes pending collected items through validation, ranking, and embedding.

    Examples:
        pulse process                 # Process up to 100 items
        pulse process -n 500          # Process more items
        pulse process --skip-embedding # Skip embedding step
    """
    async def _process():
        await init_services()

        from sqlalchemy import select
        from app.models.news_item import NewsItem
        from app.services.processing.pipeline import ProcessingPipeline

        async with get_db_session() as session:
            # Get pending items
            stmt = (
                select(NewsItem)
                .where(NewsItem.processed == 0)
                .limit(limit)
            )
            result = await session.execute(stmt)
            items = result.scalars().all()

            if not items:
                console.print("[yellow]No pending items to process.[/yellow]")
                return

            console.print(f"[cyan]Processing {len(items)} items...[/cyan]")

            pipeline = ProcessingPipeline(session)

            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
            ) as progress:
                task = progress.add_task("Processing...", total=len(items))

                stats = await pipeline.process_batch(
                    items,
                    skip_validation=skip_validation,
                    skip_embedding=skip_embedding,
                )

                progress.update(task, completed=len(items))

            console.print("\n[green]Processing complete![/green]")
            console.print(f"  Validated: {stats.get('validated', 0)}")
            console.print(f"  Ranked: {stats.get('ranked', 0)}")
            console.print(f"  Embedded: {stats.get('embedded', 0)}")
            console.print(f"  Failed: {stats.get('failed', 0)}")

    asyncio.run(_process())


# ============================================================================
# BRIEFINGS Command - List and manage briefings
# ============================================================================

@app.command()
def briefings(
    limit: int = typer.Option(10, "--limit", "-n", help="Number of briefings to show"),
    briefing_id: Optional[str] = typer.Option(None, "--id", help="Show specific briefing"),
    delete: Optional[str] = typer.Option(None, "--delete", help="Delete briefing by ID"),
):
    """
    List and manage briefings.

    View archived briefings or delete old ones.

    Examples:
        pulse briefings                # List recent briefings
        pulse briefings --id abc123    # Show specific briefing
        pulse briefings --delete xyz   # Delete briefing
    """
    async def _briefings():
        await init_services()

        from app.services.synthesis.briefing_archive import BriefingArchive

        async with get_db_session() as session:
            archive = BriefingArchive(db_session=session)

            if delete:
                deleted = await archive.delete(delete)
                if deleted:
                    console.print(f"[green]Deleted briefing {delete}[/green]")
                else:
                    console.print(f"[red]Briefing {delete} not found[/red]")
                return

            if briefing_id:
                briefing = await archive.get(briefing_id)
                if briefing:
                    console.print(Panel(
                        Markdown(briefing.to_markdown()),
                        title=briefing.title,
                        border_style="cyan",
                    ))
                else:
                    console.print(f"[red]Briefing {briefing_id} not found[/red]")
                return

            # List briefings
            items = await archive.list(limit=limit, user_id=None)

            if not items:
                console.print("[yellow]No briefings found.[/yellow]")
                return

            table = Table(title="Archived Briefings")
            table.add_column("ID", style="cyan", width=12)
            table.add_column("Title", width=40)
            table.add_column("Generated", style="dim", width=16)
            table.add_column("Sections", justify="right", width=8)
            table.add_column("Audio", justify="center", width=6)

            for item in items:
                has_audio = "✓" if item.get("has_audio") else ""
                table.add_row(
                    item["id"][:10] + "...",
                    item["title"][:38],
                    item["generated_at"][:16],
                    str(item.get("section_count", 0)),
                    has_audio,
                )

            console.print(table)

    asyncio.run(_briefings())


# ============================================================================
# NETWORK Command - Network analysis operations
# ============================================================================

network_app = typer.Typer(help="Network analysis commands")
app.add_typer(network_app, name="network")


@network_app.command("status")
def network_status():
    """Show network graph statistics."""
    async def _network_status():
        await init_services()

        from app.services.network_mapper import NetworkMapperService

        async with get_db_session() as session:
            mapper = NetworkMapperService(session)
            edge_count = await mapper.load_from_database()
            stats = mapper.get_graph_stats()

            console.print(Panel(
                f"[bold]Network Graph Statistics[/bold]\n\n"
                f"Nodes: {stats['nodes']}\n"
                f"Edges: {stats['edges']}\n"
                f"Density: {stats['density']:.4f}\n"
                f"Connected Components: {stats['components']}\n"
                f"Average Degree: {stats['avg_degree']:.2f}\n\n"
                f"Relationship Types: {', '.join(stats.get('relationship_types', []))}",
                title="◆ Network Mapper",
                border_style="cyan",
            ))

    asyncio.run(_network_status())


@network_app.command("centrality")
def network_centrality(
    metric: str = typer.Option("degree", "--metric", "-m", help="Metric: degree, betweenness, pagerank"),
    limit: int = typer.Option(20, "--limit", "-n", help="Number of results"),
):
    """Analyze entity centrality in the network."""
    async def _centrality():
        await init_services()

        from app.services.network_mapper import NetworkMapperService

        async with get_db_session() as session:
            mapper = NetworkMapperService(session)
            await mapper.load_from_database()

            if metric == "degree":
                results = mapper.get_most_connected(n=limit)
                title = "Most Connected Entities (Degree Centrality)"
            elif metric == "betweenness":
                results = mapper.get_betweenness_centrality(n=limit)
                title = "Bridge Entities (Betweenness Centrality)"
            elif metric == "pagerank":
                results = mapper.get_pagerank(n=limit)
                title = "Most Important Entities (PageRank)"
            else:
                console.print(f"[red]Unknown metric: {metric}[/red]")
                return

            if not results:
                console.print("[yellow]No entities found in network.[/yellow]")
                return

            table = Table(title=title)
            table.add_column("Entity", style="cyan", width=30)
            table.add_column("Type", style="dim", width=10)
            table.add_column("Score", justify="right", width=12)

            for r in results:
                score_val = r.get('centrality') or r.get('betweenness') or r.get('pagerank') or 0
                score = f"{score_val:.4f}"
                table.add_row(
                    r.get('name', 'Unknown'),
                    r.get('entity_type', 'unknown')[:10],
                    score,
                )

            console.print(table)

    asyncio.run(_centrality())


@network_app.command("communities")
def network_communities():
    """Detect communities in the entity network."""
    async def _communities():
        await init_services()

        from app.services.network_mapper import NetworkMapperService

        async with get_db_session() as session:
            mapper = NetworkMapperService(session)
            await mapper.load_from_database()

            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
            ) as progress:
                task = progress.add_task("Detecting communities...", total=None)
                communities = mapper.detect_communities()
                progress.update(task, description="Complete!")

            if not communities:
                console.print("[yellow]No communities detected.[/yellow]")
                return

            console.print(f"\n[bold]Found {len(communities)} communities:[/bold]\n")

            for i, comm in enumerate(communities[:10], 1):
                key_names = [e['name'] for e in comm.get('key_entities', [])[:3]]
                console.print(f"[cyan]Community {i}[/cyan] ({comm['size']} members)")
                console.print(f"  Density: {comm['density']:.3f}")
                console.print(f"  Key entities: {', '.join(key_names)}")
                console.print()

    asyncio.run(_communities())


@network_app.command("path")
def network_path(
    source: str = typer.Argument(..., help="Source entity name"),
    target: str = typer.Argument(..., help="Target entity name"),
    max_depth: int = typer.Option(6, "--depth", "-d", help="Maximum path length"),
):
    """Find path between two entities."""
    async def _path():
        await init_services()

        from app.services.network_mapper import NetworkMapperService

        async with get_db_session() as session:
            mapper = NetworkMapperService(session)
            await mapper.load_from_database()

            # Find entities by name
            source_entity = mapper.get_entity_by_name(source)
            target_entity = mapper.get_entity_by_name(target)

            if not source_entity:
                console.print(f"[red]Entity '{source}' not found.[/red]")
                return
            if not target_entity:
                console.print(f"[red]Entity '{target}' not found.[/red]")
                return

            path = mapper.find_path(
                source_id=source_entity['id'],
                target_id=target_entity['id'],
                max_depth=max_depth
            )

            if not path:
                console.print(f"[yellow]No path found between '{source}' and '{target}' within {max_depth} hops.[/yellow]")
                return

            console.print(f"\n[bold green]Path found ({len(path)} hops):[/bold green]\n")

            for i, segment in enumerate(path):
                from_name = segment['from'].get('name', 'Unknown')
                to_name = segment['to'].get('name', 'Unknown')

                rels = segment.get('relationships', [])
                rel_type = rels[0].get('relationship_type', 'related') if rels else 'related'

                if i == 0:
                    console.print(f"  [cyan]{from_name}[/cyan]")

                console.print(f"    │ ({rel_type})")
                console.print(f"    ↓")
                console.print(f"  [cyan]{to_name}[/cyan]")

    asyncio.run(_path())


@network_app.command("discover")
def network_discover(
    min_occurrences: int = typer.Option(2, "--min", "-m", help="Minimum co-occurrences"),
    days: int = typer.Option(30, "--days", "-d", help="Time window in days"),
    use_llm: bool = typer.Option(False, "--llm", help="Use LLM for relationship inference"),
):
    """Discover relationships from co-mentions."""
    async def _discover():
        await init_services()

        from app.services.network_mapper import RelationshipDiscoveryService

        async with get_db_session() as session:
            discovery = RelationshipDiscoveryService(db_session=session)

            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
            ) as progress:
                task = progress.add_task("Discovering relationships...", total=None)

                relationships = await discovery.discover_from_co_mentions(
                    min_co_occurrences=min_occurrences,
                    time_window_days=days,
                    use_llm=use_llm
                )

                progress.update(task, description="Discovery complete!")

            if not relationships:
                console.print("[yellow]No new relationships discovered.[/yellow]")
                return

            console.print(f"\n[bold green]Discovered {len(relationships)} relationships:[/bold green]\n")

            table = Table()
            table.add_column("Source", style="cyan", width=20)
            table.add_column("Type", style="dim", width=15)
            table.add_column("Target", style="cyan", width=20)
            table.add_column("Confidence", justify="right", width=10)

            for rel in relationships[:20]:
                table.add_row(
                    str(rel.source_entity_id)[:18],
                    rel.relationship_type,
                    str(rel.target_entity_id)[:18],
                    f"{(rel.confidence or 0.5):.2f}",
                )

            console.print(table)

    asyncio.run(_discover())


@network_app.command("export")
def network_export(
    output: str = typer.Option("network.json", "--output", "-o", help="Output file"),
    format_type: str = typer.Option("cytoscape", "--format", "-f", help="Format: cytoscape, json"),
):
    """Export network graph to file."""
    async def _export():
        await init_services()

        from app.services.network_mapper import NetworkMapperService

        async with get_db_session() as session:
            mapper = NetworkMapperService(session)
            await mapper.load_from_database()

            output_path = Path(output)

            if format_type == "cytoscape":
                data = mapper.export_cytoscape()
                output_path.write_text(json.dumps(data, indent=2, default=str))
            else:
                data = mapper.export_json()
                output_path.write_text(data)

            stats = mapper.get_graph_stats()
            console.print(f"[green]Exported to {output}[/green]")
            console.print(f"  Nodes: {stats['nodes']}, Edges: {stats['edges']}")

    asyncio.run(_export())


# ============================================================================
# LOCAL Command - Local Government Monitor
# ============================================================================

local_app = typer.Typer(help="Local government monitoring commands")
app.add_typer(local_app, name="local")


@local_app.command("briefing")
def local_briefing(
    days: int = typer.Option(7, "--days", "-d", help="Days to include"),
    jurisdiction: Optional[str] = typer.Option(None, "--jurisdiction", "-j", help="Filter by jurisdiction"),
):
    """Generate local government briefing."""
    async def _briefing():
        await init_services()

        from app.services.local_government import LocalIntelligenceAnalyzer

        async with get_db_session() as session:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
            ) as progress:
                task = progress.add_task("Generating briefing...", total=None)

                analyzer = LocalIntelligenceAnalyzer(session)
                briefing = await analyzer.generate_local_briefing(days=days)

                progress.update(task, description="Briefing complete!")

            # Display briefing
            console.print(Panel(
                f"[bold]Local Government Briefing[/bold]\n"
                f"Period: {briefing.get('period', 'Last 7 days')}\n"
                f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
                title="◆ Local Intelligence",
                border_style="cyan",
            ))

            # Council Meetings
            if briefing.get('council_summary'):
                console.print("\n[bold cyan]Council Meetings[/bold cyan]")
                for meeting in briefing['council_summary'].get('recent_meetings', [])[:5]:
                    console.print(f"  • {meeting.get('jurisdiction', 'Unknown')}: {meeting.get('body', 'Meeting')} - {meeting.get('meeting_date', 'N/A')}")

            # Zoning Activity
            if briefing.get('zoning_summary'):
                zoning = briefing['zoning_summary']
                console.print(f"\n[bold cyan]Zoning Activity[/bold cyan]")
                console.print(f"  New cases: {zoning.get('new_cases', 0)}")
                console.print(f"  Pending: {zoning.get('pending_count', 0)}")

            # Permits
            if briefing.get('permit_summary'):
                permits = briefing['permit_summary']
                console.print(f"\n[bold cyan]Building Permits[/bold cyan]")
                console.print(f"  Issued: {permits.get('issued_count', 0)}")
                value = permits.get('total_value', 0)
                console.print(f"  Total Value: ${value:,.0f}" if value else "  Total Value: N/A")

            # Property Transactions
            if briefing.get('property_summary'):
                prop = briefing['property_summary']
                console.print(f"\n[bold cyan]Property Transactions[/bold cyan]")
                console.print(f"  Transactions: {prop.get('transaction_count', 0)}")
                volume = prop.get('total_volume', 0)
                console.print(f"  Total Volume: ${volume:,.0f}" if volume else "  Total Volume: N/A")

            # Court Cases
            if briefing.get('court_summary'):
                court = briefing['court_summary']
                console.print(f"\n[bold cyan]Court Activity[/bold cyan]")
                console.print(f"  New filings: {court.get('new_filings', 0)}")
                console.print(f"  Active cases: {court.get('active_count', 0)}")

    asyncio.run(_briefing())


@local_app.command("stats")
def local_stats(
    jurisdiction: Optional[str] = typer.Option(None, "--jurisdiction", "-j", help="Filter by jurisdiction"),
):
    """Show local government activity statistics."""
    async def _stats():
        await init_services()

        from app.services.local_government import LocalIntelligenceAnalyzer

        async with get_db_session() as session:
            analyzer = LocalIntelligenceAnalyzer(session)
            stats = await analyzer.get_activity_stats(jurisdiction=jurisdiction)

            console.print(Panel(
                f"[bold]Local Government Statistics[/bold]",
                title="◆ Activity Stats",
                border_style="cyan",
            ))

            table = Table()
            table.add_column("Category", style="cyan", width=25)
            table.add_column("Count", justify="right", width=12)
            table.add_column("Trend", width=10)

            table.add_row("Council Meetings", str(stats.get('meetings', 0)), stats.get('meetings_trend', ''))
            table.add_row("Zoning Cases", str(stats.get('zoning', 0)), stats.get('zoning_trend', ''))
            table.add_row("Building Permits", str(stats.get('permits', 0)), stats.get('permits_trend', ''))
            table.add_row("Property Transactions", str(stats.get('property', 0)), stats.get('property_trend', ''))
            table.add_row("Court Cases", str(stats.get('court', 0)), stats.get('court_trend', ''))

            console.print(table)

    asyncio.run(_stats())


@local_app.command("watch-areas")
def local_watch_areas(
    add_predefined: Optional[str] = typer.Option(None, "--add-predefined", "-p", help="Add predefined area"),
    list_predefined: bool = typer.Option(False, "--list-predefined", "-l", help="List predefined areas"),
):
    """Manage watch areas for location-based alerts."""
    async def _watch_areas():
        await init_services()

        from app.services.local_government import GeofenceService
        from app.models.local_government import WatchArea
        from sqlalchemy import select

        async with get_db_session() as session:
            geofence = GeofenceService(session)

            if list_predefined:
                areas = geofence.get_predefined_areas()
                console.print("[bold]Predefined Watch Areas:[/bold]\n")

                table = Table()
                table.add_column("Key", style="cyan", width=20)
                table.add_column("Name", width=25)
                table.add_column("Location", style="dim", width=25)
                table.add_column("Radius", justify="right", width=8)

                for key, area in areas.items():
                    table.add_row(
                        key,
                        area['name'],
                        f"{area['latitude']:.4f}, {area['longitude']:.4f}",
                        f"{area['radius_miles']} mi",
                    )

                console.print(table)
                return

            if add_predefined:
                watch_area = await geofence.create_from_predefined(add_predefined)
                if watch_area:
                    console.print(f"[green]Created watch area: {watch_area.name}[/green]")
                else:
                    console.print(f"[red]Unknown predefined area: {add_predefined}[/red]")
                    console.print("Use --list-predefined to see available areas")
                return

            # List existing watch areas
            result = await session.execute(select(WatchArea))
            areas = result.scalars().all()

            if not areas:
                console.print("[yellow]No watch areas configured.[/yellow]")
                console.print("Use --list-predefined to see available predefined areas")
                console.print("Use --add-predefined <key> to add one")
                return

            console.print("[bold]Current Watch Areas:[/bold]\n")

            table = Table()
            table.add_column("Name", style="cyan", width=25)
            table.add_column("Location", style="dim", width=25)
            table.add_column("Radius", justify="right", width=8)
            table.add_column("Active", justify="center", width=8)
            table.add_column("Triggers", justify="right", width=10)

            for area in areas:
                status = "[green]Yes[/green]" if area.is_active else "[red]No[/red]"
                table.add_row(
                    area.name,
                    f"{area.latitude:.4f}, {area.longitude:.4f}",
                    f"{area.radius_miles} mi",
                    status,
                    str(area.trigger_count or 0),
                )

            console.print(table)

    asyncio.run(_watch_areas())


@local_app.command("scan")
def local_scan(
    hours: int = typer.Option(24, "--hours", "-h", help="Scan activity from last N hours"),
):
    """Scan recent activity for watch area matches."""
    async def _scan():
        await init_services()

        from app.services.local_government import GeofenceService

        async with get_db_session() as session:
            geofence = GeofenceService(session)

            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
            ) as progress:
                task = progress.add_task(f"Scanning last {hours} hours...", total=None)
                matches = await geofence.scan_recent_activity(hours=hours)
                progress.update(task, description="Scan complete!")

            if not matches or not matches.get('matches'):
                console.print("[yellow]No matches found in watch areas.[/yellow]")
                return

            console.print(f"\n[bold green]Found {len(matches['matches'])} matches:[/bold green]\n")

            for match in matches['matches'][:20]:
                icon = {
                    'zoning': '📋',
                    'permit': '🏗️',
                    'property': '🏠',
                    'court': '⚖️',
                }.get(match.get('type', ''), '•')

                console.print(f"  {icon} [{match.get('type', 'unknown').upper()}] {match.get('title', 'Unknown')}")
                console.print(f"     Location: {match.get('address', 'N/A')}")
                console.print(f"     Watch Area: {match.get('watch_area', 'N/A')}")
                console.print()

    asyncio.run(_scan())


@local_app.command("alerts")
def local_alerts(
    unread_only: bool = typer.Option(False, "--unread", "-u", help="Show only unread alerts"),
    limit: int = typer.Option(20, "--limit", "-n", help="Number of alerts to show"),
):
    """Show local government alerts."""
    async def _alerts():
        await init_services()

        from app.services.local_government import GeofenceService

        async with get_db_session() as session:
            geofence = GeofenceService(session)
            alerts = await geofence.get_user_alerts(unread_only=unread_only, limit=limit)

            if not alerts:
                console.print("[yellow]No alerts found.[/yellow]")
                return

            console.print(f"[bold]Local Government Alerts ({len(alerts)} shown):[/bold]\n")

            for alert in alerts:
                severity_color = {
                    'critical': 'red',
                    'high': 'yellow',
                    'medium': 'cyan',
                    'low': 'dim',
                    'info': 'white',
                }.get(alert.severity, 'white')

                read_icon = "" if alert.is_read else "[bold blue]●[/bold blue] "

                console.print(f"{read_icon}[{severity_color}][{alert.severity.upper()}][/{severity_color}] {alert.title}")
                console.print(f"  Type: {alert.alert_type} | Address: {alert.address or 'N/A'}")
                console.print(f"  Created: {alert.created_at.strftime('%Y-%m-%d %H:%M')}")
                if alert.summary:
                    console.print(f"  {alert.summary[:100]}...")
                console.print()

    asyncio.run(_alerts())


@local_app.command("collect")
def local_collect(
    collector: Optional[str] = typer.Option(None, "--collector", "-c", help="Specific collector to run"),
    list_collectors: bool = typer.Option(False, "--list", "-l", help="List available collectors"),
):
    """Run local government data collectors."""
    async def _collect():
        await init_services()

        from app.services.collectors.local import (
            HamiltonCouncilCollector, HamiltonPropertyCollector, HamiltonCourtCollector,
            HamiltonZoningCollector, ChattanoogaPermitCollector,
            CatoosaCountyCollector, WalkerCountyCollector
        )

        collectors = {
            'hamilton-council': ('Hamilton County Council', HamiltonCouncilCollector),
            'hamilton-property': ('Hamilton County Property', HamiltonPropertyCollector),
            'hamilton-court': ('Hamilton County Court', HamiltonCourtCollector),
            'hamilton-zoning': ('Hamilton County Zoning', HamiltonZoningCollector),
            'chattanooga-permits': ('Chattanooga Building Permits', ChattanoogaPermitCollector),
            'catoosa': ('Catoosa County GA', CatoosaCountyCollector),
            'walker': ('Walker County GA', WalkerCountyCollector),
        }

        if list_collectors:
            console.print("[bold]Available Local Government Collectors:[/bold]\n")

            table = Table()
            table.add_column("Key", style="cyan", width=20)
            table.add_column("Description", width=35)

            for key, (desc, _) in collectors.items():
                table.add_row(key, desc)

            console.print(table)
            return

        async with get_db_session() as session:
            if collector:
                if collector not in collectors:
                    console.print(f"[red]Unknown collector: {collector}[/red]")
                    console.print("Use --list to see available collectors")
                    return

                desc, CollectorClass = collectors[collector]
                console.print(f"[cyan]Running {desc} collector...[/cyan]")

                with Progress(
                    SpinnerColumn(),
                    TextColumn("[progress.description]{task.description}"),
                    console=console,
                ) as progress:
                    task = progress.add_task("Collecting...", total=None)

                    try:
                        coll = CollectorClass(session)
                        result = await coll.collect()
                        progress.update(task, description="Complete!")
                        console.print(f"[green]Collected {result.get('items', 0)} items[/green]")
                    except Exception as e:
                        progress.update(task, description="Failed!")
                        console.print(f"[red]Error: {e}[/red]")
            else:
                # Run all collectors
                console.print("[cyan]Running all local government collectors...[/cyan]\n")

                for key, (desc, CollectorClass) in collectors.items():
                    try:
                        coll = CollectorClass(session)
                        result = await coll.collect()
                        console.print(f"  [green]✓[/green] {desc}: {result.get('items', 0)} items")
                    except Exception as e:
                        console.print(f"  [red]✗[/red] {desc}: {e}")

    asyncio.run(_collect())


# ============================================================================
# VERSION Command
# ============================================================================

@app.command()
def version():
    """Show version information."""
    console.print(Panel(
        "[bold cyan]THE PULSE[/bold cyan]\n"
        "Personal Intelligence Platform\n\n"
        "[dim]Version: 2.2.0[/dim]\n"
        "[dim]Phase 7: Local Government Monitor[/dim]",
        title="◆ The Pulse",
        border_style="cyan",
    ))


# ============================================================================
# Main entry point
# ============================================================================

if __name__ == "__main__":
    app()
