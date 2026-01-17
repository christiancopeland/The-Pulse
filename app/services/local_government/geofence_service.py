"""
Geofence Service for location-based monitoring.

Provides:
- Geographic area definitions (watch areas)
- Distance calculations (Haversine formula)
- Alert triggering when activity occurs in watch areas
- Geocoding support for addresses
"""

import logging
from math import radians, cos, sin, asin, sqrt
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.models.local_government import (
    WatchArea, LocalGovernmentAlert,
    ZoningCase, BuildingPermit, PropertyTransaction, LocalCourtCase
)

logger = logging.getLogger(__name__)


# Predefined areas for Chattanooga/Hamilton County region
PREDEFINED_AREAS = {
    "downtown_chattanooga": {
        "name": "Downtown Chattanooga",
        "latitude": 35.0456,
        "longitude": -85.3097,
        "radius_miles": 1.5,
        "description": "Chattanooga downtown business district"
    },
    "north_shore": {
        "name": "North Shore",
        "latitude": 35.0600,
        "longitude": -85.3100,
        "radius_miles": 1.0,
        "description": "North Shore/Coolidge Park area"
    },
    "southside": {
        "name": "Southside",
        "latitude": 35.0300,
        "longitude": -85.3000,
        "radius_miles": 1.0,
        "description": "Southside/St. Elmo area"
    },
    "east_brainerd": {
        "name": "East Brainerd",
        "latitude": 35.0100,
        "longitude": -85.1500,
        "radius_miles": 2.0,
        "description": "East Brainerd corridor"
    },
    "red_bank": {
        "name": "Red Bank",
        "latitude": 35.1100,
        "longitude": -85.2900,
        "radius_miles": 1.5,
        "description": "Red Bank area"
    },
    "hixson": {
        "name": "Hixson",
        "latitude": 35.1300,
        "longitude": -85.2400,
        "radius_miles": 2.5,
        "description": "Hixson/North Hamilton County"
    },
    "fort_oglethorpe": {
        "name": "Fort Oglethorpe",
        "latitude": 34.9500,
        "longitude": -85.2600,
        "radius_miles": 2.0,
        "description": "Fort Oglethorpe, GA"
    },
    "ringgold": {
        "name": "Ringgold",
        "latitude": 34.9160,
        "longitude": -85.1080,
        "radius_miles": 2.0,
        "description": "Ringgold, GA (Catoosa County)"
    },
    "chickamauga": {
        "name": "Chickamauga",
        "latitude": 34.8712,
        "longitude": -85.2908,
        "radius_miles": 2.0,
        "description": "Chickamauga, GA (Walker County)"
    }
}


