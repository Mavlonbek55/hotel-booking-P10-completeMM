# hotel_booking/api.py
"""HTTP endpoints for availability, reservations and operational statistics."""
from __future__ import annotations

import re
from contextlib import AbstractContextManager
from datetime import date
from pathlib import Path
from typing import Any, Callable

from fastapi import Body, FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response

from hotel_booking.reservations import BookingResult, BookingService, DateRange, Guest
from hotel_booking.rooms import Room

UnitOfWork = Callable[[], AbstractContextManager[BookingService]]
FIELDS = ("guestName", "guestEmail", "room", "checkIn", "checkOut")
BODY_DETAIL = "The body must be JSON with guestName, guestEmail, room, checkIn and checkOut."
DATE_DETAIL = "checkIn and checkOut must be dates such as 2026-11-12."


class SearchStats:
    """Process-local counters for the search experiment."""
    def __init__(self) -> None:
        self.searches = 0
        self.database_queries = 0
        self.cache_hits = 0
        self.cache_misses = 0

    def snapshot(self) -> dict[str, int]:
        return {
            "searches": self.searches,
            "databaseQueries": self.database_queries,
            "cacheHits": self.cache_hits,
            "cacheMisses": self.cache_misses,
        }


def problem(status: int, title: str, detail: str) -> JSONResponse:
    return JSONResponse({"title": title, "status": status, "detail": detail},
                        status, media_type="application/problem+json")


def parse_date(value: Any) -> date | None:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def to_http(result: BookingResult) -> JSONResponse:
    if result.outcome == "Accepted":
        return JSONResponse({"id": result.reservation_id, "status": "Confirmed",
                             "notificationFailed": result.notification_failed}, 201)
    if result.outcome == "Unavailable":
        return problem(409, "Unavailable", "The room is booked for at least one night of this stay.")
    return problem(400, "InvalidDates", "checkOut must be after checkIn.")


def create_app(rooms: list[Room], unit_of_work: UnitOfWork, cache=None,
               stats: SearchStats | None = None, notification_sender=None) -> FastAPI:
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def lifespan(app):
        try:
            yield
        finally:
            if notification_sender is not None:
                notification_sender.shutdown()

    app = FastAPI(openapi_url=None, docs_url=None, redoc_url=None, lifespan=lifespan)
    stats = stats or SearchStats()

    @app.exception_handler(RequestValidationError)
    def not_json(request, error) -> JSONResponse:
        return problem(400, "InvalidRequest", BODY_DETAIL)

    @app.get("/openapi.yaml")
    def contract() -> Response:
        return Response(Path("docs/openapi.yaml").read_text(encoding="utf-8"),
                        media_type="application/yaml")

    @app.get("/stats")
    def get_stats() -> JSONResponse:
        result = stats.snapshot()
        if notification_sender is not None:
            result["notifications"] = notification_sender.snapshot()
        return JSONResponse(result)

    @app.get("/rooms/availability")
    def find_free_rooms(checkIn: str = "", checkOut: str = "",
                        limit: str = "20", after: str = "") -> JSONResponse:
        check_in, check_out = parse_date(checkIn), parse_date(checkOut)
        if check_in is None or check_out is None:
            return problem(400, "InvalidDates", DATE_DETAIL)
        stay = DateRange(check_in, check_out)
        if not stay.is_valid():
            return problem(400, "InvalidDates", "checkOut must be after checkIn.")
        if not re.fullmatch(r"[0-9]{1,3}", limit) or not 1 <= int(limit) <= 100:
            return problem(400, "InvalidRequest", "limit must be a whole number from 1 to 100.")

        stats.searches += 1
        key = None
        free = None
        if cache is not None:
            key = cache.key(checkIn, checkOut)
            cached = cache.get(key)
            if cached is not None:
                stats.cache_hits += 1
                free = [Room(item["number"], item["type"]) for item in cached]
            else:
                stats.cache_misses += 1
        if free is None:
            with unit_of_work() as service:
                before = getattr(service.store, "query_count", None)
                free = service.find_free_rooms(stay)
                if before is not None:
                    stats.database_queries += service.store.query_count - before
                else:
                    # In-memory test stores are not database queries.
                    stats.database_queries += 0
            if cache is not None and key is not None:
                cache.set(key, [{"number": room.number, "type": room.type} for room in free])

        rest = sorted((room for room in free if room.number > after), key=lambda room: room.number)
        page = rest[:int(limit)]
        return JSONResponse({
            "checkIn": checkIn, "checkOut": checkOut,
            "rooms": [{"number": room.number, "type": room.type} for room in page],
            "next": page[-1].number if len(rest) > len(page) else None,
        })

    @app.post("/reservations")
    def reserve(body: Any = Body(None)) -> JSONResponse:
        if not isinstance(body, dict) or not all(
            isinstance(body.get(field), str) and body[field].strip() for field in FIELDS
        ):
            return problem(400, "InvalidRequest", BODY_DETAIL)
        check_in, check_out = parse_date(body["checkIn"]), parse_date(body["checkOut"])
        if check_in is None or check_out is None:
            return problem(400, "InvalidDates", DATE_DETAIL)
        room = next((room for room in rooms if room.number == body["room"]), None)
        if room is None:
            return problem(400, "UnknownRoom", f"There is no room {body['room']}.")
        with unit_of_work() as service:
            result = service.reserve(Guest(body["guestName"], body["guestEmail"]),
                                     room, DateRange(check_in, check_out))
        if result.outcome == "Accepted" and cache is not None:
            cache.invalidate()
        return to_http(result)

    @app.delete("/reservations/{reservation_id}")
    def cancel(reservation_id: str) -> Response:
        with unit_of_work() as service:
            cancelled = service.cancel(reservation_id)
        if not cancelled:
            return problem(404, "NotFound", f"There is no confirmed reservation {reservation_id}.")
        if cache is not None:
            cache.invalidate()
        return Response(status_code=204)

    return app
