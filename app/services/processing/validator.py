"""
Content validation for collected news items.

Validates content quality, filters spam/junk, and ensures
items meet minimum requirements before processing.

PROC-001: Validation Pipeline
"""
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
import re
import logging

from app.models.news_item import NewsItem

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """Result of content validation."""
    is_valid: bool
    score: float  # 0.0 to 1.0 quality score
    issues: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __repr__(self):
        status = "VALID" if self.is_valid else "INVALID"
        return f"<ValidationResult({status}, score={self.score:.2f}, issues={len(self.issues)})>"


class ContentValidator:
    """
    Validates content quality for collected news items.

    Checks for:
    - Minimum content length
    - Non-empty title
    - Valid URL format
    - Spam/junk patterns
    - Excessive special characters
    - Duplicate title patterns
    """

    # Minimum lengths for content
    MIN_TITLE_LENGTH = 10
    MIN_CONTENT_LENGTH = 50
    MIN_SUMMARY_LENGTH = 20

    # Maximum ratios for spam detection
    MAX_CAPS_RATIO = 0.5  # Max 50% uppercase
    MAX_SPECIAL_CHAR_RATIO = 0.2  # Max 20% special characters
    MAX_URL_RATIO = 0.15  # Max 15% URLs in content

    # Spam patterns (compiled for performance)
    SPAM_PATTERNS = [
        re.compile(r'\b(buy now|click here|limited time|act now|free money)\b', re.I),
        re.compile(r'\b(winner|congratulations|you\'ve won)\b', re.I),
        re.compile(r'\$\d+[\s,]*\d*[\s,]*\d*\s*(per|a)\s*(day|week|month)\b', re.I),
        re.compile(r'\b(viagra|cialis|casino|poker|betting)\b', re.I),
        re.compile(r'[A-Z]{20,}'),  # Long all-caps strings
    ]

    # URL pattern for detection
    URL_PATTERN = re.compile(r'https?://\S+')

    # Valid URL pattern (basic check)
    VALID_URL_PATTERN = re.compile(
        r'^https?://'
        r'(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)*'
        r'[a-zA-Z]{2,}'
        r'(?:/[^\s]*)?$'
    )

    def __init__(self, strict_mode: bool = False):
        """
        Initialize validator.

        Args:
            strict_mode: If True, applies stricter validation rules.
        """
        self.strict_mode = strict_mode
        self._logger = logging.getLogger(f"{__name__}.ContentValidator")

    async def validate(self, item: NewsItem) -> ValidationResult:
        """
        Validate a news item.

        Args:
            item: NewsItem to validate

        Returns:
            ValidationResult with validity status and details
        """
        issues = []
        scores = []

        # Title validation
        title_score, title_issues = self._validate_title(item.title)
        scores.append(title_score)
        issues.extend(title_issues)

        # Content validation
        content = item.content or item.summary or ""
        content_score, content_issues = self._validate_content(content)
        scores.append(content_score)
        issues.extend(content_issues)

        # URL validation
        url_score, url_issues = self._validate_url(item.url)
        scores.append(url_score)
        issues.extend(url_issues)

        # Spam detection
        spam_score, spam_issues = self._detect_spam(item.title, content)
        scores.append(spam_score)
        issues.extend(spam_issues)

        # Calculate overall score (weighted average)
        weights = [0.25, 0.35, 0.15, 0.25]  # title, content, url, spam
        overall_score = sum(s * w for s, w in zip(scores, weights))

        # Determine validity
        threshold = 0.6 if self.strict_mode else 0.4
        is_valid = overall_score >= threshold and len([i for i in issues if "CRITICAL" in i]) == 0

        result = ValidationResult(
            is_valid=is_valid,
            score=overall_score,
            issues=issues,
            metadata={
                "title_score": title_score,
                "content_score": content_score,
                "url_score": url_score,
                "spam_score": spam_score,
                "strict_mode": self.strict_mode,
            }
        )

        if not is_valid:
            self._logger.debug(f"Item failed validation: {result}")

        return result

    def _validate_title(self, title: Optional[str]) -> tuple:
        """Validate title quality."""
        issues = []
        score = 1.0

        if not title:
            return 0.0, ["CRITICAL: Missing title"]

        title = title.strip()

        # Length check
        if len(title) < self.MIN_TITLE_LENGTH:
            issues.append(f"Title too short ({len(title)} chars, min {self.MIN_TITLE_LENGTH})")
            score -= 0.4

        # Check for placeholder titles
        placeholder_patterns = [
            r'^(untitled|no title|test|placeholder)\b',
            r'^\[.*\]$',  # Just brackets
            r'^https?://',  # URL as title
        ]
        for pattern in placeholder_patterns:
            if re.match(pattern, title, re.I):
                issues.append("Title appears to be a placeholder")
                score -= 0.5
                break

        # Check excessive caps
        if title.isupper() and len(title) > 20:
            issues.append("Title is all uppercase")
            score -= 0.2

        return max(0.0, score), issues

    def _validate_content(self, content: Optional[str]) -> tuple:
        """Validate content quality."""
        issues = []
        score = 1.0

        if not content:
            return 0.3, ["Content is empty (summary may still be useful)"]

        content = content.strip()

        # Length check
        if len(content) < self.MIN_CONTENT_LENGTH:
            issues.append(f"Content too short ({len(content)} chars, min {self.MIN_CONTENT_LENGTH})")
            score -= 0.3

        # Check for excessive special characters
        special_chars = sum(1 for c in content if not c.isalnum() and not c.isspace())
        if len(content) > 0:
            special_ratio = special_chars / len(content)
            if special_ratio > self.MAX_SPECIAL_CHAR_RATIO:
                issues.append(f"Excessive special characters ({special_ratio:.1%})")
                score -= 0.2

        # Check for excessive URLs
        urls = self.URL_PATTERN.findall(content)
        if len(content) > 0:
            url_chars = sum(len(u) for u in urls)
            url_ratio = url_chars / len(content)
            if url_ratio > self.MAX_URL_RATIO:
                issues.append(f"Excessive URLs in content ({url_ratio:.1%})")
                score -= 0.2

        # Check for excessive capitalization
        alpha_chars = [c for c in content if c.isalpha()]
        if alpha_chars:
            caps_ratio = sum(1 for c in alpha_chars if c.isupper()) / len(alpha_chars)
            if caps_ratio > self.MAX_CAPS_RATIO:
                issues.append(f"Excessive capitalization ({caps_ratio:.1%})")
                score -= 0.15

        return max(0.0, score), issues

    def _validate_url(self, url: Optional[str]) -> tuple:
        """Validate URL format."""
        issues = []
        score = 1.0

        if not url:
            return 0.5, ["Missing URL"]

        url = url.strip()

        # Basic format check
        if not self.VALID_URL_PATTERN.match(url):
            issues.append("Invalid URL format")
            score -= 0.5

        # Check for suspicious patterns
        suspicious_patterns = [
            r'\.(exe|zip|rar|scr)$',  # Executable files
            r'bit\.ly|tinyurl|goo\.gl',  # URL shorteners (may be spam)
        ]
        for pattern in suspicious_patterns:
            if re.search(pattern, url, re.I):
                issues.append("URL contains suspicious pattern")
                score -= 0.3
                break

        return max(0.0, score), issues

    def _detect_spam(self, title: Optional[str], content: Optional[str]) -> tuple:
        """Detect spam patterns in content."""
        issues = []
        score = 1.0

        combined = f"{title or ''} {content or ''}"

        if not combined.strip():
            return 0.5, ["No content to analyze for spam"]

        # Check against spam patterns
        for pattern in self.SPAM_PATTERNS:
            matches = pattern.findall(combined)
            if matches:
                issues.append(f"CRITICAL: Spam pattern detected: {matches[0][:30]}")
                score -= 0.4

        # Check for repetitive content
        words = combined.lower().split()
        if len(words) > 10:
            unique_words = set(words)
            uniqueness = len(unique_words) / len(words)
            if uniqueness < 0.3:
                issues.append(f"Repetitive content detected (uniqueness: {uniqueness:.1%})")
                score -= 0.3

        return max(0.0, score), issues

    async def validate_batch(self, items: List[NewsItem]) -> Dict[str, ValidationResult]:
        """
        Validate a batch of news items.

        Args:
            items: List of NewsItem to validate

        Returns:
            Dict mapping item ID to ValidationResult
        """
        results = {}
        for item in items:
            try:
                result = await self.validate(item)
                results[str(item.id)] = result
            except Exception as e:
                self._logger.error(f"Validation error for item {item.id}: {e}")
                results[str(item.id)] = ValidationResult(
                    is_valid=False,
                    score=0.0,
                    issues=[f"Validation error: {str(e)}"]
                )
        return results

    def filter_valid(
        self,
        items: List[NewsItem],
        results: Dict[str, ValidationResult]
    ) -> List[NewsItem]:
        """
        Filter items to only valid ones.

        Args:
            items: List of NewsItem
            results: Validation results from validate_batch

        Returns:
            List of valid NewsItem
        """
        return [
            item for item in items
            if str(item.id) in results and results[str(item.id)].is_valid
        ]
