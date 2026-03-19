"""Unit tests for GithubIntegrationService.

All external I/O (database, GitHub API, PyGithub SDK) is mocked so
these tests run without network or database access.
"""

from datetime import datetime
from typing import Any
from unittest.mock import MagicMock, PropertyMock, patch

import pytest

from app.api.integrations.GitHub.github_schema import (
    GitHubUser,
    PullRequestContent,
)
from app.api.integrations.GitHub.github_service import GithubIntegrationService

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def mock_db() -> MagicMock:
    db = MagicMock()
    db.query.return_value.first.return_value = None
    return db


@pytest.fixture()
def service(mock_db: MagicMock) -> GithubIntegrationService:
    """Build service with mocked DB and no real credentials."""
    with patch.object(GithubIntegrationService, "__init__", lambda self, *a, **kw: None):
        svc = GithubIntegrationService.__new__(GithubIntegrationService)
        svc.db = mock_db
        svc.use_jina_api = False
        svc._vector_service = None
        svc.credentials = None
        return svc


@pytest.fixture()
def service_with_creds(service: GithubIntegrationService) -> GithubIntegrationService:
    """Service with mock credentials pre-loaded."""
    creds = MagicMock()
    creds.github_install_id = "12345"
    creds.org_name = "test-org"
    service.credentials = creds
    return service


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_pr(
    pr_id: int = 100,
    number: int = 1,
    title: str = "Fix auth flow",
    body: str = "Resolved the login redirect bug",
    state: str = "closed",
    html_url: str = "https://github.com/test-org/repo/pull/1",
    author_login: str = "alice",
    author_id: int = 42,
    labels: list[str] | None = None,
    files: list[dict[str, str]] | None = None,
    commits: list[str] | None = None,
    created_at: datetime | None = None,
    updated_at: datetime | None = None,
    merged_at: datetime | None = None,
) -> MagicMock:
    """Build a mock PyGithub PullRequest object."""
    pr = MagicMock()
    pr.id = pr_id
    pr.number = number
    pr.title = title
    pr.body = body
    pr.state = state
    pr.html_url = html_url

    user = MagicMock()
    user.login = author_login
    user.id = author_id
    user.avatar_url = "https://avatars.githubusercontent.com/u/42"
    pr.user = user

    pr.created_at = created_at or datetime(2025, 1, 1)
    pr.updated_at = updated_at or datetime(2025, 1, 2)
    pr.merged_at = merged_at

    label_mocks = []
    for name in (labels or []):
        lbl = MagicMock()
        lbl.name = name
        label_mocks.append(lbl)
    pr.labels = label_mocks

    # Base repo info
    base = MagicMock()
    base.repo.id = 999
    base.repo.name = "repo"
    pr.base = base

    # Files
    file_mocks = []
    for f in (files or [{"filename": "src/auth.py", "status": "modified"}]):
        fm = MagicMock()
        fm.filename = f["filename"]
        fm.status = f.get("status", "modified")
        file_mocks.append(fm)
    pr.get_files.return_value = file_mocks

    # Commits
    commit_mocks = []
    for msg in (commits or ["fix: resolve redirect loop"]):
        cm = MagicMock()
        cm.commit.message = msg
        commit_mocks.append(cm)
    pr.get_commits.return_value = commit_mocks

    return pr


def _make_mock_repo(
    name: str = "repo",
    full_name: str = "test-org/repo",
    prs: list[MagicMock] | None = None,
    contributors: list[dict[str, Any]] | None = None,
    members: list[dict[str, Any]] | None = None,
) -> MagicMock:
    repo = MagicMock()
    repo.id = 999
    repo.name = name
    repo.full_name = full_name
    repo.private = False
    repo.html_url = f"https://github.com/{full_name}"
    repo.description = "A test repository"
    repo.default_branch = "main"
    repo.language = "Python"
    repo.stargazers_count = 10
    repo.forks_count = 3
    repo.open_issues_count = 5
    repo.created_at = datetime(2024, 1, 1)
    repo.updated_at = datetime(2025, 1, 1)
    repo.pushed_at = datetime(2025, 1, 2)

    if prs is not None:
        repo.get_pulls.return_value = prs
    else:
        repo.get_pulls.return_value = []

    if contributors is not None:
        contrib_mocks = []
        for c in contributors:
            cm = MagicMock()
            cm.login = c["login"]
            cm.id = c["id"]
            cm.avatar_url = c.get("avatar_url", "")
            cm.contributions = c.get("contributions", 0)
            contrib_mocks.append(cm)
        repo.get_contributors.return_value = contrib_mocks

    return repo


