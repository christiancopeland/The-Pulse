"""
Extraction Queue Manager for Entity Extraction Rate Limiting.

Manages entity extraction request queueing and rate limiting to ensure
only one extraction runs at a time and provides status feedback.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from uuid import UUID, uuid4
import asyncio


@dataclass
class ExtractionTask:
    """Represents an entity extraction task with progress tracking."""
    request_id: UUID
    status: str  # "pending", "in_progress", "completed", "failed"
    queue_position: int
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    items_total: int = 0
    items_processed: int = 0
    error_message: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "request_id": str(self.request_id),
            "status": self.status,
            "queue_position": self.queue_position,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "items_total": self.items_total,
            "items_processed": self.items_processed,
            "progress": f"{self.items_processed}/{self.items_total}" if self.items_total > 0 else "0/0",
            "error_message": self.error_message,
        }


class ExtractionQueueManager:
    """
    Manages entity extraction request queueing and rate limiting.
    Ensures only one extraction runs at a time.
    """

    def __init__(self, max_concurrent: int = 1):
        """
        Initialize the queue manager.

        Args:
            max_concurrent: Maximum concurrent extraction tasks (default 1)
        """
        self.max_concurrent = max_concurrent
        self._lock = asyncio.Lock()
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._active_task: Optional[ExtractionTask] = None
        self._pending_tasks: List[ExtractionTask] = []
        self._completed_tasks: Dict[UUID, ExtractionTask] = {}  # Keep last 10

    async def is_extraction_active(self) -> bool:
        """Check if an extraction is currently in progress."""
        async with self._lock:
            return self._active_task is not None

    async def get_status(self) -> Dict[str, Any]:
        """Get current extraction queue status."""
        async with self._lock:
            return {
                "is_active": self._active_task is not None,
                "active_task": self._active_task.to_dict() if self._active_task else None,
                "queue_size": len(self._pending_tasks),
                "pending_tasks": [t.to_dict() for t in self._pending_tasks[:5]],
                "recent_completed": [
                    t.to_dict() for t in sorted(
                        self._completed_tasks.values(),
                        key=lambda x: x.completed_at or datetime.min,
                        reverse=True
                    )[:5]
                ],
            }

    async def acquire_slot(self) -> ExtractionTask:
        """
        Acquire extraction slot. Blocks until available.

        Returns:
            ExtractionTask with status "in_progress"
        """
        await self._semaphore.acquire()
        task = ExtractionTask(
            request_id=uuid4(),
            status="in_progress",
            queue_position=0,
            created_at=datetime.now(timezone.utc),
            started_at=datetime.now(timezone.utc),
        )
        async with self._lock:
            self._active_task = task
        return task

    async def release_slot(
        self,
        task: ExtractionTask,
        success: bool,
        error: Optional[str] = None
    ) -> None:
        """
        Release extraction slot and update task status.

        Args:
            task: The task to complete
            success: Whether the extraction succeeded
            error: Error message if failed
        """
        async with self._lock:
            task.status = "completed" if success else "failed"
            task.completed_at = datetime.now(timezone.utc)
            task.error_message = error

            # Store in completed tasks
            self._completed_tasks[task.request_id] = task

            # Keep only last 10 completed
            if len(self._completed_tasks) > 10:
                oldest = min(
                    self._completed_tasks.values(),
                    key=lambda t: t.completed_at or datetime.min
                )
                del self._completed_tasks[oldest.request_id]

            self._active_task = None

        self._semaphore.release()

    async def update_progress(
        self,
        task: ExtractionTask,
        processed: int,
        total: int
    ) -> None:
        """
        Update task progress.

        Args:
            task: The task to update
            processed: Number of items processed
            total: Total items to process
        """
        task.items_processed = processed
        task.items_total = total

    async def get_task_status(self, request_id: UUID) -> Optional[ExtractionTask]:
        """
        Get status of a specific task by ID.

        Args:
            request_id: The task request ID

        Returns:
            ExtractionTask if found, None otherwise
        """
        async with self._lock:
            # Check active task
            if self._active_task and self._active_task.request_id == request_id:
                return self._active_task

            # Check pending tasks
            for task in self._pending_tasks:
                if task.request_id == request_id:
                    return task

            # Check completed tasks
            return self._completed_tasks.get(request_id)


# Global singleton instance
_extraction_manager: Optional[ExtractionQueueManager] = None


def get_extraction_manager() -> ExtractionQueueManager:
    """
    Get the shared ExtractionQueueManager instance.
    Creates one on first call and reuses it for all subsequent calls.
    """
    global _extraction_manager
    if _extraction_manager is None:
        _extraction_manager = ExtractionQueueManager(max_concurrent=1)
    return _extraction_manager
