# ADR-004: Deliver confirmation notifications through a bounded worker queue

Status: Accepted, 21 November 2026

## Context
Email delivery can take seconds after a reservation is committed. Sending it
inside the HTTP request makes guests wait for work unrelated to the booking
decision. A burst can also create more work than one sender can complete.

## Decision
Use one background worker and an in-process queue with at most 10 waiting
messages. Booking requests enqueue without waiting. If full, only the
notification is rejected and counted; the reservation remains confirmed and
the API reports `notificationFailed: true`. On shutdown, stop accepting work,
drain accepted messages, then stop the worker.

## Alternatives considered — six concurrency models
1. **Synchronous sequential delivery:** simplest, but every request waits for
   the mail delay and throughput is limited by one sender.
2. **Async I/O (`asyncio`):** effective for network waits, but blocking senders
   must be made asynchronous; overload still needs a queue policy.
3. **A thread per request:** overlaps I/O but can create unbounded threads in a burst.
4. **Thread pool:** bounds concurrent workers, but submitted backlog still needs
   an explicit capacity and rejection policy.
5. **Multiprocessing / process pool:** useful for CPU-heavy work, but adds
   process startup, memory and IPC costs for network I/O.
6. **Dedicated bounded queue + worker (chosen):** separates request latency,
   caps pending work, exposes overload counters and supports graceful draining.

A durable external broker is a possible future evolution, not the selected
in-process model.

## Consequences
- Booking responses are not delayed by simulated email delivery.
- Queue capacity is 10; `/stats` reports accepted, rejected, completed and queued.
- Backpressure rejects notification work, not the saved booking.
- Graceful shutdown drains accepted work.
- The queue is process-local and not durable; crashes can lose pending messages.
- Real delivery would need retries, idempotency and durable storage.

## Revisit when
The app runs multiple instances, notification loss is unacceptable, or burst
volume regularly exceeds one worker's capacity. Consider a durable shared
broker and monitor queue age as well as depth.
