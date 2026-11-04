
BEGIN;

-- =========================================
-- 1. Users
-- =========================================
CREATE TABLE users (
    user_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    email TEXT NOT NULL
        CHECK (LENGTH(TRIM(email)) > 0),

    user_name VARCHAR(30) NOT NULL
        CHECK (LENGTH(TRIM(user_name)) BETWEEN 1 AND 30),

    password_hash TEXT NOT NULL,

    created_at TIMESTAMPTZ NOT NULL
        DEFAULT CURRENT_TIMESTAMP
);

-- Email uniqueness, ignoring letter case
CREATE UNIQUE INDEX uq_users_email_lower
    ON users (LOWER(TRIM(email)));

-- Username uniqueness is case-sensitive, matching backend login behavior.
CREATE UNIQUE INDEX uq_users_user_name
    ON users (user_name);


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

    timezone TEXT NOT NULL DEFAULT 'UTC',

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


-- =========================================
-- 5. Proposals (Alembic revision 0006)
-- =========================================
CREATE TABLE proposals (
    proposal_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    trip_id BIGINT NOT NULL
        REFERENCES trips(trip_id)
        ON DELETE CASCADE,

    author_id BIGINT NOT NULL
        REFERENCES users(user_id),

    title TEXT NOT NULL
        CHECK (LENGTH(TRIM(title)) > 0),

    description TEXT NOT NULL
        CHECK (LENGTH(TRIM(description)) > 0),

    estimated_cost NUMERIC NOT NULL
        CHECK (estimated_cost >= 0),

    location TEXT NOT NULL
        CHECK (LENGTH(TRIM(location)) > 0),

    starts_at TIMESTAMPTZ NOT NULL,
    ends_at TIMESTAMPTZ NOT NULL,

    status TEXT NOT NULL DEFAULT 'PENDING'
        CHECK (status IN (
            'PENDING', 'OPEN', 'TIED', 'APPROVED',
            'REJECTED', 'WITHDRAWN', 'CANCELLED'
        )),

    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT ck_proposals_times CHECK (ends_at > starts_at)
);

CREATE INDEX idx_proposals_trip
    ON proposals(trip_id);


-- =========================================
-- 6. Itinerary items (revision 0006)
-- =========================================
CREATE TABLE itinerary_items (
    item_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    proposal_id BIGINT NOT NULL UNIQUE
        REFERENCES proposals(proposal_id)
        ON DELETE CASCADE,

    status TEXT NOT NULL DEFAULT 'ACTIVE'
        CHECK (status IN ('ACTIVE', 'CANCELLED')),

    canceled_at TIMESTAMPTZ,

    CONSTRAINT ck_itinerary_items_status CHECK (
        (status = 'ACTIVE' AND canceled_at IS NULL)
        OR
        (status = 'CANCELLED' AND canceled_at IS NOT NULL)
    )
);


-- =========================================
-- 7. Polls (revision 0006)
-- =========================================
CREATE TABLE polls (
    poll_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    proposal_id BIGINT NOT NULL UNIQUE
        REFERENCES proposals(proposal_id)
        ON DELETE CASCADE,

    status TEXT NOT NULL DEFAULT 'OPEN'
        CHECK (status IN ('OPEN', 'CLOSED', 'CANCELED')),

    deadline TIMESTAMPTZ NOT NULL,
    opened_at TIMESTAMPTZ NOT NULL,
    closed_at TIMESTAMPTZ,

    decision TEXT,
    outcome TEXT,

    resolved_by_user_id BIGINT
        REFERENCES users(user_id),

    resolved_at TIMESTAMPTZ,

    CONSTRAINT ck_polls_resolution CHECK (
        (decision IS NULL AND resolved_by_user_id IS NULL AND resolved_at IS NULL)
        OR
        (
            decision IN ('APPROVE', 'REJECT')
            AND resolved_by_user_id IS NOT NULL
            AND resolved_at IS NOT NULL
            AND status = 'CLOSED'
        )
    ),

    CONSTRAINT ck_polls_outcome CHECK (
        (status = 'CLOSED' AND outcome IN ('APPROVED', 'REJECTED', 'TIED'))
        OR
        (status IN ('OPEN', 'CANCELED') AND outcome IS NULL)
    ),

    CONSTRAINT ck_polls_closed_at CHECK (
        (status = 'OPEN' AND closed_at IS NULL)
        OR
        (status IN ('CLOSED', 'CANCELED') AND closed_at IS NOT NULL)
    ),

    CONSTRAINT ck_polls_deadline CHECK (deadline > opened_at)
);

CREATE INDEX idx_polls_status_deadline
    ON polls(status, deadline);


-- =========================================
-- 8. Eligible voters (revision 0006)
-- =========================================
CREATE TABLE eligible_voters (
    poll_id BIGINT NOT NULL
        REFERENCES polls(poll_id)
        ON DELETE CASCADE,

    user_id BIGINT NOT NULL
        REFERENCES users(user_id),

    PRIMARY KEY (poll_id, user_id)
);


-- =========================================
-- 9. Vote history (revision 0006)
-- =========================================
CREATE TABLE vote_history (
    event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    poll_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,

    choice TEXT NOT NULL
        CHECK (choice IN ('YES', 'NO')),

    updated_at TIMESTAMPTZ NOT NULL,

    CONSTRAINT fk_vote_history_eligible_voter
        FOREIGN KEY (poll_id, user_id)
        REFERENCES eligible_voters(poll_id, user_id)
        ON DELETE CASCADE
);

CREATE INDEX idx_vote_history_poll
    ON vote_history(poll_id, event_id);


-- =========================================
-- 10. Current votes (revision 0006)
-- =========================================
CREATE TABLE votes (
    poll_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,

    choice TEXT NOT NULL
        CHECK (choice IN ('YES', 'NO')),

    updated_at TIMESTAMPTZ NOT NULL,

    PRIMARY KEY (poll_id, user_id),

    CONSTRAINT fk_votes_eligible_voter
        FOREIGN KEY (poll_id, user_id)
        REFERENCES eligible_voters(poll_id, user_id)
        ON DELETE CASCADE
);

COMMIT;