class GeofenceService:
    """
    Monitor activity within geographic boundaries.

    Uses Haversine formula for accurate distance calculations
    and supports custom watch areas with configurable radii.
    """

    def __init__(self, db_session: AsyncSession, user_id: Optional[UUID] = None):
        """
        Initialize the geofence service.

        Args:
            db_session: Async SQLAlchemy session
            user_id: User ID for filtering watch areas
        """
        self.db = db_session
        self.user_id = user_id
        self._watch_areas: List[Dict] = []

    async def load_watch_areas(self) -> int:
        """
        Load watch areas from database.

        Returns:
            Number of watch areas loaded
        """
        query = select(WatchArea).where(WatchArea.is_active == True)
        if self.user_id:
            query = query.where(WatchArea.user_id == self.user_id)

        result = await self.db.execute(query)
        areas = result.scalars().all()

        self._watch_areas = [
            {
                "id": str(area.id),
                "name": area.name,
                "latitude": area.latitude,
                "longitude": area.longitude,
                "radius_miles": area.radius_miles,
                "alert_types": area.alert_types or []
            }
            for area in areas
        ]

        logger.info(f"Loaded {len(self._watch_areas)} watch areas")
        return len(self._watch_areas)

    async def create_watch_area(
        self,
        name: str,
        latitude: float,
        longitude: float,
        radius_miles: float = 1.0,
        alert_types: Optional[List[str]] = None,
        description: Optional[str] = None
    ) -> WatchArea:
        """
        Create a new watch area.

        Args:
            name: Name for the watch area
            latitude: Center latitude
            longitude: Center longitude
            radius_miles: Radius in miles
            alert_types: Types of alerts to trigger
            description: Optional description

        Returns:
            Created WatchArea
        """
        watch_area = WatchArea(
            user_id=self.user_id,
            name=name,
            latitude=latitude,
            longitude=longitude,
            radius_miles=radius_miles,
            alert_types=alert_types or ['zoning', 'permits', 'property', 'court'],
            description=description
        )

        self.db.add(watch_area)
        await self.db.commit()
        await self.db.refresh(watch_area)

        # Update local cache
        self._watch_areas.append({
            "id": str(watch_area.id),
            "name": watch_area.name,
            "latitude": watch_area.latitude,
            "longitude": watch_area.longitude,
            "radius_miles": watch_area.radius_miles,
            "alert_types": watch_area.alert_types
        })

        logger.info(f"Created watch area: {name} at ({latitude}, {longitude})")
        return watch_area

    async def create_from_predefined(self, area_key: str) -> Optional[WatchArea]:
        """
        Create a watch area from predefined locations.

        Args:
            area_key: Key from PREDEFINED_AREAS

        Returns:
            Created WatchArea or None if key not found
        """
        if area_key not in PREDEFINED_AREAS:
            logger.warning(f"Unknown predefined area: {area_key}")
            return None

        area = PREDEFINED_AREAS[area_key]
        return await self.create_watch_area(
            name=area["name"],
            latitude=area["latitude"],
            longitude=area["longitude"],
            radius_miles=area["radius_miles"],
            description=area.get("description")
        )

    def check_location(
        self,
        latitude: float,
        longitude: float,
        alert_type: Optional[str] = None
    ) -> List[Dict]:
        """
        Check if a location is within any watch area.

        Args:
            latitude: Location latitude
            longitude: Location longitude
            alert_type: Optional filter for alert type

        Returns:
            List of triggered watch areas with distances
        """
        triggered = []

        for area in self._watch_areas:
            # Filter by alert type if specified
            if alert_type and alert_type not in area.get("alert_types", []):
                continue

            distance = self._haversine(
                latitude, longitude,
                area["latitude"], area["longitude"]
            )

            if distance <= area["radius_miles"]:
                triggered.append({
                    "id": area["id"],
                    "name": area["name"],
                    "distance_miles": round(distance, 2),
                    "radius_miles": area["radius_miles"]
                })

        return triggered

    async def check_and_alert(
        self,
        latitude: float,
        longitude: float,
        alert_type: str,
        title: str,
        summary: str,
        source_type: str,
        source_id: UUID,
        source_url: Optional[str] = None,
        address: Optional[str] = None
    ) -> List[LocalGovernmentAlert]:
        """
        Check location and create alerts for triggered watch areas.

        Args:
            latitude: Location latitude
            longitude: Location longitude
            alert_type: Type of alert
            title: Alert title
            summary: Alert summary
            source_type: Source model type
            source_id: Source record ID
            source_url: Optional URL
            address: Optional address

        Returns:
            List of created alerts
        """
        triggered = self.check_location(latitude, longitude, alert_type)

        if not triggered:
            return []

        alerts = []
        for area in triggered:
            alert = LocalGovernmentAlert(
                user_id=self.user_id,
                alert_type=alert_type,
                title=title,
                summary=summary,
                source_type=source_type,
                source_id=source_id,
                source_url=source_url,
                address=address,
                latitude=latitude,
                longitude=longitude,
                watch_area_id=UUID(area["id"])
            )

            self.db.add(alert)
            alerts.append(alert)

            # Update watch area trigger count
            await self.db.execute(
                WatchArea.__table__.update()
                .where(WatchArea.id == UUID(area["id"]))
                .values(
                    last_triggered=datetime.now(timezone.utc),
                    trigger_count=WatchArea.trigger_count + 1
                )
            )

        await self.db.commit()
        logger.info(f"Created {len(alerts)} alerts for location ({latitude}, {longitude})")

        return alerts

    async def scan_recent_activity(self, hours: int = 24) -> Dict:
        """
        Scan recent activity for watch area matches.

        Args:
            hours: Hours of activity to scan

        Returns:
            Summary of matches found
        """
        from datetime import timedelta

        await self.load_watch_areas()

        if not self._watch_areas:
            return {"watch_areas": 0, "matches": 0}

        # Use naive datetime for PostgreSQL TIMESTAMP WITHOUT TIME ZONE columns
        cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=hours)
        matches = {
            "zoning": [],
            "permits": [],
            "property": [],
            "total": 0
        }

        # Scan zoning cases
        zoning_query = select(ZoningCase).where(
            and_(
                ZoningCase.collected_at >= cutoff,
                ZoningCase.latitude.isnot(None)
            )
        )
        zoning_result = await self.db.execute(zoning_query)

        for case in zoning_result.scalars():
            triggered = self.check_location(case.latitude, case.longitude, "zoning")
            if triggered:
                matches["zoning"].append({
                    "case_number": case.case_number,
                    "address": case.address,
                    "type": case.case_type,
                    "triggered_areas": triggered
                })
                matches["total"] += 1

        # Scan permits
        permit_query = select(BuildingPermit).where(
            and_(
                BuildingPermit.collected_at >= cutoff,
                BuildingPermit.latitude.isnot(None)
            )
        )
        permit_result = await self.db.execute(permit_query)

        for permit in permit_result.scalars():
            triggered = self.check_location(permit.latitude, permit.longitude, "permits")
            if triggered:
                matches["permits"].append({
                    "permit_number": permit.permit_number,
                    "address": permit.address,
                    "type": permit.permit_type,
                    "triggered_areas": triggered
                })
                matches["total"] += 1

        # Scan property transactions
        property_query = select(PropertyTransaction).where(
            and_(
                PropertyTransaction.collected_at >= cutoff,
                PropertyTransaction.latitude.isnot(None)
            )
        )
        property_result = await self.db.execute(property_query)

        for prop in property_result.scalars():
            triggered = self.check_location(prop.latitude, prop.longitude, "property")
            if triggered:
                matches["property"].append({
                    "parcel_id": prop.parcel_id,
                    "address": prop.address,
                    "sale_price": prop.sale_price,
                    "triggered_areas": triggered
                })
                matches["total"] += 1

        matches["watch_areas"] = len(self._watch_areas)
        return matches

    async def get_user_alerts(
        self,
        unread_only: bool = False,
        limit: int = 50
    ) -> List[LocalGovernmentAlert]:
        """
        Get alerts for the current user.

        Args:
            unread_only: Only return unread alerts
            limit: Maximum number to return

        Returns:
            List of alerts
        """
        query = select(LocalGovernmentAlert).where(
            LocalGovernmentAlert.user_id == self.user_id,
            LocalGovernmentAlert.is_dismissed == False
        )

        if unread_only:
            query = query.where(LocalGovernmentAlert.is_read == False)

        query = query.order_by(LocalGovernmentAlert.created_at.desc()).limit(limit)

        result = await self.db.execute(query)
        return result.scalars().all()

    async def mark_alert_read(self, alert_id: UUID) -> bool:
        """Mark an alert as read."""
        result = await self.db.execute(
            select(LocalGovernmentAlert).where(
                LocalGovernmentAlert.id == alert_id,
                LocalGovernmentAlert.user_id == self.user_id
            )
        )
        alert = result.scalar_one_or_none()

        if alert:
            alert.is_read = True
            alert.read_at = datetime.now(timezone.utc)
            await self.db.commit()
            return True

        return False

    def get_predefined_areas(self) -> Dict:
        """Get list of predefined watch areas."""
        return PREDEFINED_AREAS

    def _haversine(
        self,
        lat1: float,
        lon1: float,
        lat2: float,
        lon2: float
    ) -> float:
        """
        Calculate the great circle distance between two points in miles.

        Uses the Haversine formula for accurate Earth surface distances.

        Args:
            lat1, lon1: First point coordinates
            lat2, lon2: Second point coordinates

        Returns:
            Distance in miles
        """
        R = 3956  # Earth radius in miles

        lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])

        dlat = lat2 - lat1
        dlon = lon2 - lon1

        a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
        c = 2 * asin(sqrt(a))

        return R * c

    def calculate_bounding_box(
        self,
        latitude: float,
        longitude: float,
        radius_miles: float
    ) -> Tuple[float, float, float, float]:
        """
        Calculate bounding box for a radius around a point.

        Useful for database queries before precise distance check.

        Args:
            latitude: Center latitude
            longitude: Center longitude
            radius_miles: Radius in miles

        Returns:
            Tuple of (min_lat, max_lat, min_lon, max_lon)
        """
        # Approximate: 1 degree latitude = 69 miles
        # Longitude varies with latitude
        lat_delta = radius_miles / 69.0
        lon_delta = radius_miles / (69.0 * cos(radians(latitude)))

        return (
            latitude - lat_delta,
            latitude + lat_delta,
            longitude - lon_delta,
            longitude + lon_delta
        )
