from thefuzz import fuzz  # type: ignore[import-untyped]

from app.api.integrations.GitHub.github_schema import GitHubUser
from app.api.integrations.GitHub.github_service import GithubIntegrationService
from app.api.integrations.Jira.jira_schema import JiraUser
from app.api.integrations.Jira.jira_service import JiraIntegrationService
from app.api.profiles.profile_schema import ProfileMatchResponse
from app.utils.deps import SessionDep


class ProfileService:
    def __init__(self, db: SessionDep):
        self.db = db

    def match_jira_github(self, threshold: float = 75) -> list[ProfileMatchResponse]:
        if not 0 <= threshold <= 100:
            raise ValueError(
                f"threshold must be between 0 and 100 inclusive, got {threshold}"
            )
        unified_profiles: list[ProfileMatchResponse] = []
        github_service = GithubIntegrationService(self.db)
        jira_service = JiraIntegrationService(self.db)

        # Fetch typed models directly from integrations
        github_users = github_service.get_all_org_members()
        jira_users = jira_service.get_all_jira_users()

        for gh_user in github_users:
            match_found, best_score = self._get_best_match(gh_user, jira_users)

            if best_score >= threshold:
                unified_profiles.append(
                    ProfileMatchResponse(
                        github_account=gh_user,
                        jira_account=match_found,
                        match_score=best_score,
                    )
                )

        return unified_profiles

    def _get_best_match(
        self, gh_account: GitHubUser, jira_users: list[JiraUser]
    ) -> tuple[JiraUser | None, float]:
        best_match = None
        highest_score = 0

        gh_email = gh_account.email.lower().strip() if gh_account.email else None
        gh_name = (gh_account.name or "").lower().strip()
        gh_login = (gh_account.login or "").lower().strip()

        for jr in jira_users:
            jr_email = (jr.email_address or "").lower().strip()
            jr_name = (jr.display_name or "").lower().strip()

            if gh_email and jr_email and gh_email == jr_email:
                return jr, 100.0  # Early exit for perfect match

            name_score = 0
            if gh_name and jr_name:
                name_score = fuzz.token_set_ratio(gh_name, jr_name) * 0.5

            login_score = 0
            if gh_login and jr_name:
                if len(gh_login) > 2:
                    login_score = fuzz.partial_ratio(gh_login, jr_name) * 0.5
                else:
                    login_score = fuzz.partial_ratio(gh_login, jr_name) * 0.2

            current_points = name_score + login_score

            if current_points > highest_score:
                highest_score = current_points
                best_match = jr

        return best_match, round(highest_score, 2)
