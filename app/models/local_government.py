"""
Local Government Models for The Pulse.

Tracks local government activity including:
- City/County council meetings
- Zoning and planning cases
- Building permits
- Property transactions
- Local court cases
"""

import uuid
from datetime import datetime, timezone
from typing import Optional, List

from sqlalchemy import (
    Column, String, Integer, Float, DateTime, Text, JSON, Date,
    ForeignKey, Boolean, Index
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.database import Base


class CouncilMeeting(Base):
    """City/County council meetings and agendas."""
    __tablename__ = "council_meetings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Meeting identification
    jurisdiction = Column(String(100), nullable=False, index=True)  # chattanooga, hamilton_county
    body = Column(String(100))  # city_council, county_commission, planning_commission
    meeting_type = Column(String(100))  # regular, special, committee, work_session
    meeting_date = Column(DateTime, index=True)

    # Content
    agenda_url = Column(Text)
    agenda_text = Column(Text)
    minutes_url = Column(Text)
    minutes_text = Column(Text)
    video_url = Column(Text)

    # Extracted items
    agenda_items = Column(JSON)  # [{item_number, title, description, action_type}, ...]
    votes = Column(JSON)  # [{item, result, yeas, nays, abstentions}, ...]
    ordinances = Column(JSON)  # [{number, title, status}, ...]
    resolutions = Column(JSON)  # [{number, title, status}, ...]

    # Analysis
    topics = Column(JSON)  # Extracted topic tags
    mentioned_addresses = Column(JSON)  # Addresses mentioned
    mentioned_entities = Column(JSON)  # Entity IDs mentioned
    summary = Column(Text)  # LLM-generated summary

    # Tracking
    collected_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    processed = Column(Integer, default=0)  # 0=pending, 1=processed, 2=failed
    last_updated = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index('ix_council_jurisdiction_date', 'jurisdiction', 'meeting_date'),
    )


class ZoningCase(Base):
    """Zoning and planning cases."""
    __tablename__ = "zoning_cases"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Case identification
    case_number = Column(String(50), unique=True, index=True)
    jurisdiction = Column(String(100), nullable=False, index=True)
    case_type = Column(String(100))  # rezoning, variance, subdivision, special_use, etc.

    # Location
    address = Column(Text)
    parcel_id = Column(String(50), index=True)
    latitude = Column(Float)
    longitude = Column(Float)
    neighborhood = Column(String(100))

    # Parties
    applicant = Column(String(255))
    applicant_representative = Column(String(255))
    owner = Column(String(255))

    # Case details
    description = Column(Text)
    current_zoning = Column(String(50))
    proposed_zoning = Column(String(50))
    acreage = Column(Float)
    proposed_use = Column(Text)

    # Status
    status = Column(String(50), index=True)  # pending, approved, denied, withdrawn, continued
    filed_date = Column(Date, index=True)
    hearing_date = Column(Date)
    decision_date = Column(Date)
    conditions = Column(JSON)  # Approval conditions

    # Hearing info
    staff_recommendation = Column(String(50))  # approve, deny, defer
    staff_report_url = Column(Text)
    public_comments = Column(JSON)  # [{date, commenter, position, summary}, ...]

    # Documents
    documents = Column(JSON)  # [{title, url, date, type}, ...]

    # Entity linking
    entity_ids = Column(JSON)  # Linked entity IDs

    # Collection
    source_url = Column(Text)
    collected_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    last_updated = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index('ix_zoning_jurisdiction_status', 'jurisdiction', 'status'),
        Index('ix_zoning_location', 'latitude', 'longitude'),
    )


class BuildingPermit(Base):
    """Building permits."""
    __tablename__ = "building_permits"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Permit identification
    permit_number = Column(String(50), unique=True, index=True)
    jurisdiction = Column(String(100), nullable=False, index=True)
    permit_type = Column(String(100))  # new_construction, renovation, demo, mechanical, etc.
    permit_subtype = Column(String(100))  # residential, commercial, industrial

    # Location
    address = Column(Text)
    parcel_id = Column(String(50), index=True)
    latitude = Column(Float)
    longitude = Column(Float)
    neighborhood = Column(String(100))

    # Parties
    owner = Column(String(255))
    contractor = Column(String(255), index=True)
    contractor_license = Column(String(50))
    architect = Column(String(255))

    # Project details
    description = Column(Text)
    estimated_value = Column(Float)
    square_footage = Column(Integer)
    stories = Column(Integer)
    units = Column(Integer)  # For multi-family

    # Status
    status = Column(String(50), index=True)  # applied, issued, final, expired, revoked
    applied_date = Column(Date, index=True)
    issued_date = Column(Date)
    expires_date = Column(Date)
    final_date = Column(Date)

    # Inspections
    inspections = Column(JSON)  # [{type, date, result, inspector, notes}, ...]

    # Fees
    permit_fee = Column(Float)
    total_fees = Column(Float)

    # Entity linking
    entity_ids = Column(JSON)

    # Collection
    source_url = Column(Text)
    collected_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    last_updated = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index('ix_permit_jurisdiction_status', 'jurisdiction', 'status'),
        Index('ix_permit_location', 'latitude', 'longitude'),
    )


