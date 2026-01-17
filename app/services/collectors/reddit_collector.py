"""
Reddit collector for The Pulse.

Collects posts from RC-related and other configured subreddits.
Supports both authenticated (PRAW) and unauthenticated (JSON API) collection.
"""
import asyncio
import aiohttp
from datetime import datetime, timezone
from typing import List, Optional
import logging

from .base import BaseCollector, CollectedItem
from .config import (
    REDDIT_CLIENT_ID,
    REDDIT_CLIENT_SECRET,
    REDDIT_USER_AGENT,
    REDDIT_SUBREDDITS,
    REDDIT_POSTS_PER_SUB,
    REDDIT_CATEGORY_MAP,
)

logger = logging.getLogger(__name__)


class RedditCollector(BaseCollector):
    """Collects posts from configured subreddits."""

    def __init__(
        self,
        subreddits: Optional[List[str]] = None,
        posts_per_sub: int = REDDIT_POSTS_PER_SUB,
    ):
        """
        Initialize Reddit collector.

        Args:
            subreddits: List of subreddit names to collect from
            posts_per_sub: Number of posts to fetch per subreddit
        """
        super().__init__()
        self.subreddits = subreddits or REDDIT_SUBREDDITS
        self.posts_per_sub = posts_per_sub

    @property
    def name(self) -> str:
        return "Reddit"

    @property
    def source_type(self) -> str:
        return "reddit"

    def _get_category(self, subreddit: str) -> str:
        """Map subreddit to category using config map."""
        subreddit_lower = subreddit.lower()

        # Use the category map from config (primary source)
        if subreddit_lower in REDDIT_CATEGORY_MAP:
            return REDDIT_CATEGORY_MAP[subreddit_lower]

        # Legacy mappings for any RC hobby subreddits (kept for backwards compatibility)
        if subreddit_lower in ["rcplanes", "radiocontrol", "rccars", "fpv", "multicopter"]:
            return "rc_industry"

        # Tech subreddits
        if subreddit_lower in ["machinelearning", "artificial"]:
            return "tech_ai"
        if subreddit_lower in ["technology", "programming"]:
            return "tech_general"

        # Default to general news (not rc_industry!)
        return "general"

    async def collect(self) -> List[CollectedItem]:
        """Fetch posts from Reddit."""
        # Check if PRAW credentials are available
        if REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET:
            try:
                return await self._collect_with_praw()
            except ImportError:
                self._logger.warning("PRAW not installed, falling back to JSON API")
            except Exception as e:
                self._logger.warning(f"PRAW failed: {e}, falling back to JSON API")

        # Fall back to JSON API (no auth required, limited)
        return await self._collect_no_auth()

    async def _collect_with_praw(self) -> List[CollectedItem]:
        """Collect using PRAW (authenticated)."""
        import praw

        items = []

        def fetch_reddit():
            reddit = praw.Reddit(
                client_id=REDDIT_CLIENT_ID,
                client_secret=REDDIT_CLIENT_SECRET,
                user_agent=REDDIT_USER_AGENT,
            )

            fetched = []
            for sub_name in self.subreddits:
                try:
                    subreddit = reddit.subreddit(sub_name)
                    for post in subreddit.hot(limit=self.posts_per_sub):
                        fetched.append({
                            "subreddit": sub_name,
                            "title": post.title,
                            "selftext": post.selftext or "",
                            "url": f"https://reddit.com{post.permalink}",
                            "score": post.score,
                            "num_comments": post.num_comments,
                            "created_utc": post.created_utc,
                            "author": str(post.author) if post.author else "[deleted]",
                            "link_flair_text": post.link_flair_text or "",
                        })
                except Exception as e:
                    logger.warning(f"Failed to fetch r/{sub_name}: {e}")
                    continue
            return fetched

        loop = asyncio.get_event_loop()
        posts = await loop.run_in_executor(None, fetch_reddit)

        for post in posts:
            try:
                published = datetime.fromtimestamp(
                    post["created_utc"], tz=timezone.utc
                )
                category = self._get_category(post["subreddit"])
                summary = post["selftext"] if post["selftext"] else post["title"]

                items.append(CollectedItem(
                    source="reddit",
                    source_name=f"r/{post['subreddit']}",
                    source_url=f"https://reddit.com/r/{post['subreddit']}",
                    category=category,
                    title=self.clean_text(post["title"]),
                    summary=self.truncate_text(self.clean_text(summary), 500),
                    url=post["url"],
                    published=published,
                    author=post["author"],
                    metadata={
                        "subreddit": post["subreddit"],
                        "score": post["score"],
                        "num_comments": post["num_comments"],
                        "flair": post["link_flair_text"],
                    },
                    raw_content=post["selftext"],
                ))
            except Exception as e:
                self._logger.debug(f"Failed to process post: {e}")
                continue

        self._logger.info(f"Reddit (PRAW): collected {len(items)} posts")
        return items

    async def _collect_no_auth(self) -> List[CollectedItem]:
        """Fallback: collect via Reddit JSON API without auth."""
        items = []
        headers = {"User-Agent": REDDIT_USER_AGENT}

        async with aiohttp.ClientSession() as session:
            for sub_name in self.subreddits:
                try:
                    url = f"https://www.reddit.com/r/{sub_name}/hot.json?limit={self.posts_per_sub}"
                    async with session.get(
                        url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)
                    ) as resp:
                        if resp.status != 200:
                            self._logger.warning(
                                f"r/{sub_name} returned status {resp.status}"
                            )
                            continue

                        data = await resp.json()
                        posts = data.get("data", {}).get("children", [])

                        for post_wrapper in posts:
                            post = post_wrapper.get("data", {})
                            try:
                                created_utc = post.get(
                                    "created_utc", datetime.now().timestamp()
                                )
                                published = datetime.fromtimestamp(
                                    created_utc, tz=timezone.utc
                                )
                                category = self._get_category(sub_name)
                                summary = post.get("selftext", "") or post.get("title", "")

                                items.append(CollectedItem(
                                    source="reddit",
                                    source_name=f"r/{sub_name}",
                                    source_url=f"https://reddit.com/r/{sub_name}",
                                    category=category,
                                    title=self.clean_text(post.get("title", "")),
                                    summary=self.truncate_text(
                                        self.clean_text(summary), 500
                                    ),
                                    url=f"https://reddit.com{post.get('permalink', '')}",
                                    published=published,
                                    author=post.get("author", "[deleted]"),
                                    metadata={
                                        "subreddit": sub_name,
                                        "score": post.get("score", 0),
                                        "num_comments": post.get("num_comments", 0),
                                    },
                                    raw_content=post.get("selftext", ""),
                                ))
                            except Exception as e:
                                self._logger.debug(f"Failed to process post: {e}")
                                continue

                    # Rate limit between subreddits
                    await asyncio.sleep(1)

                except asyncio.TimeoutError:
                    self._logger.warning(f"r/{sub_name} timed out")
                except Exception as e:
                    self._logger.warning(f"r/{sub_name} error: {type(e).__name__}: {e}")
                    continue

        self._logger.info(f"Reddit (JSON): collected {len(items)} posts")
        return items
