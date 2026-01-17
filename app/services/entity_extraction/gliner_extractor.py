"""
GLiNER-based Entity Extraction for Intelligence Applications.

Zero-shot Named Entity Recognition using GLiNER for domain-specific entity types.
Optimized for intelligence analysis with support for military, government, and
geopolitical entity categories.

Features:
- Zero-shot extraction (no training required for new entity types)
- Intelligence-specific entity taxonomy
- Batch processing for efficiency
- Confidence scoring
- Fallback to regex patterns when model unavailable
"""

import re
import asyncio
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Set
from datetime import datetime

from app.core.logging import get_logger

logger = get_logger(__name__)

# Lazy load GLiNER model to avoid import-time overhead
_model = None
_model_name = "urchade/gliner_large-v2.1"

# Intelligence-specific entity types
INTEL_ENTITY_TYPES = [
    "PERSON",                  # Individual people
    "ORGANIZATION",            # Companies, NGOs, groups
    "GOVERNMENT_AGENCY",       # Government bodies and agencies
    "MILITARY_UNIT",           # Military organizations and units
    "WEAPON_SYSTEM",           # Weapons, military equipment
    "LOCATION",                # Geographic locations
    "FINANCIAL_INSTRUMENT",    # Currencies, stocks, financial products
    "POLITICAL_PARTY",         # Political parties and movements
    "CRIMINAL_ORGANIZATION",   # Criminal groups, cartels, etc.
    "EVENT",                   # Named events (operations, incidents)
    "DATE",                    # Dates and time references
]

# Extended entity types for specialized analysis
EXTENDED_ENTITY_TYPES = INTEL_ENTITY_TYPES + [
    "TREATY",                  # International agreements
    "SANCTION",                # Sanctions programs/designations
    "INFRASTRUCTURE",          # Critical infrastructure
    "TECHNOLOGY",              # Tech systems, platforms
    "IDEOLOGY",                # Political/religious ideologies
]

# Regex patterns for fallback extraction when GLiNER unavailable
FALLBACK_PATTERNS = {
    "DATE": [
        r'\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b',
        r'\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}\b',
        r'\b\d{4}-\d{2}-\d{2}\b',
    ],
    "FINANCIAL_INSTRUMENT": [
        r'\$\d+(?:\.\d+)?(?:\s*(?:million|billion|trillion|M|B|T))?\b',
        r'\b\d+(?:\.\d+)?\s*(?:USD|EUR|GBP|CNY|RUB|JPY)\b',
    ],
    "MILITARY_UNIT": [
        r'\b(?:\d+(?:st|nd|rd|th)\s+)?(?:Army|Division|Brigade|Battalion|Regiment|Squadron|Fleet)\b',
        r'\bUSS\s+[A-Z][a-z]+\b',
        r'\b(?:NATO|NORAD|CENTCOM|EUCOM|INDOPACOM)\b',
    ],
    "GOVERNMENT_AGENCY": [
        r'\b(?:FBI|CIA|NSA|DHS|DOD|DOJ|State Department|Pentagon|Kremlin|Politburo)\b',
        r'\b(?:Ministry of (?:Defense|Foreign Affairs|Interior|Finance))\b',
    ],
}


