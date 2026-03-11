"""GitHub integration service using GitHub App authentication."""

import logging
import re
import time
from typing import Any

from github import Auth, Github
from github.PullRequest import PullRequest
from pydantic import HttpUrl
from sqlalchemy.orm import Session

from app.api.embedding.embedding_service import VectorEmbeddingService
from app.api.integrations.GitHub.github_model import GithubOrgIntBaseModel
from app.api.integrations.GitHub.github_schema import (
    GitHubRepository,
    GitHubSyncResponse,
    GitHubUser,
    PullRequestContent,
)
from app.core.config import settings

logger = logging.getLogger(__name__)


class GithubIntegrationService:
    def __init__(self, db: Session, use_jina_api: bool | None = None) -> None:
        self.db = db
        self.use_jina_api = (
            use_jina_api if use_jina_api is not None else settings.USE_JINA_API
        )
        self.credentials: GithubOrgIntBaseModel | None = db.query(
            GithubOrgIntBaseModel
        ).first()
        self._vector_service: VectorEmbeddingService | None = None

    @property
    def vector_service(self) -> VectorEmbeddingService:
        if not self._vector_service:
            self._vector_service = VectorEmbeddingService(
                self.db, use_api=self.use_jina_api
            )
        return self._vector_service

    # ── GitHub App Authentication ────────────────────────────────

    def get_github_client(self) -> Github:
        """Authenticates as the GitHub App installation and returns a PyGithub client."""
        if not self.credentials:
            raise Exception("GitHub integration credentials not found in database")

        app_auth = Auth.AppAuth(
            app_id=str(settings.GITHUB_APP_ID),
            private_key=settings.GITHUB_PRIVATE_KEY,
        )
        installation_auth = app_auth.get_installation_auth(
            int(self.credentials.github_install_id)
        )
        return Github(auth=installation_auth)

    @property
    def organization_name(self) -> str:
        if not self.credentials:
            raise Exception("GitHub integration credentials not found in database")
        return self.credentials.org_name

    @property
    def installation_id(self) -> str:
        if not self.credentials:
            raise Exception("GitHub integration credentials not found in database")
        return self.credentials.github_install_id

    # ── Repository Methods ───────────────────────────────────────

    def get_repositories(self) -> list[GitHubRepository]:
        """Get all repositories accessible to the GitHub App installation."""
        gh = self.get_github_client()
        org = gh.get_organization(self.organization_name)
        repos: list[GitHubRepository] = []

        for r in org.get_repos():
            repos.append(
                GitHubRepository(
                    id=r.id,
                    name=r.name,
                    full_name=r.full_name,
                    private=r.private,
                    html_url=HttpUrl(r.html_url),
                    description=r.description,
                    default_branch=r.default_branch or "main",
                    language=r.language,
                    stargazers_count=r.stargazers_count or 0,
                    forks_count=r.forks_count or 0,
                    open_issues_count=r.open_issues_count or 0,
                    created_at=r.created_at,
                    updated_at=r.updated_at,
                    pushed_at=r.pushed_at,
                )
            )

        return repos

    def get_repo_contributors(self, repo_name: str) -> list[dict[str, Any]]:
        """Get contributors for a repository within the org."""
        gh = self.get_github_client()
        org = gh.get_organization(self.organization_name)
        repo = org.get_repo(repo_name)

        return [
            {
                "login": c.login,
                "id": c.id,
                "avatar_url": c.avatar_url,
                "contributions": c.contributions,
            }
            for c in repo.get_contributors()
        ]

    def get_repo_pull_requests(
        self,
        repo_name: str,
        state: str = "closed",
        max_results: int = 30,
    ) -> list[dict[str, Any]]:
        """Get pull requests for a repository within the org."""
        gh = self.get_github_client()
        org = gh.get_organization(self.organization_name)
        repo = org.get_repo(repo_name)
        prs_data: list[dict[str, Any]] = []

        for pr in repo.get_pulls(state=state, sort="updated", direction="desc"):
            if len(prs_data) >= max_results:
                break
            prs_data.append(
                {
                    "id": pr.id,
                    "number": pr.number,
                    "title": pr.title,
                    "state": pr.state,
                    "html_url": pr.html_url,
                    "user": {
                        "login": pr.user.login if pr.user else None,
                        "id": pr.user.id if pr.user else None,
                        "avatar_url": pr.user.avatar_url if pr.user else None,
                    },
                    "created_at": pr.created_at.isoformat() if pr.created_at else None,
                    "updated_at": pr.updated_at.isoformat() if pr.updated_at else None,
                    "merged_at": pr.merged_at.isoformat() if pr.merged_at else None,
                    "labels": [label.name for label in pr.labels],
                }
            )

        return prs_data

    # ── Sync ─────────────────────────────────────────────────────

    def sync_repo_prs(
        self,
        repo_names: list[str] | None = None,
        max_prs_per_repo: int = 100,
        include_open: bool = False,
        generate_embeddings: bool = True,
    ) -> GitHubSyncResponse:
        """Sync PRs from GitHub repos, optionally generate embeddings."""
        start_time = time.time()

        gh = self.get_github_client()
        org = gh.get_organization(self.organization_name)

        if repo_names is None:
            repos = list(org.get_repos())
            repo_names = [r.name for r in repos]

        prs_synced = 0
        embeddings_generated = 0
        errors: list[str] = []
        all_pr_contents: list[PullRequestContent] = []

        for repo_name in repo_names:
            try:
                logger.info(f"Syncing GitHub repo: {self.organization_name}/{repo_name}")
                repo = org.get_repo(repo_name)

                states = ["closed"]
                if include_open:
                    states.append("open")

                for state in states:
                    count = 0
                    for pr in repo.get_pulls(state=state, sort="updated", direction="desc"):
                        if count >= max_prs_per_repo:
                            break
                        try:
                            pr_content = self.generate_pr_context(pr)
                            all_pr_contents.append(pr_content)
                            prs_synced += 1
                            count += 1
                        except Exception as e:
                            errors.append(
                                f"Error processing PR #{pr.number} in {repo_name}: {e}"
                            )
            except Exception as e:
                errors.append(f"Error syncing repo {repo_name}: {e}")

        if generate_embeddings and all_pr_contents:
            try:
                authors_prs: dict[str, list[PullRequestContent]] = {}
                for pr_content in all_pr_contents:
                    login = pr_content.author.login
                    if login not in authors_prs:
                        authors_prs[login] = []
                    authors_prs[login].append(pr_content)
                self.vector_service.store_all_authors_pr_contexts(authors_prs)
                embeddings_generated = len(all_pr_contents)
            except Exception as e:
                errors.append(f"Error generating embeddings: {e}")

        duration = time.time() - start_time

        return GitHubSyncResponse(
            status="completed" if not errors else "completed_with_errors",
            repos_synced=repo_names,
            prs_synced=prs_synced,
            prs_created=prs_synced,
            prs_updated=0,
            embeddings_generated=embeddings_generated,
            errors=errors,
            sync_duration_seconds=round(duration, 2),
        )

    # ── PR Context / Members ─────────────────────────────────────

    def get_all_org_members(self) -> list[GitHubUser]:
        """Retrieves all members of the organization."""
        gh = self.get_github_client()
        org = gh.get_organization(self.organization_name)
        members_list = []

        for member in org.get_members():
            members_list.append(
                GitHubUser(
                    login=member.login,
                    id=member.id,
                    email=member.email,
                    name=member.name,
                    avatar_url=HttpUrl(member.avatar_url)
                    if member.avatar_url
                    else None,
                    html_url=HttpUrl(member.html_url) if member.html_url else None,
                )
            )

        return members_list

    def generate_pr_context(
        self, pr: PullRequest, max_tokens: int = 8000
    ) -> PullRequestContent:
        """Generates a structured context string from a pull request."""
        author = GitHubUser(
            login=pr.user.login,
            id=pr.user.id,
        )
        pr_content = PullRequestContent(
            id=pr.id,
            number=pr.number,
            title=pr.title,
            html_url=HttpUrl(pr.html_url),
            author=author,
            repo_id=pr.base.repo.id,
            repo_name=pr.base.repo.name,
        )

        clean_description = re.sub(
            r"<!--.*?-->", "", pr.body or "", flags=re.DOTALL
        ).strip()

        pr_content.body = clean_description

        header = (
            f"PR_INTENT: {pr.title}\n"
            f"DESCRIPTION: {clean_description[:1000]}\n"
            f"LABELS: {', '.join([label.name for label in pr.labels])}\n"
        )

        files = pr.get_files()
        pr_content.labels = [label.name for label in pr.labels]

        body = "\nFILE_CHANGES:\n"
        files_list = []
        for f in files:
            status = f.status
            body += f"- [{status.upper()}] {f.filename}\n"
            files_list.append(f.filename)

        body += "\nCOMMITS:\n"
        for commit in pr.get_commits():
            commit_message = commit.commit.message
            len_message = len(re.findall(r"\w+", commit_message))
            if len_message > 5:
                body += f"- {commit_message.splitlines()[0]}\n"

        pr_content.context = header + body
        pr_content.changed_files = files_list
        return pr_content

    def get_org_closed_prs_context_by_author(
        self, author: GitHubUser, max_prs: int = 100
    ) -> list[PullRequestContent]:
        """Retrieves closed pull requests from all repositories in the organization."""
        gh = self.get_github_client()
        org = gh.get_organization(self.organization_name)
        prs_content_list: list[PullRequestContent] = []

        for repo in org.get_repos():
            try:
                repo_prs = repo.get_pulls(
                    state="closed", sort="updated", direction="desc"
                )

                for pr in repo_prs:
                    if not pr.user:
                        continue

                    if pr.user.id != author.id:
                        continue

                    if len(prs_content_list) >= max_prs:
                        return prs_content_list

                    prs_content_list.append(self.generate_pr_context(pr))
            except Exception as e:
                logger.warning("Skipping repo %s: %s", repo.name, str(e))
                continue

        return prs_content_list

    def get_org_closed_prs_context_all_authors(
        self, max_prs_per_author: int = 100
    ) -> dict[str, list[PullRequestContent]]:
        """Retrieves closed pull requests grouped by author for all org members."""
        gh = self.get_github_client()
        org = gh.get_organization(self.organization_name)
        authors_prs: dict[str, list[PullRequestContent]] = {}

        for repo in org.get_repos():
            try:
                repo_prs = repo.get_pulls(
                    state="closed", sort="updated", direction="desc"
                )
                for pr in repo_prs:
                    if pr.user:
                        author_login = pr.user.login
                        if author_login not in authors_prs:
                            authors_prs[author_login] = []
                        authors_prs[author_login].append(self.generate_pr_context(pr))
            except Exception as e:
                logger.warning("Skipping repo %s: %s", repo.name, str(e))
                continue

        for author in authors_prs:
            authors_prs[author] = authors_prs[author][:max_prs_per_author]

        return authors_prs

    def sync_author_prs_to_vectors(
        self, author: GitHubUser, max_prs: int = 100
    ) -> dict[str, int | str]:
        """Fetch PRs for an author and store their vectors."""
        pr_contents = self.get_org_closed_prs_context_by_author(author, max_prs)
        self.vector_service.store_pr_contexts(author, pr_contents)
        return {
            "author_login": author.login,
            "prs_synced": len(pr_contents),
        }

    def sync_all_authors_prs_to_vectors(
        self, max_prs_per_author: int = 100
    ) -> dict[str, int]:
        """Fetch PRs for all authors and store their vectors."""
        authors_prs = self.get_org_closed_prs_context_all_authors(max_prs_per_author)
        self.vector_service.store_all_authors_pr_contexts(authors_prs)
        return {
            "total_authors": len(authors_prs),
            "total_prs": sum(len(prs) for prs in authors_prs.values()),
        }
