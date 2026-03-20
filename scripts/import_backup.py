import json
import os
import sys
import uuid
from datetime import datetime

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlmodel import Field, Session, SQLModel, select

from app.api.user.user_model import Role, User
from app.db.session import engine


# Local ResourceProfile model that matches the ACTUAL database schema
class LocalResourceProfile(SQLModel, table=True):
    __tablename__ = "resource_profiles"
    id: int | None = Field(default=None, primary_key=True)
    user_id: uuid.UUID = Field(foreign_key="user.id", unique=True, index=True)
    phone_number: str | None = None
    address: str | None = None
    position: str | None = None  # Matches code model
    jira_account_id: str | None = None
    jira_display_name: str | None = None
    jira_email: str | None = None
    jira_avatar_url: str | None = None
    jira_connected_at: datetime | None = None
    github_id: int | None = None
    github_login: str | None = None
    github_display_name: str | None = None
    github_email: str | None = None
    github_avatar_url: str | None = None
    github_connected_at: datetime | None = None
    skills: str | None = None
    domains: str | None = None
    jira_workload: int = 0
    github_workload: int = 0
    total_workload: int = 0
    workload_updated_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


BACKUP_FILE = "/Users/dilukalahiru/Downloads/resourceiq_backup_20260318_191457.json"


def parse_datetime(dt_str: str | None) -> datetime | None:
    if not dt_str:
        return None
    try:
        # Handle formats like "2026-03-18T19:15:02.929929+00:00" or "2026-03-18T19:04:47.939666"
        if "+" in dt_str:
            dt_str = dt_str.split("+")[0]
        return datetime.fromisoformat(dt_str)
    except ValueError:
        return None


def import_data():
    if not os.path.exists(BACKUP_FILE):
        print(f"Error: Backup file not found at {BACKUP_FILE}")
        return

    print(f"Reading backup from {BACKUP_FILE}...")
    with open(BACKUP_FILE) as f:
        data = json.load(f)

    # Note: Using create_all might not do anything if table exists,
    # but it won't hurt. SQLModel knows about LocalResourceProfile now.
    print("Ensuring tables exist...")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        # Import Users
        print("Importing users...")
        users_map = {}  # email -> User object
        for u_data in data.get("users", []):
            email = u_data["email"]
            db_user = session.exec(select(User).where(User.email == email)).first()
            if not db_user:
                print(f"  Adding user: {email}")
                db_user = User(
                    id=uuid.UUID(u_data["id"]),
                    email=email,
                    hashed_password=u_data["hashed_password"],
                    is_active=u_data["is_active"],
                    is_superuser=u_data["is_superuser"],
                    full_name=u_data["full_name"],
                    role=Role(u_data["role"]),
                )
                session.add(db_user)
            else:
                print(f"  User already exists: {email}")
            users_map[email] = db_user

        session.commit()  # Commit users first to ensure FKs work

        # Import Resource Profiles
        print("Importing resource profiles...")
        for p_data in data.get("resource_profiles", []):
            email = p_data["user_email"]
            user = users_map.get(email)
            if not user:
                user = session.exec(select(User).where(User.email == email)).first()

            if not user:
                print(f"  Skipping profile for {email}: User not found in database")
                continue

            # Using LocalResourceProfile for the query as well
            db_profile = session.exec(
                select(LocalResourceProfile).where(
                    LocalResourceProfile.user_id == user.id
                )
            ).first()
            if not db_profile:
                print(f"  Adding profile for user: {email}")
                db_profile = LocalResourceProfile(
                    user_id=user.id,
                    phone_number=p_data.get("phone_number"),
                    address=p_data.get("address"),
                    position_id=p_data.get(
                        "position_id"
                    ),  # Uses position_id as in DB and JSON
                    jira_account_id=p_data.get("jira_account_id"),
                    jira_display_name=p_data.get("jira_display_name"),
                    jira_email=p_data.get("jira_email"),
                    jira_avatar_url=p_data.get("jira_avatar_url"),
                    jira_connected_at=parse_datetime(p_data.get("jira_connected_at")),
                    github_id=p_data.get("github_id"),
                    github_login=p_data.get("github_login"),
                    github_display_name=p_data.get("github_display_name"),
                    github_email=p_data.get("github_email"),
                    github_avatar_url=p_data.get("github_avatar_url"),
                    github_connected_at=parse_datetime(
                        p_data.get("github_connected_at")
                    ),
                    skills=p_data.get("skills"),
                    domains=p_data.get("domains"),
                    jira_workload=p_data.get("jira_workload", 0),
                    github_workload=p_data.get("github_workload", 0),
                    total_workload=p_data.get("total_workload", 0),
                    workload_updated_at=parse_datetime(
                        p_data.get("workload_updated_at")
                    ),
                )
                session.add(db_profile)
            else:
                print(f"  Profile already exists for user: {email}")

        session.commit()
    print("Import completed successfully!")


if __name__ == "__main__":
    import_data()
