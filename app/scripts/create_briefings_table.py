"""
Create briefings table for Phase 4: Synthesis Engine.

Run this script to add the briefings table:
    python -m app.scripts.create_briefings_table
"""
import asyncio
import sys
sys.path.insert(0, '.')

from sqlalchemy import text
from app.database import engine


CREATE_BRIEFINGS_TABLE = """
CREATE TABLE IF NOT EXISTS briefings (
    id VARCHAR(36) PRIMARY KEY,
    generated_at TIMESTAMP WITH TIME ZONE NOT NULL,
    period_start TIMESTAMP WITH TIME ZONE NOT NULL,
    period_end TIMESTAMP WITH TIME ZONE NOT NULL,
    title VARCHAR(500) NOT NULL,
    executive_summary TEXT NOT NULL,
    sections JSONB DEFAULT '[]'::jsonb,
    entity_highlights JSONB DEFAULT '[]'::jsonb,
    audio_path VARCHAR(500),
    briefing_metadata JSONB DEFAULT '{}'::jsonb,
    user_id VARCHAR(36),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
)
"""

CREATE_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_briefings_user_id ON briefings(user_id)",
    "CREATE INDEX IF NOT EXISTS idx_briefings_generated_at ON briefings(generated_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_briefings_period ON briefings(period_start, period_end)",
]


async def create_briefings_table():
    """Create the briefings table."""
    print("Creating briefings table...")

    async with engine.begin() as conn:
        await conn.execute(text(CREATE_BRIEFINGS_TABLE))
        for index_sql in CREATE_INDEXES:
            await conn.execute(text(index_sql))

    print("Briefings table created successfully!")


if __name__ == "__main__":
    asyncio.run(create_briefings_table())
