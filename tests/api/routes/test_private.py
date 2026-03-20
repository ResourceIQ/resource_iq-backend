from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.api.user.user_model import User
from app.core.config import settings


from tests.utils.utils import random_email


def test_create_user(
    client: TestClient, db: Session, superuser_token_headers: dict[str, str]
) -> None:
    email = random_email()
    r = client.post(
        f"{settings.API_V1_STR}/users/",
        headers=superuser_token_headers,
        json={
            "email": email,
            "password": "password123",
            "full_name": "Pollo Listo",
        },
    )

    assert r.status_code == 200

    data = r.json()

    user = db.exec(select(User).where(User.id == data["id"])).first()

    assert user
    assert user.email == email
    assert user.full_name == "Pollo Listo"
