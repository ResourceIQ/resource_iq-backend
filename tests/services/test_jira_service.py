"""Unit tests for JiraIntegrationService.

All external I/O (database, HTTP, Jira SDK) is mocked so these tests
run without any network or database access.
"""

import time
from datetime import datetime
from typing import Any
from unittest.mock import MagicMock, PropertyMock, patch

import pytest

from app.api.integrations.Jira.jira_schema import (
    JiraAssignIssueRequest,
    JiraComment,
    JiraCreateIssueRequest,
    JiraIssueContent,
    JiraUser,
)
from app.api.integrations.Jira.jira_service import JiraIntegrationService

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_db() -> MagicMock:
    """Provide a mock SQLAlchemy Session."""
    db = MagicMock()
    db.query.return_value.first.return_value = None
    return db


@pytest.fixture()
def service(mock_db: MagicMock) -> JiraIntegrationService:
    """Build service with mocked DB and Jina disabled."""
    with patch.object(JiraIntegrationService, "__init__", lambda self, *a, **kw: None):
        svc = JiraIntegrationService.__new__(JiraIntegrationService)
        svc.db = mock_db
        svc.use_jina_api = False
        svc._vector_service = None
        svc._client = None
        svc.integration = None
        return svc


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_issue_content(**overrides: Any) -> JiraIssueContent:
    defaults: dict[str, Any] = {
        "issue_id": "10001",
        "issue_key": "PROJ-1",
        "project_key": "PROJ",
        "summary": "Fix login bug",
        "description": "Users cannot login",
        "issue_type": "Bug",
        "status": "Done",
        "priority": "High",
        "labels": ["backend", "auth"],
        "assignee": JiraUser(account_id="user-1", display_name="Alice"),
        "reporter": JiraUser(account_id="user-2", display_name="Bob"),
        "issue_url": "https://jira.example.com/browse/PROJ-1",
        "comments": [],
        "created_at": datetime(2025, 1, 1),
        "updated_at": datetime(2025, 1, 2),
    }
    defaults.update(overrides)
    return JiraIssueContent(**defaults)


def _make_mock_jira_issue(
    key: str = "PROJ-1",
    issue_id: str = "10001",
    summary: str = "Fix login bug",
    description: str | None = "Users cannot login",
    issue_type: str = "Bug",
    status: str = "Done",
    priority: str = "High",
    labels: list[str] | None = None,
    assignee: dict[str, Any] | None = None,
    reporter: dict[str, Any] | None = None,
) -> MagicMock:
    """Build a mock Jira SDK Issue object."""
    issue = MagicMock()
    issue.id = issue_id
    issue.key = key

    fields = MagicMock()
    fields.summary = summary
    fields.description = description
    fields.labels = labels or []

    issuetype = MagicMock()
    issuetype.name = issue_type
    fields.issuetype = issuetype

    status_obj = MagicMock()
    status_obj.name = status
    fields.status = status_obj

    priority_obj = MagicMock()
    priority_obj.name = priority
    fields.priority = priority_obj

    if assignee:
        assignee_obj = MagicMock()
        assignee_obj.accountId = assignee.get("accountId", "")
        assignee_obj.displayName = assignee.get("displayName")
        assignee_obj.emailAddress = assignee.get("emailAddress")
        assignee_obj.avatarUrls = None
        assignee_obj.active = True
        fields.assignee = assignee_obj
    else:
        fields.assignee = None

    if reporter:
        reporter_obj = MagicMock()
        reporter_obj.accountId = reporter.get("accountId", "")
        reporter_obj.displayName = reporter.get("displayName")
        reporter_obj.emailAddress = reporter.get("emailAddress")
        reporter_obj.avatarUrls = None
        reporter_obj.active = True
        fields.reporter = reporter_obj
    else:
        fields.reporter = None

    fields.created = "2025-01-01T00:00:00Z"
    fields.updated = "2025-01-02T00:00:00Z"
    fields.resolutiondate = None

    comment_container = MagicMock()
    comment_container.comments = []
    fields.comment = comment_container

    issue.fields = fields
    return issue


# ===================================================================
# 1. Static / pure methods
# ===================================================================


class TestDetectTerminalStatuses:
    def test_finds_standard_terminal_statuses(self) -> None:
        statuses = ["Open", "In Progress", "Done", "Closed"]
        result = JiraIntegrationService._detect_terminal_statuses(statuses)
        assert "Done" in result
        assert "Closed" in result

    def test_returns_last_status_when_no_terminals(self) -> None:
        statuses = ["Backlog", "In Progress", "Review"]
        result = JiraIntegrationService._detect_terminal_statuses(statuses)
        assert result == ["Review"]

    def test_empty_list_returns_empty(self) -> None:
        assert JiraIntegrationService._detect_terminal_statuses([]) == []

    def test_all_terminal_statuses(self) -> None:
        statuses = ["Done", "Closed", "Resolved", "Complete", "Completed"]
        result = JiraIntegrationService._detect_terminal_statuses(statuses)
        assert set(result) == {"Done", "Closed", "Resolved", "Complete", "Completed"}


class TestMatchesSelectedStatus:
    def test_matches_when_status_in_selected(self) -> None:
        issue = _make_issue_content(issue_type="Bug", status="Done")
        status_map = {"Bug": {"Done", "Closed"}}
        assert JiraIntegrationService._matches_selected_status(issue, status_map)

    def test_no_match_when_status_not_selected(self) -> None:
        issue = _make_issue_content(issue_type="Bug", status="In Progress")
        status_map = {"Bug": {"Done", "Closed"}}
        assert not JiraIntegrationService._matches_selected_status(issue, status_map)

    def test_fallback_to_defaults_when_type_missing(self) -> None:
        issue = _make_issue_content(issue_type="Story", status="Done")
        status_map = {"Bug": {"Done"}}
        assert JiraIntegrationService._matches_selected_status(issue, status_map)

    def test_fallback_rejects_non_terminal(self) -> None:
        issue = _make_issue_content(issue_type="Story", status="In Progress")
        status_map = {"Bug": {"Done"}}
        assert not JiraIntegrationService._matches_selected_status(issue, status_map)