class PropertyTransaction(Base):
    """Property sales and transfers."""
    __tablename__ = "property_transactions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Property identification
    parcel_id = Column(String(50), index=True)
    address = Column(Text)
    jurisdiction = Column(String(100), nullable=False, index=True)
    county = Column(String(100))

    # Location
    latitude = Column(Float)
    longitude = Column(Float)
    neighborhood = Column(String(100))

    # Transaction
    transaction_type = Column(String(50))  # sale, transfer, foreclosure, quit_claim
    sale_price = Column(Float, index=True)
    sale_date = Column(Date, index=True)

    # Parties
    grantor = Column(String(255), index=True)  # Seller
    grantee = Column(String(255), index=True)  # Buyer
    grantor_type = Column(String(50))  # individual, corporation, trust, estate
    grantee_type = Column(String(50))

    # Document
    deed_type = Column(String(50))  # warranty, quit_claim, special_warranty
    deed_book = Column(String(50))
    deed_page = Column(String(50))
    instrument_number = Column(String(50), unique=True)
    document_url = Column(Text)

    # Property details (from assessor)
    assessed_value = Column(Float)
    land_value = Column(Float)
    building_value = Column(Float)
    acreage = Column(Float)
    property_class = Column(String(50))  # residential, commercial, agricultural
    property_use = Column(String(100))

    # Mortgage info if available
    mortgage_amount = Column(Float)
    lender = Column(String(255))

    # Entity linking
    entity_ids = Column(JSON)

    # Collection
    source_url = Column(Text)
    collected_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index('ix_property_jurisdiction_date', 'jurisdiction', 'sale_date'),
        Index('ix_property_location', 'latitude', 'longitude'),
    )


class LocalCourtCase(Base):
    """Local court cases (civil, criminal, domestic, probate)."""
    __tablename__ = "local_court_cases"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Case identification
    case_number = Column(String(100), unique=True, index=True)
    court = Column(String(100), nullable=False, index=True)  # hamilton_county_circuit, etc.
    jurisdiction = Column(String(100))  # TN, GA
    county = Column(String(100))
    case_type = Column(String(50), index=True)  # civil, criminal, domestic, probate

    # Case info
    case_title = Column(Text)
    case_subtype = Column(String(100))  # breach_of_contract, personal_injury, etc.
    description = Column(Text)

    # Parties
    plaintiffs = Column(JSON)  # [{name, type, attorney}, ...]
    defendants = Column(JSON)  # [{name, type, attorney}, ...]
    other_parties = Column(JSON)  # Witnesses, intervenors, etc.

    # For criminal cases
    charges = Column(JSON)  # [{charge, statute, class, disposition}, ...]
    bail_amount = Column(Float)

    # Dates
    filed_date = Column(Date, index=True)
    closed_date = Column(Date)
    next_hearing = Column(DateTime)

    # Status
    status = Column(String(50), index=True)  # active, closed, dismissed, settled
    disposition = Column(Text)
    disposition_date = Column(Date)
    judgment_amount = Column(Float)

    # Events/Docket
    events = Column(JSON)  # [{date, type, description, document_url}, ...]

    # Documents
    documents = Column(JSON)  # [{title, url, date, type}, ...]

    # Entity linking
    entity_ids = Column(JSON)  # Linked entity IDs

    # Related cases
    related_cases = Column(JSON)  # Related case numbers

    # Collection
    source_url = Column(Text)
    collected_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    last_updated = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index('ix_court_court_status', 'court', 'status'),
        Index('ix_court_type_filed', 'case_type', 'filed_date'),
    )


class WatchArea(Base):
    """Geofenced watch areas for alerts."""
    __tablename__ = "watch_areas"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Owner
    user_id = Column(UUID(as_uuid=True), ForeignKey('users.user_id'), nullable=False)

    # Area definition
    name = Column(String(100), nullable=False)
    description = Column(Text)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    radius_miles = Column(Float, nullable=False, default=1.0)

    # Alert settings
    alert_types = Column(JSON)  # ['zoning', 'permits', 'property', 'court']
    is_active = Column(Boolean, default=True)
    notification_enabled = Column(Boolean, default=True)

    # Metadata
    color = Column(String(20), default='#00d4ff')  # For map display
    icon = Column(String(50), default='pin')

    # Tracking
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    last_triggered = Column(DateTime)
    trigger_count = Column(Integer, default=0)


class LocalGovernmentAlert(Base):
    """Alerts generated from local government activity."""
    __tablename__ = "local_government_alerts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Owner
    user_id = Column(UUID(as_uuid=True), ForeignKey('users.user_id'), nullable=False)

    # Alert details
    alert_type = Column(String(50), nullable=False)  # zoning, permit, property, court, meeting
    severity = Column(String(20), default='info')  # info, low, medium, high, critical
    title = Column(String(255), nullable=False)
    summary = Column(Text)

    # Source
    source_type = Column(String(50))  # zoning_case, building_permit, etc.
    source_id = Column(UUID(as_uuid=True))
    source_url = Column(Text)

    # Location
    address = Column(Text)
    latitude = Column(Float)
    longitude = Column(Float)
    watch_area_id = Column(UUID(as_uuid=True), ForeignKey('watch_areas.id'))

    # Status
    is_read = Column(Boolean, default=False)
    is_dismissed = Column(Boolean, default=False)

    # Tracking
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    read_at = Column(DateTime)

    # Relationships
    watch_area = relationship("WatchArea")
