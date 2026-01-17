"""
Crawl4AI-based web scraping service for The Pulse.

Provides unified web scraping capabilities using crawl4ai with:
- JavaScript rendering via Playwright
- Stealth mode for anti-bot bypass
- LLM-powered article extraction via Ollama
- Content filtering and markdown output
- Domain-specific handling

This service replaces Firecrawl for all web scraping needs.
"""

import asyncio
import logging
import json
from typing import Optional, Tuple, Dict, Any, List
from urllib.parse import urlparse
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# Feature availability flags
CRAWL4AI_AVAILABLE = False
DEEP_CRAWL_AVAILABLE = False
LLM_EXTRACTION_AVAILABLE = False

try:
    from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode
    from crawl4ai.content_filter_strategy import PruningContentFilter
    from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator
    CRAWL4AI_AVAILABLE = True
    logger.info("crawl4ai core loaded successfully")
except ImportError as e:
    logger.warning(f"crawl4ai not installed: {e}. Run: pip install crawl4ai && crawl4ai-setup")

# Try to import deep crawling features
if CRAWL4AI_AVAILABLE:
    try:
        from crawl4ai.deep_crawling import BFSDeepCrawlStrategy
        from crawl4ai.deep_crawling.scorers import KeywordRelevanceScorer
        DEEP_CRAWL_AVAILABLE = True
        logger.info("crawl4ai deep crawling features loaded")
    except ImportError:
        logger.info("Deep crawling features not available")

# Try to import LLM extraction
if CRAWL4AI_AVAILABLE:
    try:
        from crawl4ai import LLMConfig
        from crawl4ai.extraction_strategy import LLMExtractionStrategy
        LLM_EXTRACTION_AVAILABLE = True
        logger.info("LLM extraction strategy loaded")
    except ImportError:
        logger.info("LLM extraction not available")


# =============================================================================
# Domain Configuration
# =============================================================================

@dataclass
class DomainConfig:
    """Configuration for domain-specific crawling behavior."""
    wait_for: Optional[str] = None
    scroll_first: bool = False
    scroll_count: int = 3
    delay_before_extract: float = 0.0
    js_code: Optional[str] = None
    requires_stealth: bool = False
    blocked: bool = False
    block_reason: Optional[str] = None


DOMAIN_CONFIGS: Dict[str, DomainConfig] = {
    # News sites - removed wait_for to avoid timeouts on dynamic/SPA sites
    "aljazeera.com": DomainConfig(
        delay_before_extract=1.0,
        requires_stealth=True
    ),
    "apnews.com": DomainConfig(
        delay_before_extract=1.0,
        requires_stealth=True
    ),
    "local3news.com": DomainConfig(
        delay_before_extract=1.0
    ),
    "propublica.org": DomainConfig(
        delay_before_extract=1.0
    ),
    # RC manufacturer sites - no wait_for to avoid timeouts on dynamic sites
    "horizonhobby.com": DomainConfig(
        scroll_first=True,
        scroll_count=2,
        delay_before_extract=2.0
    ),
    "traxxas.com": DomainConfig(
        scroll_first=True,
        delay_before_extract=2.0
    ),
    "fmshobby.com": DomainConfig(
        delay_before_extract=2.0
    ),
    # Sites to block
    "twitter.com": DomainConfig(blocked=True, block_reason="Use API instead"),
    "x.com": DomainConfig(blocked=True, block_reason="Use API instead"),
    "facebook.com": DomainConfig(blocked=True, block_reason="Requires auth"),
}


def get_domain_config(url: str) -> Optional[DomainConfig]:
    """Get domain-specific configuration for a URL."""
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower().replace("www.", "")

        if domain in DOMAIN_CONFIGS:
            return DOMAIN_CONFIGS[domain]

        for configured_domain, config in DOMAIN_CONFIGS.items():
            if domain.endswith(configured_domain):
                return config

        return None
    except Exception:
        return None


# =============================================================================
# Pydantic Models for Extraction
# =============================================================================

class ExtractedArticle(BaseModel):
    """Schema for extracted news articles."""
    title: str = Field(default="", description="Article title")
    heading: str = Field(default="", description="Article heading/subtitle")
    url: str = Field(default="", description="Article URL")


class ArticleListExtraction(BaseModel):
    """Schema for extracting multiple articles from a page."""
    articles: List[ExtractedArticle] = Field(default_factory=list)


class ContentExtraction(BaseModel):
    """Schema for extracting article content."""
    title: str = Field(default="", description="Article title")
    summary: str = Field(default="", description="Brief summary")
    content: str = Field(default="", description="Main content text")
    key_points: List[str] = Field(default_factory=list, description="Key points")


# =============================================================================
# Main Service Class
# =============================================================================

