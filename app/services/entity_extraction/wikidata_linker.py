"""
WikiData Entity Linking Service.

Disambiguates extracted entities to canonical WikiData IDs for cross-source
matching and enrichment. Uses the WikiData Search API and SPARQL endpoint
for entity resolution and property retrieval.

Features:
- Fuzzy matching for entity names with disambiguation
- Type validation (person, organization, location)
- Property retrieval (birth date, headquarters, coordinates, etc.)
- Cross-reference to other databases (Wikipedia, GND, VIAF)
- Caching to reduce API calls
- Rate limiting to respect WikiData guidelines

All WikiData APIs are FREE and open.
"""

import asyncio
import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING
import aiohttp

from app.core.logging import get_logger

if TYPE_CHECKING:
    import redis

logger = get_logger(__name__)

# WikiData API endpoints
WIKIDATA_SEARCH_API = "https://www.wikidata.org/w/api.php"
WIKIDATA_SPARQL_ENDPOINT = "https://query.wikidata.org/sparql"

# Common WikiData type QIDs for filtering
WIKIDATA_TYPE_QIDS = {
    # Person types
    "Q5": "human",
    "Q15632617": "fictional human",
    # Organization types
    "Q43229": "organization",
    "Q4830453": "business",
    "Q783794": "company",
    "Q7278": "political party",
    "Q163740": "nonprofit organization",
    "Q484652": "international organization",
    "Q2659904": "government organization",
    # Location types
    "Q515": "city",
    "Q6256": "country",
    "Q35657": "state",
    "Q35120": "geographic location",
    "Q82794": "geographic region",
    # Military
    "Q176799": "military unit",
    "Q15627509": "military organization",
    # Other
    "Q1656682": "event",
    "Q131569": "treaty",
}

# Reverse mapping for type inference
TYPE_MAPPINGS = {
    "Q5": "PERSON",
    "Q15632617": "PERSON",
    "Q43229": "ORGANIZATION",
    "Q4830453": "ORGANIZATION",
    "Q783794": "ORGANIZATION",
    "Q7278": "POLITICAL_PARTY",
    "Q163740": "ORGANIZATION",
    "Q484652": "ORGANIZATION",
    "Q2659904": "GOVERNMENT_AGENCY",
    "Q515": "LOCATION",
    "Q6256": "LOCATION",
    "Q35657": "LOCATION",
    "Q35120": "LOCATION",
    "Q82794": "LOCATION",
    "Q176799": "MILITARY_UNIT",
    "Q15627509": "MILITARY_UNIT",
    "Q1656682": "EVENT",
    "Q131569": "TREATY",
}

# Useful WikiData properties
IMPORTANT_PROPERTIES = {
    "P31": "instance_of",        # What type of thing is this
    "P279": "subclass_of",       # Subclass relationship
    "P17": "country",            # Country
    "P131": "located_in",        # Administrative location
    "P625": "coordinates",       # Geographic coordinates
    "P569": "birth_date",        # Date of birth (for persons)
    "P570": "death_date",        # Date of death
    "P106": "occupation",        # Person's occupation
    "P39": "position_held",      # Political/official positions
    "P102": "member_of_party",   # Political party membership
    "P108": "employer",          # Current employer
    "P159": "headquarters",      # Headquarters location
    "P571": "inception",         # When was it founded
    "P576": "dissolved",         # When was it dissolved
    "P36": "capital",            # Capital city
    "P6": "head_of_government",  # Current leader
    "P35": "head_of_state",      # Head of state
    "P856": "official_website",  # Official website
    "P18": "image",              # Main image
}


