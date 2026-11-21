from __future__ import annotations

from datetime import date

from sqlalchemy import exists, func, select, text
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from hotel_booking.reservations.domain import DateRange, Guest, Reservation
from hotel_booking.rooms import Room


class OverlapRejected(Exception):
    """The database rejected a confirmed reservation that overlaps another stay."""


class InMemoryReservationStore:
    """Keeps reservations in a list. PostgresReservationStore below has the same methods."""

    def __init__(self) -> None:
        self._rows: list[Reservation] = []

    def count(self) -> int:
        return len(self._rows)

    def next_id(self) -> str:
        return f"R{101 + self.count()}"

    def has_overlap(self, room: Room, stay: DateRange) -> bool:
        return any(row.blocks(room, stay) for row in self._rows)

    def save(self, reservation: Reservation) -> None:
        self._rows.append(reservation)

    def find(self, reservation_id: str) -> Reservation | None:
        return next((row for row in self._rows if row.id == reservation_id), None)

    def count_confirmed(self, room: Room, stay: DateRange) -> int:
        return sum(1 for row in self._rows if row.blocks(room, stay))


class ReservationsTables(DeclarativeBase):
    """The tables the Reservations module owns."""


class ReservationRow(ReservationsTables):
    """One row of the reservations table in db/init.sql."""

    __tablename__ = "reservations"
    id: Mapped[str] = mapped_column(primary_key=True)
    guest_name: Mapped[str]
    guest_email: Mapped[str]
    room: Mapped[str]
    check_in: Mapped[date]
    check_out: Mapped[date]
    status: Mapped[str]


class PostgresReservationStore:
    """Keeps reservations in PostgreSQL. main.py creates one per request (a unit of work): it
    remembers the reservations it hands out, and save_changes writes their changes and commits."""

    def __init__(self, session: Session, rooms: list[Room]) -> None:
        self._session = session
        self._rooms = {room.number: room for room in rooms}
        self._loaded: list[tuple[ReservationRow, Reservation]] = []

    def count(self) -> int:
        return self._session.scalar(select(func.count()).select_from(ReservationRow)) or 0

    def next_id(self) -> str:
        value = self._session.scalar(text("SELECT nextval('reservation_ids')"))
        return f"R{value}"

    def has_overlap(self, room: Room, stay: DateRange) -> bool:
        return bool(self._session.scalar(select(exists(self._confirmed(room, stay)))))

    def save(self, reservation: Reservation) -> None:
        row = ReservationRow(
            id=reservation.id,
            guest_name=reservation.guest.name,
            guest_email=reservation.guest.email,
            room=reservation.room.number,
            check_in=reservation.stay.check_in,
            check_out=reservation.stay.check_out,
            status=reservation.status.value,
        )
        # Savepoint keeps the request transaction usable if the database rejects overlap.
        from sqlalchemy.exc import IntegrityError
        try:
            with self._session.begin_nested():
                self._session.add(row)
                self._session.flush()
        except IntegrityError as exc:
            original = getattr(exc, "orig", None)
            constraint = getattr(getattr(original, "diag", None), "constraint_name", None)
            if constraint == "reservations_no_overlap":
                raise OverlapRejected from exc
            raise

    def find(self, reservation_id: str) -> Reservation | None:
        row = self._session.get(ReservationRow, reservation_id)
        if row is None:
            return None
        reservation = Reservation(
            row.id,
            Guest(row.guest_name, row.guest_email),
            self._rooms[row.room],
            DateRange(row.check_in, row.check_out),
        )
        if row.status == "Cancelled":
            reservation.cancel()
        self._loaded.append((row, reservation))
        return reservation

    def count_confirmed(self, room: Room, stay: DateRange) -> int:
        return self._session.scalar(
            select(func.count()).select_from(self._confirmed(room, stay).subquery())
        ) or 0

    def save_changes(self) -> None:
        """The end of the request: copy each loaded reservation's status to its row; SQLAlchemy writes what changed."""
        for row, reservation in self._loaded:
            row.status = reservation.status.value
        self._session.commit()

    @staticmethod
    def _confirmed(room: Room, stay: DateRange):
        # Confirmed reservations of this room that share at least one night with the stay.
        return select(ReservationRow.id).where(
            ReservationRow.room == room.number,
            ReservationRow.status == "Confirmed",
            ReservationRow.check_in < stay.check_out,
            stay.check_in < ReservationRow.check_out,
        )