def _make_mock_github_client(
    repos: list[MagicMock] | None = None,
    members: list[dict[str, Any]] | None = None,
) -> MagicMock:
    gh = MagicMock()
    org = MagicMock()

    if repos is not None:
        org.get_repos.return_value = repos
    else:
        org.get_repos.return_value = []

    if members is not None:
        member_mocks = []
        for m in members:
            mm = MagicMock()
            mm.login = m["login"]
            mm.id = m["id"]
            mm.email = m.get("email")
            mm.name = m.get("name")
            mm.avatar_url = m.get("avatar_url")
            mm.html_url = m.get("html_url")
            member_mocks.append(mm)
        org.get_members.return_value = member_mocks

    def get_repo(name: str) -> MagicMock:
        for r in (repos or []):
            if r.name == name:
                return r
        raise Exception(f"Repo {name} not found")

    org.get_repo = get_repo
    gh.get_organization.return_value = org
    return gh


# ===================================================================
# 1. Client initialization and properties
# ===================================================================

class TestGetGithubClient:
    def test_raises_without_credentials(self, service: GithubIntegrationService) -> None:
        with pytest.raises(Exception, match="credentials not found"):
            service.get_github_client()

    @patch("app.api.integrations.GitHub.github_service.settings")
    def test_raises_without_app_config(
        self, mock_settings: MagicMock, service_with_creds: GithubIntegrationService
    ) -> None:
        mock_settings.GITHUB_APP_ID = None
        mock_settings.GITHUB_PRIVATE_KEY = None

        with pytest.raises(Exception, match="GitHub App ID or Private Key missing"):
            service_with_creds.get_github_client()

    @patch("app.api.integrations.GitHub.github_service.Github")
    @patch("app.api.integrations.GitHub.github_service.Auth")
    @patch("app.api.integrations.GitHub.github_service.settings")
    def test_successful_client_creation(
        self,
        mock_settings: MagicMock,
        mock_auth: MagicMock,
        mock_github_cls: MagicMock,
        service_with_creds: GithubIntegrationService,
    ) -> None:
        mock_settings.GITHUB_APP_ID = 123456
        mock_settings.GITHUB_PRIVATE_KEY = "fake-private-key"

        mock_app_auth = MagicMock()
        mock_install_auth = MagicMock()
        mock_auth.AppAuth.return_value = mock_app_auth
        mock_app_auth.get_installation_auth.return_value = mock_install_auth

        mock_client = MagicMock()
        mock_github_cls.return_value = mock_client

        result = service_with_creds.get_github_client()

        mock_auth.AppAuth.assert_called_once_with(
            app_id="123456", private_key="fake-private-key"
        )
        mock_app_auth.get_installation_auth.assert_called_once_with(12345)
        assert result is mock_client


class TestProperties:
    def test_organization_name(self, service_with_creds: GithubIntegrationService) -> None:
        assert service_with_creds.organization_name == "test-org"

    def test_organization_name_raises_without_creds(self, service: GithubIntegrationService) -> None:
        with pytest.raises(Exception, match="credentials not found"):
            _ = service.organization_name

    def test_installation_id(self, service_with_creds: GithubIntegrationService) -> None:
        assert service_with_creds.installation_id == "12345"

    def test_installation_id_raises_without_creds(self, service: GithubIntegrationService) -> None:
        with pytest.raises(Exception, match="credentials not found"):
            _ = service.installation_id


# ===================================================================
# 2. Repository methods
# ===================================================================

