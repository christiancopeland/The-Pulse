"""
Local Government API routes for The Pulse.

Provides endpoints for:
- Local government briefings
- Watch area management
- Activity queries (zoning, permits, property, court)
- Alerts
- Statistics
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional, List
from uuid import UUID
from datetime import datetime, timedelta
from pydantic import BaseModel, Field

from app.core.dependencies import get_db, get_local_user, LocalUser
from app.services.local_government import GeofenceService, LocalIntelligenceAnalyzer
from app.models.local_government import (
    WatchArea, LocalGovernmentAlert,
    CouncilMeeting, ZoningCase, BuildingPermit, PropertyTransaction, LocalCourtCase
)
from sqlalchemy import select, desc, func

router = APIRouter(prefix="/local", tags=["local-government"])


# ==================== Pydantic Models ====================

class WatchAreaCreate(BaseModel):
    """Request model for creating a watch area."""
    name: str = Field(..., max_length=100)
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    radius_miles: float = Field(1.0, ge=0.1, le=50)
    alert_types: List[str] = Field(default=['zoning', 'permits', 'property', 'court'])
    description: Optional[str] = None


class LocationCheck(BaseModel):
    """Request model for checking a location."""
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    alert_type: Optional[str] = None


# ==================== Briefing Endpoints ====================

@router.get("/briefing")
async def get_local_briefing(
    days: int = Query(7, ge=1, le=90, description="Days to include"),
    jurisdiction: Optional[str] = Query(None, description="Filter by jurisdiction"),
    db=Depends(get_db),
    current_user: LocalUser = Depends(get_local_user)
):
    """Get local government briefing."""
    analyzer = LocalIntelligenceAnalyzer(db, user_id=current_user.user_id)
    briefing = await analyzer.generate_local_briefing(days=days)

    return briefing


@router.get("/stats")
async def get_local_stats(
    jurisdiction: Optional[str] = Query(None),
    db=Depends(get_db),
    current_user: LocalUser = Depends(get_local_user)
):
    """Get local government activity statistics."""
    analyzer = LocalIntelligenceAnalyzer(db, user_id=current_user.user_id)
    stats = await analyzer.get_activity_stats(jurisdiction=jurisdiction)

    return stats


# ==================== Watch Area Endpoints ====================

@router.get("/watch-areas")
async def list_watch_areas(
    db=Depends(get_db),
    current_user: LocalUser = Depends(get_local_user)
):
    """List user's watch areas."""
    query = select(WatchArea).where(
        WatchArea.user_id == current_user.user_id
    ).order_by(WatchArea.name)

    result = await db.execute(query)
    areas = result.scalars().all()

    return {
        "count": len(areas),
        "watch_areas": [
            {
                "id": str(area.id),
                "name": area.name,
                "description": area.description,
                "latitude": area.latitude,
                "longitude": area.longitude,
                "radius_miles": area.radius_miles,
                "alert_types": area.alert_types,
                "is_active": area.is_active,
                "trigger_count": area.trigger_count,
                "last_triggered": area.last_triggered.isoformat() if area.last_triggered else None
            }
            for area in areas
        ]
    }


@router.post("/watch-areas")
async def create_watch_area(
    request: WatchAreaCreate,
    db=Depends(get_db),
    current_user: LocalUser = Depends(get_local_user)
):
    """Create a new watch area."""
    geofence = GeofenceService(db, user_id=current_user.user_id)

    watch_area = await geofence.create_watch_area(
        name=request.name,
        latitude=request.latitude,
        longitude=request.longitude,
        radius_miles=request.radius_miles,
        alert_types=request.alert_types,
        description=request.description
    )

    return {
        "id": str(watch_area.id),
        "name": watch_area.name,
        "message": "Watch area created"
    }


@router.post("/watch-areas/predefined/{area_key}")
async def create_predefined_watch_area(
    area_key: str,
    db=Depends(get_db),
    current_user: LocalUser = Depends(get_local_user)
):
    """Create a watch area from predefined locations."""
    geofence = GeofenceService(db, user_id=current_user.user_id)

    watch_area = await geofence.create_from_predefined(area_key)

    if not watch_area:
        raise HTTPException(status_code=404, detail=f"Unknown predefined area: {area_key}")

    return {
        "id": str(watch_area.id),
        "name": watch_area.name,
        "message": "Watch area created from predefined location"
    }


@router.get("/watch-areas/predefined")
async def list_predefined_areas(
    db=Depends(get_db),
    current_user: LocalUser = Depends(get_local_user)
):
    """List available predefined watch areas."""
    geofence = GeofenceService(db, user_id=current_user.user_id)
    return {"areas": geofence.get_predefined_areas()}


