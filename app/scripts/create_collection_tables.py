"""
Database migration script for Phase 1: Storage Foundation

Creates all tables required for The Pulse including the new SITREP integration tables:
- news_items: Unified model for all collected content
- collection_runs: Track collection execution history
- entity_relationships: Relationships between tracked entities

Run this script to apply the migration:
    python app/scripts/create_collection_tables.py

Or import and call apply_migration() from your application.
"""
import asyncio
import logging
from sqlalchemy import text

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def apply_migration(engine):
    """Apply the collection tables migration."""

    # Import all models to register them with Base
    from app.models.user import User
    from app.models.project import ResearchProject, ProjectFolder, Document
    from app.models.conversation import Conversation, Message
    from app.models.news_article import NewsArticle
    from app.models.entities import TrackedEntity, EntityMention, EntityRelationship
    from app.models.news_item import NewsItem, CollectionRun
    from app.database import Base

    async with engine.begin() as conn:
        logger.info("=" * 60)
        logger.info("Starting The Pulse database migration")
        logger.info("=" * 60)

        # Enable required PostgreSQL extensions
        logger.info("Enabling PostgreSQL extensions...")
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm;"))
        logger.info("pg_trgm extension enabled")

        # Create all tables from SQLAlchemy models
        logger.info("Creating all tables from SQLAlchemy models...")
        await conn.run_sync(Base.metadata.create_all)
        logger.info("All tables created successfully")

        # Add any additional columns or indexes not in models
        logger.info("Applying additional migrations...")

        # Add openai_api_key column to users if not exists
        await conn.execute(text("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_name='users' AND column_name='openai_api_key'
                ) THEN
                    ALTER TABLE users ADD COLUMN openai_api_key VARCHAR;
                END IF;
            END $$;
        """))
        logger.info("Checked users.openai_api_key column")

        # Add news_item_id column to entity_mentions if not exists
        await conn.execute(text("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_name='entity_mentions' AND column_name='news_item_id'
                ) THEN
                    ALTER TABLE entity_mentions
                    ADD COLUMN news_item_id UUID REFERENCES news_items(id) ON DELETE CASCADE;
                END IF;
            END $$;
        """))
        logger.info("Checked entity_mentions.news_item_id column")

        # Update check constraint on entity_mentions to allow news_item_id
        await conn.execute(text("""
            DO $$
            BEGIN
                -- Drop old constraint if it exists
                IF EXISTS (
                    SELECT 1 FROM pg_constraint
                    WHERE conname = 'check_one_source_id'
                ) THEN
                    ALTER TABLE entity_mentions DROP CONSTRAINT check_one_source_id;
                END IF;

                -- Add new constraint that includes news_item_id
                ALTER TABLE entity_mentions ADD CONSTRAINT check_one_source_id
                CHECK (
                    (CASE WHEN document_id IS NOT NULL THEN 1 ELSE 0 END +
                     CASE WHEN news_article_id IS NOT NULL THEN 1 ELSE 0 END +
                     CASE WHEN news_item_id IS NOT NULL THEN 1 ELSE 0 END) = 1
                );
            EXCEPTION
                WHEN duplicate_object THEN
                    NULL; -- Constraint already exists
            END $$;
        """))
        logger.info("Updated entity_mentions check constraint")

        # Create GIN index for news_items categories if not exists
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_news_items_categories_gin
            ON news_items USING GIN(categories);
        """))
        logger.info("Checked GIN index on news_items.categories")

        logger.info("=" * 60)
        logger.info("Migration completed successfully!")
        logger.info("=" * 60)

        # Print table summary
        result = await conn.execute(text("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
            ORDER BY table_name;
        """))
        tables = [row[0] for row in result.fetchall()]
        logger.info(f"Tables in database: {', '.join(tables)}")


async def rollback_migration(engine):
    """Rollback the collection tables migration (for development/testing)."""

    async with engine.begin() as conn:
        logger.warning("Rolling back Phase 1 migration...")

        # Drop in reverse order of dependencies
        await conn.execute(text("DROP TABLE IF EXISTS entity_relationships CASCADE;"))
        await conn.execute(text("DROP TABLE IF EXISTS collection_runs CASCADE;"))
        await conn.execute(text("DROP TABLE IF EXISTS news_items CASCADE;"))

        # Remove added column from entity_mentions
        await conn.execute(text("""
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_name='entity_mentions' AND column_name='news_item_id'
                ) THEN
                    ALTER TABLE entity_mentions DROP COLUMN news_item_id;
                END IF;
            END $$;
        """))

        logger.warning("Rollback completed - new tables dropped")


async def main():
    """Run migration as standalone script."""
    import sys
    from pathlib import Path

    # Add project root to path
    project_root = Path(__file__).parent.parent.parent
    sys.path.insert(0, str(project_root))

    # Load .env file
    env_file = project_root / '.env'
    if env_file.exists():
        try:
            from dotenv import load_dotenv
            load_dotenv(env_file)
            logger.info(f"Loaded environment from {env_file}")
        except ImportError:
            logger.warning("python-dotenv not installed, using system env vars")

    # Now import database after env is loaded
    from app.database import engine

    if len(sys.argv) > 1 and sys.argv[1] == '--rollback':
        await rollback_migration(engine)
    else:
        await apply_migration(engine)


if __name__ == "__main__":
    asyncio.run(main())
