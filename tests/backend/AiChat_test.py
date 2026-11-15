import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from threading import Barrier
from unittest.mock import Mock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete, select
from sqlalchemy.orm import Session

from backend.app.core import filter as authentication
from backend.app.core import security
from backend.app.core.AiChatClient import get_ai_chat_client
from backend.app.core.config import Settings
from backend.app.core.database import get_session
from backend.app.main import app
from backend.app.models import (
    AiChatDraft,
    AiChatMessage,
    AiChatSession,
    ItineraryItem,
    Proposal,
    Trip,
    TripMember,
    User,
)
from backend.app.repositories.AiChatRepository import AiChatRepository
from backend.app.schemas.AiChat import (
    AiChatDraftDecisionRequest,
    AiChatSendMessageRequest,
)
from backend.app.services.AiChatService import AiChatService


@pytest.fixture
def mock_session():
    session = Mock(spec=Session)
    rows = {(User, 7): User(user_id=7), (Trip, 12): Trip(trip_id=12)}
    session.get.side_effect = lambda model, identity: rows.get((model, identity))
    session.scalar.return_value = TripMember(trip_id=12, user_id=7, role="MEMBER")
    return session


@pytest.fixture
def client(monkeypatch, mock_session):
    settings = Settings(_env_file=None, jwt_secret="ai-chat-test-secret-" * 3)
    monkeypatch.setattr(authentication, "get_settings", lambda: settings)
    monkeypatch.setattr(security, "get_settings", lambda: settings)
    monkeypatch.setitem(app.dependency_overrides, get_session, lambda: mock_session)
    with TestClient(app, headers={"X-CSRF-Protection": "1"}) as client:
        yield client


def test_delete_chat_returns_empty_response_and_commits(client, mock_session):
    path = "/api/v1/chats/20"
    assert client.delete(path).status_code == 401
    mock_session.scalar.assert_not_called()
    client.cookies.set("access_token", security.create_access_token(7))
    chat = AiChatSession(chat_id=20, trip_id=12, user_id=7, title="Plan")
    mock_session.scalar.side_effect = [
        chat,
        Trip(trip_id=12),
        TripMember(trip_id=12, user_id=7, role="MEMBER"),
        chat,
    ]

    response = client.delete(path)

    assert response.status_code == 204
    assert response.content == b""
    mock_session.delete.assert_called_once_with(chat)
    mock_session.commit.assert_called_once()


@pytest.mark.parametrize(
    ("remaining_member", "expected"), [(None, 404), (False, 403), (True, 404)]
)
def test_delete_chat_rejects_unavailable_chat(
    client, mock_session, remaining_member, expected
):
    client.cookies.set("access_token", security.create_access_token(7))
    if remaining_member is None:
        mock_session.scalar.side_effect = [None]
    else:
        mock_session.scalar.side_effect = [
            AiChatSession(chat_id=20, trip_id=12, user_id=7, title="Plan"),
            Trip(trip_id=12),
            TripMember(trip_id=12, user_id=7, role="MEMBER")
            if remaining_member
            else None,
            None,  # The chat was removed before the locked lookup.
        ]

    assert client.delete("/api/v1/chats/20").status_code == expected
    mock_session.delete.assert_not_called()
    mock_session.commit.assert_not_called()
    mock_session.rollback.assert_called_once()


@pytest.mark.parametrize("chat_ids", [(21, 20), ()])
def test_list_chats_returns_sessions_or_empty_list(client, mock_session, chat_ids):
    path = "/api/v1/trips/12/chats"
    assert client.get(path).status_code == 401
    client.cookies.set("access_token", security.create_access_token(7))
    now = datetime(2030, 1, 1, tzinfo=UTC)
    mock_session.scalars.return_value = [
        AiChatSession(
            chat_id=chat_id,
            trip_id=12,
            user_id=7,
            title=f"Chat {chat_id}",
            created_at=now,
            updated_at=now,
        )
        for chat_id in chat_ids
    ]

    response = client.get(path)
    assert response.status_code == 200, response.text
    assert response.json() == [
        {
            "chat_id": chat_id,
            "trip_id": 12,
            "user_id": 7,
            "title": f"Chat {chat_id}",
            "created_at": "2030-01-01T00:00:00Z",
            "updated_at": "2030-01-01T00:00:00Z",
        }
        for chat_id in chat_ids
    ]
    mock_session.commit.assert_not_called()