class TestGetRepositories:
    @patch.object(GithubIntegrationService, "get_github_client")
    @patch.object(GithubIntegrationService, "organization_name", new_callable=PropertyMock, return_value="test-org")
    def test_returns_repo_list(
        self,
        _mock_org: MagicMock,
        mock_get_client: MagicMock,
        service: GithubIntegrationService,
    ) -> None:
        repo = _make_mock_repo()
        gh = _make_mock_github_client(repos=[repo])
        mock_get_client.return_value = gh

        result = service.get_repositories()

        assert len(result) == 1
        assert result[0].name == "repo"
        assert result[0].full_name == "test-org/repo"
        assert result[0].language == "Python"

    @patch.object(GithubIntegrationService, "get_github_client")
    @patch.object(GithubIntegrationService, "organization_name", new_callable=PropertyMock, return_value="test-org")
    def test_returns_empty_list(
        self,
        _mock_org: MagicMock,
        mock_get_client: MagicMock,
        service: GithubIntegrationService,
    ) -> None:
        gh = _make_mock_github_client(repos=[])
        mock_get_client.return_value = gh

        result = service.get_repositories()
        assert result == []


class TestGetRepoContributors:
    @patch.object(GithubIntegrationService, "get_github_client")
    @patch.object(GithubIntegrationService, "organization_name", new_callable=PropertyMock, return_value="test-org")
    def test_returns_contributors(
        self,
        _mock_org: MagicMock,
        mock_get_client: MagicMock,
        service: GithubIntegrationService,
    ) -> None:
        repo = _make_mock_repo(
            name="my-repo",
            contributors=[
                {"login": "alice", "id": 1, "avatar_url": "https://a.com/a.png", "contributions": 50},
                {"login": "bob", "id": 2, "avatar_url": "https://a.com/b.png", "contributions": 30},
            ],
        )
        gh = _make_mock_github_client(repos=[repo])
        mock_get_client.return_value = gh

        result = service.get_repo_contributors("my-repo")

        assert len(result) == 2
        assert result[0]["login"] == "alice"
        assert result[0]["contributions"] == 50
        assert result[1]["login"] == "bob"


class TestGetRepoPullRequests:
    @patch.object(GithubIntegrationService, "get_github_client")
    @patch.object(GithubIntegrationService, "organization_name", new_callable=PropertyMock, return_value="test-org")
    def test_returns_pr_list(
        self,
        _mock_org: MagicMock,
        mock_get_client: MagicMock,
        service: GithubIntegrationService,
    ) -> None:
        pr = _make_mock_pr(
            number=1,
            title="Fix bug",
            labels=["bugfix"],
            merged_at=datetime(2025, 1, 3),
        )
        repo = _make_mock_repo(name="my-repo", prs=[pr])
        gh = _make_mock_github_client(repos=[repo])
        mock_get_client.return_value = gh

        result = service.get_repo_pull_requests("my-repo", state="closed", max_results=10)

        assert len(result) == 1
        assert result[0]["title"] == "Fix bug"
        assert result[0]["labels"] == ["bugfix"]
        assert result[0]["user"]["login"] == "alice"

    @patch.object(GithubIntegrationService, "get_github_client")
    @patch.object(GithubIntegrationService, "organization_name", new_callable=PropertyMock, return_value="test-org")
    def test_respects_max_results(
        self,
        _mock_org: MagicMock,
        mock_get_client: MagicMock,
        service: GithubIntegrationService,
    ) -> None:
        prs = [_make_mock_pr(pr_id=i, number=i) for i in range(5)]
        repo = _make_mock_repo(name="my-repo", prs=prs)
        gh = _make_mock_github_client(repos=[repo])
        mock_get_client.return_value = gh

        result = service.get_repo_pull_requests("my-repo", max_results=2)
        assert len(result) == 2


# ===================================================================
# 3. PR context generation
# ===================================================================

