"""
Shodan collector for The Pulse.

Collects internet-exposed device and vulnerability data from Shodan:
- Vulnerable services
- Exposed devices
- Infrastructure scanning results
- CVE associations

API Documentation: https://developer.shodan.io/api
Requires paid API key ($60-500/mo depending on tier).
"""
import asyncio
import aiohttp
import os
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
import logging

from .base import BaseCollector, CollectedItem
from .config import API_TIMEOUT_SECONDS

logger = logging.getLogger(__name__)


class ShodanCollector(BaseCollector):
    """
    Shodan API collector for infrastructure vulnerability intelligence.

    Features:
    - Monitors saved searches/alerts
    - Fetches recently discovered vulnerable devices
    - Extracts CVE associations
    - Geolocation and organization data

    Requires paid API key from https://account.shodan.io/
    """

    API_BASE = "https://api.shodan.io"

    # Default vulnerability searches
    DEFAULT_QUERIES = [
        "vuln:CVE-2024",  # Recent CVEs
        "port:3389 has_vuln:true",  # Vulnerable RDP
        "port:22 has_vuln:true",  # Vulnerable SSH
        "product:elasticsearch",  # Exposed databases
        "product:mongodb",
        "http.title:\"Dashboard\" has_vuln:true",  # Vulnerable dashboards
    ]

    def __init__(
        self,
        api_key: Optional[str] = None,
        queries: Optional[List[str]] = None,
        max_results: int = 20,
    ):
        """
        Initialize Shodan collector.

        Args:
            api_key: Shodan API key (paid tier required for searches)
            queries: List of Shodan search queries
            max_results: Maximum results per query
        """
        super().__init__()
        self.api_key = api_key or os.getenv("SHODAN_API_KEY")
        self.queries = queries or self.DEFAULT_QUERIES[:3]  # Limit default queries
        self.max_results = max_results

        if not self.api_key:
            self._logger.warning(
                "SHODAN_API_KEY not set - collector will be disabled. "
                "Get API key at https://account.shodan.io/"
            )

    @property
    def name(self) -> str:
        return "Shodan"

    @property
    def source_type(self) -> str:
        return "shodan"

    async def _search(
        self,
        session: aiohttp.ClientSession,
        query: str,
    ) -> List[Dict[str, Any]]:
        """Execute a Shodan search query."""
        results = []
        url = f"{self.API_BASE}/shodan/host/search"
        params = {
            "key": self.api_key,
            "query": query,
            "minify": "true",
        }

        try:
            async with session.get(
                url,
                params=params,
                timeout=aiohttp.ClientTimeout(total=API_TIMEOUT_SECONDS),
            ) as response:
                if response.status == 401:
                    self._logger.error("Shodan API key invalid")
                    return []
                elif response.status == 402:
                    self._logger.warning("Shodan query requires paid tier")
                    return []
                elif response.status == 429:
                    self._logger.warning("Shodan rate limit exceeded")
                    return []
                elif response.status != 200:
                    self._logger.debug(f"Shodan search returned {response.status}")
                    return []

                data = await response.json()
                matches = data.get("matches", [])[:self.max_results]
                self._logger.debug(f"Shodan query '{query}': {len(matches)} results")
                return matches

        except asyncio.TimeoutError:
            self._logger.warning(f"Shodan search timed out")
        except Exception as e:
            self._logger.warning(f"Shodan error: {type(e).__name__}: {e}")

        return results

    def _match_to_item(self, match: Dict[str, Any], query: str) -> Optional[CollectedItem]:
        """Convert Shodan match to CollectedItem."""
        try:
            ip = match.get("ip_str", "")
            port = match.get("port", 0)
            transport = match.get("transport", "tcp")

            # Get service info
            product = match.get("product", "")
            version = match.get("version", "")
            os_info = match.get("os", "")

            # Get organization
            org = match.get("org", "")
            asn = match.get("asn", "")

            # Get location
            location = match.get("location", {})
            country = location.get("country_name", "")
            city = location.get("city", "")

            # Get vulnerabilities
            vulns = match.get("vulns", {})
            vuln_list = list(vulns.keys()) if vulns else []

            # Get timestamp
            timestamp = match.get("timestamp")
            if timestamp:
                try:
                    published = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                except ValueError:
                    published = datetime.now(timezone.utc)
            else:
                published = datetime.now(timezone.utc)

            # Build title
            service_name = product or f"port {port}"
            title = f"Exposed: {service_name} on {ip}:{port}"

            # Build summary
            summary_parts = []
            if org:
                summary_parts.append(f"Org: {org}")
            if country:
                summary_parts.append(f"Location: {city}, {country}" if city else country)
            if vuln_list:
                summary_parts.append(f"Vulns: {', '.join(vuln_list[:3])}")
            if os_info:
                summary_parts.append(f"OS: {os_info}")

            summary = " | ".join(summary_parts) if summary_parts else f"{ip}:{port}"

            return CollectedItem(
                source="shodan",
                source_name="Shodan",
                source_url=self.API_BASE,
                category="cyber",
                title=title,
                summary=self.truncate_text(summary, 500),
                url=f"https://www.shodan.io/host/{ip}",
                published=published,
                metadata={
                    "ip": ip,
                    "port": port,
                    "transport": transport,
                    "product": product,
                    "version": version,
                    "os": os_info,
                    "organization": org,
                    "asn": asn,
                    "country": country,
                    "city": city,
                    "vulns": vuln_list,
                    "query": query,
                    "tags": match.get("tags", []),
                },
            )

        except Exception as e:
            self._logger.debug(f"Failed to parse Shodan match: {e}")
            return None

    async def collect(self) -> List[CollectedItem]:
        """Fetch exposed devices from Shodan."""
        if not self.api_key:
            self._logger.warning("Shodan collection skipped - no API key configured")
            return []

        self._logger.info(f"Collecting from Shodan ({len(self.queries)} queries)")
        items = []
        seen_ips = set()

        async with aiohttp.ClientSession() as session:
            for query in self.queries:
                matches = await self._search(session, query)

                for match in matches:
                    ip = match.get("ip_str", "")
                    port = match.get("port", 0)
                    key = f"{ip}:{port}"

                    # Deduplicate
                    if key in seen_ips:
                        continue
                    seen_ips.add(key)

                    item = self._match_to_item(match, query)
                    if item:
                        items.append(item)

                # Rate limit between queries
                await asyncio.sleep(1)

        self._logger.info(f"Shodan collection complete: {len(items)} exposed services")
        return items
