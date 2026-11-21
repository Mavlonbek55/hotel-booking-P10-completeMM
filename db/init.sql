-- PostgreSQL schema. This file runs only when the hotel-data volume is first created.
CREATE EXTENSION IF NOT EXISTS btree_gist;

CREATE TABLE rooms (
    number text PRIMARY KEY,
    type text NOT NULL
);

CREATE SEQUENCE IF NOT EXISTS reservation_ids START WITH 101;

CREATE TABLE reservations (
    id text PRIMARY KEY,
    guest_name text NOT NULL,
    guest_email text NOT NULL,
    room text NOT NULL,
    check_in date NOT NULL,
    check_out date NOT NULL,
    status text NOT NULL CHECK (status IN ('Confirmed', 'Cancelled')),
    CHECK (check_out > check_in),
    CONSTRAINT reservations_no_overlap
      EXCLUDE USING gist (
        room WITH =,
        daterange(check_in, check_out, '[)') WITH &&
      ) WHERE (status = 'Confirmed')
);

INSERT INTO rooms (number, type) VALUES ('R7', 'Standard'), ('R8', 'Deluxe')
ON CONFLICT (number) DO NOTHING;