@dataclass
class LinkedEntity:
    """
    An entity linked to WikiData.

    Attributes:
        original_text: The original extracted text
        wikidata_id: WikiData QID (e.g., Q76 for Barack Obama)
        label: Canonical name from WikiData
        description: WikiData description
        entity_type: Inferred type (PERSON, ORGANIZATION, etc.)
        aliases: Alternative names
        properties: Key WikiData properties
        confidence: Linking confidence score (0.0-1.0)
        wikipedia_url: Link to Wikipedia article if available
    """
    original_text: str
    wikidata_id: str
    label: str
    description: str
    entity_type: str
    aliases: List[str] = field(default_factory=list)
    properties: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0
    wikipedia_url: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "original_text": self.original_text,
            "wikidata_id": self.wikidata_id,
            "wikidata_url": f"https://www.wikidata.org/wiki/{self.wikidata_id}",
            "label": self.label,
            "description": self.description,
            "entity_type": self.entity_type,
            "aliases": self.aliases,
            "properties": self.properties,
            "confidence": self.confidence,
            "wikipedia_url": self.wikipedia_url,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "LinkedEntity":
        """Create LinkedEntity from dictionary representation."""
        return cls(
            original_text=data["original_text"],
            wikidata_id=data["wikidata_id"],
            label=data["label"],
            description=data["description"],
            entity_type=data["entity_type"],
            aliases=data.get("aliases", []),
            properties=data.get("properties", {}),
            confidence=data.get("confidence", 0.0),
            wikipedia_url=data.get("wikipedia_url"),
        )