# ===================================================================
# 2. Context generation
# ===================================================================


class TestGenerateIssueContext:
    def test_basic_context(self, service: JiraIntegrationService) -> None:
        issue = _make_issue_content()
        ctx = service._generate_issue_context(issue)

        assert "ISSUE_TYPE: Bug" in ctx
        assert "SUMMARY: Fix login bug" in ctx
        assert "STATUS: Done" in ctx
        assert "PRIORITY: High" in ctx
        assert "LABELS: backend, auth" in ctx
        assert "DESCRIPTION: Users cannot login" in ctx

    def test_context_without_optional_fields(
        self, service: JiraIntegrationService
    ) -> None:
        issue = _make_issue_content(
            priority=None, labels=[], description=None, comments=[]
        )
        ctx = service._generate_issue_context(issue)

        assert "PRIORITY" not in ctx
        assert "LABELS" not in ctx
        assert "DESCRIPTION" not in ctx
        assert "KEY_COMMENTS" not in ctx

    def test_context_with_comments(self, service: JiraIntegrationService) -> None:
        comments = [
            JiraComment(
                id="c1",
                author=JiraUser(account_id="u1", display_name="Alice"),
                body="This is a comment",
                created=datetime(2025, 1, 1),
            )
        ]
        issue = _make_issue_content(comments=comments)
        ctx = service._generate_issue_context(issue)
        assert "KEY_COMMENTS" in ctx
        assert "This is a comment" in ctx

    def test_description_jira_markup_cleaned(
        self, service: JiraIntegrationService
    ) -> None:
        issue = _make_issue_content(
            description="{code}print('hello'){code} [~user123] some text"
        )
        ctx = service._generate_issue_context(issue)
        assert "{code}" not in ctx
        assert "[~user123]" not in ctx
        assert "some text" in ctx


# ===================================================================
# 3. HMAC state generation / verification
# ===================================================================


class TestStateTokens:
    @patch("app.api.integrations.Jira.jira_service.settings")
    def test_generate_and_verify_state(
        self, mock_settings: MagicMock, service: JiraIntegrationService
    ) -> None:
        mock_settings.SECRET_KEY = "test-secret-key"

        state = service._generate_state(ttl_seconds=300)
        assert state.count(":") == 3

        result = service._verify_state(state)
        assert result is True

    @patch("app.api.integrations.Jira.jira_service.settings")
    def test_expired_state_fails(
        self, mock_settings: MagicMock, service: JiraIntegrationService
    ) -> None:
        mock_settings.SECRET_KEY = "test-secret-key"

        state = service._generate_state(ttl_seconds=60)

        # Fast-forward time by 120s so the token is expired
        with patch(
            "app.api.integrations.Jira.jira_service.time.time",
            return_value=time.time() + 120,
        ):
            assert service._verify_state(state) is False

    @patch("app.api.integrations.Jira.jira_service.settings")
    def test_tampered_state_fails(
        self, mock_settings: MagicMock, service: JiraIntegrationService
    ) -> None:
        mock_settings.SECRET_KEY = "test-secret-key"

        state = service._generate_state()
        tampered = state[:-4] + "XXXX"
        assert service._verify_state(tampered) is False

    def test_malformed_state_fails(self, service: JiraIntegrationService) -> None:
        assert service._verify_state("garbage") is False
        assert service._verify_state("") is False
        assert service._verify_state("a:b") is False


# ===================================================================
# 4. OAuth flow
# ===================================================================


class TestBuildAuthorizationUrl:
    @patch("app.api.integrations.Jira.jira_service.settings")
    def test_builds_url_when_oauth_configured(
        self, mock_settings: MagicMock, service: JiraIntegrationService
    ) -> None:
        mock_settings.jira_oauth_enabled = True
        mock_settings.SECRET_KEY = "test-secret"
        mock_settings.ATLASSIAN_API_AUDIENCE = "api.atlassian.com"
        mock_settings.ATLASSIAN_CLIENT_ID = "client-id-123"
        mock_settings.ATLASSIAN_SCOPES = ["read:jira-work", "write:jira-work"]
        mock_settings.ATLASSIAN_REDIRECT_URI = "https://myapp.com/callback"
        mock_settings.ATLASSIAN_AUTH_URL = "https://auth.atlassian.com/authorize"

        result = service.build_authorization_url()

        assert "client-id-123" in str(result.auth_url)
        assert "auth.atlassian.com" in str(result.auth_url)
        assert result.state is not None

    @patch("app.api.integrations.Jira.jira_service.settings")
    def test_raises_when_oauth_not_configured(
        self, mock_settings: MagicMock, service: JiraIntegrationService
    ) -> None:
        mock_settings.jira_oauth_enabled = False

        with pytest.raises(ValueError, match="Atlassian OAuth is not configured"):
            service.build_authorization_url()


class TestHandleOAuthCallback:
    @patch("app.api.integrations.Jira.jira_service.settings")
    def test_rejects_invalid_state(
        self, mock_settings: MagicMock, service: JiraIntegrationService
    ) -> None:
        mock_settings.SECRET_KEY = "test-secret"

        with pytest.raises(ValueError, match="Invalid or expired state"):
            service.handle_oauth_callback(code="auth-code", state="bad:state:here:sig")

    @patch.object(JiraIntegrationService, "_exchange_code_for_token")
    @patch.object(JiraIntegrationService, "_verify_state", return_value=True)
    def test_successful_callback(
        self,
        _mock_verify: MagicMock,
        mock_exchange: MagicMock,
        service: JiraIntegrationService,
    ) -> None:
        mock_token = MagicMock()
        mock_token.cloud_id = "cloud-123"
        mock_token.jira_site_url = "https://mysite.atlassian.net"
        mock_token.expires_at = datetime(2025, 12, 31)
        mock_token.scope = "read:jira-work"
        mock_exchange.return_value = mock_token

        result = service.handle_oauth_callback(code="valid-code", state="valid-state")

        assert result.status == "connected"
        assert result.cloud_id == "cloud-123"