@pytest.mark.parametrize(("trip_id", "expected"), [(12, 403), (99, 404)])
def test_list_chats_rejects_unavailable_trips_without_reading_chats(
    client, mock_session, trip_id, expected
):
    mock_session.scalar.return_value = None
    client.cookies.set("access_token", security.create_access_token(7))
    assert client.get(f"/api/v1/trips/{trip_id}/chats").status_code == expected
    mock_session.scalars.assert_not_called()


def test_create_chat_returns_complete_response_and_commits(client, mock_session):
    path = "/api/v1/trips/12/chats"
    assert client.post(path, json={}).status_code == 401

    now = datetime(2030, 1, 1, tzinfo=UTC)

    def assign_database_defaults():
        chat = mock_session.add.call_args.args[0]
        chat.chat_id = 20
        chat.created_at = chat.updated_at = now

    mock_session.flush.side_effect = assign_database_defaults
    client.cookies.set("access_token", security.create_access_token(7))
    response = client.post(path, json={"title": " My plan "})
    assert response.status_code == 201, response.text
    assert response.json() == {
        "chat_id": 20,
        "trip_id": 12,
        "user_id": 7,
        "title": "My plan",
        "created_at": "2030-01-01T00:00:00Z",
        "updated_at": "2030-01-01T00:00:00Z",
    }
    mock_session.commit.assert_called_once_with()
    mock_session.rollback.assert_not_called()


@pytest.mark.parametrize(
    ("trip_id", "expected", "detail"),
    [(12, 403, "Trip membership required."), (99, 404, "Trip not found.")],
)
def test_create_chat_preserves_trip_access_errors(
    client, mock_session, trip_id, expected, detail
):
    mock_session.scalar.return_value = None
    client.cookies.set("access_token", security.create_access_token(7))
    response = client.post(f"/api/v1/trips/{trip_id}/chats", json={})
    assert response.status_code == expected
    assert response.json() == {"detail": detail}
    mock_session.add.assert_not_called()
    mock_session.commit.assert_not_called()
    mock_session.rollback.assert_called_once_with()


def test_create_chat_rolls_back_on_write_failure(client, mock_session):
    mock_session.flush.side_effect = RuntimeError("test write failure")
    client.cookies.set("access_token", security.create_access_token(7))
    with pytest.raises(RuntimeError, match="test write failure"):
        client.post("/api/v1/trips/12/chats", json={})
    mock_session.commit.assert_not_called()
    mock_session.rollback.assert_called_once_with()


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("POST", "/api/v1/trips/12/chats", {"user_id": 8}),
        ("POST", "/api/v1/chats/20/messages", {"content": " "}),
        ("POST", "/api/v1/chats/20/messages", {"content": "hi", "role": "ASSISTANT"}),
        ("GET", "/api/v1/chats/20/messages?limit=101", None),
        ("GET", "/api/v1/chats/20/messages?before_id=0", None),
        ("PATCH", "/api/v1/chats/20/drafts/30", {"decision": "APPROVE"}),
        (
            "PATCH",
            "/api/v1/chats/20/drafts/30",
            {"decision": "ACCEPT", "proposals": []},
        ),
    ],
)
def test_invalid_input_is_rejected_before_service(client, method, path, body):
    client.cookies.set("access_token", security.create_access_token(7))
    assert client.request(method, path, json=body).status_code == 422