class WikiDataLinker:
    """
    Links extracted entities to WikiData for disambiguation.

    Features:
    - Fuzzy matching for entity names
    - Type validation (filters results by expected type)
    - Property retrieval for enrichment
    - Cross-reference to other databases
    - Result caching to reduce API calls

    Usage:
        linker = WikiDataLinker()
        linked = await linker.link_entity("Vladimir Putin", entity_type="PERSON")
        if linked:
            print(f"WikiData ID: {linked.wikidata_id}")
            print(f"Description: {linked.description}")

        # Batch linking
        results = await linker.link_batch(["Putin", "Xi Jinping", "Moscow"])
    """

    USER_AGENT = "ThePulse/1.0 (https://github.com/thepulse; contact@example.com)"
    CACHE_TTL_HOURS = 24
    REQUEST_DELAY_MS = 500  # Rate limiting delay between requests (increased from 100ms)
    MAX_RETRIES = 3  # Maximum retries on 429 errors
    BACKOFF_MULTIPLIER = 2  # Exponential backoff multiplier
    REDIS_CACHE_PREFIX = "wikidata:entity:"
    REDIS_TTL_SECONDS = 86400  # 24 hours

    def __init__(
        self,
        cache_enabled: bool = True,
        max_cache_size: int = 10000,
        redis_client: Optional["redis.Redis"] = None
    ):
        """
        Initialize the WikiData linker.

        Args:
            cache_enabled: Enable result caching
            max_cache_size: Maximum number of cached results
            redis_client: Optional Redis client for persistent caching
        """
        self.cache_enabled = cache_enabled
        self.max_cache_size = max_cache_size
        self.redis_client = redis_client
        self._cache: Dict[str, Tuple[LinkedEntity, datetime]] = {}  # L1 in-memory cache
        self._last_request_time: Optional[datetime] = None

    async def _rate_limit(self) -> None:
        """Apply rate limiting between requests."""
        if self._last_request_time:
            elapsed = (datetime.now() - self._last_request_time).total_seconds() * 1000
            if elapsed < self.REQUEST_DELAY_MS:
                await asyncio.sleep((self.REQUEST_DELAY_MS - elapsed) / 1000)
        self._last_request_time = datetime.now()

    def _get_cache_key(self, entity_text: str, entity_type: Optional[str]) -> str:
        """Generate cache key for entity lookup."""
        key_str = f"{entity_text.lower()}:{entity_type or 'any'}"
        return hashlib.md5(key_str.encode()).hexdigest()

    def _check_cache(self, cache_key: str) -> Optional[LinkedEntity]:
        """Check cache for existing result. Checks L1 memory cache, then Redis."""
        if not self.cache_enabled:
            return None

        # L1: Check in-memory cache first (fastest)
        if cache_key in self._cache:
            result, timestamp = self._cache[cache_key]
            if datetime.now() - timestamp < timedelta(hours=self.CACHE_TTL_HOURS):
                return result
            else:
                del self._cache[cache_key]

        # L2: Check Redis cache if available
        if self.redis_client:
            try:
                redis_key = f"{self.REDIS_CACHE_PREFIX}{cache_key}"
                cached_data = self.redis_client.get(redis_key)
                if cached_data:
                    data = json.loads(cached_data)
                    result = LinkedEntity.from_dict(data)
                    # Populate L1 cache for faster subsequent lookups
                    self._cache[cache_key] = (result, datetime.now())
                    logger.debug(f"WikiData cache hit (Redis): {cache_key[:8]}...")
                    return result
            except Exception as e:
                logger.warning(f"Redis cache read error: {e}")

        return None

    def _update_cache(self, cache_key: str, result: LinkedEntity) -> None:
        """Update cache with new result. Writes to both L1 memory and Redis."""
        if not self.cache_enabled:
            return

        # L1: Update in-memory cache
        # Evict old entries if cache is full
        if len(self._cache) >= self.max_cache_size:
            # Remove oldest 10%
            sorted_keys = sorted(
                self._cache.keys(),
                key=lambda k: self._cache[k][1]
            )
            for key in sorted_keys[:len(sorted_keys) // 10]:
                del self._cache[key]

        self._cache[cache_key] = (result, datetime.now())

        # L2: Update Redis cache if available
        if self.redis_client:
            try:
                redis_key = f"{self.REDIS_CACHE_PREFIX}{cache_key}"
                data = result.to_dict()
                self.redis_client.setex(
                    redis_key,
                    self.REDIS_TTL_SECONDS,
                    json.dumps(data)
                )
                logger.debug(f"WikiData cache write (Redis): {cache_key[:8]}...")
            except Exception as e:
                logger.warning(f"Redis cache write error: {e}")

    async def link_entity(
        self,
        entity_text: str,
        entity_type: Optional[str] = None,
        min_confidence: float = 0.5
    ) -> Optional[LinkedEntity]:
        """
        Link an entity to WikiData.

        Args:
            entity_text: Entity name to link
            entity_type: Expected type (PERSON, ORGANIZATION, LOCATION, etc.)
            min_confidence: Minimum confidence threshold

        Returns:
            LinkedEntity if found and meets confidence threshold, None otherwise
        """
        if not entity_text or not entity_text.strip():
            return None

        entity_text = entity_text.strip()

        # Check cache
        cache_key = self._get_cache_key(entity_text, entity_type)
        cached = self._check_cache(cache_key)
        if cached:
            return cached

        await self._rate_limit()

        try:
            async with aiohttp.ClientSession() as session:
                # Search WikiData for entity
                candidates = await self._search_wikidata(session, entity_text)

                if not candidates:
                    logger.debug(f"No WikiData results for: {entity_text}")
                    return None

                # Filter by type if specified
                if entity_type:
                    candidates = await self._filter_by_type(
                        session, candidates, entity_type
                    )

                if not candidates:
                    logger.debug(f"No type-matching results for: {entity_text} ({entity_type})")
                    return None

                # Get best match
                best = candidates[0]
                wikidata_id = best.get("id")

                # Calculate confidence based on match quality
                confidence = self._calculate_confidence(entity_text, best)

                if confidence < min_confidence:
                    logger.debug(f"Low confidence ({confidence:.2f}) for: {entity_text}")
                    return None

                # Fetch detailed entity information
                details = await self._get_entity_details(session, wikidata_id)

                # Build LinkedEntity
                linked = LinkedEntity(
                    original_text=entity_text,
                    wikidata_id=wikidata_id,
                    label=best.get("label", entity_text),
                    description=best.get("description", ""),
                    entity_type=self._infer_type(details) or entity_type or "UNKNOWN",
                    aliases=details.get("aliases", []),
                    properties=details.get("properties", {}),
                    confidence=confidence,
                    wikipedia_url=details.get("wikipedia_url")
                )

                # Cache result
                self._update_cache(cache_key, linked)

                return linked

        except aiohttp.ClientError as e:
            logger.error(f"WikiData API error: {e}")
            return None
        except Exception as e:
            logger.error(f"WikiData linking failed for '{entity_text}': {e}")
            return None

    async def _search_wikidata(
        self,
        session: aiohttp.ClientSession,
        query: str,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Search WikiData for entities matching query with retry on rate limit."""
        params = {
            "action": "wbsearchentities",
            "search": query,
            "language": "en",
            "format": "json",
            "limit": limit,
            "type": "item"
        }

        headers = {"User-Agent": self.USER_AGENT}

        for attempt in range(self.MAX_RETRIES):
            async with session.get(
                WIKIDATA_SEARCH_API,
                params=params,
                headers=headers
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get("search", [])
                elif response.status == 429:
                    # Rate limited - exponential backoff
                    delay = self.REQUEST_DELAY_MS * (self.BACKOFF_MULTIPLIER ** attempt) / 1000
                    logger.warning(f"WikiData rate limited (429), retrying in {delay:.1f}s (attempt {attempt + 1}/{self.MAX_RETRIES})")
                    await asyncio.sleep(delay)
                else:
                    logger.warning(f"WikiData search returned {response.status}")
                    return []

        logger.warning(f"WikiData search failed after {self.MAX_RETRIES} retries for: {query}")
        return []

    async def _filter_by_type(
        self,
        session: aiohttp.ClientSession,
        candidates: List[Dict],
        expected_type: str
    ) -> List[Dict]:
        """Filter candidates by expected entity type."""
        # Get QIDs that match expected type
        matching_qids = {
            qid for qid, etype in TYPE_MAPPINGS.items()
            if etype == expected_type
        }

        if not matching_qids:
            return candidates  # No filter if type unknown

        filtered = []
        for candidate in candidates:
            wikidata_id = candidate.get("id")

            # Quick check via description for common types
            desc = candidate.get("description", "").lower()
            if expected_type == "PERSON" and any(
                term in desc for term in ["politician", "president", "leader", "born"]
            ):
                filtered.append(candidate)
                continue
            elif expected_type == "ORGANIZATION" and any(
                term in desc for term in ["company", "organization", "agency", "group"]
            ):
                filtered.append(candidate)
                continue
            elif expected_type == "LOCATION" and any(
                term in desc for term in ["city", "country", "capital", "region"]
            ):
                filtered.append(candidate)
                continue

            # Full type check via API (expensive, do sparingly)
            if len(filtered) < 3:  # Only check if we don't have enough matches
                details = await self._get_entity_details(session, wikidata_id)
                instance_of = details.get("properties", {}).get("instance_of", [])
                if any(qid in matching_qids for qid in instance_of):
                    filtered.append(candidate)

        return filtered if filtered else candidates[:3]  # Fallback to top 3

    async def _get_entity_details(
        self,
        session: aiohttp.ClientSession,
        wikidata_id: str
    ) -> Dict[str, Any]:
        """Get detailed entity information from WikiData."""
        params = {
            "action": "wbgetentities",
            "ids": wikidata_id,
            "languages": "en",
            "format": "json",
            "props": "labels|descriptions|aliases|claims|sitelinks"
        }

        headers = {"User-Agent": self.USER_AGENT}

        async with session.get(
            WIKIDATA_SEARCH_API,
            params=params,
            headers=headers
        ) as response:
            if response.status != 200:
                return {}

            data = await response.json()
            entity = data.get("entities", {}).get(wikidata_id, {})

            # Extract aliases
            aliases = [
                alias["value"]
                for alias in entity.get("aliases", {}).get("en", [])
            ]

            # Extract key properties
            claims = entity.get("claims", {})
            properties = {}

            # Instance of (P31)
            if "P31" in claims:
                properties["instance_of"] = [
                    claim.get("mainsnak", {}).get("datavalue", {}).get("value", {}).get("id")
                    for claim in claims["P31"]
                    if claim.get("mainsnak", {}).get("datavalue")
                ]

            # Country (P17)
            if "P17" in claims:
                claim = claims["P17"][0]
                country_id = claim.get("mainsnak", {}).get("datavalue", {}).get("value", {}).get("id")
                if country_id:
                    properties["country_qid"] = country_id

            # Coordinates (P625)
            if "P625" in claims:
                claim = claims["P625"][0]
                coords = claim.get("mainsnak", {}).get("datavalue", {}).get("value", {})
                if coords:
                    properties["coordinates"] = {
                        "latitude": coords.get("latitude"),
                        "longitude": coords.get("longitude")
                    }

            # Inception/founding date (P571)
            if "P571" in claims:
                claim = claims["P571"][0]
                time_value = claim.get("mainsnak", {}).get("datavalue", {}).get("value", {})
                if time_value:
                    properties["inception"] = time_value.get("time")

            # Official website (P856)
            if "P856" in claims:
                claim = claims["P856"][0]
                url = claim.get("mainsnak", {}).get("datavalue", {}).get("value")
                if url:
                    properties["website"] = url

            # Wikipedia URL
            wikipedia_url = None
            sitelinks = entity.get("sitelinks", {})
            if "enwiki" in sitelinks:
                title = sitelinks["enwiki"].get("title", "")
                wikipedia_url = f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}"

            return {
                "aliases": aliases,
                "properties": properties,
                "wikipedia_url": wikipedia_url
            }

    def _infer_type(self, details: Dict[str, Any]) -> Optional[str]:
        """Infer entity type from WikiData properties."""
        instance_of = details.get("properties", {}).get("instance_of", [])

        for qid in instance_of:
            if qid in TYPE_MAPPINGS:
                return TYPE_MAPPINGS[qid]

        return None

    def _calculate_confidence(
        self,
        query: str,
        result: Dict[str, Any]
    ) -> float:
        """Calculate confidence score for entity match."""
        label = result.get("label", "").lower()
        query_lower = query.lower()

        # Exact match
        if label == query_lower:
            return 0.95

        # Label contains query or vice versa
        if query_lower in label or label in query_lower:
            return 0.85

        # Partial match (check word overlap)
        query_words = set(query_lower.split())
        label_words = set(label.split())
        overlap = len(query_words & label_words)
        total = len(query_words | label_words)

        if total > 0:
            jaccard = overlap / total
            return 0.5 + (jaccard * 0.4)

        return 0.5

    async def link_batch(
        self,
        entities: List[str],
        entity_types: Optional[List[str]] = None,
        min_confidence: float = 0.5
    ) -> Dict[str, Optional[LinkedEntity]]:
        """
        Link multiple entities to WikiData.

        Args:
            entities: List of entity names to link
            entity_types: Optional list of expected types (same order as entities)
            min_confidence: Minimum confidence threshold

        Returns:
            Dict mapping entity text to LinkedEntity (or None if not found)
        """
        results = {}

        types = entity_types or [None] * len(entities)

        for entity, etype in zip(entities, types):
            try:
                result = await self.link_entity(entity, etype, min_confidence)
                results[entity] = result
            except Exception as e:
                logger.error(f"Failed to link '{entity}': {e}")
                results[entity] = None

            # Small delay between batch requests
            await asyncio.sleep(0.05)

        return results

    async def enrich_entity(
        self,
        linked: LinkedEntity
    ) -> LinkedEntity:
        """
        Enrich a linked entity with additional WikiData properties.

        Fetches more detailed information like:
        - Occupation (for persons)
        - Headquarters (for organizations)
        - Population (for locations)
        - etc.
        """
        # This would use SPARQL for complex queries
        # For now, return as-is
        return linked

    def clear_cache(self) -> None:
        """Clear the linking cache (both L1 memory and Redis)."""
        self._cache.clear()

        # Clear Redis cache if available
        if self.redis_client:
            try:
                # Find and delete all WikiData cache keys
                pattern = f"{self.REDIS_CACHE_PREFIX}*"
                keys = self.redis_client.keys(pattern)
                if keys:
                    self.redis_client.delete(*keys)
                    logger.info(f"Cleared {len(keys)} WikiData entries from Redis cache")
            except Exception as e:
                logger.warning(f"Failed to clear Redis cache: {e}")

    @property
    def cache_size(self) -> int:
        """Get current cache size (L1 memory only, for quick access)."""
        return len(self._cache)

    @property
    def redis_cache_size(self) -> int:
        """Get Redis cache size (WikiData entries only)."""
        if not self.redis_client:
            return 0
        try:
            pattern = f"{self.REDIS_CACHE_PREFIX}*"
            keys = self.redis_client.keys(pattern)
            return len(keys)
        except Exception:
            return 0


# Convenience function
async def link_entity(
    entity_text: str,
    entity_type: Optional[str] = None
) -> Optional[LinkedEntity]:
    """
    Quick entity linking function.

    Creates a new linker instance per call - for repeated use,
    instantiate WikiDataLinker directly.

    Args:
        entity_text: Entity name to link
        entity_type: Expected entity type

    Returns:
        LinkedEntity if found, None otherwise
    """
    linker = WikiDataLinker()
    return await linker.link_entity(entity_text, entity_type)