class TestExchangeCodeForToken:
    @patch("app.api.integrations.Jira.jira_service.settings")
    def test_raises_when_oauth_not_configured(
        self, mock_settings: MagicMock, service: JiraIntegrationService
    ) -> None:
        mock_settings.jira_oauth_enabled = False

        with pytest.raises(ValueError, match="Atlassian OAuth is not configured"):
            service._exchange_code_for_token("code")

    @patch.object(JiraIntegrationService, "_store_token")
    @patch.object(JiraIntegrationService, "_fetch_accessible_resources")
    @patch("app.api.integrations.Jira.jira_service.httpx")
    @patch("app.api.integrations.Jira.jira_service.settings")
    def test_successful_token_exchange(
        self,
        mock_settings: MagicMock,
        mock_httpx: MagicMock,
        mock_fetch_resources: MagicMock,
        mock_store: MagicMock,
        service: JiraIntegrationService,
    ) -> None:
        mock_settings.jira_oauth_enabled = True
        mock_settings.ATLASSIAN_CLIENT_ID = "cid"
        mock_settings.ATLASSIAN_CLIENT_SECRET = "csecret"
        mock_settings.ATLASSIAN_REDIRECT_URI = "https://app.com/cb"
        mock_settings.ATLASSIAN_TOKEN_URL = "https://auth.atlassian.com/oauth/token"

        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {
            "access_token": "at-123",
            "refresh_token": "rt-456",
            "expires_in": 3600,
            "scope": "read:jira-work",
            "token_type": "Bearer",
        }
        mock_httpx.post.return_value = resp

        mock_fetch_resources.return_value = [
            {"id": "cloud-abc", "url": "https://mysite.atlassian.net"}
        ]

        stored_token = MagicMock()
        mock_store.return_value = stored_token

        result = service._exchange_code_for_token("auth-code")

        mock_httpx.post.assert_called_once()
        mock_fetch_resources.assert_called_once_with("at-123")
        mock_store.assert_called_once()
        assert result == stored_token

    @patch("app.api.integrations.Jira.jira_service.httpx")
    @patch("app.api.integrations.Jira.jira_service.settings")
    def test_token_exchange_failure(
        self,
        mock_settings: MagicMock,
        mock_httpx: MagicMock,
        service: JiraIntegrationService,
    ) -> None:
        mock_settings.jira_oauth_enabled = True
        mock_settings.ATLASSIAN_CLIENT_ID = "cid"
        mock_settings.ATLASSIAN_CLIENT_SECRET = "csecret"
        mock_settings.ATLASSIAN_REDIRECT_URI = "https://app.com/cb"
        mock_settings.ATLASSIAN_TOKEN_URL = "https://auth.atlassian.com/oauth/token"

        resp = MagicMock()
        resp.status_code = 400
        resp.text = "invalid_grant"
        mock_httpx.post.return_value = resp

        with pytest.raises(ValueError, match="Token exchange failed"):
            service._exchange_code_for_token("bad-code")


# ===================================================================
# 5. Jira client initialization
# ===================================================================


class TestGetJiraClient:
    def test_returns_cached_client(self, service: JiraIntegrationService) -> None:
        mock_client = MagicMock()
        service._client = mock_client
        assert service.get_jira_client() is mock_client

    @patch("app.api.integrations.Jira.jira_service.JIRA")
    @patch("app.api.integrations.Jira.jira_service.settings")
    def test_basic_auth_fallback(
        self,
        mock_settings: MagicMock,
        mock_jira_cls: MagicMock,
        service: JiraIntegrationService,
    ) -> None:
        mock_settings.jira_oauth_enabled = False
        service.integration = MagicMock()
        service.integration.jira_url = "https://jira.example.com"
        service.integration.jira_email = "test@example.com"
        mock_settings.JIRA_API_TOKEN = "token-123"

        mock_client = MagicMock()
        mock_jira_cls.return_value = mock_client

        result = service.get_jira_client()

        mock_jira_cls.assert_called_once_with(
            server="https://jira.example.com",
            basic_auth=("test@example.com", "token-123"),
        )
        assert result is mock_client

    @patch("app.api.integrations.Jira.jira_service.settings")
    def test_raises_when_no_credentials(
        self, mock_settings: MagicMock, service: JiraIntegrationService
    ) -> None:
        mock_settings.jira_oauth_enabled = False
        service.integration = None
        mock_settings.JIRA_URL = None
        mock_settings.JIRA_EMAIL = None
        mock_settings.JIRA_API_TOKEN = None

        with pytest.raises(ValueError, match="Jira credentials not configured"):
            service.get_jira_client()

    @patch("app.api.integrations.Jira.jira_service.JIRA")
    @patch.object(JiraIntegrationService, "_get_active_token")
    @patch("app.api.integrations.Jira.jira_service.settings")
    def test_oauth_client_initialization(
        self,
        mock_settings: MagicMock,
        mock_get_token: MagicMock,
        mock_jira_cls: MagicMock,
        service: JiraIntegrationService,
    ) -> None:
        mock_settings.jira_oauth_enabled = True

        mock_token = MagicMock()
        mock_token.access_token = "oauth-token"
        mock_token.cloud_id = "cloud-abc"
        mock_token.jira_site_url = "https://mysite.atlassian.net"
        mock_token.id = 1
        mock_get_token.return_value = mock_token

        mock_client = MagicMock()
        mock_client._session.headers = {}
        mock_jira_cls.return_value = mock_client

        result = service.get_jira_client()

        assert result is mock_client
        assert mock_client._session.headers["Authorization"] == "Bearer oauth-token"


