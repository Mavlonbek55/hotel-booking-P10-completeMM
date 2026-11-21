"""The four API tests: HTTP in, HTTP out, with the reservations in a list.

Run them with the other tests from the hotel-booking folder: python -m unittest -v
"""
import unittest
import queue
import threading
import time
from contextlib import contextmanager

from fastapi.testclient import TestClient

from hotel_booking.api import create_app
from hotel_booking.notifications.internal import EmailNotificationSender, QueuedNotificationSender
from hotel_booking.reservations import BookingService
from hotel_booking.reservations.internal import InMemoryReservationStore
from hotel_booking.rooms import Room

R7 = Room("R7", "Standard")
R8 = Room("R8", "Deluxe")
SEARCH = "/rooms/availability?checkIn=2026-11-12&checkOut=2026-11-14"
MAYA = {
    "guestName": "Maya",
    "guestEmail": "maya@example.com",
    "room": "R7",
    "checkIn": "2026-11-12",
    "checkOut": "2026-11-14",
}
OMAR = {
    "guestName": "Omar",
    "guestEmail": "omar@example.com",
    "room": "R7",
    "checkIn": "2026-11-13",
    "checkOut": "2026-11-15",
}


class FakeCache:
    def __init__(self):
        self.version = 1
        self.values = {}
        self.invalidations = 0

    def key(self, check_in, check_out):
        return f"availability:v{self.version}:{check_in}:{check_out}"

    def get(self, key):
        return self.values.get(key)

    def set(self, key, value):
        self.values[key] = value

    def invalidate(self):
        self.version += 1
        self.values.clear()
        self.invalidations += 1


def new_client(cache=None, notifications=None) -> TestClient:
    """The web app with the in-memory store; requests run without a network or database."""
    service = BookingService([R7, R8], InMemoryReservationStore(), notifications or EmailNotificationSender())

    @contextmanager
    def unit_of_work():
        yield service  # a list in memory has nothing to save at the end of a request

    return TestClient(create_app([R7, R8], unit_of_work, cache, notification_sender=notifications))


class BlockingSender:
    def __init__(self):
        self.started = threading.Event()
        self.release = threading.Event()
        self.sent = 0

    def send_confirmation(self, confirmation):
        self.started.set()
        self.release.wait(timeout=3)
        self.sent += 1


class ApiTests(unittest.TestCase):
    def test_search_answers_200_with_the_free_rooms(self):
        response = new_client().get(SEARCH)
        self.assertEqual(200, response.status_code)
        self.assertEqual(
            '{"checkIn":"2026-11-12","checkOut":"2026-11-14","rooms":[{"number":"R7","type":"Standard"},'
            '{"number":"R8","type":"Deluxe"}],"next":null}',
            response.text,
        )

    def test_booking_answers_201_then_409_for_a_shared_night(self):
        client = new_client()
        first = client.post("/reservations", json=MAYA)
        self.assertEqual(201, first.status_code)
        self.assertEqual(
            '{"id":"R101","status":"Confirmed","notificationFailed":false}', first.text
        )
        second = client.post("/reservations", json=OMAR)
        self.assertEqual(409, second.status_code)
        self.assertEqual("Unavailable", second.json()["title"])

    def test_wrong_dates_answer_400_with_problem_details(self):
        response = new_client().post(
            "/reservations",
            json={
                **OMAR,
                "room": "R8",
                "checkIn": "2026-11-15",
                "checkOut": "2026-11-15",
            },
        )
        self.assertEqual(400, response.status_code)
        self.assertEqual("application/problem+json", response.headers["content-type"])
        self.assertEqual(
            '{"title":"InvalidDates","status":400,"detail":"checkOut must be after checkIn."}',
            response.text,
        )

    def test_successful_booking_invalidates_availability_cache(self):
        cache = FakeCache()
        client = new_client(cache)
        client.get(SEARCH)
        self.assertEqual(0, cache.invalidations)
        response = client.post("/reservations", json=MAYA)
        self.assertEqual(201, response.status_code)
        self.assertEqual(1, cache.invalidations)
        self.assertEqual(2, cache.version)

    def test_successful_cancellation_invalidates_availability_cache(self):
        cache = FakeCache()
        client = new_client(cache)
        client.post("/reservations", json=MAYA)
        self.assertEqual(204, client.delete("/reservations/R101").status_code)
        self.assertEqual(2, cache.invalidations)
        self.assertEqual(3, cache.version)

    def test_cancel_answers_204_then_404(self):
        client = new_client()
        client.post("/reservations", json=MAYA)
        self.assertEqual(204, client.delete("/reservations/R101").status_code)
        second = client.delete("/reservations/R101")
        self.assertEqual(404, second.status_code)
        self.assertEqual("NotFound", second.json()["title"])


    def test_notification_queue_counts_and_graceful_drain(self):
        sender = QueuedNotificationSender(EmailNotificationSender(send_seconds=0.01), capacity=10)
        client = new_client(notifications=sender)
        response = client.post("/reservations", json=MAYA)
        self.assertEqual(201, response.status_code)
        self.assertFalse(response.json()["notificationFailed"])
        sender.shutdown()
        counts = sender.snapshot()
        self.assertEqual((1, 0, 1, 0), (counts["accepted"], counts["rejected"], counts["completed"], counts["queued"]))

    def test_full_queue_rejects_notification_only(self):
        slow = BlockingSender()
        sender = QueuedNotificationSender(slow, capacity=1)
        from hotel_booking.notifications import Confirmation
        from datetime import date
        def message(n):
            return Confirmation(f"R{n}", f"{n}@example.com", "R7", date(2027, 1, n), date(2027, 1, n+1))
        sender.send_confirmation(message(1))
        self.assertTrue(slow.started.wait(timeout=1))
        sender.send_confirmation(message(2))
        with self.assertRaises(queue.Full):
            sender.send_confirmation(message(3))
        self.assertEqual(1, sender.snapshot()["rejected"])
        slow.release.set()
        sender.shutdown()
        self.assertEqual(2, sender.snapshot()["completed"])

    def test_stats_exposes_queue_metrics(self):
        slow = BlockingSender()
        sender = QueuedNotificationSender(slow, capacity=10)
        client = new_client(notifications=sender)
        client.post("/reservations", json=MAYA)
        self.assertTrue(slow.started.wait(timeout=1))
        second = {**MAYA, "guestName": "Nora", "guestEmail": "nora@example.com",
                  "checkIn": "2026-12-01", "checkOut": "2026-12-02"}
        client.post("/reservations", json=second)
        counts = client.get("/stats").json()["notifications"]
        self.assertEqual(2, counts["accepted"])
        self.assertEqual(0, counts["rejected"])
        self.assertEqual(1, counts["queued"])
        slow.release.set()
        sender.shutdown()


if __name__ == "__main__":
    unittest.main()
