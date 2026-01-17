"""
ArXiv research paper collector for The Pulse.

Collects recent AI/ML research papers from ArXiv.org API.
Focuses on computer science categories relevant to AI development.
"""
import asyncio
from datetime import datetime, timezone
from typing import List, Optional
import logging

from .base import BaseCollector, CollectedItem
from .config import ARXIV_CATEGORIES, ARXIV_MAX_PAPERS

logger = logging.getLogger(__name__)


class ArxivCollector(BaseCollector):
    """Collects recent AI/ML research papers from ArXiv."""

    def __init__(
        self,
        categories: Optional[List[str]] = None,
        max_papers: int = ARXIV_MAX_PAPERS,
    ):
        """
        Initialize ArXiv collector.

        Args:
            categories: ArXiv categories to search (e.g., cs.AI, cs.LG)
            max_papers: Maximum papers to fetch
        """
        super().__init__()
        self.categories = categories or ARXIV_CATEGORIES
        self.max_papers = max_papers

    @property
    def name(self) -> str:
        return "ArXiv"

    @property
    def source_type(self) -> str:
        return "arxiv"

    async def collect(self) -> List[CollectedItem]:
        """Fetch recent papers from ArXiv."""
        items = []

        try:
            import arxiv
        except ImportError:
            self._logger.error("arxiv package not installed. Run: pip install arxiv")
            return items

        # Build query for multiple categories
        category_query = " OR ".join([f"cat:{cat}" for cat in self.categories])
        self._logger.info(
            f"Fetching up to {self.max_papers} papers from categories: {self.categories}"
        )

        # ArXiv API is synchronous, run in executor
        def fetch_papers():
            client = arxiv.Client()
            search = arxiv.Search(
                query=category_query,
                max_results=self.max_papers,
                sort_by=arxiv.SortCriterion.SubmittedDate,
                sort_order=arxiv.SortOrder.Descending,
            )
            return list(client.results(search))

        try:
            loop = asyncio.get_event_loop()
            papers = await loop.run_in_executor(None, fetch_papers)
            self._logger.info(f"Retrieved {len(papers)} papers from ArXiv")

            for paper in papers:
                try:
                    # Get primary category
                    primary_cat = paper.primary_category or "cs.AI"

                    # Map to our category system - all ArXiv papers are research
                    if "LG" in primary_cat or "ML" in primary_cat:
                        category = "research"
                    elif "CL" in primary_cat:
                        category = "research"
                    else:
                        category = "research"

                    # Get full abstract
                    full_abstract = self.clean_text(paper.summary)

                    # Create summary (truncated) but keep full in raw_content
                    summary = self.truncate_text(full_abstract, 1000)

                    # Extract author info
                    authors = [a.name for a in paper.authors[:5]]
                    author_str = ", ".join(authors)
                    if len(paper.authors) > 5:
                        author_str += f" (+{len(paper.authors) - 5} more)"

                    # Published date
                    if paper.published:
                        if hasattr(paper.published, 'tzinfo') and paper.published.tzinfo:
                            published = paper.published
                        else:
                            published = paper.published.replace(tzinfo=timezone.utc)
                    else:
                        published = datetime.now(timezone.utc)

                    items.append(CollectedItem(
                        source="arxiv",
                        source_name="ArXiv",
                        source_url="https://arxiv.org",
                        category=category,
                        title=self.clean_text(paper.title),
                        summary=summary,
                        url=paper.entry_id,
                        published=published,
                        author=author_str,
                        metadata={
                            "authors": authors,
                            "author_count": len(paper.authors),
                            "author_string": author_str,
                            "categories": paper.categories,
                            "primary_category": primary_cat,
                            "pdf_url": paper.pdf_url,
                            "comment": paper.comment or "",
                            "abstract_length": len(full_abstract),
                        },
                        raw_content=full_abstract,
                    ))

                    self._logger.debug(
                        f"Collected paper: {paper.title[:60]}... "
                        f"(abstract: {len(full_abstract)} chars)"
                    )

                except Exception as e:
                    self._logger.warning(f"Failed to process paper: {e}")
                    continue

            self._logger.info(f"Successfully processed {len(items)} papers")

        except Exception as e:
            self._logger.error(f"ArXiv API error: {type(e).__name__}: {e}")

        return items
