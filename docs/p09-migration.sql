-- Review existing confirmed overlaps before running this migration.
-- This query lists conflicting pairs; resolve them deliberately before adding the constraint.
SELECT a.id AS reservation_a, b.id AS reservation_b, a.room,
       a.check_in, a.check_out, b.check_in, b.check_out
FROM reservations a
JOIN reservations b ON a.room = b.room AND a.id < b.id
 AND a.status = 'Confirmed' AND b.status = 'Confirmed'
 AND daterange(a.check_in, a.check_out, '[)') && daterange(b.check_in, b.check_out, '[)');

CREATE EXTENSION IF NOT EXISTS btree_gist;
CREATE SEQUENCE IF NOT EXISTS reservation_ids START WITH 101;
-- Keep generated IDs above any existing numeric Rxxx identifier.
SELECT setval('reservation_ids', GREATEST(100, COALESCE((
  SELECT MAX(NULLIF(regexp_replace(id, '^R', ''), '')::bigint) FROM reservations
  WHERE id ~ '^R[0-9]+$'
), 100)), true);

ALTER TABLE reservations
  ADD CONSTRAINT reservations_no_overlap
  EXCLUDE USING gist (room WITH =, daterange(check_in, check_out, '[)') WITH &&)
  WHERE (status = 'Confirmed');