# ===================================================================
# 6. Issue parsing
# ===================================================================


class TestParseJiraUser:
    def test_parse_valid_user(self, service: JiraIntegrationService) -> None:
        user_data = MagicMock()
        user_data.accountId = "acc-123"
        user_data.displayName = "Alice"
        user_data.emailAddress = "alice@example.com"
        user_data.avatarUrls = None
        user_data.active = True

        result = service._parse_jira_user(user_data)

        assert result is not None
        assert result.account_id == "acc-123"
        assert result.display_name == "Alice"
        assert result.email_address == "alice@example.com"

    def test_parse_none_returns_none(self, service: JiraIntegrationService) -> None:
        assert service._parse_jira_user(None) is None


class TestParseIssue:
    @patch.object(
        JiraIntegrationService,
        "jira_url",
        new_callable=PropertyMock,
        return_value="https://jira.example.com",
    )
    def test_parse_basic_issue(
        self, _mock_url: MagicMock, service: JiraIntegrationService
    ) -> None:
        mock_issue = _make_mock_jira_issue(
            key="TEST-42",
            summary="Test issue",
            description="Test description",
            assignee={"accountId": "user-1", "displayName": "Alice"},
        )

        result = service._parse_issue(mock_issue)

        assert result.issue_key == "TEST-42"
        assert result.summary == "Test issue"
        assert result.description == "Test description"
        assert result.issue_type == "Bug"
        assert result.status == "Done"
        assert result.assignee is not None
        assert result.assignee.account_id == "user-1"
        assert result.context is not None

    @patch.object(
        JiraIntegrationService,
        "jira_url",
        new_callable=PropertyMock,
        return_value="https://jira.example.com",
    )
    def test_parse_issue_without_assignee(
        self, _mock_url: MagicMock, service: JiraIntegrationService
    ) -> None:
        mock_issue = _make_mock_jira_issue(assignee=None)
        result = service._parse_issue(mock_issue)
        assert result.assignee is None

    @patch.object(
        JiraIntegrationService,
        "jira_url",
        new_callable=PropertyMock,
        return_value="https://jira.example.com",
    )
    def test_parse_issue_extracts_project_key(
        self, _mock_url: MagicMock, service: JiraIntegrationService
    ) -> None:
        mock_issue = _make_mock_jira_issue(key="MYPROJ-99")
        result = service._parse_issue(mock_issue)
        assert result.project_key == "MYPROJ"


# ===================================================================
# 7. API methods (mocked HTTP)
# ===================================================================


class TestGetAllProjects:
    @patch("app.api.integrations.Jira.jira_service.httpx")
    @patch.object(JiraIntegrationService, "get_jira_client")
    def test_returns_project_list(
        self,
        mock_get_client: MagicMock,
        mock_httpx: MagicMock,
        service: JiraIntegrationService,
    ) -> None:
        mock_client = MagicMock()
        mock_client._session.headers = {"Authorization": "Bearer token"}
        mock_client._options = {"server": "https://api.atlassian.com/ex/jira/cloud-123"}
        mock_get_client.return_value = mock_client

        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = [
            {"key": "PROJ", "name": "Project One", "id": "10001"},
            {"key": "TEST", "name": "Test Project", "id": "10002"},
        ]
        mock_httpx.get.return_value = resp

        result = service.get_all_projects()

        assert len(result) == 2
        assert result[0]["key"] == "PROJ"
        assert result[1]["name"] == "Test Project"

    @patch("app.api.integrations.Jira.jira_service.httpx.get")
    @patch.object(JiraIntegrationService, "get_jira_client")
    def test_raises_on_401(
        self,
        mock_get_client: MagicMock,
        mock_httpx_get: MagicMock,
        service: JiraIntegrationService,
    ) -> None:
        mock_client = MagicMock()
        mock_client._session.headers = {"Authorization": "Bearer bad-token"}
        mock_client._options = {"server": "https://api.atlassian.com/ex/jira/cloud-123"}
        mock_get_client.return_value = mock_client

        resp = MagicMock()
        resp.status_code = 401
        mock_httpx_get.return_value = resp

        with pytest.raises(ValueError, match="OAuth token is invalid"):
            service.get_all_projects()

    @patch.object(JiraIntegrationService, "get_jira_client")
    def test_raises_when_no_auth_header(
        self, mock_get_client: MagicMock, service: JiraIntegrationService
    ) -> None:
        mock_client = MagicMock()
        headers_mock = MagicMock()
        headers_mock.get.return_value = None
        mock_client._session.headers = headers_mock
        mock_get_client.return_value = mock_client

        with pytest.raises(ValueError, match="No Authorization header"):
            service.get_all_projects()


class TestGetAllJiraUsers:
    @patch("app.api.integrations.Jira.jira_service.httpx")
    @patch.object(JiraIntegrationService, "get_jira_client")
    def test_filters_to_atlassian_users(
        self,
        mock_get_client: MagicMock,
        mock_httpx: MagicMock,
        service: JiraIntegrationService,
    ) -> None:
        mock_client = MagicMock()
        mock_client._session.headers = {"Authorization": "Bearer token"}
        mock_client._options = {"server": "https://api.atlassian.com/ex/jira/cloud-123"}
        mock_get_client.return_value = mock_client

        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = [
            {
                "accountId": "u1",
                "displayName": "Alice",
                "emailAddress": "alice@test.com",
                "accountType": "atlassian",
                "active": True,
                "avatarUrls": {"48x48": "https://avatar.com/alice.png"},
            },
            {
                "accountId": "bot-1",
                "displayName": "Automation Bot",
                "accountType": "app",
                "active": True,
            },
        ]
        mock_httpx.get.return_value = resp

        result = service.get_all_jira_users()

        assert len(result) == 1
        assert result[0].account_id == "u1"
        assert result[0].display_name == "Alice"


