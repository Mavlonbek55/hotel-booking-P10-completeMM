# Design Notes

## P03 notes

The original app searches rooms, accepts a valid booking, rejects overlapping stays, permits a new guest to check in on the previous guest's check-out date, rejects invalid dates, cancels reservations, and includes a race demonstration. A stay includes its check-in date and excludes its check-out date.

# P04 design notes

## 1. Refactoring

Refactoring means improving the internal structure of code without intentionally changing its externally observable behaviour. The P03 demo output and booking rules should stay the same. P04 adds a new requirement, R6, separately: a notification failure must not remove or hide an already-saved booking.

## 2. What the original design makes difficult

- `BookingService` was coupled to concrete storage (`ReservationStore` implemented as a list) and a concrete email sender.
- Adding SMS or another delivery method would require changing booking logic.
- Replacing the list with PostgreSQL would require changing booking logic instead of adding a new storage implementation.
- Tests using only the real email sender cannot reliably simulate a delivery failure.

## 3. SOLID review

- **S — Single Responsibility Principle:** Booking rules, persistence details and notification delivery should have separate responsibilities. `BookingService` coordinates the booking use case; store classes handle persistence; sender classes handle notifications.
- **O — Open/Closed Principle:** The service should be open to extension but closed to modification. New senders (such as SMS) and stores can implement the protocols without editing booking rules.
- **L — Liskov Substitution Principle:** Any implementation that fulfils `ReservationStore` or `NotificationSender` must be usable in place of another implementation while respecting the same contract.
- **I — Interface Segregation Principle:** The service depends on small, purpose-specific protocols instead of a large class containing unrelated operations.
- **D — Dependency Inversion Principle:** High-level booking policy depends on abstractions (`ReservationStore` and `NotificationSender` protocols), not on concrete in-memory storage or email classes.

The tightly coupled P03 design mainly conflicts with O and D, and mixes responsibilities in ways that weaken S and I. Substitutable implementations must still follow the contracts for L.

## 4. Target design

`BookingService` receives a `ReservationStore` and a `NotificationSender` through its constructor. `InMemoryReservationStore` implements the storage protocol. `EmailNotificationSender`, `SmsNotificationSender`, and test fakes implement the notification protocol. `main.py` is the composition root: it chooses the concrete implementations. Domain objects (`Guest`, `Room`, `DateRange`, `Reservation`) live in `domain.py`.

## 5. Proof that behaviour is preserved

Run from the project root:

```bash
python -m unittest -v
python main.py
python main.py --race
```

Verification performed for this project:

- All 8 unit tests pass.
- The standard demo prints the same 9 lines documented in `README.md`.
- The race demo prints `Double booking! Both requests checked before either one saved.` This is intentionally preserved for P04; concurrency protection is outside the refactoring scope.
- A fake sender that raises an exception verifies R6: the reservation remains saved and the result remains `Accepted` with `notification_failed=True`.
- An SMS sender can be supplied to `BookingService` without changing `booking.py`.

## 6. Limitation

The race demo demonstrates a genuine check-then-save race in this teaching implementation. A production system would need an atomic storage operation/transaction or database constraint to prevent concurrent double bookings. P04 is a structure/refactoring exercise, not a concurrency fix.


# P06 design notes

## 7. Modular monolith

For P06, the app is organised into four business modules: Rooms, Reservations, Payments and Notifications. Each module exposes a small public contract from its package `__init__.py`; implementation details live in its `internal.py` file where appropriate. Reservations owns the booking rules. `main.py` is the composition root and is the only place that imports the internal implementations to wire the application together.

## 8. Module responsibilities and dependencies

- **Rooms** owns the room record and the public `RoomCatalog` contract. It does not import the other modules.
- **Reservations** owns `Guest`, `DateRange`, `Reservation`, `BookingResult`, the booking service and the reservation-store contract. It depends on the public `Room` type, not on Rooms' internal implementation.
- **Payments** owns the payment status and payment contract; its simulated implementation is internal.
- **Notifications** owns the confirmation message and sender contract; email/SMS implementations are internal.
- **main.py** chooses the concrete catalog, store, payment service and notification sender.