@dataclass
class ExtractedEntity:
    """
    An extracted entity with metadata.

    Attributes:
        text: The extracted entity text
        entity_type: Classification (PERSON, ORGANIZATION, etc.)
        start: Character offset start position
        end: Character offset end position
        confidence: Extraction confidence score (0.0-1.0)
        source: Extraction method ('gliner' or 'regex')
        normalized: Normalized/cleaned version of text
        context: Surrounding text context (optional)
    """
    text: str
    entity_type: str
    start: int
    end: int
    confidence: float
    source: str = "gliner"
    normalized: Optional[str] = None
    context: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Normalize text after initialization."""
        if self.normalized is None:
            self.normalized = self._normalize_text(self.text)

    @staticmethod
    def _normalize_text(text: str) -> str:
        """Normalize entity text for matching."""
        # Remove extra whitespace
        normalized = " ".join(text.split())
        # Remove leading/trailing punctuation
        normalized = normalized.strip(".,;:!?\"'()[]{}").strip()
        return normalized

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "text": self.text,
            "entity_type": self.entity_type,
            "start": self.start,
            "end": self.end,
            "confidence": self.confidence,
            "source": self.source,
            "normalized": self.normalized,
            "context": self.context,
            "metadata": self.metadata,
        }


class IntelligenceEntityExtractor:
    """
    Hybrid NER for intelligence applications.

    Uses GLiNER for zero-shot extraction of domain-specific entities,
    with regex fallback for reliability when model unavailable.

    Entity Types:
    - PERSON: Individual people (leaders, officials, analysts)
    - ORGANIZATION: Companies, NGOs, advocacy groups
    - GOVERNMENT_AGENCY: Government bodies (CIA, Pentagon, etc.)
    - MILITARY_UNIT: Military organizations and units
    - WEAPON_SYSTEM: Weapons, military equipment, platforms
    - LOCATION: Geographic locations (countries, cities, regions)
    - FINANCIAL_INSTRUMENT: Currencies, stocks, financial products
    - POLITICAL_PARTY: Political parties and movements
    - CRIMINAL_ORGANIZATION: Criminal groups, cartels
    - EVENT: Named events, operations, incidents
    - DATE: Dates and time references

    Usage:
        extractor = IntelligenceEntityExtractor()
        entities = extractor.extract("Putin met with Xi in Moscow on January 15.")

        # Async batch processing
        results = await extractor.extract_batch_async(texts)
    """

    DEFAULT_THRESHOLD = 0.5
    DEFAULT_MODEL = "urchade/gliner_large-v2.1"
    CONTEXT_WINDOW = 50  # Characters of context on each side

    def __init__(
        self,
        model_name: Optional[str] = None,
        entity_types: Optional[List[str]] = None,
        use_fallback: bool = True,
        cache_enabled: bool = True
    ):
        """
        Initialize the entity extractor.

        Args:
            model_name: GLiNER model to use (default: gliner_large-v2.1)
            entity_types: Entity types to extract (default: INTEL_ENTITY_TYPES)
            use_fallback: Whether to use regex fallback when model unavailable
            cache_enabled: Enable result caching for repeated texts
        """
        self.model_name = model_name or self.DEFAULT_MODEL
        self.entity_types = entity_types or INTEL_ENTITY_TYPES
        self.use_fallback = use_fallback
        self.cache_enabled = cache_enabled

        self._model = None
        self._model_loaded = False
        self._cache: Dict[str, List[ExtractedEntity]] = {}

        # Try to load model on init
        self._load_model()

    def _load_model(self) -> bool:
        """
        Lazy load GLiNER model.

        Returns:
            True if model loaded successfully, False otherwise.
        """
        global _model

        if self._model_loaded:
            return self._model is not None

        if _model is not None:
            self._model = _model
            self._model_loaded = True
            return True

        try:
            from gliner import GLiNER
            logger.info(f"Loading GLiNER model: {self.model_name}")
            _model = GLiNER.from_pretrained(self.model_name)
            self._model = _model
            self._model_loaded = True
            logger.info("GLiNER model loaded successfully")
            return True

        except ImportError:
            logger.warning(
                "GLiNER not installed. Run: pip install gliner\n"
                "Falling back to regex-based extraction."
            )
            self._model_loaded = True
            return False

        except Exception as e:
            logger.error(f"Failed to load GLiNER model: {e}")
            self._model_loaded = True
            return False

    def extract(
        self,
        text: str,
        entity_types: Optional[List[str]] = None,
        threshold: float = DEFAULT_THRESHOLD,
        include_context: bool = False
    ) -> List[ExtractedEntity]:
        """
        Extract entities from text.

        Args:
            text: Text to analyze
            entity_types: Entity types to extract (overrides default)
            threshold: Confidence threshold for GLiNER (0.0-1.0)
            include_context: Include surrounding context in results

        Returns:
            List of extracted entities sorted by position
        """
        if not text or not text.strip():
            return []

        # Check cache
        cache_key = f"{text[:100]}_{threshold}_{','.join(entity_types or self.entity_types)}"
        if self.cache_enabled and cache_key in self._cache:
            return self._cache[cache_key]

        types = entity_types or self.entity_types
        entities: List[ExtractedEntity] = []

        # Try GLiNER extraction
        if self._model is not None:
            try:
                predictions = self._model.predict_entities(
                    text,
                    types,
                    threshold=threshold
                )

                for pred in predictions:
                    entity = ExtractedEntity(
                        text=pred["text"],
                        entity_type=pred["label"],
                        start=pred["start"],
                        end=pred["end"],
                        confidence=pred["score"],
                        source="gliner"
                    )

                    if include_context:
                        entity.context = self._extract_context(text, pred["start"], pred["end"])

                    entities.append(entity)

            except Exception as e:
                logger.error(f"GLiNER extraction failed: {e}")
                # Fall through to fallback

        # Apply fallback patterns if enabled and needed
        if self.use_fallback and (not entities or self._model is None):
            fallback_entities = self._extract_with_fallback(text, types, include_context)

            # Merge results, avoiding duplicates
            existing_spans = {(e.start, e.end) for e in entities}
            for fe in fallback_entities:
                if (fe.start, fe.end) not in existing_spans:
                    entities.append(fe)

        # Sort by position
        entities.sort(key=lambda e: e.start)

        # Deduplicate overlapping entities (keep higher confidence)
        entities = self._deduplicate_overlapping(entities)

        # Cache results
        if self.cache_enabled:
            self._cache[cache_key] = entities

        return entities

    def _extract_with_fallback(
        self,
        text: str,
        entity_types: List[str],
        include_context: bool = False
    ) -> List[ExtractedEntity]:
        """Extract entities using regex fallback patterns."""
        entities = []

        for entity_type in entity_types:
            patterns = FALLBACK_PATTERNS.get(entity_type, [])

            for pattern in patterns:
                try:
                    for match in re.finditer(pattern, text, re.IGNORECASE):
                        entity = ExtractedEntity(
                            text=match.group(),
                            entity_type=entity_type,
                            start=match.start(),
                            end=match.end(),
                            confidence=0.7,  # Fixed confidence for regex
                            source="regex"
                        )

                        if include_context:
                            entity.context = self._extract_context(text, match.start(), match.end())

                        entities.append(entity)

                except re.error as e:
                    logger.warning(f"Invalid regex pattern for {entity_type}: {e}")

        return entities

    def _extract_context(self, text: str, start: int, end: int) -> str:
        """Extract surrounding context for an entity."""
        context_start = max(0, start - self.CONTEXT_WINDOW)
        context_end = min(len(text), end + self.CONTEXT_WINDOW)

        context = text[context_start:context_end]

        # Add ellipsis if truncated
        if context_start > 0:
            context = "..." + context
        if context_end < len(text):
            context = context + "..."

        return context

    def _deduplicate_overlapping(
        self,
        entities: List[ExtractedEntity]
    ) -> List[ExtractedEntity]:
        """Remove overlapping entities, keeping highest confidence."""
        if not entities:
            return []

        # Sort by start position, then by length (longer first)
        entities.sort(key=lambda e: (e.start, -(e.end - e.start)))

        result = []
        last_end = -1

        for entity in entities:
            # If this entity doesn't overlap with previous
            if entity.start >= last_end:
                result.append(entity)
                last_end = entity.end
            # If overlapping, keep if higher confidence
            elif result and entity.confidence > result[-1].confidence:
                result[-1] = entity
                last_end = entity.end

        return result

    def extract_batch(
        self,
        texts: List[str],
        entity_types: Optional[List[str]] = None,
        threshold: float = DEFAULT_THRESHOLD,
        include_context: bool = False
    ) -> List[List[ExtractedEntity]]:
        """
        Extract entities from multiple texts.

        Args:
            texts: List of texts to analyze
            entity_types: Entity types to extract
            threshold: Confidence threshold
            include_context: Include surrounding context

        Returns:
            List of entity lists, one per input text
        """
        return [
            self.extract(text, entity_types, threshold, include_context)
            for text in texts
        ]

    async def extract_async(
        self,
        text: str,
        entity_types: Optional[List[str]] = None,
        threshold: float = DEFAULT_THRESHOLD,
        include_context: bool = False
    ) -> List[ExtractedEntity]:
        """
        Async wrapper for extract().

        Runs extraction in thread pool to avoid blocking event loop.
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            lambda: self.extract(text, entity_types, threshold, include_context)
        )

    async def extract_batch_async(
        self,
        texts: List[str],
        entity_types: Optional[List[str]] = None,
        threshold: float = DEFAULT_THRESHOLD,
        include_context: bool = False
    ) -> List[List[ExtractedEntity]]:
        """
        Async batch extraction.

        Processes texts in parallel using thread pool.
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            lambda: self.extract_batch(texts, entity_types, threshold, include_context)
        )

    def get_entity_type_stats(
        self,
        entities: List[ExtractedEntity]
    ) -> Dict[str, int]:
        """Get count of entities by type."""
        stats: Dict[str, int] = {}
        for entity in entities:
            stats[entity.entity_type] = stats.get(entity.entity_type, 0) + 1
        return stats

    def filter_by_type(
        self,
        entities: List[ExtractedEntity],
        entity_types: List[str]
    ) -> List[ExtractedEntity]:
        """Filter entities by type."""
        return [e for e in entities if e.entity_type in entity_types]

    def filter_by_confidence(
        self,
        entities: List[ExtractedEntity],
        min_confidence: float
    ) -> List[ExtractedEntity]:
        """Filter entities by minimum confidence."""
        return [e for e in entities if e.confidence >= min_confidence]

    def clear_cache(self) -> None:
        """Clear the extraction cache."""
        self._cache.clear()

    @property
    def is_model_loaded(self) -> bool:
        """Check if GLiNER model is loaded."""
        return self._model is not None

    @property
    def available_entity_types(self) -> List[str]:
        """Get list of available entity types."""
        return self.entity_types.copy()


# Convenience function for quick extraction
def extract_entities(
    text: str,
    entity_types: Optional[List[str]] = None,
    threshold: float = 0.5
) -> List[ExtractedEntity]:
    """
    Quick entity extraction function.

    Creates a new extractor instance per call - for repeated use,
    instantiate IntelligenceEntityExtractor directly.

    Args:
        text: Text to analyze
        entity_types: Entity types to extract
        threshold: Confidence threshold

    Returns:
        List of extracted entities
    """
    extractor = IntelligenceEntityExtractor()
    return extractor.extract(text, entity_types, threshold)
