# app/services/integration_service.py
import re
from typing import Any

from github import Github, GithubIntegration
from github.PullRequest import PullRequest

from app.api.integrations.GitHub.github_model import GithubOrgIntBaseModel
from app.core.config import settings
from app.db.session import Session


class GithubIntegrationService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.credentials: GithubOrgIntBaseModel | None = db.query(
            GithubOrgIntBaseModel
        ).first()

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

    def get_all_org_members(self) -> list[dict[str, Any]]:
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
                {
                    "login": member.login,  # GitHub Username
                    "name": member.name,  # Real Name (if public)
                    "email": member.email,  # Public Email
                    "github_id": member.id,
                }
            )

        return members_list

    def generate_pr_context(
        self, pr: PullRequest, include_diffs: bool = False, max_tokens: int = 8000
    ) -> str:
        """
        Generates a structured context string from a pull request.

        Args:
            pr: The PullRequest object to generate context from
            include_diffs: If True, includes actual code diffs (can be large). Default False.
            max_tokens: Maximum tokens for the context string
        """
        # 1. Header: Intent & Impact
        clean_description = re.sub(
            r"<!--.*?-->", "", pr.body or "", flags=re.DOTALL
        ).strip()

        header = (
            f"PR_INTENT: {pr.title}\n"
            f"DESCRIPTION: {clean_description[:1000]}\n"
            f"STATE: {pr.state}\n"
            f"LABELS: {', '.join([l.name for l in pr.labels])}\n"
            f"COMMITS: {pr.commits}\n"
            f"CHANGED_FILES: {pr.changed_files}\n"
            f"ADDITIONS: +{pr.additions}\n"
            f"DELETIONS: -{pr.deletions}\n"
        )

        # 2. Body: File Changes Summary
        files = pr.get_files()
        file_list = [f.filename for f in files]

        body = "\nFILE_CHANGES:\n"
        for f in files:
            status = f.status  # 'added', 'removed', 'modified', 'renamed'
            body += (
                f"- [{status.upper()}] {f.filename} (+{f.additions}/-{f.deletions})\n"
            )

        # 3. Optional: Code Diffs (only if explicitly requested)
        if include_diffs:
            footer = "\nCODE_DIFFS:\n"
            diff_content = ""
            forbidden_extensions = (".json", ".lock", ".yaml", ".md", ".txt")

            for f in files:
                if f.filename.endswith(forbidden_extensions) or not f.patch:
                    continue

                clean_patch = re.sub(r"@@.*?@@", "", f.patch)
                file_diff = f"FILE: {f.filename}\n{clean_patch}\n"

                if len(header + body + footer + diff_content + file_diff) > max_tokens:
                    diff_content += "\n[TRUNCATED: PR TOO LARGE]"
                    break

                diff_content += file_diff

            return header + body + footer + diff_content

        return header + body

    def get_org_closed_prs_context(self, max_prs: int = 5000) -> list[str]:
        """
        Retrieves closed pull requests from all repositories in the organization.
        Note: This iterates through all org repositories, which can be slow for large orgs.
        """
        gh = self.get_github_client()
        org = gh.get_organization(self.organization_name)
        prs_content_list: list[str] = []

        # Iterate through all repositories in the organization
        for repo in org.get_repos():
            try:
                # Get closed PRs from each repository
                repo_prs = repo.get_pulls(
                    state="closed", sort="updated", direction="desc"
                )

                for pr in repo_prs:
                    if len(prs_content_list) >= max_prs:
                        return prs_content_list
                    prs_content_list.append(self.generate_pr_context(pr))
            except Exception as e:
                # Skip repositories where we don't have access or encounter errors
                print(f"Skipping repo {repo.name}: {str(e)}")
                continue

        return prs_content_list
