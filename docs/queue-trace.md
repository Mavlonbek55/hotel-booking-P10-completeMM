# P10 — Notification queue trace

## Purpose
`EmailNotificationSender` simulates email delivery. Set `HOTEL_EMAIL_SECONDS=1`
to make each delivery take about one second. `QueuedNotificationSender` places
the message on a bounded in-process queue; a background worker delivers it.

## Capacity and backpressure
The queue capacity is 10 waiting messages. `put_nowait` does not block a booking.
When full, the sender raises `queue.Full`; `BookingService` catches the delivery
error and returns an accepted booking with `notificationFailed=true`. The
reservation has already been saved and is not rolled back.

`GET /stats` exposes `notifications`:
- `accepted`: messages placed on the queue.
- `rejected`: messages refused because the queue was full or shutting down.
- `completed`: messages delivered by the worker.
- `queued`: messages currently waiting (not including the in-flight message).

## Burst experiment
1. Start Docker and run `$env:HOTEL_EMAIL_SECONDS = "1"; python main.py`.
2. In another terminal run `python tools/burst.py`.
3. Read `http://localhost:5080/stats`.
4. Stop the API with Ctrl+C. Shutdown stops accepting messages, drains accepted
   work, then stops the worker.

The burst tool uses distinct dates to avoid P09 overlap conflicts.

## Limits
This queue is process-local and not durable. A crash can lose pending messages;
multiple API instances have independent queues. A production deployment needing
durability should use a shared broker and idempotent consumers.
