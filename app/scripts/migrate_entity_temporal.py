"""
Migration script to add temporal columns to tracked_entities and backfill data.

PULSE-VIZ-005: Add first_seen/last_seen columns
PULSE-VIZ-007: Backfill temporal data from entity_mentions

Run with:
    python -m app.scripts.migrate_entity_temporal
    OR
    cd /home/kento/The-Pulse && python app/scripts/migrate_entity_temporal.py
"""
import asyncio
import logging
import sys
from pathlib import Path

# Add project root to path for direct execution
project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from sqlalchemy import text
from app.database import engine as async_engine  # engine is the async engine

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def migrate_add_columns():
    """
    VIZ-005: Add first_seen and last_seen columns to tracked_entities.

    Idempotent - safe to run multiple times.
    """
    logger.info("VIZ-005: Adding temporal columns to tracked_entities...")

    async with async_engine.begin() as conn:
        # Add first_seen column if not exists
        await conn.execute(text("""
            ALTER TABLE tracked_entities
            ADD COLUMN IF NOT EXISTS first_seen TIMESTAMP WITH TIME ZONE;
        """))
        logger.info("  - Added first_seen column")

        # Add last_seen column if not exists
        await conn.execute(text("""
            ALTER TABLE tracked_entities
            ADD COLUMN IF NOT EXISTS last_seen TIMESTAMP WITH TIME ZONE;
        """))
        logger.info("  - Added last_seen column")

        # Add indexes for temporal queries (IF NOT EXISTS for idempotency)
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_tracked_entities_first_seen
            ON tracked_entities(first_seen);
        """))
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_tracked_entities_last_seen
            ON tracked_entities(last_seen);
        """))
        logger.info("  - Created temporal indexes")

    logger.info("VIZ-005: Migration complete")


async def backfill_temporal_data():
    """
    VIZ-007: Backfill first_seen/last_seen from entity_mentions.

    Uses MIN(timestamp) for first_seen and MAX(timestamp) for last_seen.
    Handles malformed timestamps gracefully by attempting to cast and skipping failures.
    Only updates entities that have NULL temporal fields.
    """
    logger.info("VIZ-007: Backfilling temporal data from entity_mentions...")

    async with async_engine.begin() as conn:
        # First, check how many entities need backfilling
        check_result = await conn.execute(text("""
            SELECT COUNT(*) FROM tracked_entities
            WHERE first_seen IS NULL OR last_seen IS NULL
        """))
        null_count = check_result.scalar()
        logger.info(f"  - Found {null_count} entities with NULL temporal fields")

        if null_count == 0:
            logger.info("  - No entities need backfilling")
            return

        # Backfill from entity_mentions timestamps
        # Use a safe cast that handles malformed timestamps
        result = await conn.execute(text("""
            UPDATE tracked_entities te
            SET
                first_seen = COALESCE(te.first_seen, agg.min_ts),
                last_seen = COALESCE(te.last_seen, agg.max_ts)
            FROM (
                SELECT
                    entity_id,
                    MIN(
                        CASE
                            WHEN timestamp ~ '^\\d{4}-\\d{2}-\\d{2}'
                            THEN timestamp::timestamptz
                            ELSE NULL
                        END
                    ) as min_ts,
                    MAX(
                        CASE
                            WHEN timestamp ~ '^\\d{4}-\\d{2}-\\d{2}'
                            THEN timestamp::timestamptz
                            ELSE NULL
                        END
                    ) as max_ts
                FROM entity_mentions
                GROUP BY entity_id
                HAVING MIN(
                    CASE
                        WHEN timestamp ~ '^\\d{4}-\\d{2}-\\d{2}'
                        THEN timestamp::timestamptz
                        ELSE NULL
                    END
                ) IS NOT NULL
            ) agg
            WHERE te.entity_id = agg.entity_id
            AND (te.first_seen IS NULL OR te.last_seen IS NULL)
        """))

        # Get count of updated rows
        updated_from_mentions = result.rowcount
        logger.info(f"  - Backfilled {updated_from_mentions} entities from mentions")

        # For entities with no valid mentions, use created_at as fallback
        # Handle both ISO string and timestamp formats in created_at
        fallback_result = await conn.execute(text("""
            UPDATE tracked_entities
            SET
                first_seen = CASE
                    WHEN created_at ~ '^\\d{4}-\\d{2}-\\d{2}'
                    THEN created_at::timestamptz
                    ELSE NOW()
                END,
                last_seen = CASE
                    WHEN created_at ~ '^\\d{4}-\\d{2}-\\d{2}'
                    THEN created_at::timestamptz
                    ELSE NOW()
                END
            WHERE first_seen IS NULL
        """))

        fallback_count = fallback_result.rowcount
        if fallback_count > 0:
            logger.info(f"  - Used created_at fallback for {fallback_count} entities without mentions")

        # Final verification
        verify_result = await conn.execute(text("""
            SELECT COUNT(*) FROM tracked_entities
            WHERE first_seen IS NULL OR last_seen IS NULL
        """))
        remaining_null = verify_result.scalar()

        if remaining_null > 0:
            logger.warning(f"  - {remaining_null} entities still have NULL temporal fields")
        else:
            logger.info("  - All entities now have temporal data")

    logger.info("VIZ-007: Backfill complete")


async def show_stats():
    """Show statistics about temporal data."""
    async with async_engine.begin() as conn:
        # Count entities with temporal data
        result = await conn.execute(text("""
            SELECT
                COUNT(*) as total,
                COUNT(first_seen) as with_first_seen,
                COUNT(last_seen) as with_last_seen,
                MIN(first_seen) as earliest,
                MAX(last_seen) as latest
            FROM tracked_entities
        """))
        row = result.fetchone()

        logger.info("\n=== Temporal Data Statistics ===")
        logger.info(f"Total entities: {row.total}")
        logger.info(f"With first_seen: {row.with_first_seen}")
        logger.info(f"With last_seen: {row.with_last_seen}")
        logger.info(f"Earliest first_seen: {row.earliest}")
        logger.info(f"Latest last_seen: {row.latest}")


async def migrate_and_backfill():
    """Run full migration: add columns then backfill."""
    await migrate_add_columns()
    await backfill_temporal_data()
    await show_stats()


if __name__ == "__main__":
    asyncio.run(migrate_and_backfill())
