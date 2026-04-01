from unittest.mock import MagicMock, patch
from uuid import uuid4

from fastapi.testclient import TestClient

from app.api.user.user_model import Role
from app.core.config import settings
from tests.utils.utils import random_email, random_lower_string


def _create_mock_user(role: Role = Role.USER):
    """Create a mock user object."""
    user = MagicMock()
    user.id = uuid4()
    user.email = random_email()
    user.role = role
    user.full_name = "Mock User"
    return user


def _create_user_and_headers_with_mocks(
    _client: TestClient, role: Role = Role.USER
) -> tuple[MagicMock, dict[str, str]]:
    """Create a mock user and authentication headers."""
    user = _create_mock_user(role)
    headers = {"Authorization": f"Bearer mock-token-{user.id}"}
    return user, headers


@patch("tests.utils.user.user_authentication_headers")
def test_patch_my_profile_updates_burnout_level(
    mock_auth_headers: MagicMock, client: TestClient
) -> None:
    user, headers = _create_user_and_headers_with_mocks(client)
    mock_auth_headers.return_value = headers

    response = client.patch(
        f"{settings.API_V1_STR}/profiles/me",
        headers=headers,
        json={"burnout_level": 7.5},
    )

    assert response.status_code == 200
    content = response.json()
    assert content["burnout_level"] == 7.5


def test_patch_my_profile_rejects_position_for_normal_user(
    client: TestClient,
) -> None:
    user, headers = _create_user_and_headers_with_mocks(client)

    response = client.patch(
        f"{settings.API_V1_STR}/profiles/me",
        headers=headers,
        json={"position_id": 1},
    )

    assert response.status_code == 403
    assert response.json() == {
        "detail": "Moderator or admin access required",
    }


def test_patch_my_profile_allows_admin_to_update_position(
    client: TestClient,
) -> None:
    admin_user, headers = _create_user_and_headers_with_mocks(client, role=Role.ADMIN)
    position_id = 123

    response = client.patch(
        f"{settings.API_V1_STR}/profiles/me",
        headers=headers,
        json={"burnout_level": 2.25, "position_id": position_id},
    )

    assert response.status_code == 200
    content = response.json()
    assert content["burnout_level"] == 2.25
    assert content["position_id"] == position_id


def test_put_my_profile_skills_rejects_normal_user(
    client: TestClient,
) -> None:
    user, headers = _create_user_and_headers_with_mocks(client)

    response = client.put(
        f"{settings.API_V1_STR}/profiles/me/skills",
        headers=headers,
        json={"position_id": 1},
    )

    assert response.status_code == 403
    assert response.json() == {
        "detail": "Role 'user' is not authorized. Required: ['admin', 'moderator']"
    }


def test_patch_my_profile_updates_jira_and_github_accounts(
    client: TestClient,
) -> None:
    user, headers = _create_user_and_headers_with_mocks(client)
    jira_old = f"jira-{random_lower_string()}"
    jira_new = f"jira-{random_lower_string()}"
    github_old = f"gh-{random_lower_string()}"
    github_new = f"gh-{random_lower_string()}"
    github_id_old = uuid4().int % 2_000_000_000
    github_id_new = uuid4().int % 2_000_000_000

    jira_connect = client.post(
        f"{settings.API_V1_STR}/profiles/me/connect/jira",
        headers=headers,
        json={
            "jira_account_id": jira_old,
            "jira_display_name": "Old Jira Name",
            "jira_email": "old-jira@example.com",
            "jira_avatar_url": "https://example.com/old-jira.png",
        },
    )
    assert jira_connect.status_code == 200

    github_connect = client.post(
        f"{settings.API_V1_STR}/profiles/me/connect/github",
        headers=headers,
        json={
            "github_id": github_id_old,
            "github_login": github_old,
            "github_display_name": "Old GitHub Name",
            "github_email": "old-github@example.com",
            "github_avatar_url": "https://example.com/old-github.png",
        },
    )
    assert github_connect.status_code == 200

    response = client.patch(
        f"{settings.API_V1_STR}/profiles/me",
        headers=headers,
        json={
            "jira_account_id": jira_new,
            "jira_display_name": "New Jira Name",
            "jira_email": "new-jira@example.com",
            "jira_avatar_url": "https://example.com/new-jira.png",
            "github_id": github_id_new,
            "github_login": github_new,
            "github_display_name": "New GitHub Name",
            "github_email": "new-github@example.com",
            "github_avatar_url": "https://example.com/new-github.png",
        },
    )

    assert response.status_code == 200
    content = response.json()
    assert content["jira_account_id"] == jira_new
    assert content["jira_display_name"] == "New Jira Name"
    assert content["github_id"] == github_id_new
    assert content["github_login"] == github_new


def test_patch_profile_by_user_id_allows_admin_to_update_target_user(
    client: TestClient,
) -> None:
    target_user, _ = _create_user_and_headers_with_mocks(client)
    admin_user, admin_headers = _create_user_and_headers_with_mocks(
        client, role=Role.ADMIN
    )
    jira_target = f"jira-{random_lower_string()}"
    github_target = f"gh-{random_lower_string()}"
    position_id = 999

    response = client.patch(
        f"{settings.API_V1_STR}/profiles/{target_user.id}",
        headers=admin_headers,
        json={
            "burnout_level": 4.0,
            "position_id": position_id,
            "jira_account_id": jira_target,
            "jira_display_name": "Target Jira",
            "github_login": github_target,
            "github_id": uuid4().int % 2_000_000_000,
        },
    )

    assert response.status_code == 200
    content = response.json()
    assert content["user_id"] == str(target_user.id)
    assert content["burnout_level"] == 4.0
    assert content["position_id"] == position_id
    assert content["jira_account_id"] == jira_target
    assert content["github_login"] == github_target


def test_patch_profile_by_user_id_rejects_normal_user(
    client: TestClient,
) -> None:
    target_user, _ = _create_user_and_headers_with_mocks(client)
    user, user_headers = _create_user_and_headers_with_mocks(client, role=Role.USER)

    response = client.patch(
        f"{settings.API_V1_STR}/profiles/{target_user.id}",
        headers=user_headers,
        json={"burnout_level": 1.0},
    )

    assert response.status_code == 403
    assert response.json() == {
        "detail": "Role 'user' is not authorized. Required: ['admin', 'moderator']"
    }
