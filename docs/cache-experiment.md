# P08 · Cache experiment

## Method
The measurement tool sends 1,000 sequential GET requests for 12–14 November 2026 to
`/rooms/availability`. Average and p95 are measured client-side. Counter differences
come from `/stats`; database queries count the per-room PostgreSQL overlap checks.

## Measurements

| Run | Searches | Database queries | Cache hits | Cache misses | Average | p95 |
|---|---:|---:|---:|---:|---:|---:|
| No cache (baseline) | 1,000 | 2,000 | 0 | 0 | Record actual output | Record actual output |
| Cache-aside, TTL 30 s | 1,000 | 2 | 999 | 1 | Record actual output | Record actual output |

**Important:** run the measurement tool against your own laptop and replace the timing
cells with its actual output. Do not use the example timings as measured results.

## Stale result demonstration
1. Search 12–14 November and confirm R7 and R8 are free.
2. Book R7 as Maya.
3. Before the 30-second TTL expires, a cached search can still show R7 if invalidation
   is disabled. This demonstrates why TTL alone is not enough.
4. Try to book R7 as Omar. The booking operation reads PostgreSQL, not Redis, and
   returns `409 Unavailable`; PostgreSQL remains the source of truth.
5. With P08 invalidation enabled, a successful booking increments `availability:version`,
   so the next search uses a new cache key and no longer returns R7.

## Hot key and next bottleneck
All guests searching the same check-in/check-out dates share one key. A successful
booking or cancellation increments the global version, making old availability keys
unreachable. This keeps search results fresh after a change, but frequent bookings
can reduce the cache hit rate. The next bottleneck is POST `/reservations`: the booking
path still performs database work and the P07 check-then-save race remains for P09.

## Result
The cache-aside pattern reduces repeated database availability checks. The booking rule
does not trust cached data; PostgreSQL remains authoritative.