class TestGeneratePrContext:
    def test_basic_context_generation(self, service: GithubIntegrationService) -> None:
        pr = _make_mock_pr(
            title="Add caching layer",
            body="Implements Redis caching for API responses",
            labels=["enhancement", "backend"],
            files=[
                {"filename": "src/cache.py", "status": "added"},
                {"filename": "src/api.py", "status": "modified"},
            ],
            commits=["feat: add Redis cache helper for responses", "refactor: integrate caching layer in the API"],
        )

        result = service.generate_pr_context(pr)

        assert result.title == "Add caching layer"
        assert result.number == 1
        assert result.author.login == "alice"
        assert result.repo_name == "repo"
        assert "PR_INTENT: Add caching layer" in result.context
        assert "DESCRIPTION: Implements Redis caching" in result.context
        assert "enhancement, backend" in result.context
        assert "src/cache.py" in result.context
        assert "src/api.py" in result.context
        assert "feat: add Redis cache helper for responses" in result.context

    def test_strips_html_comments_from_body(self, service: GithubIntegrationService) -> None:
        pr = _make_mock_pr(
            body="<!-- This is a comment -->\nActual description here"
        )

        result = service.generate_pr_context(pr)

        assert result.body is not None
        assert "<!-- This is a comment -->" not in result.body
        assert "Actual description here" in result.body

    def test_handles_none_body(self, service: GithubIntegrationService) -> None:
        pr = _make_mock_pr(body=None)

        result = service.generate_pr_context(pr)

        assert result.body == ""
        assert "DESCRIPTION:" in result.context

    def test_skips_short_commit_messages(self, service: GithubIntegrationService) -> None:
        pr = _make_mock_pr(
            commits=["fix", "feat: add proper authentication module for users"]
        )

        result = service.generate_pr_context(pr)

        # "fix" has only 1 word so should be skipped; the second commit should appear
        assert "feat: add proper authentication" in result.context

    def test_changed_files_list(self, service: GithubIntegrationService) -> None:
        pr = _make_mock_pr(
            files=[
                {"filename": "a.py", "status": "added"},
                {"filename": "b.py", "status": "modified"},
                {"filename": "c.py", "status": "removed"},
            ]
        )

        result = service.generate_pr_context(pr)

        assert len(result.changed_files) == 3
        assert "a.py" in result.changed_files
        assert "[ADDED] a.py" in result.context
        assert "[MODIFIED] b.py" in result.context
        assert "[REMOVED] c.py" in result.context

    def test_labels_extracted(self, service: GithubIntegrationService) -> None:
        pr = _make_mock_pr(labels=["bug", "critical"])

        result = service.generate_pr_context(pr)

        assert result.labels == ["bug", "critical"]


# ===================================================================
# 4. Organization members
# ===================================================================

class TestGetAllOrgMembers:
    @patch.object(GithubIntegrationService, "get_github_client")
    @patch.object(GithubIntegrationService, "organization_name", new_callable=PropertyMock, return_value="test-org")
    def test_returns_member_list(
        self,
        _mock_org: MagicMock,
        mock_get_client: MagicMock,
        service: GithubIntegrationService,
    ) -> None:
        gh = _make_mock_github_client(
            members=[
                {"login": "alice", "id": 1, "email": "alice@test.com", "name": "Alice", "avatar_url": "https://a.com/a.png", "html_url": "https://github.com/alice"},
                {"login": "bob", "id": 2, "email": None, "name": "Bob", "avatar_url": "https://a.com/b.png", "html_url": "https://github.com/bob"},
            ]
        )
        mock_get_client.return_value = gh

        result = service.get_all_org_members()

        assert len(result) == 2
        assert result[0].login == "alice"
        assert result[0].email == "alice@test.com"
        assert result[1].login == "bob"

    @patch.object(GithubIntegrationService, "get_github_client")
    @patch.object(GithubIntegrationService, "organization_name", new_callable=PropertyMock, return_value="test-org")
    def test_handles_member_without_avatar(
        self,
        _mock_org: MagicMock,
        mock_get_client: MagicMock,
        service: GithubIntegrationService,
    ) -> None:
        gh = _make_mock_github_client(
            members=[{"login": "noavatar", "id": 3, "avatar_url": None, "html_url": None}]
        )
        mock_get_client.return_value = gh

        result = service.get_all_org_members()

        assert len(result) == 1
        assert result[0].avatar_url is None


