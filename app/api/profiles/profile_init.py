"""Initialize test profiles on server startup."""

import logging
import uuid
from datetime import datetime
from typing import Any, TypedDict, cast

from sqlalchemy.orm import Session

from app.api.profiles.profile_model import ResourceProfile
from app.api.user.user_model import User
from app.core.security import get_password_hash

logger = logging.getLogger(__name__)

# Default password for test users (should be changed in production)
DEFAULT_TEST_PASSWORD = "TestUser123!"


class TeamMember(TypedDict):
    """Type definition for team member data."""

    name: str
    email: str
    jira_account_id: str
    jira_display_name: str
    github_login: str | None
    github_id: int | None


# Team member data with correct Jira and GitHub mappings
TEAM_MEMBERS: list[TeamMember] = [
    {
        "name": "Senuja Jayasekara",
        "email": "senuja.20234041@iit.ac.lk",
        "jira_account_id": "712020:89f1d656-bd54-43fb-bd95-4e7801a9cd26",
        "jira_display_name": "Senuja Jayasekara",
        "github_login": "Senuja0x",
        "github_id": 137871237,
    },
    {
        "name": "Supuni Liyanage",
        "email": "supuni.20234044@iit.ac.lk",
        "jira_account_id": "712020:061ce5a3-9da4-4ea6-9277-b49f2e308440",
        "jira_display_name": "Supuni Liyanage",
        "github_login": None,
        "github_id": None,
    },
    {
        "name": "Diluka Lahiru",
        "email": "diluka.20234038@iit.ac.lk",
        "jira_account_id": "712020:6f546f83-8a44-4f7a-aa56-cc239c354676",
        "jira_display_name": "Diluka Lahiru",
        "github_login": "dilukalahiru",
        "github_id": 106172155,
    },
    {
        "name": "Lakshan Hirusha",
        "email": "hirusha.20234077@iit.ac.lk",
        "jira_account_id": "712020:2216be6d-7a28-402d-886c-ea2dad9e8114",
        "jira_display_name": "hirusha.20234077",
        "github_login": "LakshanHirusha",
        "github_id": 177405293,
    },
    {
        "name": "Avishka Gunathilaka",
        "email": "avishka.20234058@iit.ac.lk",
        "jira_account_id": "712020:962160c5-131c-42da-8cfd-586b06c9e50d",
        "jira_display_name": "Avishka Gunathilaka",
        "github_login": None,
        "github_id": None,
    },
    {
        "name": "Nirodha Adhikari",
        "email": "nirodha.20234073@iit.ac.lk",
        "jira_account_id": "712020:4ce64f91-e192-4723-8401-80125362a9c3",
        "jira_display_name": "Nirodha Adhikari",
        "github_login": "nirodha-adhikari",
        "github_id": 103508455,
    },
]


def create_or_get_user(
    db: Session, email: str, full_name: str, update_password: bool = True
) -> User:
    """Create a user if not exists, or return existing one."""
    existing = db.query(User).filter(cast(Any, User.email == email)).first()
    if existing:
        # Update password if it's a placeholder
        if update_password and existing.hashed_password.startswith("$2b$12$placeholder"):
            existing.hashed_password = get_password_hash(DEFAULT_TEST_PASSWORD)
            existing.full_name = full_name
            db.commit()
            db.refresh(existing)
            logger.info(f"Updated password for user: {email}")
        return existing

    user = User(
        id=uuid.uuid4(),
        email=email,
        full_name=full_name,
        hashed_password=get_password_hash(DEFAULT_TEST_PASSWORD),
        is_active=True,
        is_superuser=False,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    logger.info(f"Created user: {email}")
    return user


def init_test_profiles(db: Session) -> None:
    """
    Initialize team member profiles with correct Jira and GitHub mappings.
    """
    logger.info("Initializing team member profiles...")

    profiles_created = 0
    profiles_updated = 0

    for member in TEAM_MEMBERS:
        try:
            # Check if profile already exists for this Jira account
            existing_profile: ResourceProfile | None = None
            if member["jira_account_id"]:
                existing_profile = (
                    db.query(ResourceProfile)
                    .filter(
                        cast(
                            Any,
                            ResourceProfile.jira_account_id == member["jira_account_id"],
                        )
                    )
                    .first()
                )

            profile: ResourceProfile
            if existing_profile:
                # Update existing profile with correct data
                profile = existing_profile

                # Get the user
                user = (
                    db.query(User)
                    .filter(cast(Any, User.id == existing_profile.user_id))
                    .first()
                )
                if user and user.email != member["email"]:
                    # Update user email if different
                    user.email = member["email"]
                    user.full_name = member["name"]

                profiles_updated += 1
            else:
                # Create new user and profile
                user = create_or_get_user(db, member["email"], member["name"])

                # Check if profile exists for this user
                existing_user_profile = (
                    db.query(ResourceProfile)
                    .filter(cast(Any, ResourceProfile.user_id == user.id))
                    .first()
                )
                if not existing_user_profile:
                    profile = ResourceProfile(user_id=user.id)
                    db.add(profile)
                    profiles_created += 1
                else:
                    profile = existing_user_profile
                    profiles_updated += 1

            # Update Jira fields
            profile.jira_account_id = member["jira_account_id"]
            profile.jira_display_name = member["jira_display_name"]
            profile.jira_email = member["email"]
            profile.jira_connected_at = profile.jira_connected_at or datetime.utcnow()

            # Update GitHub fields
            if member["github_login"]:
                profile.github_login = member["github_login"]
                profile.github_id = member["github_id"]
                profile.github_display_name = member["github_login"]
                profile.github_connected_at = (
                    profile.github_connected_at or datetime.utcnow()
                )
            else:
                # Clear GitHub fields if not linked
                profile.github_login = None
                profile.github_id = None
                profile.github_display_name = None
                profile.github_connected_at = None

            profile.updated_at = datetime.utcnow()
            db.commit()

            status = "✅ Fully Linked" if member["github_login"] else "⚠️ GitHub Missing"
            logger.info(
                f"Profile: {member['name']} - Jira: {member['jira_display_name']}, "
                f"GitHub: {member['github_login'] or 'None'} [{status}]"
            )

        except Exception as e:
            logger.error(f"Error creating profile for {member['name']}: {str(e)}")
            db.rollback()

    logger.info(
        f"Profile initialization complete. "
        f"Created: {profiles_created}, Updated: {profiles_updated}"
    )
