# The Pulse

A comprehensive research and intelligence monitoring platform that empowers journalists, investigators, and private citizens to conduct deep research while staying informed through automated tracking and analysis.

## Vision

Replace all fragmented media consumption with a single, curated intelligence feed. The Pulse sifts through the noise, extracts signal, and dramatically increases the ROI of time invested in learning and staying informed.

## Target Users

- Investigative journalists
- Private investigators
- Concerned citizens
- Amateur researchers
- Anyone drowning in information overload

## Core Features

| Feature | Description |
|---------|-------------|
| **Multi-Source Collection** | Automated ingestion from RSS, GDELT, ArXiv, Reddit, SEC EDGAR, ACLED, local news |
| **Entity Tracking** | Track people, organizations, locations across all content with WikiData linking |
| **Network Analysis** | Visualize entity relationships with interactive graph (1000+ nodes supported) |
| **Semantic Search** | Vector-based search across all processed content |
| **AI Research Assistant** | Claude-powered chat with streaming responses and context awareness |
| **Intelligence Briefings** | Auto-generated tiered briefings with "So What?" analysis |
| **Local Government Monitor** | Track council meetings, zoning, permits in your area (Chattanooga region) |

## Performance

### Network Graph API - 77x Faster

The entity relationship graph now loads in under 1 second, down from nearly a minute:

```
Before:  54,473ms API response
After:   698ms API response (77x improvement)

Full stack latency:
├─ Server API:     0.7s (was 54s)
├─ Client Layout:  5s non-blocking (FA2 Web Worker)
├─ Total Initial:  ~6s
└─ Subsequent:     < 1s (cached)
```

Achieved through multi-layer caching, dynamic algorithm selection, and offloading layout computation to client-side Web Workers.

## Tech Stack

| Component | Technology |
|-----------|------------|
| Backend | FastAPI (async Python) |
| Database | PostgreSQL + asyncpg |
| Vector Store | Qdrant |
| Cache | Redis |
| LLM | Claude Code CLI (subscription-based) |
| Embeddings | sentence-transformers (all-mpnet-base-v2) |
| Graph Viz | Sigma.js + graphology (WebGL) |
| Frontend | Vanilla JS, Jinja2 templates |

## Quick Start

### Prerequisites

- Python 3.10+
- PostgreSQL
- Docker (for Qdrant)
- Redis
- Claude Code CLI (`~/.local/bin/claude`)

### Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/The-Pulse.git
cd The-Pulse

# Create conda environment (recommended)
conda create -n the-pulse python=3.10
conda activate the-pulse

# Install dependencies
pip install -r requirements.txt

# Start services (Qdrant, Firecrawl)
./start_services.sh

# Initialize database tables
python -c "from app.database import init_db; import asyncio; asyncio.run(init_db())"

# Start the server
./run_appcmd
# or: uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Access Points

- **SIGINT Dashboard:** http://localhost:8000/dashboard
- **Original Interface:** http://localhost:8000/
- **API Docs:** http://localhost:8000/docs

## Project Structure

```
The-Pulse/
├── app/
│   ├── main.py                 # FastAPI entry point
│   ├── database.py             # SQLAlchemy async setup
│   ├── api/v1/                 # API routes
│   │   ├── collection/         # Content collection
│   │   ├── entities/           # Entity tracking
│   │   ├── network/            # Graph analysis
│   │   ├── processing/         # Content processing
│   │   ├── synthesis/          # Briefing generation
│   │   └── local/              # Local government
│   ├── services/               # Business logic
│   │   ├── collectors/         # Source collectors
│   │   ├── network_mapper/     # Graph services
│   │   ├── entity_extraction/  # GLiNER + WikiData
│   │   ├── processing/         # Content pipeline
│   │   └── synthesis/          # Briefing generation
│   └── models/                 # SQLAlchemy models
├── static/                     # Frontend assets
│   ├── js/pulse-dashboard.js   # Dashboard controller
│   └── css/sigint-theme.css    # SIGINT theme
├── templates/                  # Jinja2 templates
├── specs/                      # Feature specifications
└── docs/                       # Documentation
```

## Key APIs

| Endpoint | Purpose |
|----------|---------|
| `GET /api/v1/network/graph` | Full entity relationship graph |
| `POST /api/v1/collection/run` | Trigger content collection |
| `POST /api/v1/processing/extract-entities` | Extract entities from news |
| `GET /api/v1/synthesis/briefing/tiered` | Generate intelligence briefing |
| `WS /api/v1/websocket/ws` | Real-time chat and updates |

## Development

### Documentation Files

| File | Purpose |
|------|---------|
| `HANDOFF.md` | Session handoff state |
| `LLM_CONTEXT.md` | Architecture reference for AI agents |
| `CHANGELOG.md` | Session history |
| `LEARNED_PREFERENCES.md` | Evolved coding rules |

### Running Tests

```bash
# Verify network API performance
time curl -s "http://localhost:8000/api/v1/network/graph?include_positions=true&include_clusters=true" | jq '._timings'

# Check collection status
curl http://localhost:8000/api/v1/collection/status | jq

# View cache status
curl http://localhost:8000/api/v1/network/cache/status | jq
```

## Collectors

All collectors are **free to use** - no API keys required for basic operation:

| Collector | Source | Interval |
|-----------|--------|----------|
| RSS | Reuters, AP, BBC, Ars Technica, etc. | 30 min |
| GDELT | Global event data | 1 hour |
| ArXiv | AI/ML research papers | 2 hours |
| Reddit | RC/FPV hobbyist communities | 1 hour |
| SEC EDGAR | Corporate filings (8-K, 10-K) | 4 hours |
| ACLED | Armed conflict data | Daily |
| Local News | Chattanooga region | 30 min |

## Issues

If you have issues setting up and running locally, submit an issue and I will help you get it fixed up.

## License

MIT