def test_list_messages_paginates_and_includes_submitted_proposals(client, mock_session):
    path = "/api/v1/chats/20/messages"
    assert client.get(path).status_code == 401
    client.cookies.set("access_token", security.create_access_token(7))
    chat = AiChatSession(chat_id=20, trip_id=12, user_id=7)
    member = TripMember(trip_id=12, user_id=7, role="MEMBER")
    mock_session.scalar.side_effect = [chat, member, chat, member]
    now = datetime(2030, 1, 1, tzinfo=UTC)
    messages = [
        AiChatMessage(
            message_id=message_id,
            chat_id=20,
            role=role,
            content="Plan",
            status="COMPLETED",
            created_at=now,
        )
        for message_id, role in [(103, "ASSISTANT"), (102, "USER"), (101, "USER")]
    ]
    draft = AiChatDraft(
        draft_id=30,
        message_id=103,
        kind="PROPOSAL",
        proposals=[
            {
                "title": "Park",
                "description": "Walk",
                "location": "NYC",
                "estimated_cost": "0",
                "starts_at": "2030-01-01T13:00:00Z",
                "ends_at": "2030-01-01T14:00:00Z",
            }
        ],
        status="ACCEPTED",
        created_at=now,
        decided_at=now,
    )
    mock_session.scalars.side_effect = [messages, [draft], [messages[-1]], []]
    mock_session.execute.return_value = [(30, 42)]

    response = client.get(path, params={"limit": 2})
    assert response.status_code == 200, response.text
    page = response.json()
    assert [message["message_id"] for message in page["messages"]] == [103, 102]
    assert page["next_before_id"] == 102
    assert page["messages"][0]["draft"]["status"] == "ACCEPTED"
    assert page["messages"][0]["draft"]["proposal_ids"] == [42]
    assert page["messages"][1]["draft"] is None

    response = client.get(
        path, params={"limit": 2, "before_id": page["next_before_id"]}
    )
    assert response.status_code == 200, response.text
    assert [message["message_id"] for message in response.json()["messages"]] == [101]
    assert response.json()["next_before_id"] is None
    mock_session.execute.assert_called_once()
    mock_session.commit.assert_not_called()


def test_list_messages_returns_empty_page(client, mock_session):
    client.cookies.set("access_token", security.create_access_token(7))
    mock_session.scalar.side_effect = [
        AiChatSession(chat_id=20, trip_id=12, user_id=7),
        TripMember(trip_id=12, user_id=7, role="MEMBER"),
    ]
    mock_session.scalars.return_value = []
    response = client.get("/api/v1/chats/20/messages")
    assert response.status_code == 200
    assert response.json() == {"messages": [], "next_before_id": None}


@pytest.mark.parametrize(("owns_chat", "expected"), [(False, 404), (True, 403)])
def test_list_messages_denies_access_before_reading_history(
    client, mock_session, owns_chat, expected
):
    client.cookies.set("access_token", security.create_access_token(7))
    chat = AiChatSession(chat_id=20, trip_id=12, user_id=7) if owns_chat else None
    mock_session.scalar.side_effect = [chat, None]
    assert client.get("/api/v1/chats/20/messages").status_code == expected
    mock_session.scalars.assert_not_called()


@pytest.fixture
def send_state(monkeypatch, mock_session):
    chat = AiChatSession(chat_id=20, trip_id=12, user_id=7)
    trip = mock_session.get(Trip, 12)
    trip.name = "NYC weekend"
    trip.destination = "New York"
    trip.start_date = date(2030, 1, 1)
    trip.end_date = date(2030, 1, 2)
    trip.timezone = "America/New_York"
    member = TripMember(trip_id=12, user_id=7, role="MEMBER")
    saved = []

    def scalar(statement):
        model = statement.column_descriptions[0]["entity"]
        if model is None:
            return 0
        if model is AiChatSession:
            return chat
        if model is TripMember:
            return member
        return saved[1]  # The assistant placeholder looked up after generation.

    def assign_database_defaults():
        row = mock_session.add.call_args.args[0]
        row.created_at = datetime(2030, 1, 1, tzinfo=UTC)
        if isinstance(row, AiChatMessage):
            row.message_id = 101 + len(saved)
        else:
            row.draft_id = 30
        saved.append(row)

    mock_session.scalar.side_effect = scalar
    mock_session.scalars.return_value = []
    mock_session.execute.return_value = []
    mock_session.flush.side_effect = assign_database_defaults
    provider = Mock()
    monkeypatch.setitem(app.dependency_overrides, get_ai_chat_client, lambda: provider)
    return chat, provider, saved


