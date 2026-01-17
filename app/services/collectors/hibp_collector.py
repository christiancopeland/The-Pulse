"""
Have I Been Pwned collector for The Pulse.

Monitors for new data breaches and compromised credential databases:
- Recent breach additions
- Breach metadata (affected accounts, data types)
- Sensitive breach flags

API Documentation: https://haveibeenpwned.com/API/v3
Requires paid API key ($3.50/mo) from https://haveibeenpwned.com/API/Key
Rate limit: 10 requests per minute.
"""
import asyncio
import aiohttp
import os
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Dict, Any
import logging

from .base import BaseCollector, CollectedItem
from .config import API_TIMEOUT_SECONDS

logger = logging.getLogger(__name__)


class HIBPCollector(BaseCollector):
    """
    Have I Been Pwned API collector for breach monitoring.

    Features:
    - Fetches recently added breaches
    - Extracts breach metadata and data types
    - Identifies sensitive breaches
    - Community-standard breach intelligence

    Requires API key ($3.50/mo) from https://haveibeenpwned.com/API/Key
    Rate limit: 10 requests/minute
    """

    API_BASE = "https://haveibeenpwned.com/api/v3"

    def __init__(
        self,
        api_key: Optional[str] = None,
        days_back: int = 30,
    ):
        """
        Initialize HIBP collector.

        Args:
            api_key: HIBP API key ($3.50/mo from https://haveibeenpwned.com/API/Key)
            days_back: Only report breaches added in last N days
        """
        super().__init__()
        self.api_key = api_key or os.getenv("HIBP_API_KEY")
        self.days_back = days_back

        if not self.api_key:
            self._logger.warning(
                "HIBP_API_KEY not set - collector will be disabled. "
                "Get key at https://haveibeenpwned.com/API/Key ($3.50/mo)"
            )

    @property
    def name(self) -> str:
        return "Have I Been Pwned"

    @property
    def source_type(self) -> str:
        return "hibp"

    def _get_headers(self) -> Dict[str, str]:
        """Get API request headers."""
        return {
            "hibp-api-key": self.api_key,
            "User-Agent": "ThePulse/1.0",
            "Accept": "application/json",
        }

    async def _fetch_all_breaches(
        self,
        session: aiohttp.ClientSession,
    ) -> List[Dict[str, Any]]:
        """Fetch all breaches from HIBP API."""
        breaches = []
        url = f"{self.API_BASE}/breaches"

        try:
            async with session.get(
                url,
                headers=self._get_headers(),
                timeout=aiohttp.ClientTimeout(total=API_TIMEOUT_SECONDS),
            ) as response:
                if response.status == 401:
                    self._logger.error("HIBP API key invalid")
                    return []
                elif response.status == 429:
                    self._logger.warning("HIBP rate limit exceeded")
                    return []
                elif response.status != 200:
                    self._logger.warning(f"HIBP returned status {response.status}")
                    return []

                breaches = await response.json()
                self._logger.debug(f"HIBP: received {len(breaches)} total breaches")

        except asyncio.TimeoutError:
            self._logger.warning(f"HIBP timed out after {API_TIMEOUT_SECONDS}s")
        except Exception as e:
            self._logger.warning(f"HIBP error: {type(e).__name__}: {e}")

        return breaches

    def _breach_to_item(self, breach: Dict[str, Any]) -> Optional[CollectedItem]:
        """Convert HIBP breach to CollectedItem."""
        try:
            name = breach.get("Name", "")
            title = breach.get("Title", name)
            description = breach.get("Description", "")
            domain = breach.get("Domain", "")

            # Parse dates
            breach_date = breach.get("BreachDate", "")
            added_date = breach.get("AddedDate", "")

            if added_date:
                try:
                    published = datetime.fromisoformat(added_date.replace("Z", "+00:00"))
                except ValueError:
                    published = datetime.now(timezone.utc)
            else:
                published = datetime.now(timezone.utc)

            # Extract metadata
            pwn_count = breach.get("PwnCount", 0)
            data_classes = breach.get("DataClasses", [])
            is_verified = breach.get("IsVerified", False)
            is_sensitive = breach.get("IsSensitive", False)
            is_fabricated = breach.get("IsFabricated", False)
            is_spam_list = breach.get("IsSpamList", False)

            # Skip fabricated or spam list breaches
            if is_fabricated or is_spam_list:
                return None

            # Build summary
            summary_parts = []
            if pwn_count:
                summary_parts.append(f"{pwn_count:,} accounts")
            if data_classes:
                summary_parts.append(f"Data: {', '.join(data_classes[:5])}")
            if is_verified:
                summary_parts.append("Verified")
            if is_sensitive:
                summary_parts.append("SENSITIVE")

            summary = " | ".join(summary_parts) if summary_parts else description[:500]

            # Build URL
            url = f"https://haveibeenpwned.com/PwnedWebsites#{name}"

            return CollectedItem(
                source="hibp",
                source_name="Have I Been Pwned",
                source_url=self.API_BASE,
                category="cyber",
                title=f"Breach: {title}",
                summary=self.truncate_text(summary, 500),
                url=url,
                published=published,
                raw_content=self.clean_text(description),
                metadata={
                    "breach_name": name,
                    "domain": domain,
                    "breach_date": breach_date,
                    "added_date": added_date,
                    "pwn_count": pwn_count,
                    "data_classes": data_classes,
                    "is_verified": is_verified,
                    "is_sensitive": is_sensitive,
                },
            )

        except Exception as e:
            self._logger.debug(f"Failed to parse HIBP breach: {e}")
            return None

    async def collect(self) -> List[CollectedItem]:
        """Fetch recent breaches from HIBP."""
        if not self.api_key:
            self._logger.warning("HIBP collection skipped - no API key configured")
            return []

        self._logger.info(f"Collecting from HIBP (last {self.days_back} days)")
        items = []

        # Calculate cutoff date
        cutoff = datetime.now(timezone.utc) - timedelta(days=self.days_back)

        async with aiohttp.ClientSession() as session:
            breaches = await self._fetch_all_breaches(session)

            for breach in breaches:
                # Filter by added date
                added_date = breach.get("AddedDate", "")
                if added_date:
                    try:
                        added = datetime.fromisoformat(added_date.replace("Z", "+00:00"))
                        if added < cutoff:
                            continue
                    except ValueError:
                        pass

                item = self._breach_to_item(breach)
                if item:
                    items.append(item)

        self._logger.info(f"HIBP collection complete: {len(items)} recent breaches")
        return items