# ===================================================================
# 5. Sync PRs
# ===================================================================

class TestSyncRepoPrs:
    @patch.object(GithubIntegrationService, "vector_service", new_callable=PropertyMock)
    @patch.object(GithubIntegrationService, "generate_pr_context")
    @patch.object(GithubIntegrationService, "get_github_client")
    @patch.object(GithubIntegrationService, "organization_name", new_callable=PropertyMock, return_value="test-org")
    def test_sync_with_explicit_repos(
        self,
        _mock_org: MagicMock,
        mock_get_client: MagicMock,
        mock_gen_ctx: MagicMock,
        mock_vector_svc: MagicMock,
        service: GithubIntegrationService,
    ) -> None:
        pr = _make_mock_pr()
        repo = _make_mock_repo(name="my-repo", prs=[pr])
        gh = _make_mock_github_client(repos=[repo])
        mock_get_client.return_value = gh

        pr_content = PullRequestContent(
            id=100, number=1, title="Fix", html_url="https://github.com/test/pull/1",
            author=GitHubUser(login="alice", id=42), repo_id=999, repo_name="my-repo",
            context="test context",
        )
        mock_gen_ctx.return_value = pr_content

        mock_vs = MagicMock()
        mock_vector_svc.return_value = mock_vs

        result = service.sync_repo_prs(
            repo_names=["my-repo"],
            max_prs_per_repo=100,
            generate_embeddings=True,
        )

        assert result.status == "completed"
        assert result.repos_synced == ["my-repo"]
        assert result.prs_synced == 1
        assert result.embeddings_generated == 1

    @patch.object(GithubIntegrationService, "generate_pr_context")
    @patch.object(GithubIntegrationService, "get_github_client")
    @patch.object(GithubIntegrationService, "organization_name", new_callable=PropertyMock, return_value="test-org")
    def test_sync_without_embeddings(
        self,
        _mock_org: MagicMock,
        mock_get_client: MagicMock,
        mock_gen_ctx: MagicMock,
        service: GithubIntegrationService,
    ) -> None:
        pr = _make_mock_pr()
        repo = _make_mock_repo(name="my-repo", prs=[pr])
        gh = _make_mock_github_client(repos=[repo])
        mock_get_client.return_value = gh

        pr_content = PullRequestContent(
            id=100, number=1, title="Fix", html_url="https://github.com/test/pull/1",
            author=GitHubUser(login="alice", id=42), repo_id=999,
        )
        mock_gen_ctx.return_value = pr_content

        result = service.sync_repo_prs(
            repo_names=["my-repo"],
            generate_embeddings=False,
        )

        assert result.status == "completed"
        assert result.prs_synced == 1
        assert result.embeddings_generated == 0

    @patch.object(GithubIntegrationService, "get_github_client")
    @patch.object(GithubIntegrationService, "organization_name", new_callable=PropertyMock, return_value="test-org")
    def test_sync_discovers_repos_when_none_provided(
        self,
        _mock_org: MagicMock,
        mock_get_client: MagicMock,
        service: GithubIntegrationService,
    ) -> None:
        repo1 = _make_mock_repo(name="repo-a")
        repo2 = _make_mock_repo(name="repo-b")
        gh = _make_mock_github_client(repos=[repo1, repo2])
        mock_get_client.return_value = gh

        result = service.sync_repo_prs(
            repo_names=None,
            generate_embeddings=False,
        )

        assert set(result.repos_synced) == {"repo-a", "repo-b"}

    @patch.object(GithubIntegrationService, "get_github_client")
    @patch.object(GithubIntegrationService, "organization_name", new_callable=PropertyMock, return_value="test-org")
    def test_sync_handles_repo_error_gracefully(
        self,
        _mock_org: MagicMock,
        mock_get_client: MagicMock,
        service: GithubIntegrationService,
    ) -> None:
        gh = _make_mock_github_client(repos=[])
        org = gh.get_organization.return_value
        org.get_repo.side_effect = Exception("Repo not accessible")
        mock_get_client.return_value = gh

        result = service.sync_repo_prs(
            repo_names=["broken-repo"],
            generate_embeddings=False,
        )

        assert result.status == "completed_with_errors"
        assert any("broken-repo" in e for e in result.errors)

    @patch.object(GithubIntegrationService, "generate_pr_context")
    @patch.object(GithubIntegrationService, "get_github_client")
    @patch.object(GithubIntegrationService, "organization_name", new_callable=PropertyMock, return_value="test-org")
    def test_sync_includes_open_prs_when_requested(
        self,
        _mock_org: MagicMock,
        mock_get_client: MagicMock,
        mock_gen_ctx: MagicMock,
        service: GithubIntegrationService,
    ) -> None:
        pr = _make_mock_pr()
        repo = _make_mock_repo(name="my-repo", prs=[pr])
        gh = _make_mock_github_client(repos=[repo])
        mock_get_client.return_value = gh

        pr_content = PullRequestContent(
            id=100, number=1, title="Fix", html_url="https://github.com/test/pull/1",
            author=GitHubUser(login="alice", id=42), repo_id=999,
        )
        mock_gen_ctx.return_value = pr_content

        result = service.sync_repo_prs(
            repo_names=["my-repo"],
            include_open=True,
            generate_embeddings=False,
        )

        # repo.get_pulls should be called for both "closed" and "open"
        calls = repo.get_pulls.call_args_list
        states = [c.kwargs.get("state") for c in calls]
        assert "closed" in states
        assert "open" in states


