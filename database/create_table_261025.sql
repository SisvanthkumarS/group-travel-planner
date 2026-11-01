
BEGIN;

-- =========================================
-- 1. Users
-- =========================================
CREATE TABLE users (
    user_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    email TEXT NOT NULL
        CHECK (LENGTH(TRIM(email)) > 0),

    password_hash TEXT NOT NULL,

    created_at TIMESTAMPTZ NOT NULL
        DEFAULT CURRENT_TIMESTAMP
);

-- Email uniqueness, ignoring letter case
CREATE UNIQUE INDEX uq_users_email_lower
    ON users (LOWER(TRIM(email)));


-- =========================================
-- 2. Trips
-- =========================================
CREATE TABLE trips (
    trip_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    name TEXT NOT NULL
        CHECK (LENGTH(TRIM(name)) > 0),

    destination TEXT NOT NULL
        CHECK (LENGTH(TRIM(destination)) > 0),

    start_date DATE NOT NULL,
    end_date DATE NOT NULL,

    organizer_id BIGINT NOT NULL
        REFERENCES users(user_id)
        ON DELETE CASCADE,

    CONSTRAINT ck_trips_dates
        CHECK (start_date <= end_date)
);


-- =========================================
-- 3. Trip members
-- =========================================
CREATE TABLE trip_members (
    trip_id BIGINT NOT NULL
        REFERENCES trips(trip_id)
        ON DELETE CASCADE,

    user_id BIGINT NOT NULL
        REFERENCES users(user_id)
        ON DELETE CASCADE,

    role TEXT NOT NULL
        CHECK (role IN ('ORGANIZER', 'MEMBER')),

    joined_at TIMESTAMPTZ NOT NULL
        DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (trip_id, user_id)
);

-- Find all trips belonging to a user efficiently
CREATE INDEX idx_trip_members_user_id
    ON trip_members(user_id);


-- =========================================
-- 4. Invitations
-- =========================================
CREATE TABLE invitations (
    invitation_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    trip_id BIGINT NOT NULL
        REFERENCES trips(trip_id)
        ON DELETE CASCADE,

    invited_user_id BIGINT NOT NULL
        REFERENCES users(user_id)
        ON DELETE CASCADE,

    invited_by_user_id BIGINT NOT NULL
        REFERENCES users(user_id)
        ON DELETE CASCADE,

    status TEXT NOT NULL DEFAULT 'PENDING'
        CHECK (status IN ('PENDING', 'ACCEPTED', 'DECLINED')),

    created_at TIMESTAMPTZ NOT NULL
        DEFAULT CURRENT_TIMESTAMP,

    responded_at TIMESTAMPTZ,

    CONSTRAINT ck_invitation_response_time
        CHECK (
            (status = 'PENDING' AND responded_at IS NULL)
            OR
            (status IN ('ACCEPTED', 'DECLINED')
                AND responded_at IS NOT NULL)
        )
);

-- Prevent duplicate pending invitations
-- for the same user and trip
CREATE UNIQUE INDEX uq_pending_invitation
    ON invitations (trip_id, invited_user_id)
    WHERE status = 'PENDING';

-- Find invitations received by a user
CREATE INDEX idx_invitations_invited_user
    ON invitations(invited_user_id);

COMMIT;