## 9. Architecture checks

`pyproject.toml` defines three Import Linter contracts. They prohibit Reservations from importing other modules' internal implementations, prohibit Rooms from depending on other modules, and prohibit Payments/Notifications from depending on Reservations. Run `lint-imports` from the project root to check these module boundaries.

## 10. Verification for P06

Run `python -m unittest -v`, `lint-imports`, `python main.py`, and `python main.py --race` from the project root. The eight unit tests protect booking behaviour and notification failure handling. Import Linter checks the three architecture contracts. The normal demo should keep the same nine output lines as P04. The race demo intentionally still demonstrates the check-then-save race; concurrency protection is outside P06's refactoring scope and is addressed in P09.

# P07 design notes

## Capacity estimate

The estimate uses 1,440 visitors per day, 20 searches per visitor, 20 bookings per day, a peak factor of 10, and 40 rooms queried per search. This gives about 0.33 searches per second on average and 3.33 searches per second at peak (200 per minute). At 40 database checks per search, the peak estimate is 133 queries per second. Estimated reservation storage is 4.38 MB per year. Estimated peak bandwidth is 6.67 KB/s for search answers and 333 KB/s for photos. These are assumptions, not measurements; P08 will measure p95 search time and database queries per search.

## API decisions

- Search results are ordered by room number as text, not as a numeric value. Therefore R10 comes before R7.
- Clients should compare the stable `title` field in an error response. The `detail` field is a human-readable sentence and may change.
- Room type is catalog data read from the rooms table, not a fixed list in the API. A new room type does not require changing the API contract.

## API tests

- GET `/rooms/availability` for 12–14 November returns 200 and the free rooms R7 and R8.
- POST `/reservations` for Maya returns 201; a second overlapping booking from Omar returns 409 Unavailable.
- POST with check-out equal to check-in returns 400 InvalidDates as `application/problem+json`.
- DELETE `/reservations/R101` returns 204 the first time and 404 NotFound the second time.

## After

- Checks: 12 Python tests pass (8 booking behaviour tests and 4 API tests); Import Linter keeps all 3 module-boundary contracts.
- API check: the seven documented requests return the expected status codes and bodies.
- Restart check: after Maya's R7 booking is saved, restarting the web app does not remove it; the availability search still shows only R8 as free.
- The `--demo` and `--race` modes continue to use the in-memory stores and preserve the P06 demonstrations.
# P08 design notes

## Cache rule

GET `/rooms/availability` uses Redis cache-aside with a 30-second TTL and the key
`availability:v{version}:{checkIn}:{checkOut}`. The free-room list is cached; booking
and cancellation decisions never read Redis. PostgreSQL remains the source of truth.

A successful POST or DELETE increments `availability:version`. A new version creates
a new key namespace, so the next search reloads availability from PostgreSQL.

## After

- `/stats` reports searches, database overlap queries, cache hits and cache misses.
- `tools/measure.py` measures 1,000 identical searches and prints average and p95 latency.
- `docs/cache-experiment.md` records the baseline and cache-aside comparison. Timing values
  must be filled with results from the local machine.
- Redis is an additional runtime dependency; this version does not fall back to PostgreSQL
  when Redis is unavailable. The P07 race remains for P09.


# P10 design notes

## Background notification delivery

Confirmation messages are now placed on a bounded queue and delivered by one
worker thread. This keeps slow email work out of the booking request. The queue
holds up to 10 waiting messages. If full, it rejects the notification and the
booking remains saved; the API indicates `notificationFailed: true`.

## Counters and shutdown

`GET /stats` includes accepted, rejected, completed and queued notification
counts. During application shutdown the queue stops accepting work, waits for
accepted messages to finish, and then stops the worker.

## Verification

`tools/burst.py` sends 30 bookings with distinct dates. The test suite includes
checks for queue counters, full-queue backpressure, and graceful draining.
The queue is process-local and non-durable, so a production multi-instance
deployment should consider a durable broker.