class TestFetchIssueTypes:
    @patch("app.api.integrations.Jira.jira_service.httpx")
    @patch.object(JiraIntegrationService, "get_jira_client")
    def test_excludes_subtasks(
        self,
        mock_get_client: MagicMock,
        mock_httpx: MagicMock,
        service: JiraIntegrationService,
    ) -> None:
        mock_client = MagicMock()
        mock_client._session.headers = {"Authorization": "Bearer token"}
        mock_client._options = {"server": "https://api.atlassian.com/ex/jira/cloud-123"}
        mock_get_client.return_value = mock_client

        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = [
            {"id": "1", "name": "Bug", "description": "A bug", "subtask": False},
            {"id": "2", "name": "Sub-task", "description": "Subtask", "subtask": True},
            {"id": "3", "name": "Story", "description": "A story", "subtask": False},
        ]
        mock_httpx.get.return_value = resp

        result = service.fetch_issue_types()

        assert len(result) == 2
        names = [it["name"] for it in result]
        assert "Bug" in names
        assert "Story" in names
        assert "Sub-task" not in names


class TestFetchStatusesForProject:
    @patch("app.api.integrations.Jira.jira_service.httpx")
    @patch.object(JiraIntegrationService, "get_jira_client")
    def test_returns_statuses_grouped_by_type(
        self,
        mock_get_client: MagicMock,
        mock_httpx: MagicMock,
        service: JiraIntegrationService,
    ) -> None:
        mock_client = MagicMock()
        mock_client._session.headers = {"Authorization": "Bearer token"}
        mock_client._options = {"server": "https://api.atlassian.com/ex/jira/cloud-123"}
        mock_get_client.return_value = mock_client

        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = [
            {
                "name": "Bug",
                "statuses": [
                    {"name": "Open"},
                    {"name": "In Progress"},
                    {"name": "Done"},
                ],
            },
            {
                "name": "Story",
                "statuses": [
                    {"name": "To Do"},
                    {"name": "Done"},
                ],
            },
        ]
        mock_httpx.get.return_value = resp

        result = service.fetch_statuses_for_project("PROJ")

        assert "Bug" in result
        assert "Done" in result["Bug"]
        assert len(result["Story"]) == 2


class TestFetchIssues:
    @patch.object(JiraIntegrationService, "get_jira_client")
    def test_builds_jql_from_params(
        self, mock_get_client: MagicMock, service: JiraIntegrationService
    ) -> None:
        mock_client = MagicMock()
        mock_client.search_issues.return_value = []
        mock_get_client.return_value = mock_client

        service.fetch_issues(project_key="PROJ", include_closed=False)

        call_args = mock_client.search_issues.call_args
        jql = call_args[0][0]
        assert 'project = "PROJ"' in jql
        assert "Done" in jql

    @patch.object(JiraIntegrationService, "get_jira_client")
    def test_custom_jql_overrides(
        self, mock_get_client: MagicMock, service: JiraIntegrationService
    ) -> None:
        mock_client = MagicMock()
        mock_client.search_issues.return_value = []
        mock_get_client.return_value = mock_client

        custom_jql = "assignee = currentUser()"
        service.fetch_issues(jql=custom_jql)

        call_args = mock_client.search_issues.call_args
        assert call_args[0][0] == custom_jql


# ===================================================================
# 8. Get single issue
# ===================================================================


class TestGetIssue:
    @patch("app.api.integrations.Jira.jira_service.httpx.get")
    @patch.object(
        JiraIntegrationService,
        "jira_url",
        new_callable=PropertyMock,
        return_value="https://jira.example.com",
    )
    @patch.object(JiraIntegrationService, "get_jira_client")
    def test_returns_issue_detail(
        self,
        mock_get_client: MagicMock,
        _mock_url: MagicMock,
        mock_httpx_get: MagicMock,
        service: JiraIntegrationService,
    ) -> None:
        mock_client = MagicMock()
        mock_client._session.headers = {"Authorization": "Bearer token"}
        mock_client._options = {"server": "https://api.atlassian.com/ex/jira/cloud-123"}
        mock_get_client.return_value = mock_client

        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {
            "key": "PROJ-1",
            "fields": {
                "summary": "Fix login",
                "description": "Plain text description",
                "assignee": {"displayName": "Alice"},
                "status": {"name": "In Progress"},
                "issuetype": {"name": "Bug"},
            },
        }
        mock_httpx_get.return_value = resp

        result = service.get_issue("PROJ-1")

        assert result.issue_key == "PROJ-1"
        assert result.summary == "Fix login"
        assert result.assigned_to == "Alice"
        assert result.status == "In Progress"

    @patch("app.api.integrations.Jira.jira_service.httpx.get")
    @patch.object(JiraIntegrationService, "get_jira_client")
    def test_raises_on_404(
        self,
        mock_get_client: MagicMock,
        mock_httpx_get: MagicMock,
        service: JiraIntegrationService,
    ) -> None:
        mock_client = MagicMock()
        mock_client._session.headers = {"Authorization": "Bearer token"}
        mock_client._options = {"server": "https://api.atlassian.com/ex/jira/cloud-123"}
        mock_get_client.return_value = mock_client

        resp = MagicMock()
        resp.status_code = 404
        mock_httpx_get.return_value = resp

        with pytest.raises(ValueError, match="not found"):
            service.get_issue("NONEXIST-999")


# ===================================================================
# 9. Create issue
# ===================================================================


