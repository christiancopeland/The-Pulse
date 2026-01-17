"""
SEC EDGAR Collector for The Pulse.

Collects corporate filings from the SEC EDGAR database (FREE government data).

Coverage:
- 8-K: Material events (mergers, acquisitions, executive changes)
- 10-K: Annual reports
- 10-Q: Quarterly reports
- 13-F: Institutional holdings
- Form 4: Insider trading
- S-1: IPO registrations

API Documentation: https://www.sec.gov/developer
Requirements: User-Agent header with contact email (SEC policy)
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


# Form types and their intelligence significance
FORM_TYPES: Dict[str, Dict[str, Any]] = {
    "8-K": {
        "category": "financial",
        "description": "Current report (material events)",
        "priority": "high",
    },
    "10-K": {
        "category": "financial",
        "description": "Annual report",
        "priority": "medium",
    },
    "10-Q": {
        "category": "financial",
        "description": "Quarterly report",
        "priority": "medium",
    },
    "13-F": {
        "category": "financial",
        "description": "Institutional holdings",
        "priority": "medium",
    },
    "4": {
        "category": "financial",
        "description": "Insider trading",
        "priority": "high",
    },
    "S-1": {
        "category": "financial",
        "description": "IPO registration",
        "priority": "high",
    },
    "SC 13G": {
        "category": "financial",
        "description": "Beneficial ownership (5%+)",
        "priority": "high",
    },
    "SC 13D": {
        "category": "financial",
        "description": "Beneficial ownership (activist)",
        "priority": "high",
    },
    "DEF 14A": {
        "category": "financial",
        "description": "Proxy statement",
        "priority": "low",
    },
}


class SECEdgarCollector(BaseCollector):
    """
    Collector for SEC EDGAR corporate filings.

    Features:
    - Real-time filing monitoring
    - Multiple form type support
    - Company filtering
    - CIK (Central Index Key) resolution
    - Filing content extraction

    All data is FREE (public government data).

    Important: SEC requires a User-Agent header with contact email.
    Set SEC_CONTACT_EMAIL environment variable.
    """

    # SEC EDGAR API endpoints
    SUBMISSIONS_API = "https://data.sec.gov/submissions"
    FILINGS_API = "https://efts.sec.gov/LATEST/search-index"
    COMPANY_SEARCH = "https://www.sec.gov/cgi-bin/browse-edgar"
    FULL_TEXT_SEARCH = "https://efts.sec.gov/LATEST/search-index"

    def __init__(
        self,
        contact_email: Optional[str] = None,
        form_types: Optional[List[str]] = None,
        max_items: int = 100,
        days_back: int = 1,
        companies: Optional[List[str]] = None,
    ):
        """
        Initialize SEC EDGAR collector.

        Args:
            contact_email: Email for User-Agent (required by SEC policy)
                          Set SEC_CONTACT_EMAIL env var
            form_types: List of form types to collect (e.g., ["8-K", "4"])
                       Defaults to high-priority forms
            max_items: Maximum items to fetch
            days_back: Number of days to look back
            companies: Optional list of company CIKs or names to filter
        """
        super().__init__()
        self.contact_email = contact_email or os.getenv(
            "SEC_CONTACT_EMAIL",
            "research@example.com"
        )
        self.form_types = form_types or ["8-K", "4", "S-1", "SC 13D", "SC 13G"]
        self.max_items = max_items
        self.days_back = days_back
        self.companies = companies

        # SEC requires identifying User-Agent
        self.user_agent = f"ThePulse/1.0 ({self.contact_email})"

    @property
    def name(self) -> str:
        return "SEC EDGAR"

    @property
    def source_type(self) -> str:
        return "sec_edgar"

    def _get_headers(self) -> Dict[str, str]:
        """Get request headers with required User-Agent."""
        return {
            "User-Agent": self.user_agent,
            "Accept": "application/json",
            "Accept-Encoding": "gzip, deflate",
        }

    def _get_form_info(self, form_type: str) -> Dict[str, Any]:
        """Get form type information."""
        # Normalize form type
        normalized = form_type.upper().strip()
        return FORM_TYPES.get(normalized, {
            "category": "financial",
            "description": f"{normalized} filing",
            "priority": "low",
        })

    def _build_filing_url(self, accession_number: str, cik: str) -> str:
        """Build URL to the filing on SEC website."""
        # Format accession number (remove dashes for URL)
        acc_clean = accession_number.replace("-", "")
        # CIK should be zero-padded to 10 digits
        cik_padded = str(cik).zfill(10)
        return f"https://www.sec.gov/Archives/edgar/data/{cik_padded}/{acc_clean}/{accession_number}-index.htm"

    async def collect(self) -> List[CollectedItem]:
        """Fetch recent SEC filings."""
        items = []

        try:
            async with aiohttp.ClientSession(headers=self._get_headers()) as session:
                # Use the full-text search API for recent filings
                items = await self._fetch_recent_filings(session)

        except asyncio.TimeoutError:
            self._logger.warning(
                f"SEC EDGAR API timed out after {API_TIMEOUT_SECONDS}s"
            )
        except Exception as e:
            self._logger.error(f"SEC EDGAR collection error: {type(e).__name__}: {e}")

        self._logger.info(f"SEC EDGAR collection complete: {len(items)} items")
        return items

    async def _fetch_recent_filings(
        self,
        session: aiohttp.ClientSession
    ) -> List[CollectedItem]:
        """Fetch recent filings using SEC full-text search."""
        items = []

        # Calculate date range
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=self.days_back)

        for form_type in self.form_types:
            try:
                # Build search query
                url = "https://efts.sec.gov/LATEST/search-index"
                params = {
                    "q": f'formType:"{form_type}"',
                    "dateRange": "custom",
                    "startdt": start_date.strftime("%Y-%m-%d"),
                    "enddt": end_date.strftime("%Y-%m-%d"),
                    "from": "0",
                    "size": str(min(self.max_items, 100)),
                }

                self._logger.debug(f"Querying SEC EDGAR for form {form_type}")

                async with session.get(
                    url,
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=API_TIMEOUT_SECONDS),
                ) as response:
                    if response.status != 200:
                        # Fallback to RSS feed approach
                        self._logger.debug(
                            f"SEC search API returned {response.status}, trying RSS"
                        )
                        rss_items = await self._fetch_from_rss(session, form_type)
                        items.extend(rss_items)
                        continue

                    data = await response.json()
                    hits = data.get("hits", {}).get("hits", [])

                    self._logger.debug(
                        f"SEC EDGAR {form_type}: received {len(hits)} filings"
                    )

                    # Fallback to RSS if search returns no results
                    if not hits:
                        self._logger.debug(
                            f"SEC search returned 0 hits for {form_type}, trying RSS fallback"
                        )
                        rss_items = await self._fetch_from_rss(session, form_type)
                        items.extend(rss_items)
                        continue

                    for hit in hits:
                        try:
                            source = hit.get("_source", {})
                            item = self._parse_filing(source, form_type)
                            if item:
                                items.append(item)
                        except Exception as e:
                            self._logger.debug(f"Failed to parse SEC filing: {e}")
                            continue

            except Exception as e:
                self._logger.warning(f"SEC EDGAR {form_type} error: {e}")
                # Try RSS fallback
                try:
                    rss_items = await self._fetch_from_rss(session, form_type)
                    items.extend(rss_items)
                except Exception:
                    pass

        return items

    async def _fetch_from_rss(
        self,
        session: aiohttp.ClientSession,
        form_type: str
    ) -> List[CollectedItem]:
        """Fallback: fetch from SEC RSS feed."""
        items = []

        try:
            # SEC RSS feed for latest filings
            url = "https://www.sec.gov/cgi-bin/browse-edgar"
            params = {
                "action": "getcurrent",
                "type": form_type,
                "company": "",
                "dateb": "",
                "owner": "include",
                "count": str(min(self.max_items, 40)),
                "output": "atom",
            }

            async with session.get(
                url,
                params=params,
                timeout=aiohttp.ClientTimeout(total=API_TIMEOUT_SECONDS),
            ) as response:
                if response.status == 200:
                    # Parse RSS/Atom feed
                    text = await response.text()
                    items = self._parse_rss_feed(text, form_type)

        except Exception as e:
            self._logger.warning(f"SEC RSS fallback failed for {form_type}: {e}")

        return items

    def _parse_filing(
        self,
        source: Dict[str, Any],
        form_type: str
    ) -> Optional[CollectedItem]:
        """Parse a filing from search results."""
        try:
            # Extract fields
            company_name = source.get("companyName", ["Unknown"])[0] if isinstance(source.get("companyName"), list) else source.get("companyName", "Unknown")
            cik = source.get("ciks", [""])[0] if isinstance(source.get("ciks"), list) else source.get("ciks", "")
            accession_number = source.get("accessionNumber", [""])[0] if isinstance(source.get("accessionNumber"), list) else source.get("accessionNumber", "")
            file_date = source.get("filedAt", "")

            # Parse date
            try:
                if file_date:
                    published = datetime.fromisoformat(file_date.replace("Z", "+00:00"))
                else:
                    published = datetime.now(timezone.utc)
            except ValueError:
                published = datetime.now(timezone.utc)

            # Get form info
            form_info = self._get_form_info(form_type)

            # Build title
            title = f"{form_type}: {company_name}"

            # Build summary
            summary = f"{form_info['description']} filed by {company_name}"
            if cik:
                summary += f" (CIK: {cik})"

            # Build URL
            url = self._build_filing_url(accession_number, cik) if accession_number and cik else f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}"

            return CollectedItem(
                source="sec_edgar",
                source_name="SEC EDGAR",
                source_url="https://www.sec.gov/edgar",
                category=form_info["category"],
                title=self.clean_text(title),
                summary=self.truncate_text(summary, 500),
                url=url,
                published=published,
                metadata={
                    "form_type": form_type,
                    "company_name": company_name,
                    "cik": cik,
                    "accession_number": accession_number,
                    "priority": form_info["priority"],
                    "description": form_info["description"],
                    "file_date": file_date,
                },
                raw_content="",
            )

        except Exception as e:
            self._logger.debug(f"Failed to parse filing: {e}")
            return None

    def _parse_rss_feed(self, xml_text: str, form_type: str) -> List[CollectedItem]:
        """Parse SEC RSS/Atom feed."""
        items = []

        try:
            import xml.etree.ElementTree as ET
            root = ET.fromstring(xml_text)

            # Handle Atom namespace
            ns = {"atom": "http://www.w3.org/2005/Atom"}

            for entry in root.findall(".//atom:entry", ns):
                try:
                    title_elem = entry.find("atom:title", ns)
                    link_elem = entry.find("atom:link", ns)
                    updated_elem = entry.find("atom:updated", ns)
                    summary_elem = entry.find("atom:summary", ns)

                    title = title_elem.text if title_elem is not None else f"{form_type} Filing"
                    url = link_elem.get("href", "") if link_elem is not None else ""
                    updated = updated_elem.text if updated_elem is not None else ""
                    summary = summary_elem.text if summary_elem is not None else ""

                    # Parse date
                    try:
                        published = datetime.fromisoformat(updated.replace("Z", "+00:00")) if updated else datetime.now(timezone.utc)
                    except ValueError:
                        published = datetime.now(timezone.utc)

                    form_info = self._get_form_info(form_type)

                    items.append(CollectedItem(
                        source="sec_edgar",
                        source_name="SEC EDGAR",
                        source_url="https://www.sec.gov/edgar",
                        category=form_info["category"],
                        title=self.clean_text(title),
                        summary=self.truncate_text(summary or f"{form_info['description']}", 500),
                        url=url,
                        published=published,
                        metadata={
                            "form_type": form_type,
                            "priority": form_info["priority"],
                            "description": form_info["description"],
                            "source": "rss",
                        },
                        raw_content="",
                    ))

                except Exception as e:
                    self._logger.debug(f"Failed to parse RSS entry: {e}")
                    continue

        except Exception as e:
            self._logger.warning(f"RSS parsing error: {e}")

        return items

    async def get_company_filings(
        self,
        cik_or_ticker: str,
        form_types: Optional[List[str]] = None,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Get recent filings for a specific company.

        Args:
            cik_or_ticker: CIK number or stock ticker
            form_types: Optional list of form types to filter
            limit: Maximum number of filings to return

        Returns:
            List of filing metadata dicts
        """
        filings = []

        try:
            async with aiohttp.ClientSession(headers=self._get_headers()) as session:
                # Resolve CIK if ticker provided
                cik = cik_or_ticker
                if not cik.isdigit():
                    cik = await self._resolve_cik(session, cik_or_ticker)
                    if not cik:
                        return []

                # Pad CIK to 10 digits
                cik_padded = str(cik).zfill(10)

                # Fetch company submissions
                url = f"{self.SUBMISSIONS_API}/CIK{cik_padded}.json"

                async with session.get(
                    url,
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        recent = data.get("filings", {}).get("recent", {})

                        forms = recent.get("form", [])
                        dates = recent.get("filingDate", [])
                        accessions = recent.get("accessionNumber", [])
                        descriptions = recent.get("primaryDocDescription", [])

                        for i in range(min(len(forms), limit)):
                            form = forms[i] if i < len(forms) else ""

                            # Filter by form type if specified
                            if form_types and form not in form_types:
                                continue

                            filings.append({
                                "form_type": form,
                                "filing_date": dates[i] if i < len(dates) else "",
                                "accession_number": accessions[i] if i < len(accessions) else "",
                                "description": descriptions[i] if i < len(descriptions) else "",
                                "cik": cik,
                                "company_name": data.get("name", ""),
                            })

        except Exception as e:
            self._logger.error(f"Failed to get company filings: {e}")

        return filings

    async def _resolve_cik(
        self,
        session: aiohttp.ClientSession,
        ticker: str
    ) -> Optional[str]:
        """Resolve stock ticker to CIK number."""
        try:
            # Use company tickers JSON
            url = "https://www.sec.gov/files/company_tickers.json"

            async with session.get(
                url,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as response:
                if response.status == 200:
                    data = await response.json()

                    ticker_upper = ticker.upper()
                    for company in data.values():
                        if company.get("ticker") == ticker_upper:
                            return str(company.get("cik_str"))

        except Exception as e:
            self._logger.warning(f"Failed to resolve ticker {ticker}: {e}")

        return None
