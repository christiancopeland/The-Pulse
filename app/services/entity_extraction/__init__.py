"""
Entity Extraction Module for The Pulse.

Phase 4 Implementation: Advanced entity extraction and linking.

Components:
- GLiNER Extractor: Zero-shot NER for intelligence-specific entity types
- WikiData Linker: Entity disambiguation to canonical WikiData IDs
- Auto Extractor: Automated extraction and tracking pipeline

Usage:
    from app.services.entity_extraction import (
        IntelligenceEntityExtractor,
        WikiDataLinker,
        AutoEntityExtractor,
        ExtractedEntity,
        LinkedEntity
    )

    # Extract entities from text
    extractor = IntelligenceEntityExtractor()
    entities = extractor.extract("Vladimir Putin met with Xi Jinping in Moscow...")

    # Link entities to WikiData
    linker = WikiDataLinker()
    linked = await linker.link_entity("Vladimir Putin", entity_type="PERSON")

    # Auto-extract and track from news items
    auto = AutoEntityExtractor(db_session, user_id)
    result = await auto.extract_from_news_item(item_id, auto_track=True)
"""

from .gliner_extractor import (
    IntelligenceEntityExtractor,
    ExtractedEntity,
    INTEL_ENTITY_TYPES,
    EXTENDED_ENTITY_TYPES,
    extract_entities
)

from .wikidata_linker import (
    WikiDataLinker,
    LinkedEntity,
    link_entity
)

from .auto_extractor import (
    AutoEntityExtractor,
    ExtractionResult,
    BatchExtractionResult
)

__all__ = [
    # GLiNER Extractor
    "IntelligenceEntityExtractor",
    "ExtractedEntity",
    "INTEL_ENTITY_TYPES",
    "EXTENDED_ENTITY_TYPES",
    "extract_entities",
    # WikiData Linker
    "WikiDataLinker",
    "LinkedEntity",
    "link_entity",
    # Auto Extractor
    "AutoEntityExtractor",
    "ExtractionResult",
    "BatchExtractionResult",
]