def test_send_message_without_provider_does_not_write(
    client, mock_session, monkeypatch
):
    monkeypatch.setitem(app.dependency_overrides, get_ai_chat_client, lambda: None)
    path = "/api/v1/chats/20/messages"
    body = {"content": "Plan my trip"}
    assert client.post(path, json=body).status_code == 401
    client.cookies.set("access_token", security.create_access_token(7))
    mock_session.scalar.side_effect = [
        AiChatSession(chat_id=20, trip_id=12, user_id=7),
        TripMember(trip_id=12, user_id=7, role="MEMBER"),
    ]
    assert client.post(path, json=body).status_code == 503
    mock_session.add.assert_not_called()
    mock_session.commit.assert_not_called()


def test_chat_context_returns_itinerary_used_by_send_message(
    client, mock_session, send_state
):
    _, provider, _ = send_state
    proposal = Proposal(
        title="Central Park",
        description="Walk around the lake",
        location="Manhattan",
        estimated_cost=Decimal("0.00"),
        starts_at=datetime(2030, 1, 1, 15, tzinfo=UTC),
        ends_at=datetime(2030, 1, 1, 16, tzinfo=UTC),
    )
    mock_session.execute.return_value = [(ItineraryItem(), proposal)]
    path = "/api/v1/chats/20/context"
    assert client.get(path).status_code == 401
    client.cookies.set("access_token", security.create_access_token(7))

    response = client.get(path)

    assert response.status_code == 200, response.text
    context = response.json()
    assert context["current_time"]
    assert context["destination"] == "New York"
    assert context["start_date"] == "2030-01-01"
    assert context["end_date"] == "2030-01-02"
    assert context["timezone"] == "America/New_York"
    assert context["itinerary"] == [
        {
            "title": "Central Park",
            "description": "Walk around the lake",
            "location": "Manhattan",
            "estimated_cost": "0.00",
            "starts_at": "2030-01-01T15:00:00Z",
            "ends_at": "2030-01-01T16:00:00Z",
        }
    ]
    mock_session.add.assert_not_called()
    mock_session.commit.assert_not_called()
    provider.generate.assert_not_called()

    provider.generate.return_value = {
        "content": "You already have a park walk planned."
    }
    reply = client.post(
        "/api/v1/chats/20/messages", json={"content": "What's planned?"}
    )
    assert reply.status_code == 201, reply.text
    context.pop("current_time")
    model_context = provider.generate.call_args.kwargs["trip_context"]
    assert {
        key: value for key, value in model_context.items() if key != "current_time"
    } == context


@pytest.mark.parametrize("expected", [403, 404])
def test_chat_context_requires_ownership_and_membership(client, mock_session, expected):
    client.cookies.set("access_token", security.create_access_token(7))
    mock_session.scalar.side_effect = (
        [AiChatSession(chat_id=20, trip_id=12, user_id=7), None]
        if expected == 403
        else [None]
    )

    assert client.get("/api/v1/chats/20/context").status_code == expected
    mock_session.execute.assert_not_called()


@pytest.mark.parametrize("with_draft", [False, True])
def test_send_message_commits_before_model_and_updates_placeholder(
    client, mock_session, send_state, with_draft
):
    chat, provider, saved = send_state

    def generate(*, messages, trip_context):
        mock_session.commit.assert_called_once()
        assert [(row.role, row.status) for row in saved] == [
            ("USER", "COMPLETED"),
            ("ASSISTANT", "GENERATING"),
        ]
        assert messages == [{"role": "user", "content": "Plan my trip"}]
        assert trip_context["timezone"] == "America/New_York"
        reply = {"content": "Visit the park."}
        if with_draft:
            reply["draft"] = {
                "kind": "PROPOSAL",
                "proposals": [
                    {
                        "title": "Park",
                        "description": "Walk",
                        "location": "NYC",
                        "estimated_cost": "0",
                        "starts_at": "2030-01-01T13:00:00Z",
                        "ends_at": "2030-01-01T14:00:00Z",
                    }
                ],
            }
        return reply

    provider.generate.side_effect = generate
    client.cookies.set("access_token", security.create_access_token(7))
    response = client.post(
        "/api/v1/chats/20/messages", json={"content": "Plan my trip"}
    )
    assert response.status_code == 201, response.text
    result = response.json()
    assert result["user_message"]["message_id"] == 101
    assistant = result["assistant_message"]
    assert (assistant["message_id"], assistant["content"], assistant["status"]) == (
        102,
        "Visit the park.",
        "COMPLETED",
    )
    if with_draft:
        assert isinstance(saved[2], AiChatDraft)
        assert assistant["draft"]["status"] == "PENDING"
        assert assistant["draft"]["proposal_ids"] == []
    else:
        assert len(saved) == 2
        assert assistant["draft"] is None
    assert chat.updated_at is not None
    assert mock_session.commit.call_count == 2