@router.delete("/watch-areas/{area_id}")
async def delete_watch_area(
    area_id: UUID,
    db=Depends(get_db),
    current_user: LocalUser = Depends(get_local_user)
):
    """Delete a watch area."""
    result = await db.execute(
        select(WatchArea).where(
            WatchArea.id == area_id,
            WatchArea.user_id == current_user.user_id
        )
    )
    area = result.scalar_one_or_none()

    if not area:
        raise HTTPException(status_code=404, detail="Watch area not found")

    await db.delete(area)
    await db.commit()

    return {"message": "Watch area deleted"}


@router.post("/check-location")
async def check_location(
    request: LocationCheck,
    db=Depends(get_db),
    current_user: LocalUser = Depends(get_local_user)
):
    """Check if a location is within any watch area."""
    geofence = GeofenceService(db, user_id=current_user.user_id)
    await geofence.load_watch_areas()

    triggered = geofence.check_location(
        latitude=request.latitude,
        longitude=request.longitude,
        alert_type=request.alert_type
    )

    return {
        "latitude": request.latitude,
        "longitude": request.longitude,
        "triggered_areas": triggered
    }


@router.post("/scan")
async def scan_recent_activity(
    hours: int = Query(24, ge=1, le=168),
    db=Depends(get_db),
    current_user: LocalUser = Depends(get_local_user)
):
    """Scan recent activity for watch area matches."""
    geofence = GeofenceService(db, user_id=current_user.user_id)
    matches = await geofence.scan_recent_activity(hours=hours)

    return matches


# ==================== Alert Endpoints ====================

@router.get("/alerts")
async def get_alerts(
    unread_only: bool = Query(False),
    limit: int = Query(50, ge=1, le=200),
    db=Depends(get_db),
    current_user: LocalUser = Depends(get_local_user)
):
    """Get local government alerts."""
    geofence = GeofenceService(db, user_id=current_user.user_id)
    alerts = await geofence.get_user_alerts(
        unread_only=unread_only,
        limit=limit
    )

    return {
        "count": len(alerts),
        "alerts": [
            {
                "id": str(alert.id),
                "type": alert.alert_type,
                "severity": alert.severity,
                "title": alert.title,
                "summary": alert.summary,
                "address": alert.address,
                "source_type": alert.source_type,
                "source_url": alert.source_url,
                "is_read": alert.is_read,
                "created_at": alert.created_at.isoformat()
            }
            for alert in alerts
        ]
    }


@router.post("/alerts/{alert_id}/read")
async def mark_alert_read(
    alert_id: UUID,
    db=Depends(get_db),
    current_user: LocalUser = Depends(get_local_user)
):
    """Mark an alert as read."""
    geofence = GeofenceService(db, user_id=current_user.user_id)
    success = await geofence.mark_alert_read(alert_id)

    if not success:
        raise HTTPException(status_code=404, detail="Alert not found")

    return {"message": "Alert marked as read"}


# ==================== Council Meeting Endpoints ====================

@router.get("/meetings")
async def list_council_meetings(
    jurisdiction: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db=Depends(get_db),
    current_user: LocalUser = Depends(get_local_user)
):
    """List council meetings."""
    query = select(CouncilMeeting).order_by(desc(CouncilMeeting.meeting_date))

    if jurisdiction:
        query = query.where(CouncilMeeting.jurisdiction == jurisdiction)

    query = query.limit(limit).offset(offset)

    result = await db.execute(query)
    meetings = result.scalars().all()

    return {
        "count": len(meetings),
        "meetings": [
            {
                "id": str(m.id),
                "jurisdiction": m.jurisdiction,
                "body": m.body,
                "meeting_type": m.meeting_type,
                "meeting_date": m.meeting_date.isoformat() if m.meeting_date else None,
                "agenda_url": m.agenda_url,
                "agenda_items_count": len(m.agenda_items or []),
                "summary": m.summary
            }
            for m in meetings
        ]
    }


@router.get("/meetings/{meeting_id}")
async def get_meeting(
    meeting_id: UUID,
    db=Depends(get_db),
    current_user: LocalUser = Depends(get_local_user)
):
    """Get meeting details."""
    result = await db.execute(
        select(CouncilMeeting).where(CouncilMeeting.id == meeting_id)
    )
    meeting = result.scalar_one_or_none()

    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")

    return {
        "id": str(meeting.id),
        "jurisdiction": meeting.jurisdiction,
        "body": meeting.body,
        "meeting_type": meeting.meeting_type,
        "meeting_date": meeting.meeting_date.isoformat() if meeting.meeting_date else None,
        "agenda_url": meeting.agenda_url,
        "agenda_text": meeting.agenda_text,
        "minutes_url": meeting.minutes_url,
        "video_url": meeting.video_url,
        "agenda_items": meeting.agenda_items,
        "votes": meeting.votes,
        "summary": meeting.summary
    }


