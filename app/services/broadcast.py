"""
WebSocket Broadcast Manager for The Pulse.

Provides centralized event broadcasting to connected WebSocket clients.
Used for real-time updates of:
- Collection status and progress
- Processing pipeline events
- Briefing generation status
- System health updates
"""
import asyncio
from datetime import datetime, timezone
from typing import Dict, List, Set, Optional, Any, Callable
from dataclasses import dataclass, field
from enum import Enum
import logging
import json

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class EventType(str, Enum):
    """Types of broadcast events."""
    # Collection events
    COLLECTION_STARTED = "collection.started"
    COLLECTION_PROGRESS = "collection.progress"
    COLLECTION_COMPLETED = "collection.completed"
    COLLECTION_FAILED = "collection.failed"

    # Processing events
    PROCESSING_STARTED = "processing.started"
    PROCESSING_PROGRESS = "processing.progress"
    PROCESSING_COMPLETED = "processing.completed"

    # Briefing events
    BRIEFING_STARTED = "briefing.started"
    BRIEFING_PROGRESS = "briefing.progress"
    BRIEFING_COMPLETED = "briefing.completed"

    # System events
    SYSTEM_STATUS = "system.status"
    SYSTEM_HEALTH = "system.health"

    # Entity events
    ENTITY_DETECTED = "entity.detected"
    ENTITY_MENTION = "entity.mention"


