# THE PULSE - LLM Developer Context Document

> **Purpose**: This document provides comprehensive context for LLM developers onboarding to The Pulse codebase. It covers project structure, architecture, data flows, key modules, and development patterns.

**Last Updated**: 2026-01-16 (Intelligence Collection Expansion - 23 new RSS feeds, ArXiv expansion)

---

## Table of Contents

1. [Project Overview](#project-overview)
2. [Project Structure](#project-structure)
3. [Architecture Overview](#architecture-overview)
4. [Data Flow](#data-flow)
5. [Core Modules](#core-modules)
6. [Key Data Structures](#key-data-structures)
7. [Configuration](#configuration)
8. [API Endpoints](#api-endpoints)
9. [External Dependencies](#external-dependencies)
10. [Code Patterns & Conventions](#code-patterns--conventions)
11. [Extension Points](#extension-points)
12. [Common Development Tasks](#common-development-tasks)

---

## Project Overview

**The Pulse** is a Python-based research and news monitoring platform that:

1. **Collects** news articles from multiple sources via web scraping (Firecrawl, Playwright)
2. **Processes** documents (PDFs) with text extraction and vector embeddings
3. **Tracks** entities (people, organizations, locations) across documents and news
4. **Provides** AI-powered research assistance via LLM integration (Claude Code)
5. **Outputs** real-time chat responses, entity relationship graphs, and analysis

| Attribute | Value |
|-----------|-------|
| Language | Python 3 |
| Framework | FastAPI (async) |
| Database | PostgreSQL (asyncpg) + Qdrant (vectors) |
| LLM Backend | **Claude Code CLI** (subscription-based, subprocess) |
| Embeddings | **sentence-transformers** (all-mpnet-base-v2, 768 dims) |
| Caching | Redis |
| Total Lines | ~10,000 |
| Architecture | Layered async API with services |

---

## Project Structure

```
The-Pulse/
├── app/                              # Main application code
│   ├── main.py                       # FastAPI entry point, router registration
│   ├── database.py                   # SQLAlchemy async engine & session setup
│   │
│   ├── core/                         # Core configuration & dependencies
│   │   ├── config.py                 # Pydantic settings (DB, Redis, JWT)
│   │   ├── dependencies.py           # FastAPI dependencies, auth, lifespan
│   │   ├── exceptions.py             # Custom exception classes
│   │   └── logging.py                # Centralized logging with file rotation
│   │
│   ├── models/                       # SQLAlchemy ORM models
│   │   ├── user.py                   # User model (auth, API keys)
│   │   ├── project.py                # ResearchProject, ProjectFolder, Document
│   │   ├── conversation.py           # Conversation, Message models
│   │   ├── news_article.py           # NewsArticle model
│   │   └── entities.py               # TrackedEntity, EntityMention models
│   │
│   ├── api/                          # API layer
│   │   └── v1/                       # Versioned API (v1)
│   │       ├── auth/                 # Authentication routes
│   │       │   ├── routes.py         # Login, register, API key management
│   │       │   └── schemas.py        # Pydantic schemas (placeholder)
│   │       ├── projects/             # Project management routes
│   │       │   ├── routes.py         # CRUD projects, documents, conversations
│   │       │   └── schemas.py        # Pydantic schemas (placeholder)
│   │       ├── news/                 # News article routes
│   │       │   ├── routes.py         # Article listing, scraping, analysis
│   │       │   └── schemas.py        # Pydantic schemas (placeholder)
│   │       ├── entities/             # Entity tracking routes
│   │       │   ├── routes.py         # Entity CRUD, mentions, relationships
│   │       │   └── schemas.py        # Pydantic schemas (placeholder)
│   │       ├── research_assistant/   # AI research routes
│   │       │   ├── routes.py         # Chat, structured output, analysis
│   │       │   └── schemas.py        # Pydantic schemas (placeholder)
│   │       ├── collection/           # Collection engine routes
│   │       │   ├── __init__.py       # Router exports
│   │       │   └── routes.py         # Status, triggers, history, control
│   │       ├── network/              # Network mapper routes
│   │       │   ├── __init__.py       # Router exports
│   │       │   └── routes.py         # Graph, paths, centrality, communities
│   │       ├── websocket/            # WebSocket routes
│   │       │   ├── routes.py         # Real-time chat, commands
│   │       │   └── schemas.py        # Pydantic schemas (placeholder)
│   │       └── processing/           # Content processing routes
│   │           ├── __init__.py       # Router exports
│   │           └── routes.py         # Validation, ranking, embedding, search
│   │
│   ├── services/                     # Business logic layer
│   │   ├── claude_bridge.py          # Claude Code CLI integration (NEW)
│   │   ├── local_embeddings.py       # sentence-transformers embeddings (NEW)
│   │   ├── document_processor.py     # PDF processing, chunking, embeddings
│   │   ├── entity_tracker.py         # Entity detection, mention tracking
│   │   ├── news_extraction_service.py # Web scraping, article parsing
│   │   ├── research_assistant.py     # LLM integration (Claude Code)
│   │   ├── conversation_service.py   # Chat/conversation management
│   │   ├── project_service.py        # Project CRUD operations
│   │   ├── security_service.py       # JWT token operations
│   │   ├── scheduled_scraping.py     # APScheduler news scraping
│   │   │
│   │   ├── collectors/               # Automated content collection engine (ALL FREE)
│   │   │   ├── __init__.py           # Module exports, get_all_collectors()
│   │   │   ├── base.py               # BaseCollector ABC, CollectedItem dataclass
│   │   │   ├── config.py             # Collection config (feeds, APIs, rates)
│   │   │   ├── scheduler.py          # CollectionScheduler, health monitoring
│   │   │   ├── rss_collector.py      # RSS feed collector (Reuters, AP, BBC, etc.)
│   │   │   ├── gdelt_collector.py    # GDELT API collector (8 query templates) - FREE
│   │   │   ├── acled_collector.py    # ACLED conflict data collector - FREE (research)
│   │   │   ├── opensanctions_collector.py # Sanctions/PEP data - FREE (rate-limited)
│   │   │   ├── sec_edgar_collector.py # SEC corporate filings - FREE (gov data)
│   │   │   ├── arxiv_collector.py    # ArXiv API collector (AI/ML papers)
│   │   │   ├── reddit_collector.py   # Reddit collector (RC/hobby subreddits)
│   │   │   ├── local_news_collector.py # Local news (Chattanooga/NW Georgia)
│   │   │   └── rc_manufacturer_collector.py # RC manufacturer web scraper
│   │   │
│   │   ├── network_mapper/           # Network analysis engine
│   │   │   ├── __init__.py           # Module exports
│   │   │   ├── graph_service.py      # NetworkMapperService (path, centrality, communities)
│   │   │   └── relationship_discovery.py # RelationshipDiscoveryService (co-mentions)
│   │   │
│   │   ├── local_government/         # Local Government Monitor
│   │   │   ├── __init__.py           # Module exports
│   │   │   ├── geofence_service.py   # GeofenceService (watch areas, Haversine)
│   │   │   └── local_analyzer.py     # LocalIntelligenceAnalyzer (briefings)
│   │   │
│   │   ├── collectors/local/         # Local government collectors
│   │   │   ├── __init__.py           # Module exports
│   │   │   ├── hamilton_county.py    # Hamilton County TN collectors
│   │   │   └── georgia_counties.py   # Catoosa/Walker County GA collectors
│   │   │
│   │   ├── processing/               # Content processing pipeline
│   │   │   ├── __init__.py           # Module exports
│   │   │   ├── validator.py          # ContentValidator, spam detection
│   │   │   ├── ranker.py             # RelevanceRanker, scoring system
│   │   │   ├── embedder.py           # NewsItemEmbedder, Qdrant storage
│   │   │   └── pipeline.py           # ProcessingPipeline orchestrator
│   │   │
│   │   └── entity_extraction/        # Entity extraction & linking (Phase 4)
│   │       ├── __init__.py           # Module exports
│   │       ├── gliner_extractor.py   # GLiNER zero-shot NER (11 entity types)
│   │       ├── wikidata_linker.py    # WikiData entity disambiguation
│   │       └── auto_extractor.py     # Automated extraction & tracking pipeline
│   │
│   └── scripts/                      # Database migration scripts
│       ├── create_news_articles_table.py
│       ├── create_entity_tracking_tables.py
│       ├── add_conversations_tables.py
│       └── ...                       # Various schema migrations
│
├── static/                           # Frontend assets
│   ├── css/
│   │   ├── styles.css                # Original dark theme styling (47KB)
│   │   └── sigint-theme.css          # SIGINT intelligence dashboard theme
│   └── js/
│       ├── main.js                   # Application entry point
│       ├── websocket.js              # WebSocket connection manager
│       ├── auth.js                   # Authentication flows
│       ├── chat.js                   # Chat interface
│       ├── projects.js               # Project management
│       ├── news_feed.js              # News display
│       ├── entity_tracking.js        # Entity UI + D3 graphs
│       ├── document_upload.js        # File upload handling
│       ├── workspace.js              # Panel resizing
│       ├── conversations_sidebar.js  # Conversation list
│       ├── pulse-dashboard.js        # SIGINT dashboard controller
│       ├── d3.v7.min.js              # D3.js library
│       └── marked.min.js             # Markdown parser
│
├── templates/                        # Jinja2 templates
│   ├── index.html                    # Original SPA entry template
│   └── dashboard.html                # SIGINT intelligence dashboard
│
├── requirements.txt                  # Python dependencies (96 packages)
├── run_appcmd                        # Startup script (uvicorn)
├── start_services.sh                 # Service startup (Qdrant, Firecrawl)
├── startqdrant                       # Qdrant startup script
├── browse_storage.py                 # Streamlit storage browser (run: streamlit run browse_storage.py)
├── pulse_cli.py                      # Command-line interface for The Pulse
└── README.md                         # Project documentation
```

---

## Architecture Overview

### Layered Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           INTERFACE LAYER                                   │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                    WEB DASHBOARD (SPA)                              │    │
│  │  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────────┐    │    │
│  │  │  Chat   │ │ Projects│ │  News   │ │ Entity  │ │  Document   │    │    │
│  │  │Interface│ │  Panel  │ │  Feed   │ │ Tracker │ │   Upload    │    │    │
│  │  └─────────┘ └─────────┘ └─────────┘ └─────────┘ └─────────────┘    │    │
│  │         ↓ WebSocket ↓           ↓ REST API ↓                        │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────────┘
                                    ↓
┌─────────────────────────────────────────────────────────────────────────────┐
│                            API LAYER (FastAPI)                              │
│  ┌───────────┐ ┌───────────┐ ┌───────────┐ ┌───────────┐ ┌───────────┐      │
│  │   Auth    │ │ Projects  │ │   News    │ │ Entities  │ │ Research  │      │
│  │  Router   │ │  Router   │ │  Router   │ │  Router   │ │ Assistant │      │
│  └─────┬─────┘ └─────┬─────┘ └─────┬─────┘ └─────┬─────┘ └─────┬─────┘      │
│        │             │             │             │             │            │
│        └─────────────┴─────────────┴─────────────┴─────────────┘            │
│                                    ↓                                        │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                        WebSocket Router                             │    │
│  │              Real-time chat, streaming, commands                    │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────────┘
                                    ↓
┌─────────────────────────────────────────────────────────────────────────────┐
│                          SERVICE LAYER                                      │
│  ┌────────────────┐  ┌────────────────┐  ┌────────────────┐                 │
│  │   Document     │  │    Entity      │  │    News        │                 │
│  │   Processor    │  │   Tracker      │  │  Extraction    │                 │
│  │                │  │                │  │                │                 │
│  │ • PDF parsing  │  │ • Mention scan │  │ • Firecrawl    │                 │
│  │ • Chunking     │  │ • Relationship │  │ • Playwright   │                 │
│  │ • Embeddings   │  │   analysis     │  │ • Liveblog     │                 │
│  └────────────────┘  └────────────────┘  └────────────────┘                 │
│                                                                             │
│  ┌────────────────┐  ┌────────────────┐  ┌────────────────┐                 │
│  │   Research     │  │  Conversation  │  │   Project      │                 │
│  │   Assistant    │  │   Service      │  │   Service      │                 │
│  │                │  │                │  │                │                 │
│  │ • Ollama LLM   │  │ • Message mgmt │  │ • CRUD ops     │                 │
│  │ • Structured   │  │ • Token count  │  │ • File upload  │                 │
│  │   output       │  │ • Streaming    │  │ • Folders      │                 │
│  └────────────────┘  └────────────────┘  └────────────────┘                 │
└─────────────────────────────────────────────────────────────────────────────┘
                                    ↓
┌─────────────────────────────────────────────────────────────────────────────┐
│                          STORAGE LAYER                                      │
│  ┌────────────────────┐  ┌────────────────────┐  ┌────────────────────┐     │
│  │     PostgreSQL     │  │       Qdrant       │  │       Redis        │     │
│  │   (async/asyncpg)  │  │   (vector store)   │  │     (caching)      │     │
│  │                    │  │                    │  │                    │     │
│  │ • users            │  │ • document chunks  │  │ • API keys         │     │
│  │ • research_projects│  │ • 3072-dim vectors │  │ • sessions         │     │
│  │ • project_folders  │  │ • cosine search    │  │ • temp data        │     │
│  │ • documents        │  │                    │  │                    │     │
│  │ • conversations    │  │                    │  │                    │     │
│  │ • messages         │  │                    │  │                    │     │
│  │ • news_articles    │  │                    │  │                    │     │
│  │ • tracked_entities │  │                    │  │                    │     │
│  │ • entity_mentions  │  │                    │  │                    │     │
│  └────────────────────┘  └────────────────────┘  └────────────────────┘     │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Data Flow

### Document Processing Flow

```
[User uploads PDF]
        │
        ▼
┌───────────────────────────────────────┐
│ PHASE 1: VALIDATION                   │
│                                       │
│  • Magic bytes check (PDF only)       │
│  • Duplicate check (filename)         │
│  • Create Document record             │
│                                       │
│  Output: Document ID, processing      │
└───────────────────────────────────────┘
        │
        ▼
┌───────────────────────────────────────┐
│ PHASE 2: EXTRACTION                   │
│                                       │
│  • PyPDF2 text extraction             │
│  • Batch page processing (3 pages)    │
│  • Metadata extraction                │
│  • Raw content stored                 │
│                                       │
│  Output: Full text + metadata         │
└───────────────────────────────────────┘
        │
        ▼
┌───────────────────────────────────────┐
│ PHASE 3: CHUNKING                     │
│                                       │
│  • 250 char chunks                    │
│  • 50 char overlap                    │
│  • Max 1000 chunks per doc            │
│  • Smart break points (., !, ?)       │
│                                       │
│  Output: List of text chunks          │
└───────────────────────────────────────┘
        │
        ▼
┌───────────────────────────────────────┐
│ PHASE 4: EMBEDDING                    │
│                                       │
│  • OpenAI text-embedding-3-large      │
│  • 3072-dimensional vectors           │
│  • Retry with exponential backoff     │
│                                       │
│  Output: Vector per chunk             │
└───────────────────────────────────────┘
        │
        ▼
┌───────────────────────────────────────┐
│ PHASE 5: STORAGE                      │
│                                       │
│  • Qdrant: vectors + metadata         │
│  • PostgreSQL: chunk IDs, raw_content │
│  • Update processing_status           │
│                                       │
│  Output: Indexed document             │
└───────────────────────────────────────┘
```

### Entity Tracking Flow

```
[User creates TrackedEntity]
        │
        ▼
┌───────────────────────────────────────┐
│ PHASE 1: ENTITY CREATION              │
│                                       │
│  • Store in tracked_entities table    │
│  • Normalize name (lowercase)         │
│  • Set entity_type                    │
│                                       │
└───────────────────────────────────────┘
        │
        ▼
┌───────────────────────────────────────┐
│ PHASE 2: DOCUMENT SCAN                │
│                                       │
│  • Scan all user's documents          │
│  • Search raw_content for entity name │
│  • Extract context snippets (200 chr) │
│  • Create EntityMention records       │
│                                       │
└───────────────────────────────────────┘
        │
        ▼
┌───────────────────────────────────────┐
│ PHASE 3: NEWS SCAN                    │
│                                       │
│  • Scan all news articles             │
│  • Search content for entity name     │
│  • Extract context snippets           │
│  • Create EntityMention records       │
│                                       │
└───────────────────────────────────────┘
        │
        ▼
┌───────────────────────────────────────┐
│ PHASE 4: RELATIONSHIP ANALYSIS        │
│                                       │
│  • Find co-occurring entities         │
│  • Calculate Jaccard similarity       │
│  • Build relationship network         │
│  • Return graph data (nodes, edges)   │
│                                       │
└───────────────────────────────────────┘
```

### Chat/Research Assistant Flow

```
[User sends chat message]
        │
        ▼
┌───────────────────────────────────────┐
│ WebSocket Connection                  │
│                                       │
│  • Authenticate via cookie            │
│  • Parse message type                 │
│                                       │
└───────────────────────────────────────┘
        │
        ▼
┌───────────────────────────────────────┐
│ ConversationService                   │
│                                       │
│  • Load conversation history          │
│  • Count tokens (tiktoken)            │
│  • Trim to 7000 token limit           │
│  • Add system prompt                  │
│                                       │
└───────────────────────────────────────┘
        │
        ▼
┌───────────────────────────────────────┐
│ ResearchAssistant                     │
│                                       │
│  • Call ClaudeCodeBridge              │
│  • Subprocess: ~/.local/bin/claude    │
│  • Uses subscription auth (no API key)│
│  • Stream response chunks             │
│                                       │
└───────────────────────────────────────┘
        │
        ▼
┌───────────────────────────────────────┐
│ ClaudeCodeBridge                      │
│                                       │
│  • Convert messages to prompt         │
│  • Pass via stdin (avoid arg limits)  │
│  • --output-format stream-json        │
│  • Parse JSON chunks                  │
│                                       │
└───────────────────────────────────────┘
        │
        ▼
┌───────────────────────────────────────┐
│ Response Streaming                    │
│                                       │
│  • Send chunks via WebSocket          │
│  • Render markdown (marked.js)        │
│  • Save assistant message to DB       │
│                                       │
└───────────────────────────────────────┘
```

### Collection Engine Flow

```
[Scheduler triggers collector]
        │
        ▼
┌───────────────────────────────────────┐
│ PHASE 1: COLLECTION                   │
│                                       │
│  Each collector fetches from source:  │
│  • RSSCollector: feedparser + aiohttp │
│  • GDELTCollector: GDELT DOC 2.0 API  │
│  • ArxivCollector: arxiv Python API   │
│  • RedditCollector: PRAW or JSON API  │
│  • LocalNewsCollector: RSS + scraping │
│  • RCManufacturerCollector: crawl4ai  │
│                                       │
│  Output: List[CollectedItem]          │
└───────────────────────────────────────┘
        │
        ▼
┌───────────────────────────────────────┐
│ PHASE 2: DEDUPLICATION                │
│                                       │
│  • Check by URL (fast, unique index)  │
│  • Check by content hash (SHA-256)    │
│  • Skip duplicates, count new items   │
│                                       │
│  Output: New items only               │
└───────────────────────────────────────┘
        │
        ▼
┌───────────────────────────────────────┐
│ PHASE 3: STORAGE                      │
│                                       │
│  • Convert CollectedItem → NewsItem   │
│  • Store in PostgreSQL                │
│  • Create CollectionRun record        │
│  • Log statistics (new/dup/filtered)  │
│                                       │
│  Output: Persisted NewsItem records   │
└───────────────────────────────────────┘
        │
        ▼
┌───────────────────────────────────────┐
│ PHASE 4: MONITORING                   │
│                                       │
│  • Update collector health status     │
│  • Track consecutive failures         │
│  • Expose via /api/v1/collection/     │
│                                       │
│  Output: Health metrics               │
└───────────────────────────────────────┘
```

---

## Core Modules

### Services (`app/services/`)

| Module | Class | Size | Purpose |
|--------|-------|------|---------|
| `claude_bridge.py` | `ClaudeCodeBridge` | 776 lines | **Claude Code CLI integration** (subscription auth) |
| `local_embeddings.py` | `LocalEmbeddings` | 285 lines | **sentence-transformers embeddings** (768 dims) |
| `document_processor.py` | `DocumentProcessor` | 824 lines | PDF processing, chunking, embeddings, Qdrant storage |
| `entity_tracker.py` | `EntityTrackingService` | 1036 lines | Entity detection, mention scanning, relationship analysis |
| `news_extraction_service.py` | `NewsExtractionService` | 594 lines | Web scraping via Firecrawl/Playwright |
| `research_assistant.py` | `ResearchAssistant` | 470 lines | Claude-based LLM integration, structured output |
| `conversation_service.py` | `ConversationService` | 330 lines | Chat history, token management, streaming |
| `project_service.py` | `ProjectService` | 281 lines | Project CRUD, document management |
| `security_service.py` | `SecurityService` | 30 lines | JWT token operations |
| `scheduled_scraping.py` | - | 55 lines | APScheduler news collection (6-hour interval) |
| `collectors/base.py` | `BaseCollector`, `CollectedItem` | 280 lines | Abstract collector, data structures |
| `collectors/scheduler.py` | `CollectionScheduler` | 220 lines | Scheduled execution, health monitoring |
| `collectors/rss_collector.py` | `RSSCollector` | 130 lines | Multi-feed RSS collection |
| `collectors/gdelt_collector.py` | `GDELTCollector` | 280 lines | **Enhanced GDELT** (8 query templates) - FREE |
| `collectors/acled_collector.py` | `ACLEDCollector` | 320 lines | **Armed conflict data** - FREE (research) |
| `collectors/opensanctions_collector.py` | `OpenSanctionsCollector` | 350 lines | **Sanctions/PEP data** - FREE (rate-limited) |
| `collectors/sec_edgar_collector.py` | `SECEdgarCollector` | 400 lines | **SEC filings** (8-K, 10-K, Form 4) - FREE |
| `collectors/arxiv_collector.py` | `ArxivCollector` | 120 lines | ArXiv research papers |
| `collectors/reddit_collector.py` | `RedditCollector` | 180 lines | Reddit posts (PRAW/JSON) |
| `collectors/local_news_collector.py` | `LocalNewsCollector` | 200 lines | Local news RSS + scraping |
| `collectors/rc_manufacturer_collector.py` | `RCManufacturerCollector` | 170 lines | RC manufacturer scraping |
| `processing/validator.py` | `ContentValidator` | 220 lines | Content validation, spam detection |
| `processing/ranker.py` | `RelevanceRanker` | 200 lines | Relevance scoring, source credibility |
| `processing/embedder.py` | `NewsItemEmbedder` | 280 lines | Vector embedding, Qdrant storage |
| `processing/pipeline.py` | `ProcessingPipeline` | 400 lines | Full pipeline orchestration |
| `ollama_embeddings.py` | `OllamaEmbeddings` | 150 lines | Local embedding generation (nomic-embed-text) |
| `synthesis/context_builder.py` | `ContextBuilder` | 300 lines | Entity and temporal context for synthesis |
| `synthesis/briefing_generator.py` | `BriefingGenerator` | 377 lines | Backward-compatible wrapper for TieredBriefingGenerator |
| `synthesis/tiered_briefing.py` | `TieredBriefingGenerator` | 600 lines | **Tiered intelligence briefings** with "So What?" analysis |
| `synthesis/pattern_detector.py` | `PatternDetector` | 350 lines | **Pattern detection** (escalation, sentiment, entity surge) |
| `synthesis/trend_indicators.py` | `TrendIndicatorService` | 450 lines | **6-month rolling trend indicators** (Phase 5) |
| `synthesis/audio_generator.py` | `AudioGenerator` | 250 lines | Piper TTS integration for audio briefings |
| `synthesis/briefing_archive.py` | `BriefingArchive` | 300 lines | Briefing storage and retrieval |
| `broadcast.py` | `BroadcastManager` | 350 lines | WebSocket event broadcasting for real-time updates |
| `network_mapper/graph_service.py` | `NetworkMapperService` | 860 lines | Graph analysis, path finding, centrality, communities, server-side layout (`compute_layout`), cluster visualization (`get_clusters_for_visualization`) |
| `network_mapper/relationship_discovery.py` | `RelationshipDiscoveryService` | 400 lines | Auto-discover relationships from co-mentions |
| `local_government/geofence_service.py` | `GeofenceService` | 350 lines | Watch areas, Haversine distance, location alerts |
| `local_government/local_analyzer.py` | `LocalIntelligenceAnalyzer` | 400 lines | Local government briefing generation |
| `collectors/local/hamilton_county.py` | Various collectors | 500 lines | Hamilton County TN government data collection |
| `collectors/local/georgia_counties.py` | Various collectors | 400 lines | Catoosa/Walker County GA data collection |
| `entity_extraction/gliner_extractor.py` | `IntelligenceEntityExtractor` | 450 lines | **GLiNER zero-shot NER** (11 entity types) - FREE |
| `entity_extraction/wikidata_linker.py` | `WikiDataLinker` | 400 lines | **WikiData entity disambiguation** + Redis L2 cache - FREE API |
| `entity_extraction/auto_extractor.py` | `AutoEntityExtractor` | 400 lines | **Automated extraction** + QID deduplication, progress callbacks |
| `extraction_queue_manager.py` | `ExtractionQueueManager` | 200 lines | **NEW**: Rate limiting queue for entity extraction |

### Storage Browser (`browse_storage.py`)

Streamlit-based web UI for browsing collected intelligence items.

```bash
# Start the storage browser
streamlit run browse_storage.py
```

| Feature | Description |
|---------|-------------|
| Browse Items | Paginated view of all collected news items |
| Filter by Source | reddit, gdelt, arxiv, rss, local, rc_manufacturer |
| Filter by Category | geopolitics, cyber, military, tech_ai, financial, etc. |
| Search | Title search across all items |
| Item Details | Full content, metadata, relevance scores |
| Collection Runs | History of collector executions with stats |

### CLI (`pulse_cli.py`)

| Command | Purpose |
|---------|---------|
| `generate` | Generate intelligence briefings (daily, focused, with audio) |
| `status` | Show system status (collectors, health, connections) |
| `collect` | Run collection manually (all or specific collector) |
| `search` | Search collected items (semantic or keyword) |
| `graph` | Generate entity relationship graph (HTML/JSON/DOT) |
| `process` | Run processing pipeline on pending items |
| `briefings` | List and manage archived briefings |
| `network status` | Show network graph statistics |
| `network centrality` | Analyze entity centrality (degree, betweenness, pagerank) |
| `network communities` | Detect communities in the entity network |
| `network path` | Find path between two entities by name |
| `network discover` | Discover relationships from co-mentions |
| `network export` | Export network graph to file (cytoscape, json) |
| `local briefing` | Generate local government briefing |
| `local stats` | Show local government activity statistics |
| `local watch-areas` | Manage watch areas (list, add predefined) |
| `local scan` | Scan recent activity for watch area matches |
| `local alerts` | Show local government alerts |
| `local collect` | Run local government data collectors |
| `version` | Show version information |

### API Routes (`app/api/v1/`)

| Module | Prefix | Lines | Purpose |
|--------|--------|-------|---------|
| `auth/routes.py` | `/api/auth/` | 278 | Login, register, API key management |
| `projects/routes.py` | `/api/v1/projects/` | 494 | Project CRUD, documents, conversations |
| `news/routes.py` | `/api/v1/news/` | 310 | News article management, scraping |
| `entities/routes.py` | `/api/v1/entities/` | 342 | Entity tracking, mentions, relationships |
| `research_assistant/routes.py` | `/api/v1/research_assistant/` | 260 | AI chat, structured output, analysis |
| `collection/routes.py` | `/api/v1/collection/` | 280 | Collection status, triggers, history |
| `processing/routes.py` | `/api/v1/processing/` | 660 | Validation, ranking, embedding, search, **entity extraction** |
| `synthesis/routes.py` | `/api/v1/synthesis/` | 660 | Briefing generation (tiered + legacy), archive, audio, **trend indicators** |
| `network/routes.py` | `/api/v1/network/` | 350 | Graph analysis, paths, centrality, communities |
| `local/routes.py` | `/api/v1/local/` | 534 | Local government monitoring, watch areas, alerts |
| `websocket/routes.py` | `/api/v1/websocket/` | 299 | Real-time WebSocket communication |

### Models (`app/models/`)

| Module | Models | Purpose |
|--------|--------|---------|
| `user.py` | `User` | Authentication, API keys |
| `project.py` | `ResearchProject`, `ProjectFolder`, `Document` | Project management |
| `conversation.py` | `Conversation`, `Message` | Chat history |
| `news_article.py` | `NewsArticle` | On-demand scraped news storage |
| `news_item.py` | `NewsItem`, `CollectionRun` | Automated collection storage |
| `entities.py` | `TrackedEntity`, `EntityMention` | Entity tracking |
| `local_government.py` | `CouncilMeeting`, `ZoningCase`, `BuildingPermit`, `PropertyTransaction`, `LocalCourtCase`, `WatchArea`, `LocalGovernmentAlert` | Local government monitoring |

---

## Key Data Structures

### User Model

```python
class User(Base):
    __tablename__ = "users"

    user_id: UUID (PK)           # Unique identifier
    email: String (unique)        # User email
    password_hash: String         # BCrypt hashed password
    openai_api_key: String        # Optional OpenAI API key
    created_at: DateTime
    updated_at: DateTime
```

### ResearchProject Model

```python
class ResearchProject(Base):
    __tablename__ = "research_projects"

    project_id: UUID (PK)         # Unique identifier
    name: String(255)             # Project name
    description: String           # Project description
    owner_id: String              # User ID reference
    status: String(50)            # 'active', 'archived', etc.
    settings: JSONB               # Flexible settings
    created_at: DateTime
    updated_at: DateTime

    # Relationships
    folders: List[ProjectFolder]  # cascade delete
    conversations: List[Conversation]
```

### Document Model

```python
class Document(Base):
    __tablename__ = "documents"

    document_id: UUID (PK)        # Unique identifier
    folder_id: UUID (FK)          # Parent folder
    filename: String(255)         # Original filename
    file_type: String(50)         # 'pdf'
    upload_date: DateTime
    processing_status: String(50) # 'pending', 'processing', 'completed', 'failed'
    doc_metadata: JSONB           # PDF metadata (author, pages, etc.)
    file_size: BigInteger         # Bytes
    hash_id: String(64)           # Content hash
    qdrant_chunks: Array[String]  # Vector chunk IDs
    raw_content: String           # Full extracted text
```

### TrackedEntity Model

```python
class TrackedEntity(Base):
    __tablename__ = "tracked_entities"

    entity_id: UUID (PK)          # Unique identifier
    user_id: UUID (FK)            # Owner user
    name: String                  # Entity name
    name_lower: String            # Lowercase for matching
    entity_type: String           # 'PERSON', 'ORG', 'LOCATION', 'CUSTOM'
    created_at: String            # ISO timestamp
    entity_metadata: JSON         # Additional data

    # Constraint: unique(user_id, name_lower)
```

### EntityMention Model

```python
class EntityMention(Base):
    __tablename__ = "entity_mentions"

    mention_id: UUID (PK)         # Unique identifier
    entity_id: UUID (FK)          # TrackedEntity reference
    document_id: UUID (FK, opt)   # Source document (nullable)
    news_article_id: UUID (FK, opt) # Source article (nullable)
    user_id: UUID (FK)            # Owner user
    chunk_id: String              # Chunk/section identifier
    context: String               # Surrounding text (~200 chars)
    timestamp: String             # ISO timestamp

    # Constraint: exactly one of (document_id, news_article_id) must be set
```

### NewsArticle Model

```python
class NewsArticle(Base):
    __tablename__ = "news_articles"

    id: UUID (PK)                 # Unique identifier
    title: String                 # Article title
    heading: String               # Subtitle/heading
    url: String                   # Source URL
    source_site: String           # Source website name
    content: String               # Full article text
    analysis: String              # AI-generated analysis
    scraped_at: DateTime          # Collection timestamp
    is_liveblog: Boolean          # Liveblog flag
    last_updated: DateTime        # Last content update
```

### NewsItem Model (Automated Collection)

```python
class NewsItem(Base):
    __tablename__ = "news_items"

    id: UUID (PK)                 # Unique identifier
    source_type: String(50)       # 'rss', 'gdelt', 'arxiv', 'reddit', 'local', 'rc_manufacturer'
    source_name: String(255)      # Human-readable source (e.g., "Reuters", "ArXiv")
    source_url: Text              # Feed URL or API endpoint
    title: Text                   # Item title
    content: Text                 # Full content if available
    summary: Text                 # Short summary (max 500 chars)
    url: Text (unique)            # Original article/item URL
    published_at: DateTime        # Original publication date
    collected_at: DateTime        # When we collected this item
    author: String(255)           # Author name if available
    categories: JSONB             # List of category strings
    processed: Integer            # 0=pending, 1=processed, 2=failed
    relevance_score: Float        # Calculated relevance (0.0-1.0)
    content_hash: String(64)      # SHA-256 for deduplication
    qdrant_id: String(36)         # Vector embedding ID (optional)
    item_metadata: JSONB          # Source-specific metadata
```

### CollectionRun Model

```python
class CollectionRun(Base):
    __tablename__ = "collection_runs"

    id: UUID (PK)                 # Unique identifier
    collector_type: String(50)    # 'rss', 'gdelt', etc.
    collector_name: String(255)   # Human-readable name
    started_at: DateTime          # Run start time
    completed_at: DateTime        # Run end time
    status: String(20)            # 'running', 'completed', 'failed'
    items_collected: Integer      # Total items fetched
    items_new: Integer            # New items (not duplicates)
    items_duplicate: Integer      # Duplicate items skipped
    items_filtered: Integer       # Items filtered by validation
    error_message: Text           # Error details if failed
    run_metadata: JSONB           # Additional run info
```

### Qdrant Vector Structure

```python
# Each document chunk is stored as:
{
    "id": "uuid-string",
    "vector": [float] * 768,      # sentence-transformers (all-mpnet-base-v2)
    "payload": {
        "doc_id": "document-uuid",
        "chunk_id": 0,             # Sequential chunk number
        "content": "chunk text...", # 250 chars max
        "metadata": {
            "title": "...",
            "author": "...",
            "num_pages": 10,
            "creation_date": "..."
        },
        "composite_id": "doc_uuid_0"
    }
}
```

**Note**: Embedding model changed from Ollama nomic-embed-text to sentence-transformers all-mpnet-base-v2.
Both produce 768-dimensional vectors, so existing Qdrant collections remain compatible.

---

## Configuration

### Environment Variables

```bash
# Database
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost/research_platform

# Redis
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0

# Security
SECRET_KEY=your-secret-key-here  # Required for JWT
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30

# Qdrant
QDRANT_HOST=localhost
QDRANT_PORT=6333

# Claude Code (subscription-based - NO API key needed)
# Ensure ~/.local/bin/claude exists and you're logged in via browser
# IMPORTANT: Do NOT set ANTHROPIC_API_KEY - this will cause per-token billing

# Embeddings (local - no config needed)
# Uses sentence-transformers all-mpnet-base-v2 automatically

# Phase 3: Data Source Collectors (ALL FREE - optional config)
# ACLED - Armed conflict data (FREE for research)
ACLED_API_KEY=your-free-acled-key     # Register at https://developer.acleddata.com/
ACLED_EMAIL=your-email@example.com     # Required for ACLED API

# OpenSanctions - Sanctions/PEP data (FREE - key is optional for higher rate limits)
OPENSANCTIONS_API_KEY=optional-key     # Works without key (rate-limited)

# SEC EDGAR - Corporate filings (FREE government data)
SEC_CONTACT_EMAIL=your-email@example.com  # Required by SEC policy

# DEPRECATED - No longer used after Claude migration:
# OLLAMA_HOST=http://localhost:11434
# OLLAMA_MODEL=qwen2.5-coder:14b
```

### Key Configuration (`app/core/config.py`)

```python
class Settings(BaseSettings):
    SECRET_KEY: str               # JWT signing key
    ALGORITHM: str = "HS256"      # JWT algorithm
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    DATABASE_URL: str             # PostgreSQL connection
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0

    API_TITLE: str = "Research Platform API"
    API_VERSION: str = "0.1.0"
    TEMPLATE_DIR: str = "templates"
    STATIC_DIR: str = "static"
```

### Document Processing Settings

```python
# In document_processor.py
CHUNK_SIZE = 250                  # Characters per chunk
CHUNK_OVERLAP = 50                # Overlap between chunks
MAX_CHUNKS = 1000                 # Max chunks per document

# In local_embeddings.py
EMBEDDING_MODEL = "all-mpnet-base-v2"  # sentence-transformers model
EMBEDDING_DIMENSIONS = 768             # Same as previous nomic-embed-text

BATCH_SIZE = 3                    # Pages per batch
MAX_RETRIES = 3                   # Embedding retry attempts
BACKOFF_FACTOR = 60               # Retry delay (seconds)
```

### Conversation Settings

```python
# In conversation_service.py
MAX_TOKENS = 7000                 # Context window limit
ENCODING = "cl100k_base"          # tiktoken encoding (GPT-4/3.5)
```

### Collection Settings

```python
# In collectors/config.py
RSS_TIMEOUT_SECONDS = 30          # Timeout for RSS fetches
API_TIMEOUT_SECONDS = 60          # Timeout for API calls
SCRAPE_DELAY_SECONDS = 2.0        # Delay between scrapes

# Default collection intervals (in scheduler)
RSS_INTERVAL = 30 minutes
GDELT_INTERVAL = 1 hour
ARXIV_INTERVAL = 2 hours
REDDIT_INTERVAL = 1 hour
LOCAL_NEWS_INTERVAL = 30 minutes
RC_MANUFACTURERS_INTERVAL = 4 hours

# RSS Feeds configured
RSS_FEEDS = {
    "reuters_world", "ap_top", "bbc_world",  # Geopolitics
    "ars_technica", "hacker_news",           # Tech
    "big_squid_rc",                          # RC Industry
    "chattanoogan_breaking", "wdef_news",    # Local
}

# ArXiv categories
ARXIV_CATEGORIES = ["cs.AI", "cs.LG", "cs.CL"]
ARXIV_MAX_PAPERS = 50

# Reddit subreddits
REDDIT_SUBREDDITS = ["RCPlanes", "radiocontrol", "fpv", "rccars", "Multicopter"]
REDDIT_POSTS_PER_SUB = 25
```

### Unavailable RSS Sources (Future Research)

These sources were investigated but lack public RSS feeds as of 2026-01-16. Worth checking periodically for changes:

**AI Providers (No Public RSS):**
- **Anthropic** - No RSS feed available, only email newsletter
- **Meta AI** - No public blog RSS
- **Microsoft Research** - Blocked/403
- **Mistral AI** - No RSS feed found

**Government/Security (Blocked or Killed):**
- **CISA** - Killed RSS feeds in May 2025, shifted to email/social media only
- **DOJ** - Press release RSS returns 403/404
- **ATF** - RSS blocked
- **DEA** - RSS unavailable
- **USMS** - RSS blocked

**Think Tanks (No Working RSS):**
- **Brookings Institution** - RSS feed blocked or unavailable
- **Carnegie Endowment** - Feed returns errors
- **Chatham House** - RSS unavailable

**Academic (Restricted Access):**
- **SSRN** - Returns 403, requires authenticated access
- **PubMed** - Requires custom search-generated feed URLs, no generic feed

**Local News:**
- **WTVC NewsChannel 9** - RSS redirects to error page

### Logging Configuration

```python
# In app/core/logging.py
LOG_DIR = "logs/"                 # Log directory (auto-created)
LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s:%(lineno)d | %(message)s"
MAX_BYTES = 10 * 1024 * 1024      # 10 MB per file
BACKUP_COUNT = 5                  # Keep 5 backup files

# Log files:
# - logs/pulse.log        (INFO+)  - Main application log
# - logs/pulse_debug.log  (DEBUG+) - Full debug output
# - logs/pulse_errors.log (ERROR+) - Errors only
```

**Usage in modules:**
```python
from app.core.logging import get_logger
logger = get_logger(__name__)

logger.debug("Detailed debug info")
logger.info("Normal operation")
logger.warning("Warning condition")
logger.error("Error occurred")
```

---

## API Endpoints

### Authentication (`/api/auth/`)

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/register` | Register new user |
| POST | `/login` | Login (returns JWT cookie) |
| POST | `/key` | Store OpenAI API key |
| POST | `/test-key` | Validate API key |
| GET | `/verify` | Verify auth token |
| POST | `/logout` | Clear auth cookie |
| GET | `/me` | Get current user info |

### Projects (`/api/v1/projects/`)

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/` | Create project |
| GET | `/` | List user's projects |
| GET | `/{project_id}` | Get project details |
| PUT | `/{project_id}` | Update project |
| DELETE | `/{project_id}` | Delete project |
| POST | `/{project_id}/select` | Select active project |
| POST | `/documents/upload` | Upload PDF |
| GET | `/{project_id}/documents` | List documents |
| POST | `/{project_id}/conversations` | Create conversation |
| GET | `/{project_id}/conversations` | List conversations |
| GET | `/{conversation_id}/messages` | Get messages |
| POST | `/{conversation_id}/messages` | Send message (streaming) |

### News (`/api/v1/news/`)

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/articles` | List recent articles |
| GET | `/articles/{id}/content` | Get article content |
| POST | `/articles/rescrape` | Force rescrape all |
| POST | `/articles/{id}/select` | Record article view |
| GET | `/articles/{id}/analysis` | Get analysis |
| POST | `/articles/{id}/analysis` | Store analysis |

### Entities (`/api/v1/entities/`)

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/track` | Add tracked entity |
| GET | `` | List tracked entities (supports `limit`, `offset`, `sort`, `type` params) |
| DELETE | `/{entity_name}` | Delete entity by name |
| DELETE | `/bulk` | **NEW**: Bulk delete entities by ID list |
| GET | `/{entity_name}/mentions` | Get mentions |
| GET | `/{entity_name}/relationships` | Analyze relationships |
| POST | `/{entity_name}/scan` | Manual rescan |
| GET | `/diagnostic` | System diagnostics |
| GET | `/diagnostic/articles` | Article diagnostic check |
| GET | `/duplicates` | Find duplicate entities by WikiData QID |
| POST | `/merge` | Merge secondary entity into primary |

### Research Assistant (`/api/v1/research_assistant/`)

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/chat` | Chat with streaming |
| POST | `/structured-chat` | Chat with JSON schema output |
| POST | `/generate-analysis-from-news-article` | Analyze article |
| WS | `/ws/chat` | WebSocket chat |
| WS | `/ws/conversations/{id}/chat` | WebSocket in conversation |

### Collection (`/api/v1/collection/`)

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/status` | Get status of all collectors |
| GET | `/health` | Get health summary (healthy/degraded/unhealthy) |
| POST | `/run` | Trigger collection (all or specific collector) |
| GET | `/runs` | Get collection run history |
| GET | `/runs/{run_id}` | Get specific run details |
| GET | `/items` | Get recently collected items |
| GET | `/items/stats` | Get collection statistics |
| GET | `/collectors` | List available collectors |
| POST | `/start` | Start collection scheduler |
| POST | `/stop` | Stop collection scheduler |

### Processing (`/api/v1/processing/`)

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/run` | Process pending news items (validation, ranking, embedding) |
| POST | `/batch` | Process specific items by ID |
| POST | `/validate` | Validate items (validation stage only) |
| POST | `/rank` | Rank items by relevance |
| GET | `/search` | Semantic search across processed items |
| GET | `/stats` | Get processing statistics |
| GET | `/queue` | Get items in processing queue |
| DELETE | `/embeddings/{item_id}` | Delete embedding for item |
| POST | `/extract-entities` | Extract and auto-track entities from recent news |
| POST | `/extract-entities/{item_id}` | Extract entities from specific item |
| GET | `/extract-entities/status` | **NEW**: Get extraction queue status |
| POST | `/extract-entities/bulk` | **NEW**: Fast bulk extraction (GLiNER only, no WikiData) |
| POST | `/enrich-entities` | **NEW**: Parallel WikiData enrichment for entities |

### Network (`/api/v1/network/`)

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/status` | Get network graph statistics |
| GET | `/graph` | Get full graph in Cytoscape.js format |
| GET | `/neighborhood/{entity_id}` | Get entity neighborhood up to N hops |
| GET | `/neighborhood/by-name/{name}` | Get neighborhood by entity name |
| POST | `/path` | Find shortest path between entities |
| POST | `/paths/all` | Find all paths between entities |
| GET | `/centrality/degree` | Most connected entities by degree |
| GET | `/centrality/betweenness` | Bridge entities between communities |
| GET | `/centrality/pagerank` | Most important entities by PageRank |
| GET | `/communities` | Detect communities/clusters in network |
| GET | `/timeline/{entity_id}` | Relationship timeline for entity |
| POST | `/relationships` | Add manual relationship |
| GET | `/relationships/types` | Get available relationship types |
| POST | `/discover` | Run relationship discovery from co-mentions |
| POST | `/discover/full` | Full relationship discovery across all entities |
| GET | `/discover/stats` | Discovery statistics |
| GET | `/export/cytoscape` | Export graph in Cytoscape.js format |
| GET | `/export/json` | Export graph as JSON |

### Local Government (`/api/v1/local/`)

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/briefing` | Generate local government briefing |
| GET | `/stats` | Get activity statistics |
| GET | `/watch-areas` | List user's watch areas |
| POST | `/watch-areas` | Create watch area |
| POST | `/watch-areas/predefined/{key}` | Create from predefined location |
| GET | `/watch-areas/predefined` | List predefined areas |
| DELETE | `/watch-areas/{id}` | Delete watch area |
| POST | `/check-location` | Check if location is in watch areas |
| POST | `/scan` | Scan recent activity for watch area matches |
| GET | `/alerts` | Get local government alerts |
| POST | `/alerts/{id}/read` | Mark alert as read |
| GET | `/meetings` | List council meetings |
| GET | `/meetings/{id}` | Get meeting details |
| GET | `/zoning` | List zoning cases |
| GET | `/permits` | List building permits |
| GET | `/property` | List property transactions |
| GET | `/court` | List court cases |
| GET | `/search/entity/{name}` | Search entity mentions across records |

**Predefined Watch Areas (Chattanooga Region):**
- `downtown_chattanooga` - Downtown (35.0456, -85.3097, 1.5mi)
- `north_shore` - North Shore (35.0558, -85.3140, 1.0mi)
- `southside` - Southside (35.0350, -85.3050, 1.0mi)
- `hixson` - Hixson (35.1220, -85.2340, 2.0mi)
- `red_bank` - Red Bank (35.1120, -85.2940, 1.5mi)
- `east_brainerd` - East Brainerd (35.0200, -85.1500, 2.0mi)
- `fort_oglethorpe` - Fort Oglethorpe, GA (34.9488, -85.2569, 2.0mi)
- `ringgold` - Ringgold, GA (34.9162, -85.1094, 2.0mi)
- `chickamauga` - Chickamauga, GA (34.8712, -85.2908, 1.5mi)

### WebSocket (`/api/v1/websocket/`)

| Protocol | Endpoint | Purpose |
|----------|----------|---------|
| WS | `/ws` | General WebSocket endpoint |

**Message Types:**
- `type: "chat"` - Send chat message
- `type: "command"` - Send command (project_context, etc.)
- Response: `type: "chunk"` / `"done"` / `"error"`

---

## External Dependencies

### Python Packages (Key Dependencies)

| Package | Version | Purpose |
|---------|---------|---------|
| `fastapi` | 0.115.6 | Web framework |
| `uvicorn` | 0.34.0 | ASGI server |
| `sqlalchemy` | 2.0.36 | ORM |
| `asyncpg` | 0.30.0 | PostgreSQL async driver |
| `qdrant-client` | 1.12.2 | Vector database client |
| `redis` | 5.2.1 | Caching |
| `openai` | 1.59.3 | Embeddings API |
| `pyjwt` | 2.10.1 | JWT tokens |
| `passlib` | 1.7.4 | Password hashing |
| `bcrypt` | 4.2.1 | BCrypt implementation |
| `pydantic` | 2.10.4 | Data validation |
| `pypdf2` | 3.0.1 | PDF parsing |
| `python-magic` | 0.4.27 | File type detection |
| `firecrawl-py` | 1.10.0 | Web scraping |
| `playwright` | 1.49.1 | Browser automation |
| `beautifulsoup4` | 4.12.3 | HTML parsing |
| `apscheduler` | 3.11.0 | Task scheduling |
| `tiktoken` | - | Token counting |
| `networkx` | - | Graph analysis |
| `aiohttp` | 3.13.2 | Async HTTP for collectors |
| `feedparser` | 6.0.12 | RSS/Atom feed parsing |
| `arxiv` | 2.3.1 | ArXiv API client |
| `praw` | - | Reddit API (optional) |
| `crawl4ai` | - | Web scraping (optional) |
| `trafilatura` | - | Web scraping fallback (optional) |

### External Services

| Service | Type | Port | Required |
|---------|------|------|----------|
| PostgreSQL | Database | 5432 | **Yes** |
| Qdrant | Vector DB | 6333 | **Yes** |
| Redis | Cache | 6379 | **Yes** |
| Claude Code CLI | LLM | N/A | **Yes** (subprocess at ~/.local/bin/claude) |
| Firecrawl | Scraping | - | Optional |
| Ollama | LLM | 11434 | **No** (removed after migration) |

---

## Code Patterns & Conventions

### Naming Conventions

| Element | Convention | Example |
|---------|------------|---------|
| Classes | PascalCase | `DocumentProcessor`, `EntityTrackingService` |
| Functions | snake_case | `process_pdf()`, `extract_entities()` |
| Constants | UPPER_SNAKE | `MAX_TOKENS`, `CHUNK_SIZE` |
| Modules | lowercase | `document_processor.py` |
| Routes | lowercase with underscores | `/api/v1/research_assistant/` |

### Async Patterns

```python
# All database operations use async/await
async def get_project(db: AsyncSession, project_id: UUID) -> Optional[ResearchProject]:
    result = await db.execute(
        select(ResearchProject).where(ResearchProject.project_id == project_id)
    )
    return result.scalar_one_or_none()

# Parallel operations with asyncio.gather
results = await asyncio.gather(
    self.scan_documents_for_entity(entity),
    self.scan_articles_for_entity(entity),
    return_exceptions=True
)
```

### Error Handling

```python
# Pattern 1: HTTPException for API errors
if not project:
    raise HTTPException(status_code=404, detail="Project not found")

# Pattern 2: Try/except with logging
try:
    embedding = await self._generate_embedding(chunk)
except Exception as e:
    logger.error(f"Embedding failed: {e}")
    raise EmbeddingGenerationError(str(e))

# Pattern 3: Retry with backoff
for attempt in range(max_retries):
    try:
        return await operation()
    except Exception as e:
        if attempt < max_retries - 1:
            await asyncio.sleep(backoff * (attempt + 1))
        else:
            raise
```

### Dependency Injection

```python
# FastAPI dependency injection
from app.core.dependencies import get_db, get_current_user

@router.post("/")
async def create_project(
    name: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # db and current_user are injected automatically
    pass
```

---

## Extension Points

### Adding a New API Module

1. Create directory `app/api/v1/new_module/`
2. Create `routes.py` with FastAPI router:
```python
from fastapi import APIRouter, Depends
router = APIRouter(prefix="/new_module", tags=["new_module"])

@router.get("/")
async def list_items():
    pass
```
3. Create `schemas.py` for Pydantic models
4. Register router in `app/main.py`:
```python
from app.api.v1.new_module.routes import router as new_router
app.include_router(new_router, prefix="/api/v1")
```

### Adding a New Service

1. Create `app/services/new_service.py`:
```python
class NewService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def do_something(self) -> Result:
        pass
```
2. Add dependency in `app/core/dependencies.py`:
```python
async def get_new_service(db: AsyncSession = Depends(get_db)):
    return NewService(db)
```

### Adding a New Collector

1. Create `app/services/collectors/my_collector.py`:
```python
from .base import BaseCollector, CollectedItem
from typing import List

class MyCollector(BaseCollector):
    @property
    def name(self) -> str:
        return "My Source"

    @property
    def source_type(self) -> str:
        return "my_source"

    async def collect(self) -> List[CollectedItem]:
        items = []
        # Fetch from source...
        items.append(CollectedItem(
            source="my_source",
            source_name="My Source",
            category="tech_ai",
            title="...",
            summary="...",
            url="...",
            published=datetime.now(timezone.utc),
        ))
        return items
```
2. Add to `collectors/__init__.py`:
```python
from .my_collector import MyCollector

def get_all_collectors() -> list:
    return [
        # ... existing collectors
        MyCollector(),
    ]
```
3. Register with scheduler in `scheduler.py` or via API

### Adding a New Model

1. Create or update in `app/models/`:
```python
from sqlalchemy import Column, String, UUID
from app.database import Base

class NewModel(Base):
    __tablename__ = "new_table"
    id = Column(UUID, primary_key=True)
    name = Column(String(255))
```
2. Create migration script in `app/scripts/`
3. Run migration or call `init_db()`

---

## Common Development Tasks

### Task: Add New News Source

```python
# In news_extraction_service.py, add to DEFAULT_SOURCES:
DEFAULT_SOURCES = [
    # ... existing sources
    {"url": "https://example.com/rss", "name": "Example News"},
]
```

### Task: Modify Entity Detection

```python
# In entity_tracker.py, modify _find_mentions_in_text():
def _find_mentions_in_text(self, text: str, entity_name: str) -> List[dict]:
    # Add custom matching logic
    # Return list of {context, position} dicts
```

### Task: Change Embedding Model

```python
# In document_processor.py:
EMBEDDING_MODEL = "text-embedding-3-small"  # or custom model
EMBEDDING_DIMENSIONS = 1536  # Update dimensions accordingly

# Update Qdrant collection if needed
```

### Task: Debug WebSocket Issues

```python
# In websocket/routes.py, add logging:
@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    logger.debug(f"WebSocket connection from {websocket.client}")
    # ... rest of handler
```

### Running the Application

```bash
# Start all services
./start_services.sh  # Starts Qdrant, Firecrawl

# Start the API server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Or use the helper script
./run_appcmd
```

---

## Important Files Quick Reference

| File | Purpose | When to Modify |
|------|---------|----------------|
| `app/main.py` | FastAPI app, routers | Adding routes, middleware |
| `app/database.py` | DB connection | Schema changes, connection settings |
| `app/core/config.py` | Settings | Adding config options |
| `app/core/dependencies.py` | DI, auth | Adding dependencies, auth changes |
| `app/core/logging.py` | File-based logging | Log levels, rotation, format |
| `app/services/claude_bridge.py` | **Claude Code CLI integration** | Claude behavior, session management |
| `app/services/local_embeddings.py` | **Local embeddings** | Embedding model, dimensions |
| `app/services/document_processor.py` | PDF handling | Chunking, embedding changes |
| `app/services/entity_tracker.py` | Entity detection | Mention detection, relationships |
| `app/services/news_extraction_service.py` | Scraping | Adding sources, parsing logic |
| `app/services/research_assistant.py` | LLM integration | Prompts, structured output |
| `app/models/*.py` | Database schema | Schema changes |
| `static/js/websocket.js` | Real-time comm | WebSocket message handling |
| `static/css/styles.css` | Styling | UI changes |

---

## Troubleshooting

### PostgreSQL Not Connecting

```bash
# Check PostgreSQL is running
sudo systemctl status postgresql

# Test connection
psql -U postgres -d research_platform

# Check DATABASE_URL in environment
echo $DATABASE_URL
```

### Qdrant Not Responding

```bash
# Start Qdrant
./startqdrant
# or
docker run -p 6333:6333 qdrant/qdrant

# Test connection
curl http://localhost:6333/collections
```

### Claude Code CLI Issues

```bash
# Check Claude Code is installed
~/.local/bin/claude --version

# Install Claude Code if missing
curl -fsSL https://claude.ai/install.sh | sh

# Login via browser (required for subscription auth)
~/.local/bin/claude

# Test a simple query
echo "Hello" | ~/.local/bin/claude -p - --output-format json

# IMPORTANT: If you have ANTHROPIC_API_KEY set, remove it to use subscription
unset ANTHROPIC_API_KEY
```

### Embedding Model Issues

```bash
# Test sentence-transformers installation
python -c "from sentence_transformers import SentenceTransformer; print('OK')"

# Install if missing
pip install sentence-transformers>=2.2.0

# Test embedding generation
python -c "
from app.services.local_embeddings import LocalEmbeddings
import asyncio
async def test():
    e = LocalEmbeddings()
    v = await e.generate('test')
    print(f'Embedding dims: {len(v)}')
asyncio.run(test())
"
```

### WebSocket Connection Issues

```javascript
// In browser console, check:
console.log(window.wsManager.ws.readyState);
// 0=CONNECTING, 1=OPEN, 2=CLOSING, 3=CLOSED

// Check auth token
document.cookie  // Should contain auth_token
```

### Dashboard Entity Features Not Working

The dashboard uses an auto-created local user for auth-free operation. If entity features (Trending Entities, Relationship Graph) aren't working:

```bash
# Check if local user exists in database
psql -U postgres -d research_platform -c "SELECT * FROM users WHERE email = 'local@pulse.local';"

# If missing, the user will be auto-created on first API call to /entities
# Or manually create:
psql -U postgres -d research_platform -c "
INSERT INTO users (user_id, email, password_hash)
VALUES ('00000000-0000-0000-0000-000000000001', 'local@pulse.local', 'local')
ON CONFLICT (email) DO NOTHING;
"

# Check browser console for API errors
# The entities endpoint should be: /api/v1/entities (NOT /api/v1/entities/entities)
```

### Viewing Logs

```bash
# View real-time logs
tail -f logs/pulse.log

# View debug logs (verbose)
tail -f logs/pulse_debug.log

# View errors only
tail -f logs/pulse_errors.log

# Search logs for specific module
grep "entity_tracker" logs/pulse_debug.log
```

---

## Architecture Decisions

1. **Why FastAPI?** - Async-native, automatic OpenAPI docs, Pydantic integration
2. **Why PostgreSQL?** - JSONB support, async drivers, robust for relational data
3. **Why Qdrant?** - Purpose-built for vectors, good Python client, self-hostable
4. **Why Redis?** - Fast caching, session storage, pub/sub potential
5. **Why Claude Code CLI?** - Superior reasoning, subscription-based (no per-token cost), subprocess integration
6. **Why sentence-transformers?** - Free, local, no external API, GPU acceleration available
7. **Why vanilla JavaScript?** - Simplicity, no build step, easy to modify
8. **Why WebSocket?** - Real-time streaming for chat, server-push updates

### Migration Notes (2026-01-04)

**From Ollama to Claude Code:**
- Ollama required local GPU/CPU resources for inference
- Claude Code uses subscription auth (fixed monthly cost vs per-token)
- Subprocess approach avoids SDK dependency, works with existing subscription
- ANTHROPIC_API_KEY must NOT be set (would trigger per-token billing)

**From Ollama embeddings to sentence-transformers:**
- Same 768-dimension vectors (Qdrant collections remain compatible)
- Runs locally with no external API calls
- `all-mpnet-base-v2` model provides strong semantic similarity

### Network Graph Performance Architecture (2026-01-16)

The Network API (`/api/v1/network/graph`) uses a multi-layer caching strategy for sub-second response times on graphs with 1000+ nodes:

**Performance Metrics:**
```
Before:  54,473ms API response
After:   698ms API response (77x faster!)

Breakdown:
⚡ graph_load_ms: 290ms
⚡ export_cytoscape_ms: 191ms
⚡ compute_layout_ms: 0 (skipped for large graphs)
⚡ compute_clusters_ms: 118ms
```

**Caching Layers (app/api/v1/network/routes.py):**

| Cache | TTL | Purpose |
|-------|-----|---------|
| `GraphCache` | 5 min | NetworkMapperService instance (graph structure) |
| `LayoutCache` | 5 min | Computed layout positions (deterministic with seed=42) |
| `ClusterCache` | 10 min | Community detection results |

**Key Optimizations:**
1. **SERV-009: Layout Skip** - Graphs >500 nodes skip server-side layout (client FA2 Web Worker handles it)
2. **Dynamic Iterations** - Large graphs use fewer layout iterations (30/50/100 based on node count)
3. **Label Propagation** - Used for community detection on graphs >1000 nodes (O(n) vs O(n log² n))
4. **Fixed Double Layout Bug** - Was computing layout twice when positions AND clusters requested

**Cache Invalidation:**
- Caches auto-invalidate when relationships are added via `/relationships` or `/discover` endpoints
- Manual invalidation: `POST /api/v1/network/cache/invalidate`
- Cache status: `GET /api/v1/network/cache/status`

**Key Code Locations:**
```
app/api/v1/network/routes.py:
  89-157    - LayoutCache class
  162-225   - ClusterCache class
  309-345   - SERV-009 layout skip logic (>500 nodes)
  745-798   - Cache status endpoints

app/services/network_mapper/graph_service.py:
  762-770   - Dynamic iteration count
  830-841   - Label Propagation selection (>1000 nodes)

static/js/pulse-dashboard.js:
  ~3969-3980 - Fixed switchView() double API call
```

**Client-Side (FA2 Web Worker):**
The client uses ForceAtlas2 in a Web Worker for non-blocking layout refinement:
- `static/js/fa2layout.bundle.js` - Bundled Web Worker
- `static/js/pulse-dashboard.js` - FA2WorkerManager class
- Progressive layout with batched refresh (every 50 iterations)
- Performance settings: `hideEdgesOnMove`, `gpuLayout`

### Task: Add a New RSS Feed

```python
# In collectors/config.py, add to RSS_FEEDS dict:
RSS_FEEDS = {
    # ... existing feeds
    "new_source": "https://example.com/rss",
}

# Add category mapping:
RSS_CATEGORY_MAP = {
    # ... existing mappings
    "new_source": "tech_general",  # or appropriate category
}
```

### Task: Trigger Manual Collection

```bash
# Via API
curl -X POST http://localhost:8000/api/v1/collection/run

# Run specific collector
curl -X POST "http://localhost:8000/api/v1/collection/run?collector_name=RSS%20Feeds"

# Check status
curl http://localhost:8000/api/v1/collection/status
```

---

## SIGINT Dashboard

The Pulse includes a SIGINT-themed intelligence dashboard accessible at `/dashboard`.

### Dashboard Features

| Feature | Description |
|---------|-------------|
| Briefing View | Display and interact with generated intelligence briefings |
| Collection Status | Real-time monitoring of all content collectors |
| **Network View** | Full-viewport Sigma.js + graphology WebGL graph with server-side layout, zoom controls, fullscreen modal |
| **Entity List View** | Paginated entity table with search, filter, sort, and bulk actions |
| News Feed | Filterable feed of collected items with relevance scores |
| Semantic Search | Vector-based search across the knowledge base |
| Audio Player | Listen to TTS-generated audio briefings |
| Activity Timeline | Real-time log of system events |
| Quick Actions | One-click collection, processing, and briefing generation |

### Dashboard Navigation

| Nav Item | View ID | Description |
|----------|---------|-------------|
| Briefing | `view-briefing` | Intelligence briefings |
| Feed | `view-feed` | News feed |
| Network | `view-entities` | Entity relationship graph (full viewport height) |
| Entities | `view-entity-list` | Entity list with bulk operations |
| Research | `view-research` | Semantic search |

### Dashboard Files

| File | Purpose |
|------|---------|
| `static/css/sigint-theme.css` | Military-grade dark theme with cyan/amber accents |
| `templates/dashboard.html` | 3-column grid layout with panels |
| `static/js/pulse-dashboard.js` | Dashboard controller with WebSocket integration |

### Accessing the Dashboard

```bash
# Start the server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Open in browser
# Original interface: http://localhost:8000/
# SIGINT Dashboard: http://localhost:8000/dashboard
```

---

*Last updated: 2026-01-16 (Server-Side Network API Optimization - 77x latency improvement)*
