"""
Migration script to update ArXiv papers from 'tech_ai' to 'research' category.

This script updates all existing ArXiv papers in the news_items table to use
the 'research' category instead of 'tech_ai'.

Usage:
    python -m app.scripts.migrate_arxiv_category
"""
import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.models.news_item import NewsItem
from app.core.config import settings


async def migrate_arxiv_categories():
    """Migrate ArXiv papers from tech_ai to research category."""

    # Create async engine
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        # First, count how many ArXiv papers have tech_ai category
        count_query = (
            select(func.count(NewsItem.id))
            .where(NewsItem.source_type == "arxiv")
            .where(NewsItem.categories.contains(["tech_ai"]))
        )
        result = await session.execute(count_query)
        count_before = result.scalar() or 0

        print(f"Found {count_before} ArXiv papers with 'tech_ai' category")

        if count_before == 0:
            print("No papers to migrate. Exiting.")
            return

        # Update all ArXiv papers with tech_ai to research
        # We need to replace the category in the JSONB array
        update_query = (
            update(NewsItem)
            .where(NewsItem.source_type == "arxiv")
            .where(NewsItem.categories.contains(["tech_ai"]))
            .values(categories=["research"])
        )

        result = await session.execute(update_query)
        await session.commit()

        print(f"Updated {result.rowcount} ArXiv papers to 'research' category")

        # Verify the migration
        verify_tech_ai = (
            select(func.count(NewsItem.id))
            .where(NewsItem.source_type == "arxiv")
            .where(NewsItem.categories.contains(["tech_ai"]))
        )
        result = await session.execute(verify_tech_ai)
        remaining_tech_ai = result.scalar() or 0

        verify_research = (
            select(func.count(NewsItem.id))
            .where(NewsItem.source_type == "arxiv")
            .where(NewsItem.categories.contains(["research"]))
        )
        result = await session.execute(verify_research)
        research_count = result.scalar() or 0

        print(f"\nVerification:")
        print(f"  ArXiv papers with 'tech_ai': {remaining_tech_ai}")
        print(f"  ArXiv papers with 'research': {research_count}")

        if remaining_tech_ai == 0 and research_count > 0:
            print("\nMigration successful!")
        else:
            print("\nWarning: Migration may not be complete. Please verify manually.")

    await engine.dispose()


if __name__ == "__main__":
    print("=" * 50)
    print("ArXiv Category Migration: tech_ai -> research")
    print("=" * 50)
    asyncio.run(migrate_arxiv_categories())
