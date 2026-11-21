# P08 · Hotel booking web app with PostgreSQL and Redis (Python)

This project extends the P06 modular monolith. It keeps the four modules (Rooms, Reservations,
Payments and Notifications), adds a FastAPI HTTP API, and stores rooms and reservations in
PostgreSQL. The API listens on `http://localhost:5080`.

## Requirements

- Python 3.12 or another supported Python 3 version.
- Docker Desktop running.
- Windows PowerShell, VS Code, and a terminal opened in this folder.

## Install once

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

If PowerShell blocks activation, use the interpreter directly instead:

```powershell
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Start PostgreSQL

```powershell
docker compose up -d
docker compose ps
docker compose exec db psql -U hotel -d hotel -c "SELECT * FROM rooms;"
```

The first command downloads the PostgreSQL image if it is not already on the computer. The
rooms query should show R7 (Standard) and R8 (Deluxe). Docker keeps database data in the
`hotel-data` volume. Do not use `docker compose down -v` unless you intentionally want to
delete that database volume.

## Run checks

```powershell
python -m unittest -v
lint-imports
```

Expected: 14 tests pass and Import Linter reports `Contracts: 3 kept, 0 broken.`

## Start the API

Start PostgreSQL first, then run:

```powershell
python main.py
```

Open `http://localhost:5080/openapi.yaml` to view the API contract. Use `Ctrl+C` in the
server terminal to stop the app.

## Check the API manually

The seven HTTP requests and the restart check are documented in `docs/api-check.md`. The JSON
request bodies are in `docs/requests/` and can be sent using Windows `curl.exe`.

## Keep the P06 demonstrations

```powershell
python main.py --demo
python main.py --race
```

These two modes still use in-memory stores. The normal `python main.py` command starts the
web API with PostgreSQL-backed stores.

## P08 measurement

With the API running, open a second terminal and run:

```powershell
python tools/measure.py
```

`GET /stats` reports the process counters. To run the uncached baseline, stop the API,
set `$env:HOTEL_CACHE_ENABLED = "0"` and restart it. For the cached run, stop it,
run `Remove-Item Env:HOTEL_CACHE_ENABLED -ErrorAction SilentlyContinue`, clear Redis
with `docker compose exec cache redis-cli FLUSHDB`, restart the API, and run the tool
again. Record your actual average and p95 in `docs/cache-experiment.md`.


## P09 — Prevent double booking

P09 adds a PostgreSQL exclusion constraint as the final protection against concurrent overlapping bookings. The constraint is created by `db/init.sql` only for a fresh database volume. For an existing P08 database, apply the migration in `docs/p09-migration.sql` after checking and resolving any overlapping confirmed reservations. Do not delete the Docker volume to force initialization: that destroys stored data.

Start one API instance with `python main.py` (port 5080). A second PowerShell terminal can start another instance with `$env:HOTEL_PORT = "5081"; python main.py`. Run the HTTP race test with `python tools/race_http.py`; to target both instances use `$env:HOTEL_PORTS = "5080,5081"` first. The expected database-enforced result is one 201 and one 409.

`python main.py --race` is the original in-memory race demonstration; it is not the final PostgreSQL protection. See `docs/interleaving.md` and `docs/adr-003-booking-concurrency.md`.


## P10 — Background notification queue

P10 keeps the P09 PostgreSQL overlap constraint and moves confirmation delivery
to a background worker. The in-process queue has a maximum of 10 waiting
messages. A full queue rejects the notification, not the already-saved booking;
the response reports `notificationFailed: true`.

Start the API with a one-second simulated email delay:

```powershell
$env:HOTEL_EMAIL_SECONDS = "1"
python main.py
```

In a second PowerShell terminal, run the 30-booking burst:

```powershell
python tools/burst.py
```

Check `http://localhost:5080/stats` for `notifications.accepted`,
`notifications.rejected`, `notifications.completed` and `notifications.queued`.
Stop the API with Ctrl+C; graceful shutdown drains accepted notifications.

P10 documents the experiment in `docs/queue-trace.md` and the decision in
`docs/adr-004-notification-concurrency.md`. The queue is process-local and
non-durable; see ADR-004 for the trade-offs.
