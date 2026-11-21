# ADR-003: Enforce booking exclusivity in PostgreSQL

- **Status:** Accepted
- **Date:** 2026-11-12

## Context

Concurrent requests can both observe that a room has no overlapping confirmed reservation and then insert separate rows. This is write skew. An application-level check alone is not an invariant because it is separated from the insert.

## Decision

Use a PostgreSQL GiST exclusion constraint named `reservations_no_overlap` over room equality and overlapping half-open date ranges, restricted to `status = 'Confirmed'`. Keep the application pre-check for normal user feedback. Translate a violation of this specific constraint into the domain outcome `Unavailable`, returned as HTTP 409. Use a database sequence for reservation IDs so separate processes do not generate the same ID.

## Alternatives considered

1. **Process-local lock:** simple and useful for a single-process demonstration, but each worker has a different lock. It cannot protect a deployment with two instances.
2. **Guard row with `SELECT FOR UPDATE`:** works across processes, but adds a guard-table lifecycle and makes bookings for the same room wait.
3. **Optimistic version check:** avoids waiting, but a losing transaction must roll back and retry all work; retry limits and failure handling add complexity.

## Consequences

The database prevents conflicting confirmed reservations regardless of which API instance or code path writes them. The `btree_gist` extension and GiST index add write/index-maintenance cost. Existing overlapping confirmed rows must be resolved before the constraint can be added. The application must recognize the named constraint violation and return a readable 409. The constraint covers conflicts represented in this reservations table; it does not automatically enforce rules spanning other tables.

## When to revisit

Revisit if booking rules become more complex than room equality plus date-range overlap, if confirmed status semantics change, or if write contention/index cost becomes material. Any replacement must preserve database-level enforcement across all writers.
