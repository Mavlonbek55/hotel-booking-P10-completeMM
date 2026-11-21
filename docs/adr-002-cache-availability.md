# ADR-002: Cache the free-room search in Redis

Status: Accepted, 7 November 2026

## Context
P07 performs a database overlap check for each room on every availability search.
Repeated searches for the same dates repeat the same work. The booking rule must not
depend on an old cached answer.

## Decision
Use Redis cache-aside for GET `/rooms/availability` only. The key is
`availability:v{version}:{checkIn}:{checkOut}` and the value is the list of free rooms.
The TTL is 30 seconds. A successful booking or cancellation increments
`availability:version`. POST and DELETE continue to use PostgreSQL directly.

## Alternatives considered
- No cache: simplest and always reads current database state, but repeats every room check.
- TTL only: easy to implement, but may show a room as free for up to 30 seconds after booking.
- Invalidation only: makes changes visible promptly, but a missed invalidation can leave stale
  data until the cache is cleared.

## Consequences
- Repeated searches for the same dates reuse one Redis value and reduce database reads.
- PostgreSQL remains the source of truth for booking decisions.
- If invalidation is missed, stale availability can remain until the TTL expires.
- A global version increment invalidates all date keys, so frequent bookings reduce hit rate.
- Redis is an additional service. This implementation has no PostgreSQL fallback if Redis is down.
- Simultaneous cache misses can still perform duplicate database searches.

## Revisit when
Booking writes become the bottleneck, or measured cache hit rate under realistic load is
materially lower than the experiment in `docs/cache-experiment.md`.
