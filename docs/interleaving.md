# P09 — Booking concurrency and interleaving

## The race

Two guests request room R7 for 12–14 November 2026. The original implementation performs an overlap read, pauses, then inserts. Both requests can read an empty result before either insert commits. The outcome is two confirmed rows for the same room and overlapping nights.

Run the in-memory reproduction with `python main.py --race`. The exact thread order can vary; the important observation is that both checks can complete before either save.

## Eight-step interleaving

| Step | Maya transaction | Omar transaction |
|---:|---|---|
| 1 | BEGIN | |
| 2 | SELECT overlapping confirmed reservations → none | |
| 3 | pause before INSERT | BEGIN |
| 4 | | SELECT overlapping confirmed reservations → none |
| 5 | INSERT Maya reservation | |
| 6 | | INSERT Omar reservation |
| 7 | COMMIT | COMMIT |
| 8 | Both rows are confirmed for the same room and nights | Both rows are confirmed for the same room and nights |

## Anomaly

This is **write skew**: two transactions make decisions from a mutually compatible snapshot and then write different rows that jointly violate a cross-row business rule. It is not a lost update because neither transaction overwrites the other's value.

Repeatable Read does not prevent this pattern in PostgreSQL: each transaction can consistently see the absence of an overlapping row in its snapshot. `SELECT ... FOR UPDATE` on reservation rows cannot lock a row that does not exist.

## Repairs considered

| Repair | What it protects | Limitation / cost |
|---|---|---|
| In-process mutex | Serializes check + insert inside one Python process | Does not coordinate multiple app processes or machines |
| Guard row + `SELECT FOR UPDATE` | Serializes bookings for a room across processes | Requires guard-row lifecycle and careful transaction handling; hot rooms wait |
| Optimistic guard version | Detects competing writers without waiting | Loser must roll back and retry the whole transaction; bounded retries required |
| PostgreSQL exclusion constraint | Enforces no overlapping confirmed stays in the database | Requires `btree_gist`; writes maintain a GiST index; existing conflicts must be cleaned first |

## Final decision

The durable invariant is the named PostgreSQL constraint `reservations_no_overlap`. The API keeps its overlap pre-check for a friendly early response, but the database constraint is authoritative for concurrent requests and every other write path. SQLSTATE `23P01` / the named constraint is mapped to HTTP 409.