# ===================================================================
# 6. Closed PRs by author
# ===================================================================

class TestGetOrgClosedPrsContextByAuthor:
    @patch.object(GithubIntegrationService, "generate_pr_context")
    @patch.object(GithubIntegrationService, "get_github_client")
    @patch.object(GithubIntegrationService, "organization_name", new_callable=PropertyMock, return_value="test-org")
    def test_filters_by_author_id(
        self,
        _mock_org: MagicMock,
        mock_get_client: MagicMock,
        mock_gen_ctx: MagicMock,
        service: GithubIntegrationService,
    ) -> None:
        alice_pr = _make_mock_pr(author_login="alice", author_id=42)
        bob_pr = _make_mock_pr(author_login="bob", author_id=99, pr_id=200, number=2)
        repo = _make_mock_repo(name="repo", prs=[alice_pr, bob_pr])
        gh = _make_mock_github_client(repos=[repo])
        mock_get_client.return_value = gh

        pr_content = PullRequestContent(
            id=100, number=1, title="Fix", html_url="https://github.com/test/pull/1",
            author=GitHubUser(login="alice", id=42), repo_id=999,
        )
        mock_gen_ctx.return_value = pr_content

        author = GitHubUser(login="alice", id=42)
        result = service.get_org_closed_prs_context_by_author(author)

        assert len(result) == 1
        mock_gen_ctx.assert_called_once_with(alice_pr)

    @patch.object(GithubIntegrationService, "generate_pr_context")
    @patch.object(GithubIntegrationService, "get_github_client")
    @patch.object(GithubIntegrationService, "organization_name", new_callable=PropertyMock, return_value="test-org")
    def test_respects_max_prs(
        self,
        _mock_org: MagicMock,
        mock_get_client: MagicMock,
        mock_gen_ctx: MagicMock,
        service: GithubIntegrationService,
    ) -> None:
        prs = [_make_mock_pr(pr_id=i, number=i, author_id=42) for i in range(5)]
        repo = _make_mock_repo(name="repo", prs=prs)
        gh = _make_mock_github_client(repos=[repo])
        mock_get_client.return_value = gh

        pr_content = PullRequestContent(
            id=100, number=1, title="Fix", html_url="https://github.com/test/pull/1",
            author=GitHubUser(login="alice", id=42), repo_id=999,
        )
        mock_gen_ctx.return_value = pr_content

        author = GitHubUser(login="alice", id=42)
        result = service.get_org_closed_prs_context_by_author(author, max_prs=2)

        assert len(result) == 2

    @patch.object(GithubIntegrationService, "get_github_client")
    @patch.object(GithubIntegrationService, "organization_name", new_callable=PropertyMock, return_value="test-org")
    def test_skips_prs_without_user(
        self,
        _mock_org: MagicMock,
        mock_get_client: MagicMock,
        service: GithubIntegrationService,
    ) -> None:
        pr = _make_mock_pr()
        pr.user = None
        repo = _make_mock_repo(name="repo", prs=[pr])
        gh = _make_mock_github_client(repos=[repo])
        mock_get_client.return_value = gh

        author = GitHubUser(login="alice", id=42)
        result = service.get_org_closed_prs_context_by_author(author)

        assert len(result) == 0


