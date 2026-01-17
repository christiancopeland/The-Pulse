"""
Synthesis services for The Pulse.

Phase 4 & 5: Synthesis Engine

This module provides:
- SYNTH-001: Context Builder - Builds entity and temporal context
- SYNTH-002: Briefing Generator - Generates daily intelligence briefings
- SYNTH-003: Entity-Aware Prompts - Context-rich LLM prompts
- SYNTH-004: Audio Generator - Piper TTS integration
- SYNTH-005: Briefing Archive - Stores and retrieves past briefings
- SYNTH-006: Tiered Briefing - Intelligence tiers with "So What?" analysis
- SYNTH-007: Pattern Detection - Automatic pattern and trend detection
- SYNTH-008: Trend Indicators - 6-month rolling trend tracking (Phase 5)
"""
# Core context building
from app.services.synthesis.context_builder import ContextBuilder

# Legacy-compatible briefing interface (wraps tiered system)
from app.services.synthesis.briefing_generator import (
    BriefingGenerator,
    Briefing,
    BriefingSection,
    convert_tiered_to_legacy,
)

# New tiered briefing system (preferred for new code)
from app.services.synthesis.tiered_briefing import (
    TieredBriefingGenerator,
    TieredBriefing,
    TieredBriefingSection,
    TieredBriefingItem,
    IntelligenceTier,
    SoWhatAnalysis,
    PatternAlert,
    TOPIC_TIER_MAP,
)

# Pattern detection
from app.services.synthesis.pattern_detector import (
    PatternDetector,
    PatternType,
    DetectedPattern,
)

# Trend indicators (Phase 5)
from app.services.synthesis.trend_indicators import (
    TrendIndicatorService,
    TrendIndicator,
    TrendSnapshot,
    TrendDirection,
    AlertLevel,
)

# Audio and archive
from app.services.synthesis.audio_generator import AudioGenerator
from app.services.synthesis.briefing_archive import BriefingArchive

__all__ = [
    # Context
    "ContextBuilder",

    # Legacy interface (backward compatible)
    "BriefingGenerator",
    "Briefing",
    "BriefingSection",
    "convert_tiered_to_legacy",

    # Tiered system (preferred)
    "TieredBriefingGenerator",
    "TieredBriefing",
    "TieredBriefingSection",
    "TieredBriefingItem",
    "IntelligenceTier",
    "SoWhatAnalysis",
    "PatternAlert",
    "TOPIC_TIER_MAP",

    # Pattern detection
    "PatternDetector",
    "PatternType",
    "DetectedPattern",

    # Trend indicators (Phase 5)
    "TrendIndicatorService",
    "TrendIndicator",
    "TrendSnapshot",
    "TrendDirection",
    "AlertLevel",

    # Audio and archive
    "AudioGenerator",
    "BriefingArchive",
]
