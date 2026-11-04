
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



-- proposals polls poll_eligibility votes itinerary_items
-- =========================================
-- 5. Proposals
-- =========================================
CREATE TABLE proposals (
    proposal_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    trip_id BIGINT NOT NULL
        REFERENCES trips(trip_id)
        ON DELETE CASCADE,

    author_user_id BIGINT NOT NULL
        REFERENCES users(user_id)
        ON DELETE CASCADE,

    title TEXT NOT NULL
        CHECK (LENGTH(TRIM(title)) > 0),

    location TEXT NOT NULL
        CHECK (LENGTH(TRIM(location)) > 0),

    suggested_start_at TIMESTAMPTZ NOT NULL,

    description TEXT NOT NULL
        CHECK (LENGTH(TRIM(description)) > 0),

    estimated_cost NUMERIC(12, 2) NOT NULL
        CHECK (estimated_cost >= 0),

    status TEXT NOT NULL DEFAULT 'PENDING'
        CHECK (
            status IN (
                'PENDING',
                'OPEN',
                'APPROVED',
                'REJECTED',
                'TIED',
                'WITHDRAWN',
                'CANCELLED'
            )
        ),

    created_at TIMESTAMPTZ NOT NULL
        DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT uq_proposals_trip_proposal
        UNIQUE (trip_id, proposal_id)
);

-- Find proposals belonging to a trip
CREATE INDEX idx_proposals_trip_id
    ON proposals(trip_id);

-- =========================================
-- 6. Polls
-- =========================================
CREATE TABLE polls (
    poll_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    proposal_id BIGINT NOT NULL UNIQUE
        REFERENCES proposals(proposal_id)
        ON DELETE CASCADE,

    opened_by_user_id BIGINT NOT NULL
        REFERENCES users(user_id),

    opened_at TIMESTAMPTZ NOT NULL
        DEFAULT CURRENT_TIMESTAMP,

    closes_at TIMESTAMPTZ NOT NULL,

    closed_at TIMESTAMPTZ,

    status TEXT NOT NULL DEFAULT 'OPEN'
        CHECK (status IN ('OPEN', 'CLOSED')),

    close_reason TEXT
        CHECK (
            close_reason IN ('DEADLINE', 'WITHDRAWAL')
        ),

    ballot_outcome TEXT
        CHECK (
            ballot_outcome IN (
                'APPROVED',
                'REJECTED',
                'TIED'
            )
        ),

    tie_resolution TEXT
        CHECK (
            tie_resolution IN ('APPROVED', 'REJECTED')
        ),

    resolved_by_user_id BIGINT
        REFERENCES users(user_id),

    resolved_at TIMESTAMPTZ,

    CONSTRAINT ck_polls_time
        CHECK (closes_at > opened_at),

    CONSTRAINT ck_polls_status
        CHECK (
            (
                status = 'OPEN'
                AND closed_at IS NULL
                AND close_reason IS NULL
                AND ballot_outcome IS NULL
                AND tie_resolution IS NULL
                AND resolved_by_user_id IS NULL
                AND resolved_at IS NULL
            )
            OR
            (
                status = 'CLOSED'
                AND closed_at IS NOT NULL
                AND close_reason IS NOT NULL
            )
        ),

    CONSTRAINT ck_polls_outcome
        CHECK (
            (
                close_reason = 'DEADLINE'
                AND ballot_outcome IS NOT NULL
            )
            OR
            (
                close_reason = 'WITHDRAWAL'
                AND ballot_outcome IS NULL
                AND tie_resolution IS NULL
                AND resolved_by_user_id IS NULL
                AND resolved_at IS NULL
            )
            OR
            (
                close_reason IS NULL
                AND ballot_outcome IS NULL
            )
        ),

    CONSTRAINT ck_polls_tie_resolution
        CHECK (
            (
                tie_resolution IS NULL
                AND resolved_by_user_id IS NULL
                AND resolved_at IS NULL
            )
            OR
            (
                ballot_outcome = 'TIED'
                AND tie_resolution IS NOT NULL
                AND resolved_by_user_id IS NOT NULL
                AND resolved_at IS NOT NULL
            )
        )
);

-- =========================================
-- 7. Poll Eligibility
-- =========================================
CREATE TABLE poll_eligibility (
    poll_id BIGINT NOT NULL
        REFERENCES polls(poll_id)
        ON DELETE CASCADE,

    user_id BIGINT NOT NULL
        REFERENCES users(user_id)
        ON DELETE CASCADE,

    recorded_at TIMESTAMPTZ NOT NULL
        DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (poll_id, user_id)
);

-- =========================================
-- 8. Votes
-- =========================================
CREATE TABLE votes (
    poll_id BIGINT NOT NULL,

    user_id BIGINT NOT NULL,

    choice TEXT NOT NULL
        CHECK (choice IN ('YES', 'NO')),

    updated_at TIMESTAMPTZ NOT NULL
        DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (poll_id, user_id),

    CONSTRAINT fk_votes_eligibility
        FOREIGN KEY (poll_id, user_id)
        REFERENCES poll_eligibility(poll_id, user_id)
        ON DELETE CASCADE
);

-- =========================================
-- 9. Itinerary Items
-- =========================================
CREATE TABLE itinerary_items (
    item_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    trip_id BIGINT NOT NULL,

    proposal_id BIGINT NOT NULL UNIQUE,

    scheduled_start_at TIMESTAMPTZ NOT NULL,

    status TEXT NOT NULL DEFAULT 'APPROVED'
        CHECK (
            status IN ('APPROVED', 'CANCELLED')
        ),

    CONSTRAINT fk_itinerary_trip
        FOREIGN KEY (trip_id)
        REFERENCES trips(trip_id)
        ON DELETE CASCADE,

    CONSTRAINT fk_itinerary_proposal
        FOREIGN KEY (trip_id, proposal_id)
        REFERENCES proposals(trip_id, proposal_id)
        ON DELETE CASCADE
);

-- Support efficient itinerary queries
CREATE INDEX idx_itinerary_trip_status_start
    ON itinerary_items (
        trip_id,
        status,
        scheduled_start_at
    );

-- Ensure at most one organizer per trip
CREATE UNIQUE INDEX uq_trip_members_one_organizer
    ON trip_members(trip_id)
    WHERE role = 'ORGANIZER';