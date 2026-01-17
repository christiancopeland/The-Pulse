"""
Synthesis API routes for The Pulse.

Provides endpoints for:
- Briefing generation
- Briefing retrieval and archival
- Audio briefing generation
"""
from app.api.v1.synthesis.routes import router

__all__ = ["router"]