class TestCreateIssue:
    @patch("app.api.integrations.Jira.jira_service.httpx.post")
    @patch.object(
        JiraIntegrationService,
        "jira_url",
        new_callable=PropertyMock,
        return_value="https://jira.example.com",
    )
    @patch.object(JiraIntegrationService, "get_jira_client")
    def test_create_issue_without_assignee(
        self,
        mock_get_client: MagicMock,
        _mock_url: MagicMock,
        mock_httpx_post: MagicMock,
        service: JiraIntegrationService,
    ) -> None:
        mock_client = MagicMock()
        mock_client._session.headers = {"Authorization": "Bearer token"}
        mock_client._options = {"server": "https://api.atlassian.com/ex/jira/cloud-123"}
        mock_get_client.return_value = mock_client

        resp = MagicMock()
        resp.status_code = 201
        resp.json.return_value = {"key": "PROJ-42"}
        mock_httpx_post.return_value = resp

        request = JiraCreateIssueRequest(
            project_key="PROJ",
            summary="New feature",
            description="Build this feature",
            issue_type="Story",
        )

        result = service.create_issue(request)

        assert result.issue_key == "PROJ-42"
        assert result.summary == "New feature"
        assert result.assigned_to is None

    @patch("app.api.integrations.Jira.jira_service.httpx.post")
    @patch.object(
        JiraIntegrationService,
        "jira_url",
        new_callable=PropertyMock,
        return_value="https://jira.example.com",
    )
    @patch.object(JiraIntegrationService, "get_jira_client")
    def test_create_issue_http_failure(
        self,
        mock_get_client: MagicMock,
        _mock_url: MagicMock,
        mock_httpx_post: MagicMock,
        service: JiraIntegrationService,
    ) -> None:
        mock_client = MagicMock()
        mock_client._session.headers = {"Authorization": "Bearer token"}
        mock_client._options = {"server": "https://api.atlassian.com/ex/jira/cloud-123"}
        mock_get_client.return_value = mock_client

        resp = MagicMock()
        resp.status_code = 400
        resp.text = "Bad request"
        mock_httpx_post.return_value = resp

        request = JiraCreateIssueRequest(project_key="PROJ", summary="Bad issue")

        with pytest.raises(ValueError, match="Failed to create issue"):
            service.create_issue(request)


# ===================================================================
# 10. Assign issue
# ===================================================================


class TestAssignIssue:
    @patch("app.api.integrations.Jira.jira_service.httpx")
    @patch.object(JiraIntegrationService, "get_jira_client")
    def test_assign_issue_success(
        self,
        mock_get_client: MagicMock,
        mock_httpx: MagicMock,
        service: JiraIntegrationService,
        mock_db: MagicMock,
    ) -> None:
        mock_client = MagicMock()
        mock_client._session.headers = {"Authorization": "Bearer token"}
        mock_client._options = {"server": "https://api.atlassian.com/ex/jira/cloud-123"}
        mock_get_client.return_value = mock_client

        mock_profile = MagicMock()
        mock_profile.jira_account_id = "jira-acc-123"
        mock_profile.jira_display_name = "Alice"
        mock_db.query.return_value.filter.return_value.first.return_value = mock_profile

        resp = MagicMock()
        resp.status_code = 204
        mock_httpx.put.return_value = resp

        request = JiraAssignIssueRequest(assignee_user_id="user-uuid-1")
        result = service.assign_issue("PROJ-1", request)

        assert result.issue_key == "PROJ-1"
        assert result.assigned_to == "Alice"

    @patch.object(JiraIntegrationService, "get_jira_client")
    def test_assign_raises_when_no_jira_account(
        self,
        mock_get_client: MagicMock,
        service: JiraIntegrationService,
        mock_db: MagicMock,
    ) -> None:
        mock_client = MagicMock()
        mock_client._session.headers = {"Authorization": "Bearer token"}
        mock_get_client.return_value = mock_client

        mock_db.query.return_value.filter.return_value.first.return_value = None

        request = JiraAssignIssueRequest(assignee_user_id="no-profile-user")
        with pytest.raises(ValueError, match="does not have a connected Jira account"):
            service.assign_issue("PROJ-1", request)


# ===================================================================
# 11. Webhook processing
# ===================================================================


class TestProcessWebhookEvent:
    @patch.object(JiraIntegrationService, "_parse_issue")
    @patch.object(JiraIntegrationService, "get_jira_client")
    @patch.object(JiraIntegrationService, "_build_embedding_status_map")
    def test_issue_deleted_event(
        self,
        mock_status_map: MagicMock,
        mock_get_client: MagicMock,
        mock_parse: MagicMock,
        service: JiraIntegrationService,
        mock_db: MagicMock,
    ) -> None:
        mock_db.query.return_value.filter.return_value.delete.return_value = 1

        payload = {"issue": {"id": "10001", "key": "PROJ-1"}}
        result = service.process_webhook_event("jira:issue_deleted", payload)

        assert result["processed"] is True
        assert result["action"] == "deleted"

    def test_unknown_event_type(self, service: JiraIntegrationService) -> None:
        result = service.process_webhook_event("unknown:event", {})
        assert result["processed"] is False

    @patch.object(JiraIntegrationService, "_update_resource_profiles_from_vectors")
    @patch.object(JiraIntegrationService, "_store_issue_embeddings")
    @patch.object(JiraIntegrationService, "_build_embedding_status_map")
    @patch.object(JiraIntegrationService, "_parse_issue")
    @patch.object(JiraIntegrationService, "get_jira_client")
    def test_issue_created_event_with_matching_status(
        self,
        mock_get_client: MagicMock,
        mock_parse: MagicMock,
        mock_status_map: MagicMock,
        mock_store: MagicMock,
        mock_update_profiles: MagicMock,
        service: JiraIntegrationService,
        mock_db: MagicMock,
    ) -> None:
        mock_client = MagicMock()
        mock_issue = MagicMock()
        mock_issue.key = "PROJ-1"
        mock_client.issue.return_value = mock_issue
        mock_get_client.return_value = mock_client

        issue_content = _make_issue_content(status="Done", context="some context")
        mock_parse.return_value = issue_content
        mock_status_map.return_value = {"Bug": {"Done"}}
        mock_store.return_value = (1, 0)

        payload = {"issue": {"id": "10001", "key": "PROJ-1"}}
        result = service.process_webhook_event("jira:issue_created", payload)

        assert result["processed"] is True
        assert result["action"] == "created"


