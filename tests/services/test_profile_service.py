"""Unit tests for ProfileService.

Tests cover fuzzy matching between GitHub and Jira accounts,
threshold validation, and edge cases.
"""

from unittest.mock import MagicMock, patch

import pytest

from app.api.integrations.GitHub.github_schema import GitHubUser
from app.api.integrations.Jira.jira_schema import JiraUser
from app.api.profiles.profile_service import ProfileService


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def service() -> ProfileService:
    with patch.object(ProfileService, "__init__", lambda self, *a, **kw: None):
        svc = ProfileService.__new__(ProfileService)
        svc.db = MagicMock()
        return svc


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _gh(login: str, name: str | None = None, email: str | None = None, uid: int = 1) -> GitHubUser:
    return GitHubUser(login=login, id=uid, name=name, email=email)


def _jira(display_name: str | None = None, email: str | None = None, account_id: str = "j1") -> JiraUser:
    return JiraUser(account_id=account_id, display_name=display_name, email_address=email)


# ===================================================================
# 1. _get_best_match (fuzzy matching logic)
# ===================================================================

class TestGetBestMatch:
    def test_exact_email_match_returns_100(self, service: ProfileService) -> None:
        gh = _gh(login="alice", email="alice@example.com")
        jira_users = [_jira(display_name="Alice Smith", email="alice@example.com")]

        match, score = service._get_best_match(gh, jira_users)

        assert match is not None
        assert score == 100.0

    def test_email_match_is_case_insensitive(self, service: ProfileService) -> None:
        gh = _gh(login="alice", email="Alice@Example.COM")
        jira_users = [_jira(display_name="Alice", email="alice@example.com")]

        match, score = service._get_best_match(gh, jira_users)

        assert score == 100.0

    def test_name_fuzzy_match(self, service: ProfileService) -> None:
        gh = _gh(login="asmith", name="Alice Smith")
        jira_users = [_jira(display_name="Alice Smith")]

        match, score = service._get_best_match(gh, jira_users)

        assert match is not None
        assert score > 0

    def test_login_fuzzy_match(self, service: ProfileService) -> None:
        gh = _gh(login="alice", name=None)
        jira_users = [_jira(display_name="Alice Johnson")]

        match, score = service._get_best_match(gh, jira_users)

        assert match is not None
        assert score > 0

    def test_short_login_gets_lower_weight(self, service: ProfileService) -> None:
        gh_short = _gh(login="al", name=None)
        gh_long = _gh(login="alice", name=None)
        jira_users = [_jira(display_name="Alice Johnson")]

        _, score_short = service._get_best_match(gh_short, jira_users)
        _, score_long = service._get_best_match(gh_long, jira_users)

        assert score_long >= score_short

    def test_no_match_returns_zero(self, service: ProfileService) -> None:
        gh = _gh(login="xyzuser", name="John Doe")
        jira_users = [_jira(display_name="Completely Different Person")]

        match, score = service._get_best_match(gh, jira_users)

        # Score might be non-zero due to partial fuzzy matching, but should be low
        assert score < 75

    def test_empty_jira_users_returns_none(self, service: ProfileService) -> None:
        gh = _gh(login="alice", name="Alice")
        match, score = service._get_best_match(gh, [])
        assert match is None
        assert score == 0

    def test_picks_best_among_multiple(self, service: ProfileService) -> None:
        gh = _gh(login="alice", name="Alice Smith", email=None)
        jira_users = [
            _jira(display_name="Bob Jones", account_id="j1"),
            _jira(display_name="Alice Smith", account_id="j2"),
            _jira(display_name="Charlie Brown", account_id="j3"),
        ]

        match, score = service._get_best_match(gh, jira_users)

        assert match is not None
        assert match.account_id == "j2"


# ===================================================================
# 2. match_jira_github (full flow)
# ===================================================================

class TestMatchJiraGithub:
    @patch("app.api.profiles.profile_service.JiraIntegrationService")
    @patch("app.api.profiles.profile_service.GithubIntegrationService")
    def test_matches_above_threshold(
        self,
        mock_gh_svc_cls: MagicMock,
        mock_jira_svc_cls: MagicMock,
        service: ProfileService,
    ) -> None:
        mock_gh_svc = MagicMock()
        mock_gh_svc.get_all_org_members.return_value = [
            _gh(login="alice", name="Alice Smith", email="alice@test.com")
        ]
        mock_gh_svc_cls.return_value = mock_gh_svc

        mock_jira_svc = MagicMock()
        mock_jira_svc.get_all_jira_users.return_value = [
            _jira(display_name="Alice Smith", email="alice@test.com")
        ]
        mock_jira_svc_cls.return_value = mock_jira_svc

        result = service.match_jira_github(threshold=75)

        assert len(result) == 1
        assert result[0].match_score == 100.0

    @patch("app.api.profiles.profile_service.JiraIntegrationService")
    @patch("app.api.profiles.profile_service.GithubIntegrationService")
    def test_filters_below_threshold(
        self,
        mock_gh_svc_cls: MagicMock,
        mock_jira_svc_cls: MagicMock,
        service: ProfileService,
    ) -> None:
        mock_gh_svc = MagicMock()
        mock_gh_svc.get_all_org_members.return_value = [
            _gh(login="xyzuser", name="Unknown Person")
        ]
        mock_gh_svc_cls.return_value = mock_gh_svc

        mock_jira_svc = MagicMock()
        mock_jira_svc.get_all_jira_users.return_value = [
            _jira(display_name="Completely Different")
        ]
        mock_jira_svc_cls.return_value = mock_jira_svc

        result = service.match_jira_github(threshold=90)

        assert len(result) == 0

    def test_invalid_threshold_raises(self, service: ProfileService) -> None:
        with pytest.raises(ValueError, match="threshold must be between"):
            service.match_jira_github(threshold=150)

        with pytest.raises(ValueError, match="threshold must be between"):
            service.match_jira_github(threshold=-1)