@pytest.mark.parametrize(("timeout", "expected"), [(False, 502), (True, 504)])
def test_send_message_marks_failed_placeholder_on_invalid_output_or_timeout(
    client, mock_session, send_state, timeout, expected
):
    _, provider, saved = send_state
    if timeout:
        provider.generate.side_effect = TimeoutError()
    else:
        provider.generate.return_value = {"content": " "}
    client.cookies.set("access_token", security.create_access_token(7))
    response = client.post(
        "/api/v1/chats/20/messages", json={"content": "Plan my trip"}
    )
    assert response.status_code == expected
    assert len(saved) == 2
    assert saved[0].status == "COMPLETED"
    assert (saved[1].status, saved[1].content) == ("FAILED", "")
    assert mock_session.commit.call_count == 2


def test_send_message_does_not_save_an_out_of_range_draft(client, send_state):
    _, provider, saved = send_state
    provider.generate.return_value = {
        "content": "Visit the park.",
        "draft": {
            "kind": "PROPOSAL",
            "proposals": [
                {
                    "title": "Park",
                    "description": "Walk",
                    "location": "NYC",
                    "estimated_cost": "0",
                    "starts_at": "2090-01-03T13:00:00Z",
                    "ends_at": "2090-01-03T14:00:00Z",
                }
            ],
        },
    }
    client.cookies.set("access_token", security.create_access_token(7))
    response = client.post(
        "/api/v1/chats/20/messages", json={"content": "Create a proposal"}
    )
    assert response.status_code == 502
    assert len(saved) == 2
    assert saved[1].status == "FAILED"


@pytest.fixture
def database():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL is required for PostgreSQL integration tests")
    engine = create_engine(url)
    try:
        with Session(engine) as session:
            yield session
    finally:
        engine.dispose()


def test_repository_isolates_owners_and_keeps_submitted_proposals_on_chat_delete(
    database,
):
    session = database
    repo = AiChatRepository(session)
    users = [
        User(
            user_name=uuid4().hex[:20],
            email=f"{uuid4()}@example.com",
            password_hash="unused",
        )
        for _ in range(2)
    ]
    session.add_all(users)
    session.flush()
    owner, other = users
    trip = Trip(
        name="Weekend",
        destination="NYC",
        start_date=date(2030, 1, 1),
        end_date=date(2030, 1, 2),
        organizer_id=owner.user_id,
    )
    session.add(trip)
    session.flush()
    chat = repo.add_chat(
        AiChatSession(trip_id=trip.trip_id, user_id=owner.user_id, title="Plan")
    )
    first = repo.add_message(
        AiChatMessage(chat_id=chat.chat_id, role="USER", content="Ideas?")
    )
    latest = repo.add_message(
        AiChatMessage(chat_id=chat.chat_id, role="ASSISTANT", content="Visit the park.")
    )
    proposal = Proposal(
        trip_id=trip.trip_id,
        author_id=owner.user_id,
        title="Park",
        description="Walk",
        estimated_cost=Decimal(0),
        location="NYC",
        starts_at=datetime(2030, 1, 1, 13, tzinfo=UTC),
        ends_at=datetime(2030, 1, 1, 14, tzinfo=UTC),
    )
    session.add(proposal)
    session.flush()
    draft = repo.add_draft(
        AiChatDraft(
            message_id=latest.message_id,
            kind="PROPOSAL",
            proposals=[
                {
                    "title": "Park",
                    "description": "Walk",
                    "location": "NYC",
                    "estimated_cost": "0",
                    "starts_at": "2030-01-01T13:00:00Z",
                    "ends_at": "2030-01-01T14:00:00Z",
                }
            ],
            status="ACCEPTED",
            decided_at=datetime.now(UTC),
        )
    )
    draft_id, proposal_id, chat_id = draft.draft_id, proposal.proposal_id, chat.chat_id
    repo.add_proposal_links(draft_id, [proposal_id])
    assert repo.list_chats(trip.trip_id, other.user_id) == []
    assert repo.find_chat(chat_id, other.user_id) is None
    assert repo.list_messages(chat_id, other.user_id, limit=10) == []
    assert repo.find_draft(chat_id, draft_id, other.user_id) is None
    assert repo.list_messages(chat_id, owner.user_id, limit=1) == [latest]
    assert repo.list_messages(
        chat_id, owner.user_id, limit=2, before_id=latest.message_id
    ) == [first]
    assert repo.list_drafts(chat_id, owner.user_id, [latest.message_id]) == [draft]
    assert repo.find_draft(chat_id, draft_id, owner.user_id, lock=True) == draft
    assert repo.list_proposal_ids(draft_id) == [proposal_id]

    repo.delete_chat(chat)
    assert (
        session.scalar(
            select(AiChatMessage.message_id).where(AiChatMessage.chat_id == chat_id)
        )
        is None
    )
    assert (
        session.scalar(
            select(AiChatDraft.draft_id).where(AiChatDraft.draft_id == draft_id)
        )
        is None
    )
    assert repo.list_proposal_ids(draft_id) == []
    assert (
        session.scalar(
            select(Proposal.proposal_id).where(Proposal.proposal_id == proposal_id)
        )
        == proposal_id
    )