# ===================================================================
# 7. Closed PRs all authors
# ===================================================================

class TestGetOrgClosedPrsContextAllAuthors:
    @patch.object(GithubIntegrationService, "generate_pr_context")
    @patch.object(GithubIntegrationService, "get_github_client")
    @patch.object(GithubIntegrationService, "organization_name", new_callable=PropertyMock, return_value="test-org")
    def test_groups_by_author(
        self,
        _mock_org: MagicMock,
        mock_get_client: MagicMock,
        mock_gen_ctx: MagicMock,
        service: GithubIntegrationService,
    ) -> None:
        alice_pr = _make_mock_pr(author_login="alice", author_id=42)
        bob_pr = _make_mock_pr(author_login="bob", author_id=99, pr_id=200, number=2)
        repo = _make_mock_repo(name="repo", prs=[alice_pr, bob_pr])
        gh = _make_mock_github_client(repos=[repo])
        mock_get_client.return_value = gh

        def gen_ctx(pr: Any) -> PullRequestContent:
            return PullRequestContent(
                id=pr.id, number=pr.number, title=pr.title,
                html_url=pr.html_url,
                author=GitHubUser(login=pr.user.login, id=pr.user.id),
                repo_id=999,
            )
        mock_gen_ctx.side_effect = gen_ctx

        result = service.get_org_closed_prs_context_all_authors()

        assert "alice" in result
        assert "bob" in result
        assert len(result["alice"]) == 1
        assert len(result["bob"]) == 1

    @patch.object(GithubIntegrationService, "generate_pr_context")
    @patch.object(GithubIntegrationService, "get_github_client")
    @patch.object(GithubIntegrationService, "organization_name", new_callable=PropertyMock, return_value="test-org")
    def test_respects_max_prs_per_author(
        self,
        _mock_org: MagicMock,
        mock_get_client: MagicMock,
        mock_gen_ctx: MagicMock,
        service: GithubIntegrationService,
    ) -> None:
        prs = [_make_mock_pr(pr_id=i, number=i, author_login="alice", author_id=42) for i in range(5)]
        repo = _make_mock_repo(name="repo", prs=prs)
        gh = _make_mock_github_client(repos=[repo])
        mock_get_client.return_value = gh

        mock_gen_ctx.side_effect = lambda pr: PullRequestContent(
            id=pr.id, number=pr.number, title=pr.title,
            html_url=pr.html_url,
            author=GitHubUser(login="alice", id=42), repo_id=999,
        )

        result = service.get_org_closed_prs_context_all_authors(max_prs_per_author=2)

        assert len(result["alice"]) == 2


# ===================================================================
# 8. Sync author PRs to vectors
# ===================================================================

class TestSyncAuthorPrsToVectors:
    @patch.object(GithubIntegrationService, "vector_service", new_callable=PropertyMock)
    @patch.object(GithubIntegrationService, "get_org_closed_prs_context_by_author")
    def test_sync_author_vectors(
        self,
        mock_get_prs: MagicMock,
        mock_vector_svc: MagicMock,
        service: GithubIntegrationService,
    ) -> None:
        pr_content = PullRequestContent(
            id=100, number=1, title="Fix", html_url="https://github.com/test/pull/1",
            author=GitHubUser(login="alice", id=42), repo_id=999,
        )
        mock_get_prs.return_value = [pr_content]

        mock_vs = MagicMock()
        mock_vector_svc.return_value = mock_vs

        author = GitHubUser(login="alice", id=42)
        result = service.sync_author_prs_to_vectors(author)

        assert result["author_login"] == "alice"
        assert result["prs_synced"] == 1
        mock_vs.store_pr_contexts.assert_called_once()


