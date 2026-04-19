"""API contract tests for /v1/users CRUD."""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.api.v1.deps import CurrentPrincipal, require_admin
from app.db.session import get_db
from app.main import app


async def _fake_admin() -> CurrentPrincipal:
    return CurrentPrincipal(id="admin-1", email="admin@example.com", user_type="admin")


async def _fake_db():
    yield None


@pytest.fixture(autouse=True)
def _override_dependencies():
    app.dependency_overrides[require_admin] = _fake_admin
    app.dependency_overrides[get_db] = _fake_db
    yield
    app.dependency_overrides.pop(require_admin, None)
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture(scope="session", autouse=True)
async def setup_test_db():
    """Override global DB bootstrap; this contract test does not hit DB."""
    yield


def _user_stub(*, email: str = "doctor@clinic.org"):
    return SimpleNamespace(
        id=uuid4(),
        email=email,
        role="doctor",
        provider_id=uuid4(),
        is_active=True,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


async def test_create_user_success(async_client):
    created = _user_stub()
    with (
        patch("app.api.v1.endpoints.users.UserService.get_by_email", new_callable=AsyncMock, return_value=None),
        patch("app.api.v1.endpoints.users.UserService.create_user", new_callable=AsyncMock, return_value=created) as create_mock,
    ):
        response = await async_client.post(
            "/v1/users",
            json={"email": "doctor@clinic.org", "password": "Doctor@2026!", "is_active": True},
        )

    assert response.status_code == 201
    payload = create_mock.await_args.kwargs
    assert payload["email"] == "doctor@clinic.org"
    assert payload["role"] == "doctor"
    assert payload["is_active"] is True
    data = response.json()["data"]
    assert data["email"] == "doctor@clinic.org"
    assert data["role"] == "doctor"


async def test_create_user_conflict(async_client):
    with patch("app.api.v1.endpoints.users.UserService.get_by_email", new_callable=AsyncMock, return_value=_user_stub()):
        response = await async_client.post(
            "/v1/users",
            json={"email": "doctor@clinic.org", "password": "Doctor@2026!"},
        )

    assert response.status_code == 409
    assert response.json()["detail"] == "Email already registered"


async def test_get_list_update_delete_user(async_client):
    user = _user_stub()
    with (
        patch("app.api.v1.endpoints.users.UserService.list_users", new_callable=AsyncMock, return_value=[user]) as list_mock,
        patch("app.api.v1.endpoints.users.UserService.get_by_id", new_callable=AsyncMock, side_effect=[user, user, user]) as get_mock,
        patch("app.api.v1.endpoints.users.UserService.get_by_email", new_callable=AsyncMock, return_value=None),
        patch("app.api.v1.endpoints.users.UserService.update", new_callable=AsyncMock, return_value=user) as update_mock,
        patch("app.api.v1.endpoints.users.UserService.soft_delete", new_callable=AsyncMock) as delete_mock,
    ):
        list_resp = await async_client.get("/v1/users")
        assert list_resp.status_code == 200
        list_mock.assert_awaited_once()
        assert list_resp.json()["data"][0]["email"] == user.email

        get_resp = await async_client.get(f"/v1/users/{user.id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["data"]["id"] == str(user.id)

        update_resp = await async_client.put(
            f"/v1/users/{user.id}",
            json={"email": "new-doctor@clinic.org", "is_active": False},
        )
        assert update_resp.status_code == 200
        update_kwargs = update_mock.await_args.kwargs
        assert update_kwargs["email"] == "new-doctor@clinic.org"
        assert update_kwargs["is_active"] is False

        delete_resp = await async_client.delete(f"/v1/users/{user.id}")
        assert delete_resp.status_code == 204
        delete_mock.assert_awaited_once()
        assert get_mock.await_count == 3
