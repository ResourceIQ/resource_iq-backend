import logging
import re

from github import Github, GithubIntegration
from github.PullRequest import PullRequest
from pydantic import HttpUrl

from app.api.embedding.embedding_service import VectorEmbeddingService
from app.api.integrations.GitHub.github_model import GithubOrgIntBaseModel
from app.api.integrations.GitHub.github_schema import GitHubUser, PullRequestContent
from app.core.config import settings
from app.utils.deps import SessionDep

logger = logging.getLogger(__name__)


class GithubIntegrationService:
    def __init__(self, db: SessionDep, use_jina_api: bool | None = None) -> None:
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

    def get_github_client(self) -> Github:
        """
        Authenticates as the GitHub App.
        """
        if not self.credentials:
            raise Exception("GitHub integration credentials not found in database")

        # 1. Sign JWT with Private Key
        integration = GithubIntegration(
            settings.GITHUB_APP_ID, settings.GITHUB_PRIVATE_KEY
        )

        # 2. Get Access Token for this specific Installation
        access_token = integration.get_access_token(
            int(self.credentials.github_install_id)
        ).token

        # 3. Return PyGithub Client
        return Github(access_token)

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

    def get_all_org_members(self) -> list[GitHubUser]:
        """
        Retrieves all members of the organization with their name and email.
        Note: Email is only returned if it is set to 'Public' by the user.
        """
        gh = self.get_github_client()
        org = gh.get_organization(self.organization_name)
        members_list = []

        # Use get_members() to get people officially in the org
        for member in org.get_members():
            # member is a NamedUser object
            # We access 'name' and 'email' attributes
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
        self, pr: PullRequest, include_diffs: bool = False, max_tokens: int = 8000
    ) -> PullRequestContent:
        """
        Generates a structured context string from a pull request.

        Args:
            pr: The PullRequest object to generate context from
            include_diffs: If True, includes actual code diffs (can be large). Default False.
            max_tokens: Maximum tokens for the context string
        """
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
        )

        # 1. Header: Intent & Impact
        clean_description = re.sub(
            r"<!--.*?-->", "", pr.body or "", flags=re.DOTALL
        ).strip()

        pr_content.body = clean_description

        header = (
            f"PR_INTENT: {pr.title}\n"
            f"DESCRIPTION: {clean_description[:1000]}\n"
            f"LABELS: {', '.join([label.name for label in pr.labels])}\n"
        )

        # 2. Body: File Changes Summary
        files = pr.get_files()

        body = "\nFILE_CHANGES:\n"
        for f in files:
            status = f.status  # 'added', 'removed', 'modified', 'renamed'
            body += f"- [{status.upper()}] {f.filename}\n"

        body += "\nCOMMITS:\n"
        for commit in pr.get_commits():
            commit_message = commit.commit.message
            len_message = len(re.findall(r"\w+", commit_message))
            if len_message > 5:
                body += f"- {commit_message.splitlines()[0]}\n"

        pr_content.context = header + body
        return pr_content

    def get_org_closed_prs_context_by_author(
        self, author: GitHubUser, max_prs: int = 100
    ) -> list[PullRequestContent]:
        """
        Retrieves closed pull requests from all repositories in the organization.
        Note: This iterates through all org repositories, which can be slow for large orgs.
        """
        gh = self.get_github_client()
        org = gh.get_organization(self.organization_name)
        prs_content_list: list[PullRequestContent] = []

        # Iterate through all repositories in the organization
        for repo in org.get_repos():
            try:
                # Get closed PRs from each repository
                repo_prs = repo.get_pulls(
                    state="closed", sort="updated", direction="desc"
                )

                for pr in repo_prs:
                    # Filter by author (pr.user is the PR creator)
                    if not pr.user:
                        logger.debug(f"Skipping PR #{pr.number} - no user")
                        continue

                    pr_author_id = pr.user.id
                    logger.debug(
                        f"Checking PR #{pr.number} in {repo.name}: author={pr_author_id}, looking_for={author.login}, match={pr_author_id == author.id}"
                    )

                    if pr_author_id != author.id:
                        continue

                    if len(prs_content_list) >= max_prs:
                        return prs_content_list

                    prs_content_list.append(self.generate_pr_context(pr))
            except Exception as e:
                # Skip repositories where we don't have access or encounter errors
                logger.warning("Skipping repo %s: %s", repo.name, str(e))
                continue

        return prs_content_list

    def get_org_closed_prs_context_all_authors(
        self, max_prs_per_author: int = 100
    ) -> dict[str, list[PullRequestContent]]:
        """
        Retrieves closed pull requests grouped by author for all org members.
        This method retrieves all closed pull requests from all repositories in one go,
        grouping them by author to improve performance.
        """
        gh = self.get_github_client()
        org = gh.get_organization(self.organization_name)
        authors_prs: dict[str, list[PullRequestContent]] = {}

        # Retrieve all closed PRs from all repositories
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

        # Limit the number of PRs per author
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
