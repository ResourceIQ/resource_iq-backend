"""Unit tests for user_service module functions.

Tests cover user CRUD operations and authentication logic.
Database and password hashing are fully mocked.
"""

from unittest.mock import MagicMock, patch

import pytest

from app.api.user import user_service


# ===================================================================
# 1. create_user
# ===================================================================

class TestCreateUser:
    @patch("app.api.user.user_service.get_password_hash")
    def test_creates_user_and_commits(self, mock_hash: MagicMock) -> None:
        mock_hash.return_value = "hashed_pw_123"

        session = MagicMock()
        user_create = MagicMock()
        user_create.password = "secure_password"

        mock_user = MagicMock()
        with patch("app.api.user.user_service.User") as mock_user_cls:
            mock_user_cls.model_validate.return_value = mock_user

            result = user_service.create_user(session=session, user_create=user_create)

        mock_hash.assert_called_once_with("secure_password")
        mock_user_cls.model_validate.assert_called_once_with(
            user_create, update={"hashed_password": "hashed_pw_123"}
        )
        session.add.assert_called_once_with(mock_user)
        session.commit.assert_called_once()
        session.refresh.assert_called_once_with(mock_user)
        assert result is mock_user


# ===================================================================
# 2. update_user
# ===================================================================

class TestUpdateUser:
    @patch("app.api.user.user_service.get_password_hash")
    def test_updates_user_with_password(self, mock_hash: MagicMock) -> None:
        mock_hash.return_value = "new_hashed_pw"

        session = MagicMock()
        db_user = MagicMock()
        user_in = MagicMock()
        user_in.model_dump.return_value = {
            "full_name": "Updated Name",
            "password": "new_password",
        }

        result = user_service.update_user(session=session, db_user=db_user, user_in=user_in)

        mock_hash.assert_called_once_with("new_password")
        db_user.sqlmodel_update.assert_called_once()
        call_args = db_user.sqlmodel_update.call_args
        assert call_args[1]["update"] == {"hashed_password": "new_hashed_pw"}
        session.commit.assert_called_once()

    def test_updates_user_without_password(self) -> None:
        session = MagicMock()
        db_user = MagicMock()
        user_in = MagicMock()
        user_in.model_dump.return_value = {"full_name": "Updated Name"}

        user_service.update_user(session=session, db_user=db_user, user_in=user_in)

        db_user.sqlmodel_update.assert_called_once()
        call_args = db_user.sqlmodel_update.call_args
        assert call_args[1]["update"] == {}


# ===================================================================
# 3. get_user_by_email
# ===================================================================

class TestGetUserByEmail:
    def test_returns_user_when_found(self) -> None:
        session = MagicMock()
        mock_user = MagicMock()
        session.exec.return_value.first.return_value = mock_user

        result = user_service.get_user_by_email(session=session, email="alice@test.com")

        assert result is mock_user

    def test_returns_none_when_not_found(self) -> None:
        session = MagicMock()
        session.exec.return_value.first.return_value = None

        result = user_service.get_user_by_email(session=session, email="nobody@test.com")

        assert result is None


# ===================================================================
# 4. authenticate
# ===================================================================

class TestAuthenticate:
    @patch("app.api.user.user_service.verify_password")
    @patch("app.api.user.user_service.get_user_by_email")
    def test_returns_user_on_valid_credentials(
        self, mock_get: MagicMock, mock_verify: MagicMock
    ) -> None:
        mock_user = MagicMock()
        mock_user.hashed_password = "hashed_pw"
        mock_get.return_value = mock_user
        mock_verify.return_value = True

        session = MagicMock()
        result = user_service.authenticate(
            session=session, email="alice@test.com", password="correct"
        )

        assert result is mock_user
        mock_verify.assert_called_once_with("correct", "hashed_pw")

    @patch("app.api.user.user_service.get_user_by_email")
    def test_returns_none_when_user_not_found(self, mock_get: MagicMock) -> None:
        mock_get.return_value = None

        session = MagicMock()
        result = user_service.authenticate(
            session=session, email="nobody@test.com", password="pass"
        )

        assert result is None

    @patch("app.api.user.user_service.verify_password")
    @patch("app.api.user.user_service.get_user_by_email")
    def test_returns_none_on_wrong_password(
        self, mock_get: MagicMock, mock_verify: MagicMock
    ) -> None:
        mock_user = MagicMock()
        mock_user.hashed_password = "hashed_pw"
        mock_get.return_value = mock_user
        mock_verify.return_value = False

        session = MagicMock()
        result = user_service.authenticate(
            session=session, email="alice@test.com", password="wrong"
        )

        assert result is None
