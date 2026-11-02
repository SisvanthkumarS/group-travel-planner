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