@pytest.fixture
def decision_data(database):
    repo = AiChatRepository(database)
    owner = User(
        user_name=uuid4().hex[:20],
        email=f"{uuid4()}@example.com",
        password_hash="unused",
    )
    database.add(owner)
    database.flush()
    user_id = owner.user_id
    trip = Trip(
        name="Weekend",
        destination="NYC",
        timezone="America/New_York",
        start_date=date(2090, 1, 1),
        end_date=date(2090, 1, 2),
        organizer_id=user_id,
    )
    database.add(trip)
    database.flush()
    trip_id = trip.trip_id
    database.add(TripMember(trip_id=trip_id, user_id=user_id, role="ORGANIZER"))
    chat = repo.add_chat(AiChatSession(trip_id=trip_id, user_id=user_id, title="Plan"))
    message = repo.add_message(
        AiChatMessage(chat_id=chat.chat_id, role="ASSISTANT", content="Two activities")
    )
    activity = {
        "title": "Park",
        "description": "Walk",
        "location": "NYC",
        "estimated_cost": "0",
        "starts_at": "2090-01-01T13:00:00Z",
        "ends_at": "2090-01-01T14:00:00Z",
    }
    draft = repo.add_draft(
        AiChatDraft(
            message_id=message.message_id,
            kind="ITINERARY",
            proposals=[
                activity,
                {
                    **activity,
                    "title": "Museum",
                    "starts_at": "2090-01-01T14:00:00Z",
                    "ends_at": "2090-01-01T15:00:00Z",
                },
            ],
        )
    )
    chat_id, draft_id = chat.chat_id, draft.draft_id
    database.commit()
    try:
        yield chat_id, draft_id, user_id, trip_id
    finally:
        database.rollback()
        database.execute(delete(Proposal).where(Proposal.trip_id == trip_id))
        database.execute(delete(User).where(User.user_id == user_id))
        database.commit()


@pytest.mark.parametrize(
    ("decision", "expected"), [("ACCEPT", "ACCEPTED"), ("REJECT", "REJECTED")]
)
def test_draft_decision_is_idempotent_and_cannot_be_reversed(
    database, decision_data, decision, expected
):
    chat_id, draft_id, user_id, trip_id = decision_data
    service = AiChatService(database)
    request = AiChatDraftDecisionRequest(decision=decision)
    result = service.decide_draft(chat_id, draft_id, request, user_id)
    assert result.status == expected and result.decided_at is not None
    assert service.decide_draft(chat_id, draft_id, request, user_id) == result
    opposite = AiChatDraftDecisionRequest(
        decision="REJECT" if decision == "ACCEPT" else "ACCEPT"
    )
    with pytest.raises(HTTPException) as error:
        service.decide_draft(chat_id, draft_id, opposite, user_id)
    assert error.value.status_code == 409

    proposals = list(
        database.scalars(
            select(Proposal)
            .where(Proposal.trip_id == trip_id)
            .order_by(Proposal.proposal_id)
        )
    )
    assert len(proposals) == (2 if decision == "ACCEPT" else 0)
    assert [proposal.proposal_id for proposal in proposals] == result.proposal_ids
    assert all(
        proposal.author_id == user_id and proposal.status == "PENDING"
        for proposal in proposals
    )


