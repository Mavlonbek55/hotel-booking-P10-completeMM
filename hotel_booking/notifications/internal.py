from __future__ import annotations

import queue
import threading
import time

from hotel_booking.notifications import Confirmation


class EmailNotificationSender:
    """Simulated immediate sender. It never connects to a real mail service."""

    def __init__(self, send_seconds: float = 0) -> None:
        self.sent = 0
        self.send_seconds = max(0.0, send_seconds)

    def send_confirmation(self, confirmation: Confirmation) -> None:
        if self.send_seconds:
            time.sleep(self.send_seconds)
        self.sent += 1


class SmsNotificationSender:
    """Simulated, like the email sender."""

    def __init__(self) -> None:
        self.sent = 0

    def send_confirmation(self, confirmation: Confirmation) -> None:
        self.sent += 1


class QueuedNotificationSender:
    """A bounded in-process queue serviced by one background worker.

    send_confirmation never waits for delivery. A full queue raises queue.Full so
    BookingService can report notificationFailed without undoing the saved booking.
    """

    def __init__(self, sender: EmailNotificationSender, capacity: int = 10) -> None:
        if capacity < 1:
            raise ValueError("capacity must be at least 1")
        self.sender = sender
        self.capacity = capacity
        self._queue: queue.Queue[Confirmation | None] = queue.Queue(maxsize=capacity)
        self._lock = threading.Lock()
        self.accepted = 0
        self.rejected = 0
        self.completed = 0
        self._closing = False
        self._worker = threading.Thread(target=self._work, name="notification-worker", daemon=True)
        self._worker.start()

    def send_confirmation(self, confirmation: Confirmation) -> None:
        with self._lock:
            if self._closing:
                self.rejected += 1
                raise queue.Full("notification queue is shutting down")
            try:
                self._queue.put_nowait(confirmation)
            except queue.Full:
                self.rejected += 1
                raise
            self.accepted += 1

    def _work(self) -> None:
        while True:
            item = self._queue.get()
            try:
                if item is None:
                    return
                self.sender.send_confirmation(item)
                with self._lock:
                    self.completed += 1
            finally:
                self._queue.task_done()

    def snapshot(self) -> dict[str, int]:
        with self._lock:
            return {
                "accepted": self.accepted,
                "rejected": self.rejected,
                "completed": self.completed,
                "queued": self._queue.qsize(),
            }

    def shutdown(self) -> None:
        """Stop accepting work, drain accepted notifications, then stop the worker."""
        with self._lock:
            if self._closing:
                return
            self._closing = True
        self._queue.join()
        self._queue.put(None)
        self._worker.join()
