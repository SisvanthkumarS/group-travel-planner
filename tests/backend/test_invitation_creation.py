from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.models import Trip, User
from backend.app.schemas.invitation import CreateInvitationRequest
from backend.app.services.InvitationService import InvitationService


@pytest.fixture
def service():
    service = InvitationService(Mock(spec=Session))
    service.trip_invitation_repository = Mock()
    service.trip_repository = Mock()
    service.user_repository = Mock()
    service.repository = Mock()
    service.trip_invitation_repository.find_trip_for_update.return_value = Trip(
        trip_id=12, organizer_id=7
    )
    service.trip_repository.find_membership.return_value = None
    service.repository.find_pending.return_value = None
    recipient = User(user_id=8, user_name="Alice", email="alice@example.com")
    service.user_repository.find_by_email.return_value = recipient
    service.user_repository.find_by_user_name.return_value = recipient

    def persist(invitation):
        invitation.invitation_id = 9
        invitation.created_at = datetime.now(UTC)
        return invitation

    service.repository.add.side_effect = persist
    return service


@pytest.mark.parametrize(
    "identifier", [{"email": "alice@example.com"}, {"user_name": "Alice"}]
)
def test_create_invitation_commits_pending_record(service, identifier):
    result = service.create_invitation(12, CreateInvitationRequest(**identifier), 7)
    assert (result.trip_id, result.invited_user_id, result.invited_by_user_id) == (
        12,
        8,
        7,
    )
    assert result.status == "PENDING" and result.responded_at is None
    service.session.commit.assert_called_once()
    service.session.rollback.assert_not_called()


@pytest.mark.parametrize(
    "case, expected",
    [
        ("missing-trip", 404),
        ("not-organizer", 403),
        ("missing-user", 404),
        ("self", 409),
        ("member", 409),
        ("pending", 409),
    ],
)
def test_rejected_invitation_rolls_back_without_writing(service, case, expected):
    if case == "missing-trip":
        service.trip_invitation_repository.find_trip_for_update.return_value = None
    elif case == "not-organizer":
        service.trip_invitation_repository.find_trip_for_update.return_value.organizer_id = 99
    elif case == "missing-user":
        service.user_repository.find_by_email.return_value = None
    elif case == "self":
        service.user_repository.find_by_email.return_value = User(user_id=7)
    elif case == "member":
        service.trip_repository.find_membership.return_value = Mock()
    else:
        service.repository.find_pending.return_value = Mock()
    with pytest.raises(HTTPException) as error:
        service.create_invitation(
            12, CreateInvitationRequest(email="alice@example.com"), 7
        )
    assert error.value.status_code == expected
    service.repository.add.assert_not_called()
    service.session.commit.assert_not_called()
    service.session.rollback.assert_called_once()


def test_email_lookup_does_not_fall_back_to_username(service):
    service.user_repository.find_by_email.return_value = None
    with pytest.raises(HTTPException) as error:
        service.create_invitation(
            12,
            CreateInvitationRequest(email="missing@example.com", user_name="Alice"),
            7,
        )
    assert error.value.status_code == 404
    service.user_repository.find_by_user_name.assert_not_called()


@pytest.mark.parametrize(
    "constraint, expected", [("uq_pending_invitation", 409), ("unrelated", None)]
)
def test_constraint_errors_are_handled_selectively(service, constraint, expected):
    original = RuntimeError("Database constraint violation")
    original.diag = SimpleNamespace(constraint_name=constraint)
    database_error = IntegrityError("INSERT", {}, original)
    service.repository.add.side_effect = database_error
    with pytest.raises(HTTPException if expected else IntegrityError) as error:
        service.create_invitation(12, CreateInvitationRequest(user_name="Alice"), 7)
    if expected:
        assert error.value.status_code == expected
    else:
        assert error.value is database_error
    service.session.rollback.assert_called_once()


def test_invitation_commit_failure_rolls_back(service):
    service.session.commit.side_effect = RuntimeError("Commit failed")
    with pytest.raises(RuntimeError, match="Commit failed"):
        service.create_invitation(12, CreateInvitationRequest(user_name="Alice"), 7)
    service.session.rollback.assert_called_once()