# ===================================================================
# 12. Sync issues
# ===================================================================


class TestSyncIssues:
    @patch.object(JiraIntegrationService, "_update_resource_profiles_from_vectors")
    @patch.object(JiraIntegrationService, "_store_issue_embeddings")
    @patch.object(JiraIntegrationService, "_parse_issue")
    @patch.object(JiraIntegrationService, "fetch_issues")
    @patch.object(JiraIntegrationService, "_build_embedding_status_map")
    def test_sync_with_explicit_project_keys(
        self,
        mock_status_map: MagicMock,
        mock_fetch: MagicMock,
        mock_parse: MagicMock,
        mock_store: MagicMock,
        mock_update_profiles: MagicMock,
        service: JiraIntegrationService,
        mock_db: MagicMock,
    ) -> None:
        mock_status_map.return_value = {"Bug": {"Done"}}

        mock_issue = _make_mock_jira_issue()
        mock_fetch.return_value = [mock_issue]

        issue_content = _make_issue_content(status="Done")
        mock_parse.return_value = issue_content
        mock_store.return_value = (1, 0)

        result = service.sync_issues(
            project_keys=["PROJ"],
            max_results=50,
            generate_embeddings=True,
        )

        assert result.status == "completed"
        assert result.projects_synced == ["PROJ"]
        assert result.issues_synced == 1

    @patch.object(JiraIntegrationService, "_update_resource_profiles_from_vectors")
    @patch.object(JiraIntegrationService, "_store_issue_embeddings")
    @patch.object(JiraIntegrationService, "_parse_issue")
    @patch.object(JiraIntegrationService, "fetch_issues")
    @patch.object(JiraIntegrationService, "_build_embedding_status_map")
    def test_sync_without_embeddings(
        self,
        mock_status_map: MagicMock,
        mock_fetch: MagicMock,
        mock_parse: MagicMock,
        mock_store: MagicMock,
        mock_update_profiles: MagicMock,
        service: JiraIntegrationService,
        mock_db: MagicMock,
    ) -> None:
        mock_status_map.return_value = {}
        mock_fetch.return_value = [_make_mock_jira_issue()]
        mock_parse.return_value = _make_issue_content()

        result = service.sync_issues(
            project_keys=["PROJ"],
            generate_embeddings=False,
        )

        mock_store.assert_not_called()
        assert result.status == "completed"

    @patch.object(JiraIntegrationService, "_update_resource_profiles_from_vectors")
    @patch.object(JiraIntegrationService, "fetch_issues")
    @patch.object(JiraIntegrationService, "_build_embedding_status_map")
    def test_sync_handles_fetch_error_gracefully(
        self,
        mock_status_map: MagicMock,
        mock_fetch: MagicMock,
        mock_update_profiles: MagicMock,
        service: JiraIntegrationService,
        mock_db: MagicMock,
    ) -> None:
        mock_status_map.return_value = {}
        mock_fetch.side_effect = Exception("Network error")

        result = service.sync_issues(project_keys=["PROJ"], generate_embeddings=False)

        assert result.status == "completed_with_errors"
        assert any("Network error" in e for e in result.errors)

    @patch.object(JiraIntegrationService, "_update_resource_profiles_from_vectors")
    @patch.object(JiraIntegrationService, "get_all_projects")
    @patch.object(JiraIntegrationService, "fetch_issues")
    @patch.object(JiraIntegrationService, "_build_embedding_status_map")
    def test_sync_discovers_projects_when_none_provided(
        self,
        mock_status_map: MagicMock,
        mock_fetch: MagicMock,
        mock_get_projects: MagicMock,
        mock_update_profiles: MagicMock,
        service: JiraIntegrationService,
        mock_db: MagicMock,
    ) -> None:
        mock_status_map.return_value = {}
        mock_get_projects.return_value = [{"key": "PROJ1"}, {"key": "PROJ2"}]
        mock_fetch.return_value = []

        result = service.sync_issues(project_keys=None, generate_embeddings=False)

        assert set(result.projects_synced) == {"PROJ1", "PROJ2"}
        mock_get_projects.assert_called_once()


# ===================================================================
# 13. Jira URL property
# ===================================================================


class TestJiraUrlProperty:
    @patch("app.api.integrations.Jira.jira_service.settings")
    def test_uses_client_header_first(
        self, mock_settings: MagicMock, service: JiraIntegrationService
    ) -> None:
        mock_client = MagicMock()
        mock_client._session.headers = {
            "_jira_site_url": "https://from-header.atlassian.net"
        }
        service._client = mock_client

        assert service.jira_url == "https://from-header.atlassian.net"

    @patch("app.api.integrations.Jira.jira_service.settings")
    def test_falls_back_to_integration(
        self, mock_settings: MagicMock, service: JiraIntegrationService
    ) -> None:
        service._client = None
        service.integration = MagicMock()
        service.integration.jira_url = "https://from-integration.atlassian.net"
        mock_settings.jira_oauth_enabled = False

        assert service.jira_url == "https://from-integration.atlassian.net"

    @patch("app.api.integrations.Jira.jira_service.settings")
    def test_falls_back_to_settings(
        self, mock_settings: MagicMock, service: JiraIntegrationService
    ) -> None:
        service._client = None
        service.integration = None
        mock_settings.jira_oauth_enabled = False
        mock_settings.JIRA_URL = "https://from-settings.atlassian.net"

        assert service.jira_url == "https://from-settings.atlassian.net"


# ===================================================================
# 14. Token refresh
# ===================================================================


