from fastapi.testclient import TestClient
from sqlmodel import Session

from app.core.config import settings
from tests.utils.utils import random_lower_string


def test_create_team(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    name = random_lower_string()
    description = random_lower_string()
    data = {"name": name, "description": description}
    response = client.post(
        f"{settings.API_V1_STR}/teams/",
        headers=superuser_token_headers,
        json=data,
    )
    assert response.status_code == 200
    content = response.json()
    assert content["name"] == name
    assert content["description"] == description
    assert "id" in content


def test_list_teams(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    response = client.get(
        f"{settings.API_V1_STR}/teams/",
        headers=superuser_token_headers,
    )
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_get_team(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    name = random_lower_string()
    data = {"name": name}
    response = client.post(
        f"{settings.API_V1_STR}/teams/",
        headers=superuser_token_headers,
        json=data,
    )
    team_id = response.json()["id"]

    response = client.get(
        f"{settings.API_V1_STR}/teams/{team_id}",
        headers=superuser_token_headers,
    )
    assert response.status_code == 200
    assert response.json()["name"] == name


def test_update_team(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    name = random_lower_string()
    data = {"name": name}
    response = client.post(
        f"{settings.API_V1_STR}/teams/",
        headers=superuser_token_headers,
        json=data,
    )
    team_id = response.json()["id"]

    new_name = random_lower_string()
    response = client.patch(
        f"{settings.API_V1_STR}/teams/{team_id}",
        headers=superuser_token_headers,
        json={"name": new_name},
    )
    assert response.status_code == 200
    assert response.json()["name"] == new_name


def test_delete_team(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    name = random_lower_string()
    data = {"name": name}
    response = client.post(
        f"{settings.API_V1_STR}/teams/",
        headers=superuser_token_headers,
        json=data,
    )
    team_id = response.json()["id"]

    response = client.delete(
        f"{settings.API_V1_STR}/teams/{team_id}",
        headers=superuser_token_headers,
    )
    assert response.status_code == 200
    assert response.json()["message"] == "Team deleted successfully"

    response = client.get(
        f"{settings.API_V1_STR}/teams/{team_id}",
        headers=superuser_token_headers,
    )
    assert response.status_code == 404
