import uuid
from datetime import datetime
from typing import Any, cast

from fastapi import HTTPException
from thefuzz import fuzz

from app.api.integrations.GitHub.github_schema import GitHubUser
from app.api.integrations.GitHub.github_service import GithubIntegrationService
from app.api.integrations.Jira.jira_schema import JiraUser
from app.api.integrations.Jira.jira_service import JiraIntegrationService
from app.api.profiles.profile_model import ResourceProfile
from app.api.profiles.profile_schema import (
    GitHubConnectionRequest,
    JiraConnectionRequest,
    ProfileMatchResponse,
    UpdateProfileRequest,
)
from app.utils.deps import SessionDep


class ProfileService:
    def __init__(self, db: SessionDep):
        self.db = db

    def _get_profile_by_user_id(self, user_id: uuid.UUID) -> ResourceProfile | None:
        return (
            self.db.query(ResourceProfile)
            .filter(cast(Any, ResourceProfile.user_id == user_id))
            .first()
        )

    def get_profile_by_user_id(self, user_id: uuid.UUID) -> ResourceProfile | None:
        return self._get_profile_by_user_id(user_id)

    def get_or_create_profile(self, user_id: uuid.UUID) -> ResourceProfile:
        profile = self._get_profile_by_user_id(user_id)
        if not profile:
            profile = ResourceProfile(user_id=user_id)
            self.db.add(profile)
            self.db.commit()
            self.db.refresh(profile)
        return profile

    def _update_jira_connection(
        self,
        profile: ResourceProfile,
        target_user_id: uuid.UUID,
        request: JiraConnectionRequest,
    ) -> None:
        existing = (
            self.db.query(ResourceProfile)
            .filter(
                cast(Any, ResourceProfile.jira_account_id == request.jira_account_id)
            )
            .filter(cast(Any, ResourceProfile.user_id != target_user_id))
            .first()
        )
        if existing:
            raise HTTPException(
                status_code=400,
                detail="Jira account already connected to another user",
            )

        profile.jira_account_id = request.jira_account_id
        profile.jira_display_name = request.jira_display_name
        profile.jira_email = request.jira_email
        profile.jira_avatar_url = request.jira_avatar_url
        profile.jira_connected_at = datetime.utcnow()

    def _update_github_connection(
        self,
        profile: ResourceProfile,
        target_user_id: uuid.UUID,
        request: GitHubConnectionRequest,
    ) -> None:
        if request.github_login:
            existing = (
                self.db.query(ResourceProfile)
                .filter(cast(Any, ResourceProfile.github_login == request.github_login))
                .filter(cast(Any, ResourceProfile.user_id != target_user_id))
                .first()
            )
            if existing:
                raise HTTPException(
                    status_code=400,
                    detail="GitHub account already connected to another user",
                )

        profile.github_id = request.github_id
        profile.github_login = request.github_login
        profile.github_display_name = request.github_display_name
        profile.github_email = request.github_email
        profile.github_avatar_url = request.github_avatar_url
        profile.github_connected_at = datetime.utcnow()

    def _apply_profile_updates(
        self,
        profile: ResourceProfile,
        request: UpdateProfileRequest,
        *,
        allow_position_update: bool,
    ) -> None:
        if request.burnout_level is not None:
            profile.burnout_level = request.burnout_level

        if request.position_id is not None:
            if not allow_position_update:
                raise HTTPException(
                    status_code=403,
                    detail="Moderator or admin access required",
                )

            from app.api.profiles.position_model import JobPosition

            position = self.db.get(JobPosition, request.position_id)
            if not position:
                raise HTTPException(
                    status_code=400,
                    detail="Invalid position_id: Job position not found",
                )
            profile.position_id = request.position_id

        if request.jira_account_id is not None:
            self._update_jira_connection(
                profile,
                profile.user_id,
                JiraConnectionRequest(
                    jira_account_id=request.jira_account_id,
                    jira_display_name=request.jira_display_name,
                    jira_email=request.jira_email,
                    jira_avatar_url=request.jira_avatar_url,
                ),
            )
        elif (
            request.jira_display_name is not None
            or request.jira_email is not None
            or request.jira_avatar_url is not None
        ):
            if not profile.jira_account_id:
                raise HTTPException(
                    status_code=400,
                    detail="jira_account_id is required to update Jira details",
                )
            if request.jira_display_name is not None:
                profile.jira_display_name = request.jira_display_name
            if request.jira_email is not None:
                profile.jira_email = request.jira_email
            if request.jira_avatar_url is not None:
                profile.jira_avatar_url = request.jira_avatar_url

        if request.github_login is not None:
            self._update_github_connection(
                profile,
                profile.user_id,
                GitHubConnectionRequest(
                    github_id=request.github_id,
                    github_login=request.github_login,
                    github_display_name=request.github_display_name,
                    github_email=request.github_email,
                    github_avatar_url=request.github_avatar_url,
                ),
            )
        elif (
            request.github_id is not None
            or request.github_display_name is not None
            or request.github_email is not None
            or request.github_avatar_url is not None
        ):
            if not profile.github_login:
                raise HTTPException(
                    status_code=400,
                    detail="github_login is required to update GitHub details",
                )
            if request.github_id is not None:
                profile.github_id = request.github_id
            if request.github_display_name is not None:
                profile.github_display_name = request.github_display_name
            if request.github_email is not None:
                profile.github_email = request.github_email
            if request.github_avatar_url is not None:
                profile.github_avatar_url = request.github_avatar_url

    def update_profile_for_user(
        self,
        user_id: uuid.UUID,
        request: UpdateProfileRequest,
        *,
        allow_position_update: bool,
        create_if_missing: bool = True,
    ) -> ResourceProfile:
        profile = self._get_profile_by_user_id(user_id)
        if not profile:
            if not create_if_missing:
                raise HTTPException(status_code=404, detail="Profile not found")
            profile = ResourceProfile(user_id=user_id)
            self.db.add(profile)
            self.db.commit()
            self.db.refresh(profile)

        self._apply_profile_updates(
            profile,
            request,
            allow_position_update=allow_position_update,
        )

        profile.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(profile)
        return profile

    def update_position_for_user(
        self, user_id: uuid.UUID, position_id: int | None
    ) -> ResourceProfile:
        if position_id is not None:
            from app.api.profiles.position_model import JobPosition

            position = self.db.get(JobPosition, position_id)
            if not position:
                raise HTTPException(
                    status_code=400,
                    detail="Invalid position_id: Job position not found",
                )

        profile = self.get_or_create_profile(user_id)
        if position_id is not None:
            profile.position_id = position_id

        profile.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(profile)
        return profile

    def connect_jira_for_user(
        self, user_id: uuid.UUID, request: JiraConnectionRequest
    ) -> ResourceProfile:
        profile = self.get_or_create_profile(user_id)
        self._update_jira_connection(profile, user_id, request)
        profile.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(profile)
        return profile

    def connect_github_for_user(
        self, user_id: uuid.UUID, request: GitHubConnectionRequest
    ) -> ResourceProfile:
        profile = self.get_or_create_profile(user_id)
        self._update_github_connection(profile, user_id, request)
        profile.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(profile)
        return profile

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