class Crawl4AIService:
    """
    Unified web scraping service using crawl4ai.

    Replaces Firecrawl for:
    - Article extraction from news sites
    - Content scraping for collectors
    - Liveblog/dynamic content handling
    """

    def __init__(
        self,
        headless: bool = True,
        cache_enabled: bool = True,
        timeout_ms: int = 30000,
        stealth_mode: bool = True,
        ollama_url: str = "http://localhost:11434",
        ollama_model: str = "qwen2.5-coder:7b",
    ):
        """
        Initialize the Crawl4AI service.

        Args:
            headless: Run browser in headless mode
            cache_enabled: Enable content caching
            timeout_ms: Page timeout in milliseconds
            stealth_mode: Enable stealth mode for anti-bot bypass
            ollama_url: URL for local Ollama instance
            ollama_model: Model to use for LLM extraction
        """
        if not CRAWL4AI_AVAILABLE:
            raise ImportError("crawl4ai not installed. Run: pip install crawl4ai")

        self.ollama_url = ollama_url
        self.ollama_model = ollama_model
        self.timeout_ms = timeout_ms
        self.stealth_mode = stealth_mode

        extra_args = [
            "--disable-blink-features=AutomationControlled",
            "--disable-dev-shm-usage",
            "--no-first-run",
        ]

        self.browser_config = BrowserConfig(
            headless=headless,
            verbose=False,
            extra_args=extra_args,
        )

        self.cache_mode = CacheMode.ENABLED if cache_enabled else CacheMode.BYPASS
        self._crawler: Optional[AsyncWebCrawler] = None

    async def __aenter__(self):
        """Async context manager entry."""
        self._crawler = AsyncWebCrawler(config=self.browser_config)
        await self._crawler.__aenter__()
        return self

    async def __aexit__(self, *args):
        """Async context manager exit."""
        if self._crawler:
            await self._crawler.__aexit__(*args)
            self._crawler = None

    def _get_run_config(
        self,
        wait_for: Optional[str] = None,
        js_code: Optional[str] = None,
        use_fit_markdown: bool = True,
        extraction_strategy: Optional[Any] = None,
    ) -> CrawlerRunConfig:
        """Create run configuration for a crawl."""
        config_params = {
            "cache_mode": self.cache_mode,
            "page_timeout": self.timeout_ms,
        }

        if wait_for:
            config_params["wait_for"] = wait_for

        if js_code:
            config_params["js_code"] = [js_code] if isinstance(js_code, str) else js_code

        if use_fit_markdown:
            config_params["markdown_generator"] = DefaultMarkdownGenerator(
                content_filter=PruningContentFilter(
                    threshold=0.48,
                    threshold_type="fixed",
                    min_word_threshold=0
                )
            )

        if extraction_strategy:
            config_params["extraction_strategy"] = extraction_strategy

        return CrawlerRunConfig(**config_params)

    def _extract_content(self, result) -> str:
        """Extract markdown content from a crawl result."""
        if hasattr(result, 'markdown'):
            if hasattr(result.markdown, 'fit_markdown') and result.markdown.fit_markdown:
                return result.markdown.fit_markdown
            elif hasattr(result.markdown, 'raw_markdown'):
                return result.markdown.raw_markdown
            else:
                return str(result.markdown)
        return result.html if hasattr(result, 'html') else ""

    def _extract_metadata(self, result, url: str) -> Dict[str, Any]:
        """Extract metadata from a crawl result."""
        metadata = {
            "title": "",
            "description": "",
            "status_code": getattr(result, 'status_code', 200),
            "links": {"internal": 0, "external": 0},
        }

        if hasattr(result, 'metadata') and result.metadata:
            metadata["title"] = result.metadata.get("title", "")
            metadata["description"] = result.metadata.get("description", "")

        if hasattr(result, 'links') and result.links:
            metadata["links"]["internal"] = len(result.links.get("internal", []))
            metadata["links"]["external"] = len(result.links.get("external", []))

        return metadata

    async def fetch(
        self,
        url: str,
        wait_for: Optional[str] = None,
        js_code: Optional[str] = None,
    ) -> Tuple[str, str, Dict[str, Any]]:
        """
        Fetch URL and return content with metadata.

        Args:
            url: Target URL to fetch
            wait_for: CSS selector to wait for
            js_code: JavaScript to execute before extraction

        Returns:
            Tuple of (markdown_content, final_url, metadata_dict)
        """
        if self._crawler is None:
            raise RuntimeError("Service not initialized. Use 'async with' context manager.")

        domain_config = get_domain_config(url)

        if domain_config and domain_config.blocked:
            raise Exception(f"Domain blocked: {domain_config.block_reason}")

        # Apply domain-specific settings
        effective_wait_for = wait_for
        effective_js_code = js_code

        if domain_config:
            # Only use domain wait_for if explicitly provided and not overridden
            if not effective_wait_for and domain_config.wait_for:
                effective_wait_for = domain_config.wait_for
            if domain_config.js_code and not effective_js_code:
                effective_js_code = domain_config.js_code
            if domain_config.scroll_first and not effective_js_code:
                effective_js_code = f"""
                (async () => {{
                    for (let i = 0; i < {domain_config.scroll_count}; i++) {{
                        window.scrollTo(0, document.body.scrollHeight);
                        await new Promise(r => setTimeout(r, 1000));
                    }}
                }})();
                """

        # Try with wait_for first, fallback to without if it fails
        run_config = self._get_run_config(
            wait_for=effective_wait_for,
            js_code=effective_js_code,
        )

        logger.debug(f"Crawling: {url}")
        try:
            result = await self._crawler.arun(url=url, config=run_config)
        except Exception as e:
            # If wait_for failed, retry without it
            if effective_wait_for and "wait" in str(e).lower():
                logger.debug(f"Wait condition failed, retrying without wait_for: {e}")
                run_config = self._get_run_config(js_code=effective_js_code)
                result = await self._crawler.arun(url=url, config=run_config)
            else:
                raise

        if not result.success:
            error_msg = getattr(result, 'error_message', 'Unknown error')
            raise Exception(f"Crawl failed: {error_msg}")

        content = self._extract_content(result)
        metadata = self._extract_metadata(result, url)
        final_url = str(result.url) if hasattr(result, 'url') else url

        logger.debug(f"Crawl complete: {len(content)} chars")
        return content, final_url, metadata

    async def fetch_many(
        self,
        urls: List[str],
        wait_for: Optional[str] = None,
        max_concurrent: int = 3,
    ) -> List[Dict[str, Any]]:
        """
        Fetch multiple URLs concurrently.

        Args:
            urls: List of URLs to fetch
            wait_for: CSS selector to wait for
            max_concurrent: Maximum concurrent requests

        Returns:
            List of result dicts
        """
        if self._crawler is None:
            raise RuntimeError("Service not initialized. Use 'async with' context manager.")

        semaphore = asyncio.Semaphore(max_concurrent)

        async def fetch_one(url: str) -> Dict[str, Any]:
            async with semaphore:
                try:
                    content, final_url, metadata = await self.fetch(url, wait_for=wait_for)
                    return {
                        "url": url,
                        "final_url": final_url,
                        "content": content,
                        "metadata": metadata,
                        "success": True,
                        "error": None
                    }
                except Exception as e:
                    logger.warning(f"Failed to fetch {url}: {e}")
                    return {
                        "url": url,
                        "final_url": url,
                        "content": "",
                        "metadata": {},
                        "success": False,
                        "error": str(e)
                    }

        results = await asyncio.gather(*[fetch_one(url) for url in urls])
        return list(results)

    async def extract_articles(
        self,
        url: str,
        use_llm: bool = True,
    ) -> List[ExtractedArticle]:
        """
        Extract news articles from a page.

        Replaces Firecrawl's extract_articles method.

        Args:
            url: Target URL to extract articles from
            use_llm: Use LLM for structured extraction (requires Ollama)

        Returns:
            List of ExtractedArticle objects
        """
        if self._crawler is None:
            raise RuntimeError("Service not initialized. Use 'async with' context manager.")

        if use_llm and LLM_EXTRACTION_AVAILABLE:
            return await self._extract_articles_with_llm(url)
        else:
            return await self._extract_articles_from_markdown(url)

    async def _extract_articles_with_llm(self, url: str) -> List[ExtractedArticle]:
        """Extract articles using LLM-based structured extraction."""
        llm_config = LLMConfig(
            provider=f"ollama/{self.ollama_model}",
            api_base=self.ollama_url
        )

        extraction_strategy = LLMExtractionStrategy(
            llm_config=llm_config,
            schema=ArticleListExtraction.model_json_schema(),
            extraction_type="schema",
            instruction="""Extract news articles from this page. For each article, extract:
1. The article title (headline)
2. The article heading/subtitle (if available)
3. The article URL

Focus on:
- Political activities and developments
- Criminal cases, investigations, and law enforcement
- Government operations and policies
- Court proceedings and legal matters

Exclude weather, sports, and entertainment articles unless they relate to government or crime."""
        )

        run_config = self._get_run_config(extraction_strategy=extraction_strategy)
        result = await self._crawler.arun(url=url, config=run_config)

        if not result.success:
            raise Exception(f"Crawl failed: {getattr(result, 'error_message', 'Unknown')}")

        articles = []
        if hasattr(result, 'extracted_content') and result.extracted_content:
            try:
                extracted = json.loads(result.extracted_content)
                if isinstance(extracted, dict) and 'articles' in extracted:
                    for article_data in extracted['articles']:
                        articles.append(ExtractedArticle(**article_data))
            except (json.JSONDecodeError, TypeError) as e:
                logger.warning(f"Failed to parse LLM extraction: {e}")

        return articles

    async def _extract_articles_from_markdown(self, url: str) -> List[ExtractedArticle]:
        """Extract articles by parsing markdown content."""
        content, final_url, metadata = await self.fetch(url)

        articles = []
        lines = content.split('\n')

        for i, line in enumerate(lines):
            line = line.strip()
            if line.startswith('#') and not line.startswith('##'):
                title = line.lstrip('#').strip()
                heading = ""

                # Look for subtitle in next line
                if i + 1 < len(lines):
                    next_line = lines[i + 1].strip()
                    if next_line and not next_line.startswith('#'):
                        heading = next_line[:200]

                if title and len(title) > 10:
                    articles.append(ExtractedArticle(
                        title=title,
                        heading=heading,
                        url=final_url
                    ))

        return articles

    async def scrape_article_content(
        self,
        url: str,
        is_liveblog: bool = False,
    ) -> str:
        """
        Scrape the main content from a news article.

        Replaces Firecrawl/Playwright article scraping.

        Args:
            url: Article URL
            is_liveblog: Whether the article is a liveblog

        Returns:
            Extracted text content
        """
        wait_for = None
        js_code = None

        if is_liveblog or 'liveblog' in url.lower():
            wait_for = ".wysiwyg-content, .timeline-item, article"
            js_code = """
            (async () => {
                // Try to click "Read more" buttons
                const buttons = document.querySelectorAll('button');
                for (const btn of buttons) {
                    if (btn.textContent.includes('Read more')) {
                        btn.click();
                        await new Promise(r => setTimeout(r, 1000));
                    }
                }
                // Scroll to load content
                for (let i = 0; i < 3; i++) {
                    window.scrollTo(0, document.body.scrollHeight);
                    await new Promise(r => setTimeout(r, 1000));
                }
            })();
            """

        content, final_url, metadata = await self.fetch(
            url,
            wait_for=wait_for,
            js_code=js_code,
        )

        return self._clean_content(content)

    def _clean_content(self, content: str) -> str:
        """Clean and filter content."""
        filtered_phrases = [
            "support propublica's investigative reporting",
            "donate now",
            "recommended stories",
            "this is a modal window",
            "chapters",
            "descriptions off",
            "captions settings",
        ]

        for phrase in filtered_phrases:
            content = content.replace(phrase.lower(), '')
            content = content.replace(phrase.capitalize(), '')

        return '\n'.join(line.strip() for line in content.split('\n') if line.strip())