def test_send_message_blocks_a_second_turn_until_the_first_reply_is_available(
    database, decision_data
):
    chat_id, _, user_id, _ = decision_data
    provider = Mock()
    service = AiChatService(database, provider)
    first = AiChatSendMessageRequest(content="Suggest a park.")
    second = AiChatSendMessageRequest(content="Where is that park?")

    def generate_first(**kwargs):
        with Session(database.get_bind()) as other_session:
            with pytest.raises(HTTPException) as error:
                AiChatService(other_session, provider).send_message(
                    chat_id, second, user_id
                )
            assert error.value.status_code == 409
        return {"content": "Visit Central Park."}

    provider.generate.side_effect = generate_first
    service.send_message(chat_id, first, user_id)
    provider.generate.side_effect = None
    provider.generate.return_value = {"content": "It is in Manhattan."}
    service.send_message(chat_id, second, user_id)
    assert provider.generate.call_count == 2
    assert provider.generate.call_args.kwargs["messages"][-2:] == [
        {"role": "assistant", "content": "Visit Central Park."},
        {"role": "user", "content": second.content},
    ]


def test_send_message_recovers_expired_generation(database, decision_data):
    chat_id, _, user_id, _ = decision_data
    stale = AiChatRepository(database).add_message(
        AiChatMessage(
            chat_id=chat_id,
            role="ASSISTANT",
            status="GENERATING",
            content="",
            created_at=datetime.now(UTC) - timedelta(days=1),
        )
    )
    stale_id = stale.message_id
    database.commit()
    provider = Mock()
    provider.generate.return_value = {"content": "Welcome back."}
    AiChatService(database, provider).send_message(
        chat_id, AiChatSendMessageRequest(content="Hello"), user_id
    )
    assert database.get(AiChatMessage, stale_id).status == "FAILED"


@pytest.mark.parametrize(
    ("failure", "expected"),
    [("date", 422), ("overlap", 422), ("itinerary", 422), ("capacity", 409)],
)
def test_invalid_batch_leaves_draft_pending_and_proposals_unchanged(
    database, decision_data, failure, expected
):
    chat_id, draft_id, user_id, trip_id = decision_data
    draft = database.get(AiChatDraft, draft_id)
    existing = 0
    if failure == "date":
        first, second = draft.proposals
        draft.proposals = [
            first,
            {
                **second,
                "starts_at": "2090-01-03T13:00:00Z",
                "ends_at": "2090-01-03T14:00:00Z",
            },
        ]
    elif failure == "overlap":
        first, second = draft.proposals
        draft.proposals = [{**first}, {**first, "title": second["title"]}]
    elif failure == "itinerary":
        existing = 1
        proposal = Proposal(
            trip_id=trip_id,
            author_id=user_id,
            title="Existing activity",
            description="Walk",
            estimated_cost=Decimal(0),
            location="NYC",
            starts_at=datetime(2090, 1, 1, 13, tzinfo=UTC),
            ends_at=datetime(2090, 1, 1, 14, tzinfo=UTC),
            status="APPROVED",
        )
        database.add(proposal)
        database.flush()
        database.add(ItineraryItem(proposal_id=proposal.proposal_id))
    else:
        existing = 99
        database.add_all(
            [
                Proposal(
                    trip_id=trip_id,
                    author_id=user_id,
                    title=f"Existing {index}",
                    description="Walk",
                    estimated_cost=Decimal(0),
                    location="NYC",
                    starts_at=datetime(2090, 1, 1, 13, tzinfo=UTC),
                    ends_at=datetime(2090, 1, 1, 14, tzinfo=UTC),
                )
                for index in range(existing)
            ]
        )
    database.commit()
    service = AiChatService(database)
    with pytest.raises(HTTPException) as error:
        service.decide_draft(
            chat_id, draft_id, AiChatDraftDecisionRequest(decision="ACCEPT"), user_id
        )
    assert error.value.status_code == expected
    assert database.get(AiChatDraft, draft_id).status == "PENDING"
    assert service.repository.list_proposal_ids(draft_id) == []
    assert (
        len(list(database.scalars(select(Proposal).where(Proposal.trip_id == trip_id))))
        == existing
    )