# ==================== Zoning Case Endpoints ====================

@router.get("/zoning")
async def list_zoning_cases(
    jurisdiction: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db=Depends(get_db),
    current_user: LocalUser = Depends(get_local_user)
):
    """List zoning cases."""
    query = select(ZoningCase).order_by(desc(ZoningCase.filed_date))

    if jurisdiction:
        query = query.where(ZoningCase.jurisdiction == jurisdiction)
    if status:
        query = query.where(ZoningCase.status == status)

    query = query.limit(limit).offset(offset)

    result = await db.execute(query)
    cases = result.scalars().all()

    return {
        "count": len(cases),
        "cases": [
            {
                "id": str(c.id),
                "case_number": c.case_number,
                "jurisdiction": c.jurisdiction,
                "case_type": c.case_type,
                "address": c.address,
                "applicant": c.applicant,
                "status": c.status,
                "filed_date": c.filed_date.isoformat() if c.filed_date else None,
                "hearing_date": c.hearing_date.isoformat() if c.hearing_date else None
            }
            for c in cases
        ]
    }


# ==================== Permit Endpoints ====================

@router.get("/permits")
async def list_permits(
    jurisdiction: Optional[str] = Query(None),
    permit_type: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db=Depends(get_db),
    current_user: LocalUser = Depends(get_local_user)
):
    """List building permits."""
    query = select(BuildingPermit).order_by(desc(BuildingPermit.applied_date))

    if jurisdiction:
        query = query.where(BuildingPermit.jurisdiction == jurisdiction)
    if permit_type:
        query = query.where(BuildingPermit.permit_type == permit_type)

    query = query.limit(limit).offset(offset)

    result = await db.execute(query)
    permits = result.scalars().all()

    return {
        "count": len(permits),
        "permits": [
            {
                "id": str(p.id),
                "permit_number": p.permit_number,
                "jurisdiction": p.jurisdiction,
                "permit_type": p.permit_type,
                "address": p.address,
                "contractor": p.contractor,
                "estimated_value": p.estimated_value,
                "status": p.status,
                "applied_date": p.applied_date.isoformat() if p.applied_date else None
            }
            for p in permits
        ]
    }


# ==================== Property Transaction Endpoints ====================

@router.get("/property")
async def list_property_transactions(
    jurisdiction: Optional[str] = Query(None),
    min_price: Optional[float] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db=Depends(get_db),
    current_user: LocalUser = Depends(get_local_user)
):
    """List property transactions."""
    query = select(PropertyTransaction).order_by(desc(PropertyTransaction.sale_date))

    if jurisdiction:
        query = query.where(PropertyTransaction.jurisdiction == jurisdiction)
    if min_price:
        query = query.where(PropertyTransaction.sale_price >= min_price)

    query = query.limit(limit).offset(offset)

    result = await db.execute(query)
    transactions = result.scalars().all()

    return {
        "count": len(transactions),
        "transactions": [
            {
                "id": str(t.id),
                "parcel_id": t.parcel_id,
                "address": t.address,
                "jurisdiction": t.jurisdiction,
                "sale_price": t.sale_price,
                "sale_date": t.sale_date.isoformat() if t.sale_date else None,
                "grantor": t.grantor,
                "grantee": t.grantee
            }
            for t in transactions
        ]
    }


# ==================== Court Case Endpoints ====================

@router.get("/court")
async def list_court_cases(
    court: Optional[str] = Query(None),
    case_type: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db=Depends(get_db),
    current_user: LocalUser = Depends(get_local_user)
):
    """List court cases."""
    query = select(LocalCourtCase).order_by(desc(LocalCourtCase.filed_date))

    if court:
        query = query.where(LocalCourtCase.court == court)
    if case_type:
        query = query.where(LocalCourtCase.case_type == case_type)

    query = query.limit(limit).offset(offset)

    result = await db.execute(query)
    cases = result.scalars().all()

    return {
        "count": len(cases),
        "cases": [
            {
                "id": str(c.id),
                "case_number": c.case_number,
                "court": c.court,
                "case_type": c.case_type,
                "case_title": c.case_title,
                "status": c.status,
                "filed_date": c.filed_date.isoformat() if c.filed_date else None,
                "next_hearing": c.next_hearing.isoformat() if c.next_hearing else None
            }
            for c in cases
        ]
    }


# ==================== Entity Search ====================

@router.get("/search/entity/{entity_name}")
async def search_entity_mentions(
    entity_name: str,
    db=Depends(get_db),
    current_user: LocalUser = Depends(get_local_user)
):
    """Search for entity mentions across local government records."""
    analyzer = LocalIntelligenceAnalyzer(db, user_id=current_user.user_id)
    mentions = await analyzer.find_entity_mentions(entity_name)

    return mentions