# ===================================================================
# 9. Sync all authors to vectors
# ===================================================================

class TestSyncAllAuthorsPrsToVectors:
    @patch.object(GithubIntegrationService, "vector_service", new_callable=PropertyMock)
    @patch.object(GithubIntegrationService, "generate_pr_context")
    @patch.object(GithubIntegrationService, "get_github_client")
    @patch.object(GithubIntegrationService, "organization_name", new_callable=PropertyMock, return_value="test-org")
    def test_sync_all_authors(
        self,
        _mock_org: MagicMock,
        mock_get_client: MagicMock,
        mock_gen_ctx: MagicMock,
        mock_vector_svc: MagicMock,
        service: GithubIntegrationService,
    ) -> None:
        alice_pr = _make_mock_pr(author_login="alice", author_id=42)
        bob_pr = _make_mock_pr(author_login="bob", author_id=99, pr_id=200, number=2)
        repo = _make_mock_repo(name="repo", prs=[alice_pr, bob_pr])
        gh = _make_mock_github_client(repos=[repo])
        mock_get_client.return_value = gh

        def gen_ctx(pr: Any) -> PullRequestContent:
            return PullRequestContent(
                id=pr.id, number=pr.number, title=pr.title,
                html_url=pr.html_url,
                author=GitHubUser(login=pr.user.login, id=pr.user.id),
                repo_id=999,
            )
        mock_gen_ctx.side_effect = gen_ctx

        mock_vs = MagicMock()
        mock_vs.store_pr_contexts.return_value = 1
        mock_vector_svc.return_value = mock_vs

        result = service.sync_all_authors_prs_to_vectors(max_prs_per_author=100)

        assert result["total_authors"] == 2
        assert result["total_prs"] == 2

    @patch.object(GithubIntegrationService, "get_github_client")
    @patch.object(GithubIntegrationService, "organization_name", new_callable=PropertyMock, return_value="test-org")
    def test_skips_failing_repos(
        self,
        _mock_org: MagicMock,
        mock_get_client: MagicMock,
        service: GithubIntegrationService,
    ) -> None:
        failing_repo = _make_mock_repo(name="broken")
        failing_repo.get_pulls.side_effect = Exception("Access denied")

        good_repo = _make_mock_repo(name="good")

        gh = _make_mock_github_client(repos=[failing_repo, good_repo])
        mock_get_client.return_value = gh

        result = service.sync_all_authors_prs_to_vectors()

        assert result["total_prs"] == 0

    @patch.object(GithubIntegrationService, "vector_service", new_callable=PropertyMock)
    @patch.object(GithubIntegrationService, "generate_pr_context")
    @patch.object(GithubIntegrationService, "get_github_client")
    @patch.object(GithubIntegrationService, "organization_name", new_callable=PropertyMock, return_value="test-org")
    def test_respects_max_prs_per_author_limit(
        self,
        _mock_org: MagicMock,
        mock_get_client: MagicMock,
        mock_gen_ctx: MagicMock,
        mock_vector_svc: MagicMock,
        service: GithubIntegrationService,
    ) -> None:
        prs = [_make_mock_pr(pr_id=i, number=i, author_login="alice", author_id=42) for i in range(10)]
        repo = _make_mock_repo(name="repo", prs=prs)
        gh = _make_mock_github_client(repos=[repo])
        mock_get_client.return_value = gh

        mock_gen_ctx.side_effect = lambda pr: PullRequestContent(
            id=pr.id, number=pr.number, title=pr.title,
            html_url=pr.html_url,
            author=GitHubUser(login="alice", id=42), repo_id=999,
        )

        mock_vs = MagicMock()
        mock_vs.store_pr_contexts.return_value = 3
        mock_vector_svc.return_value = mock_vs

        result = service.sync_all_authors_prs_to_vectors(max_prs_per_author=3)

        assert mock_gen_ctx.call_count == 3