# =============================================================================
# Convenience Functions
# =============================================================================

async def crawl_url(
    url: str,
    timeout: int = 30,
    wait_for: Optional[str] = None,
) -> str:
    """
    Simple function to crawl a URL and get markdown content.

    Args:
        url: Target URL
        timeout: Timeout in seconds
        wait_for: CSS selector to wait for

    Returns:
        Markdown content
    """
    if not CRAWL4AI_AVAILABLE:
        raise ImportError("crawl4ai not installed")

    async with Crawl4AIService(timeout_ms=timeout * 1000) as service:
        content, final_url, metadata = await service.fetch(url, wait_for=wait_for)

        title = metadata.get("title", "No title")
        output = f"## {title}\n\n**URL:** {final_url}\n\n{content}"
        return output


async def extract_articles_from_url(
    url: str,
    timeout: int = 30,
) -> List[ExtractedArticle]:
    """
    Extract articles from a news page.

    Args:
        url: News page URL
        timeout: Timeout in seconds

    Returns:
        List of extracted articles
    """
    if not CRAWL4AI_AVAILABLE:
        raise ImportError("crawl4ai not installed")

    async with Crawl4AIService(timeout_ms=timeout * 1000) as service:
        return await service.extract_articles(url)


# =============================================================================
# Exports
# =============================================================================

__all__ = [
    # Main class
    "Crawl4AIService",
    # Convenience functions
    "crawl_url",
    "extract_articles_from_url",
    # Feature flags
    "CRAWL4AI_AVAILABLE",
    "DEEP_CRAWL_AVAILABLE",
    "LLM_EXTRACTION_AVAILABLE",
    # Models
    "ExtractedArticle",
    "ArticleListExtraction",
    "ContentExtraction",
    # Config
    "DomainConfig",
    "DOMAIN_CONFIGS",
    "get_domain_config",
]
