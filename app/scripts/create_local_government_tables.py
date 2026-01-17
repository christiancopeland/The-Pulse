#!/usr/bin/env python
"""
Create local government tables in the database.

Usage:
    python -m app.scripts.create_local_government_tables

Or from project root:
    python app/scripts/create_local_government_tables.py
"""

import asyncio
import logging
import sys
from pathlib import Path

# Add project root to path for direct execution
project_root = Path(__file__).resolve().parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from sqlalchemy import text
from app.database import engine

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def create_tables():
    """Create local government tables."""
    async with engine.begin() as conn:
        # Council Meetings
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS council_meetings (
                id UUID PRIMARY KEY,
                jurisdiction VARCHAR(100) NOT NULL,
                body VARCHAR(100),
                meeting_type VARCHAR(100),
                meeting_date TIMESTAMP,
                agenda_url TEXT,
                agenda_text TEXT,
                minutes_url TEXT,
                minutes_text TEXT,
                video_url TEXT,
                agenda_items JSONB,
                votes JSONB,
                ordinances JSONB,
                resolutions JSONB,
                topics JSONB,
                mentioned_addresses JSONB,
                mentioned_entities JSONB,
                summary TEXT,
                collected_at TIMESTAMP DEFAULT NOW(),
                processed INTEGER DEFAULT 0,
                last_updated TIMESTAMP DEFAULT NOW()
            )
        """))
        logger.info("Created council_meetings table")

        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_council_jurisdiction_date
            ON council_meetings (jurisdiction, meeting_date)
        """))

        # Zoning Cases
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS zoning_cases (
                id UUID PRIMARY KEY,
                case_number VARCHAR(50) UNIQUE,
                jurisdiction VARCHAR(100) NOT NULL,
                case_type VARCHAR(100),
                address TEXT,
                parcel_id VARCHAR(50),
                latitude FLOAT,
                longitude FLOAT,
                neighborhood VARCHAR(100),
                applicant VARCHAR(255),
                applicant_representative VARCHAR(255),
                owner VARCHAR(255),
                description TEXT,
                current_zoning VARCHAR(50),
                proposed_zoning VARCHAR(50),
                acreage FLOAT,
                proposed_use TEXT,
                status VARCHAR(50),
                filed_date DATE,
                hearing_date DATE,
                decision_date DATE,
                conditions JSONB,
                staff_recommendation VARCHAR(50),
                staff_report_url TEXT,
                public_comments JSONB,
                documents JSONB,
                entity_ids JSONB,
                source_url TEXT,
                collected_at TIMESTAMP DEFAULT NOW(),
                last_updated TIMESTAMP DEFAULT NOW()
            )
        """))
        logger.info("Created zoning_cases table")

        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_zoning_jurisdiction_status
            ON zoning_cases (jurisdiction, status)
        """))
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_zoning_location
            ON zoning_cases (latitude, longitude)
        """))

        # Building Permits
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS building_permits (
                id UUID PRIMARY KEY,
                permit_number VARCHAR(50) UNIQUE,
                jurisdiction VARCHAR(100) NOT NULL,
                permit_type VARCHAR(100),
                permit_subtype VARCHAR(100),
                address TEXT,
                parcel_id VARCHAR(50),
                latitude FLOAT,
                longitude FLOAT,
                neighborhood VARCHAR(100),
                owner VARCHAR(255),
                contractor VARCHAR(255),
                contractor_license VARCHAR(50),
                architect VARCHAR(255),
                description TEXT,
                estimated_value FLOAT,
                square_footage INTEGER,
                stories INTEGER,
                units INTEGER,
                status VARCHAR(50),
                applied_date DATE,
                issued_date DATE,
                expires_date DATE,
                final_date DATE,
                inspections JSONB,
                permit_fee FLOAT,
                total_fees FLOAT,
                entity_ids JSONB,
                source_url TEXT,
                collected_at TIMESTAMP DEFAULT NOW(),
                last_updated TIMESTAMP DEFAULT NOW()
            )
        """))
        logger.info("Created building_permits table")

        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_permit_jurisdiction_status
            ON building_permits (jurisdiction, status)
        """))
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_permit_location
            ON building_permits (latitude, longitude)
        """))

        # Property Transactions
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS property_transactions (
                id UUID PRIMARY KEY,
                parcel_id VARCHAR(50),
                address TEXT,
                jurisdiction VARCHAR(100) NOT NULL,
                county VARCHAR(100),
                latitude FLOAT,
                longitude FLOAT,
                neighborhood VARCHAR(100),
                transaction_type VARCHAR(50),
                sale_price FLOAT,
                sale_date DATE,
                grantor VARCHAR(255),
                grantee VARCHAR(255),
                grantor_type VARCHAR(50),
                grantee_type VARCHAR(50),
                deed_type VARCHAR(50),
                deed_book VARCHAR(50),
                deed_page VARCHAR(50),
                instrument_number VARCHAR(50) UNIQUE,
                document_url TEXT,
                assessed_value FLOAT,
                land_value FLOAT,
                building_value FLOAT,
                acreage FLOAT,
                property_class VARCHAR(50),
                property_use VARCHAR(100),
                mortgage_amount FLOAT,
                lender VARCHAR(255),
                entity_ids JSONB,
                source_url TEXT,
                collected_at TIMESTAMP DEFAULT NOW()
            )
        """))
        logger.info("Created property_transactions table")

        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_property_jurisdiction_date
            ON property_transactions (jurisdiction, sale_date)
        """))
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_property_location
            ON property_transactions (latitude, longitude)
        """))

        # Local Court Cases
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS local_court_cases (
                id UUID PRIMARY KEY,
                case_number VARCHAR(100) UNIQUE,
                court VARCHAR(100) NOT NULL,
                jurisdiction VARCHAR(100),
                county VARCHAR(100),
                case_type VARCHAR(50),
                case_title TEXT,
                case_subtype VARCHAR(100),
                description TEXT,
                plaintiffs JSONB,
                defendants JSONB,
                other_parties JSONB,
                charges JSONB,
                bail_amount FLOAT,
                filed_date DATE,
                closed_date DATE,
                next_hearing TIMESTAMP,
                status VARCHAR(50),
                disposition TEXT,
                disposition_date DATE,
                judgment_amount FLOAT,
                events JSONB,
                documents JSONB,
                entity_ids JSONB,
                related_cases JSONB,
                source_url TEXT,
                collected_at TIMESTAMP DEFAULT NOW(),
                last_updated TIMESTAMP DEFAULT NOW()
            )
        """))
        logger.info("Created local_court_cases table")

        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_court_court_status
            ON local_court_cases (court, status)
        """))
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_court_type_filed
            ON local_court_cases (case_type, filed_date)
        """))

        # Watch Areas
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS watch_areas (
                id UUID PRIMARY KEY,
                user_id UUID NOT NULL REFERENCES users(user_id),
                name VARCHAR(100) NOT NULL,
                description TEXT,
                latitude FLOAT NOT NULL,
                longitude FLOAT NOT NULL,
                radius_miles FLOAT NOT NULL DEFAULT 1.0,
                alert_types JSONB,
                is_active BOOLEAN DEFAULT TRUE,
                notification_enabled BOOLEAN DEFAULT TRUE,
                color VARCHAR(20) DEFAULT '#00d4ff',
                icon VARCHAR(50) DEFAULT 'pin',
                created_at TIMESTAMP DEFAULT NOW(),
                last_triggered TIMESTAMP,
                trigger_count INTEGER DEFAULT 0
            )
        """))
        logger.info("Created watch_areas table")

        # Local Government Alerts
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS local_government_alerts (
                id UUID PRIMARY KEY,
                user_id UUID NOT NULL REFERENCES users(user_id),
                alert_type VARCHAR(50) NOT NULL,
                severity VARCHAR(20) DEFAULT 'info',
                title VARCHAR(255) NOT NULL,
                summary TEXT,
                source_type VARCHAR(50),
                source_id UUID,
                source_url TEXT,
                address TEXT,
                latitude FLOAT,
                longitude FLOAT,
                watch_area_id UUID REFERENCES watch_areas(id),
                is_read BOOLEAN DEFAULT FALSE,
                is_dismissed BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT NOW(),
                read_at TIMESTAMP
            )
        """))
        logger.info("Created local_government_alerts table")

        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS ix_alerts_user_read
            ON local_government_alerts (user_id, is_read)
        """))

    logger.info("All local government tables created successfully")


if __name__ == "__main__":
    asyncio.run(create_tables())