class TestRefreshAccessToken:
    @patch.object(JiraIntegrationService, "_store_token")
    @patch("app.api.integrations.Jira.jira_service.httpx")
    @patch("app.api.integrations.Jira.jira_service.settings")
    def test_successful_refresh(
        self,
        mock_settings: MagicMock,
        mock_httpx: MagicMock,
        mock_store: MagicMock,
        service: JiraIntegrationService,
    ) -> None:
        mock_settings.ATLASSIAN_CLIENT_ID = "cid"
        mock_settings.ATLASSIAN_CLIENT_SECRET = "csecret"
        mock_settings.ATLASSIAN_TOKEN_URL = "https://auth.atlassian.com/oauth/token"

        token = MagicMock()
        token.refresh_token = "old-rt"
        token.cloud_id = "cloud-1"
        token.jira_site_url = "https://site.atlassian.net"
        token.scope = "read:jira-work"
        token.token_type = "Bearer"

        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {
            "access_token": "new-at",
            "refresh_token": "new-rt",
            "expires_in": 3600,
        }
        mock_httpx.post.return_value = resp

        stored = MagicMock()
        stored.expires_at = datetime(2025, 12, 31)
        mock_store.return_value = stored

        result = service._refresh_access_token(token)

        assert result is stored
        mock_store.assert_called_once()

    def test_raises_without_refresh_token(
        self, service: JiraIntegrationService
    ) -> None:
        token = MagicMock()
        token.refresh_token = None

        with pytest.raises(ValueError, match="No refresh token"):
            service._refresh_access_token(token)

    @patch("app.api.integrations.Jira.jira_service.httpx")
    @patch("app.api.integrations.Jira.jira_service.settings")
    def test_raises_on_http_failure(
        self,
        mock_settings: MagicMock,
        mock_httpx: MagicMock,
        service: JiraIntegrationService,
    ) -> None:
        mock_settings.ATLASSIAN_CLIENT_ID = "cid"
        mock_settings.ATLASSIAN_CLIENT_SECRET = "csecret"
        mock_settings.ATLASSIAN_TOKEN_URL = "https://auth.atlassian.com/oauth/token"

        token = MagicMock()
        token.refresh_token = "old-rt"

        resp = MagicMock()
        resp.status_code = 401
        resp.text = "unauthorized"
        mock_httpx.post.return_value = resp

        with pytest.raises(ValueError, match="Token refresh failed"):
            service._refresh_access_token(token)


# ===================================================================
# 15. Update issue type selected statuses
# ===================================================================


class TestUpdateIssueTypeSelectedStatuses:
    def test_updates_successfully(
        self, service: JiraIntegrationService, mock_db: MagicMock
    ) -> None:
        row = MagicMock()
        row.id = 1
        row.issue_type_id = "10001"
        row.issue_type_name = "Bug"
        row.available_statuses = ["Open", "In Progress", "Done"]
        row.selected_statuses = ["Done"]
        mock_db.query.return_value.filter.return_value.first.return_value = row

        result = service.update_issue_type_selected_statuses("10001", ["Open", "Done"])

        assert result.issue_type_name == "Bug"
        mock_db.commit.assert_called()

    def test_raises_when_type_not_found(
        self, service: JiraIntegrationService, mock_db: MagicMock
    ) -> None:
        mock_db.query.return_value.filter.return_value.first.return_value = None

        with pytest.raises(ValueError, match="not found"):
            service.update_issue_type_selected_statuses("99999", ["Done"])

    def test_raises_on_invalid_statuses(
        self, service: JiraIntegrationService, mock_db: MagicMock
    ) -> None:
        row = MagicMock()
        row.id = 2
        row.issue_type_id = "10001"
        row.issue_type_name = "Bug"
        row.available_statuses = ["Open", "Done"]
        row.selected_statuses = []
        mock_db.query.return_value.filter.return_value.first.return_value = row

        with pytest.raises(ValueError, match="Invalid statuses"):
            service.update_issue_type_selected_statuses("10001", ["NonExistent"])


# ===================================================================
# 11. Developer Stats
# ===================================================================


class TestGetDeveloperStats:
    @patch.object(JiraIntegrationService, "get_jira_client")
    @patch.object(JiraIntegrationService, "_parse_jira_user")
    def test_get_developer_stats_success(
        self,
        mock_parse_user: MagicMock,
        mock_get_client: MagicMock,
        service: JiraIntegrationService,
    ) -> None:
        # Mock Jira client and user
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        mock_user = JiraUser(
            account_id="user-123",
            display_name="Alice",
            email_address="alice@example.com",
            active=True,
        )
        mock_parse_user.return_value = mock_user

        # Mock issues return
        issue_done = MagicMock()
        issue_done.fields.status.statusCategory = MagicMock(key="done")
        issue_done.fields.status.name = "Done"

        issue_active = MagicMock()
        issue_active.fields.status.statusCategory = MagicMock(key="indeterminate")
        issue_active.fields.status.name = "In Progress"

        issue_todo = MagicMock()
        issue_todo.fields.status.statusCategory = MagicMock(key="new")
        issue_todo.fields.status.name = "To Do"

        issue_pr = MagicMock()
        issue_pr.fields.status.statusCategory = MagicMock(key="indeterminate")
        issue_pr.fields.status.name = "PR Review"

        issue_fallback = MagicMock()
        issue_fallback.fields.status.statusCategory = None
        issue_fallback.fields.status.name = "Done"

        mock_client.search_issues.side_effect = [
            [
                issue_done,
                issue_active,
                issue_todo,
                issue_pr,
                issue_fallback,
            ],  # First call: assigned
            [MagicMock(), MagicMock()],  # Second call: reported bugs
        ]

        result = service.get_developer_stats("user-123")

        assert result.account_id == "user-123"
        assert result.solved_tickets == 2  # issue_done and issue_fallback
        assert result.active_tickets == 3
        assert result.todo_tickets == 1
        assert result.inprogress_tickets == 1
        assert result.pr_review_tickets == 1
        assert result.done_tickets == 2
        assert result.total_tickets == 5
        assert result.bugs_reported == 2

        assert mock_client.search_issues.call_count == 2
        calls = mock_client.search_issues.call_args_list
        assert 'assignee = "user-123"' in calls[0][0][0]
        assert "issuetype = Bug" in calls[1][0][0]