@dataclass
class BroadcastEvent:
    """Event structure for broadcasting."""
    event_type: EventType
    data: Dict[str, Any]
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    source: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert event to dictionary for JSON serialization."""
        return {
            "type": "event",
            "event": self.event_type.value,
            "data": self.data,
            "timestamp": self.timestamp.isoformat(),
            "source": self.source,
        }

    def to_json(self) -> str:
        """Convert event to JSON string."""
        return json.dumps(self.to_dict())


class BroadcastManager:
    """
    Manages WebSocket connections and event broadcasting.

    Supports:
    - Connection tracking with optional client IDs
    - Topic-based subscriptions
    - Broadcast to all or filtered recipients
    - Event history for late-joining clients
    """

    def __init__(self, max_history: int = 100):
        """
        Initialize broadcast manager.

        Args:
            max_history: Maximum events to keep in history
        """
        self._connections: Dict[str, WebSocket] = {}
        self._subscriptions: Dict[str, Set[EventType]] = {}
        self._event_history: List[BroadcastEvent] = []
        self._max_history = max_history
        self._listeners: Dict[EventType, List[Callable]] = {}
        self._lock = asyncio.Lock()
        self._connection_counter = 0

    async def connect(
        self,
        websocket: WebSocket,
        client_id: Optional[str] = None,
        accept: bool = True
    ) -> str:
        """
        Register a WebSocket connection.

        Args:
            websocket: WebSocket connection to register
            client_id: Optional client identifier
            accept: Whether to accept the connection

        Returns:
            Client ID for this connection
        """
        async with self._lock:
            if accept:
                await websocket.accept()

            # Generate client ID if not provided
            if not client_id:
                self._connection_counter += 1
                client_id = f"client_{self._connection_counter}"

            self._connections[client_id] = websocket
            self._subscriptions[client_id] = set()

            logger.info(f"WebSocket connected: {client_id}")
            return client_id

    async def disconnect(self, client_id: str):
        """Remove a WebSocket connection."""
        async with self._lock:
            if client_id in self._connections:
                del self._connections[client_id]
                del self._subscriptions[client_id]
                logger.info(f"WebSocket disconnected: {client_id}")

    async def subscribe(
        self,
        client_id: str,
        event_types: List[EventType]
    ):
        """
        Subscribe a client to specific event types.

        Args:
            client_id: Client to subscribe
            event_types: List of event types to subscribe to
        """
        async with self._lock:
            if client_id in self._subscriptions:
                self._subscriptions[client_id].update(event_types)
                logger.debug(f"Client {client_id} subscribed to: {event_types}")

    async def unsubscribe(
        self,
        client_id: str,
        event_types: Optional[List[EventType]] = None
    ):
        """
        Unsubscribe a client from event types.

        Args:
            client_id: Client to unsubscribe
            event_types: List of event types to unsubscribe from.
                        If None, unsubscribes from all.
        """
        async with self._lock:
            if client_id in self._subscriptions:
                if event_types is None:
                    self._subscriptions[client_id].clear()
                else:
                    self._subscriptions[client_id] -= set(event_types)

    async def broadcast(
        self,
        event: BroadcastEvent,
        exclude: Optional[List[str]] = None
    ) -> int:
        """
        Broadcast an event to all subscribed clients.

        Args:
            event: Event to broadcast
            exclude: Client IDs to exclude from broadcast

        Returns:
            Number of clients that received the event
        """
        exclude = exclude or []
        sent_count = 0
        failed_clients = []

        # Add to history
        self._event_history.append(event)
        if len(self._event_history) > self._max_history:
            self._event_history = self._event_history[-self._max_history:]

        # Notify internal listeners
        if event.event_type in self._listeners:
            for listener in self._listeners[event.event_type]:
                try:
                    await listener(event)
                except Exception as e:
                    logger.error(f"Listener error for {event.event_type}: {e}")

        # Broadcast to WebSocket clients
        event_json = event.to_json()

        for client_id, websocket in list(self._connections.items()):
            if client_id in exclude:
                continue

            # Check subscription (empty set = subscribed to all)
            subscriptions = self._subscriptions.get(client_id, set())
            if subscriptions and event.event_type not in subscriptions:
                continue

            try:
                await websocket.send_text(event_json)
                sent_count += 1
            except Exception as e:
                logger.warning(f"Failed to send to {client_id}: {e}")
                failed_clients.append(client_id)

        # Clean up failed connections
        for client_id in failed_clients:
            await self.disconnect(client_id)

        logger.debug(
            f"Broadcast {event.event_type}: sent to {sent_count} clients"
        )
        return sent_count

    async def send_to(
        self,
        client_id: str,
        event: BroadcastEvent
    ) -> bool:
        """
        Send an event to a specific client.

        Args:
            client_id: Target client
            event: Event to send

        Returns:
            True if sent successfully
        """
        websocket = self._connections.get(client_id)
        if not websocket:
            return False

        try:
            await websocket.send_text(event.to_json())
            return True
        except Exception as e:
            logger.warning(f"Failed to send to {client_id}: {e}")
            await self.disconnect(client_id)
            return False

    def add_listener(
        self,
        event_type: EventType,
        callback: Callable
    ):
        """Add an internal listener for an event type."""
        if event_type not in self._listeners:
            self._listeners[event_type] = []
        self._listeners[event_type].append(callback)

    def remove_listener(
        self,
        event_type: EventType,
        callback: Callable
    ):
        """Remove an internal listener."""
        if event_type in self._listeners:
            self._listeners[event_type] = [
                cb for cb in self._listeners[event_type]
                if cb != callback
            ]

    def get_recent_events(
        self,
        event_types: Optional[List[EventType]] = None,
        limit: int = 10
    ) -> List[BroadcastEvent]:
        """
        Get recent events from history.

        Args:
            event_types: Filter by event types
            limit: Maximum events to return

        Returns:
            List of recent events
        """
        events = self._event_history

        if event_types:
            events = [e for e in events if e.event_type in event_types]

        return events[-limit:]

    @property
    def connection_count(self) -> int:
        """Get number of active connections."""
        return len(self._connections)

    def get_status(self) -> Dict[str, Any]:
        """Get broadcast manager status."""
        return {
            "active_connections": self.connection_count,
            "subscriptions": {
                client_id: [et.value for et in subs]
                for client_id, subs in self._subscriptions.items()
            },
            "event_history_size": len(self._event_history),
            "listener_counts": {
                et.value: len(listeners)
                for et, listeners in self._listeners.items()
            },
        }


# Singleton instance
_broadcast_manager: Optional[BroadcastManager] = None


def get_broadcast_manager() -> BroadcastManager:
    """Get or create the global broadcast manager instance."""
    global _broadcast_manager
    if _broadcast_manager is None:
        _broadcast_manager = BroadcastManager()
    return _broadcast_manager


# Convenience functions for common events
async def emit_collection_started(
    collector_name: str,
    source_type: str,
) -> int:
    """Emit collection started event."""
    manager = get_broadcast_manager()
    event = BroadcastEvent(
        event_type=EventType.COLLECTION_STARTED,
        data={
            "collector": collector_name,
            "source_type": source_type,
        },
        source=collector_name,
    )
    return await manager.broadcast(event)


async def emit_collection_progress(
    collector_name: str,
    items_collected: int,
    message: Optional[str] = None,
) -> int:
    """Emit collection progress event."""
    manager = get_broadcast_manager()
    event = BroadcastEvent(
        event_type=EventType.COLLECTION_PROGRESS,
        data={
            "collector": collector_name,
            "items_collected": items_collected,
            "message": message,
        },
        source=collector_name,
    )
    return await manager.broadcast(event)


async def emit_collection_completed(
    collector_name: str,
    run_id: str,
    items_collected: int,
    items_new: int,
    items_duplicate: int,
    duration_seconds: float,
) -> int:
    """Emit collection completed event."""
    manager = get_broadcast_manager()
    event = BroadcastEvent(
        event_type=EventType.COLLECTION_COMPLETED,
        data={
            "collector": collector_name,
            "run_id": run_id,
            "items_collected": items_collected,
            "items_new": items_new,
            "items_duplicate": items_duplicate,
            "duration_seconds": duration_seconds,
        },
        source=collector_name,
    )
    return await manager.broadcast(event)


async def emit_collection_failed(
    collector_name: str,
    error: str,
    run_id: Optional[str] = None,
) -> int:
    """Emit collection failed event."""
    manager = get_broadcast_manager()
    event = BroadcastEvent(
        event_type=EventType.COLLECTION_FAILED,
        data={
            "collector": collector_name,
            "error": error,
            "run_id": run_id,
        },
        source=collector_name,
    )
    return await manager.broadcast(event)


async def emit_system_status(
    status: Dict[str, Any]
) -> int:
    """Emit system status event."""
    manager = get_broadcast_manager()
    event = BroadcastEvent(
        event_type=EventType.SYSTEM_STATUS,
        data=status,
        source="system",
    )
    return await manager.broadcast(event)


async def emit_briefing_progress(
    briefing_id: str,
    stage: str,
    progress: float,
    message: Optional[str] = None,
) -> int:
    """Emit briefing generation progress event."""
    manager = get_broadcast_manager()
    event = BroadcastEvent(
        event_type=EventType.BRIEFING_PROGRESS,
        data={
            "briefing_id": briefing_id,
            "stage": stage,
            "progress": progress,
            "message": message,
        },
        source="synthesis",
    )
    return await manager.broadcast(event)