def test_accept_rolls_back_flushed_proposals_when_link_write_fails(
    database, decision_data, monkeypatch
):
    chat_id, draft_id, user_id, trip_id = decision_data
    service = AiChatService(database)
    original = service.repository.add_proposal_links

    def fail_after_flush(draft_id, proposal_ids):
        original(draft_id, proposal_ids)
        raise RuntimeError("test link write failure")

    monkeypatch.setattr(service.repository, "add_proposal_links", fail_after_flush)
    with pytest.raises(RuntimeError, match="test link write failure"):
        service.decide_draft(
            chat_id, draft_id, AiChatDraftDecisionRequest(decision="ACCEPT"), user_id
        )
    assert (
        list(database.scalars(select(Proposal).where(Proposal.trip_id == trip_id)))
        == []
    )
    assert service.repository.list_proposal_ids(draft_id) == []
    draft = database.get(AiChatDraft, draft_id)
    assert draft.status == "PENDING" and draft.decided_at is None


def test_concurrent_accepts_return_same_proposal_ids(database, decision_data):
    chat_id, draft_id, user_id, trip_id = decision_data
    engine = database.get_bind()
    ready = Barrier(2)

    def accept():
        with Session(engine) as session:
            # Both requests start with the same pending draft in their identity maps.
            cached = session.get(AiChatDraft, draft_id)
            assert cached.status == "PENDING"
            ready.wait(timeout=10)
            return AiChatService(session).decide_draft(
                chat_id,
                draft_id,
                AiChatDraftDecisionRequest(decision="ACCEPT"),
                user_id,
            )

    with ThreadPoolExecutor(max_workers=2) as pool:
        first, second = [pool.submit(accept) for _ in range(2)]
        result = first.result(timeout=20)
        assert result == second.result(timeout=20)
    assert len(result.proposal_ids) == 2
    assert set(
        database.scalars(
            select(Proposal.proposal_id).where(Proposal.trip_id == trip_id)
        )
    ) == set(result.proposal_ids)


def test_draft_decision_requires_owner_and_membership(database, decision_data):
    chat_id, draft_id, user_id, _ = decision_data
    service = AiChatService(database)
    request = AiChatDraftDecisionRequest(decision="REJECT")
    with pytest.raises(HTTPException) as error:
        service.decide_draft(chat_id, draft_id, request, 0)
    assert error.value.status_code == 404

    with pytest.raises(HTTPException) as error:
        service.decide_draft(chat_id, draft_id + 1, request, user_id)
    assert error.value.status_code == 404

    trip_id = decision_data[3]
    database.delete(database.get(TripMember, (trip_id, user_id)))
    database.commit()
    with pytest.raises(HTTPException) as error:
        service.decide_draft(chat_id, draft_id, request, user_id)
    assert error.value.status_code == 403
    assert database.get(AiChatDraft, draft_id).status == "PENDING"


def test_delete_chat_cascades_to_drafts_and_keeps_submitted_proposals(
    database, decision_data
):
    chat_id, draft_id, user_id, trip_id = decision_data
    service = AiChatService(database)
    accepted = service.decide_draft(
        chat_id, draft_id, AiChatDraftDecisionRequest(decision="ACCEPT"), user_id
    )

    service.delete_chat(chat_id, user_id)

    with Session(database.get_bind()) as reader:
        assert reader.get(AiChatSession, chat_id) is None
        assert (
            reader.scalar(
                select(AiChatMessage.message_id).where(AiChatMessage.chat_id == chat_id)
            )
            is None
        )
        assert reader.get(AiChatDraft, draft_id) is None
        assert AiChatRepository(reader).list_proposal_ids(draft_id) == []
        assert set(
            reader.scalars(
                select(Proposal.proposal_id).where(Proposal.trip_id == trip_id)
            )
        ) == set(accepted.proposal_ids)
