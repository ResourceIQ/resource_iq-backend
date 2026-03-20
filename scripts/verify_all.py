import os
import sys

from sqlmodel import Session, select

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.api.dashboard.dashboard_service import get_dashboard_data
from app.api.profiles.profile_model import ResourceProfile
from app.api.score.score_service import ScoreService
from app.api.user.user_model import User
from app.api.user.user_service import get_user_by_email
from app.db.session import engine


def verify_all():
    print("--- Starting Backend Verification ---")
    with Session(engine) as session:
        # 1. Verify Users
        try:
            users = session.exec(select(User)).all()
            print(f"[OK] Users table accessible. Count: {len(users)}")
            if users:
                test_email = users[0].email
                user = get_user_by_email(session=session, email=test_email)
                if user:
                    print(
                        f"[OK] UserService: Successfully fetched user by email: {test_email}"
                    )
                else:
                    print(
                        f"[ERROR] UserService: Failed to fetch user by email: {test_email}"
                    )
        except Exception as e:
            print(f"[ERROR] Users: {e}")

        # 2. Verify Resource Profiles
        try:
            profiles = session.exec(select(ResourceProfile)).all()
            print(f"[OK] ResourceProfile table accessible. Count: {len(profiles)}")
            if profiles:
                # Check if 'position' field (resolved earlier) is working
                pos = profiles[0].position
                print(
                    f"[OK] ResourceProfile: 'position' field accessible (value: {pos})"
                )
        except Exception as e:
            print(f"[ERROR] ResourceProfile: {e}")

        # 3. Verify Dashboard Service
        try:
            dash_data = get_dashboard_data(session)
            print("[OK] DashboardService: get_dashboard_data successful.")
        except Exception as e:
            print(f"[ERROR] DashboardService: {e}")

        # 4. Verify Score Service
        try:
            score_service = ScoreService(session)
            positions = score_service.get_job_positions()
            print(
                f"[OK] ScoreService: get_job_positions successful. Count: {len(positions)}"
            )
        except Exception as e:
            print(f"[ERROR] ScoreService: {e}")

    print("--- Verification Finished ---")


if __name__ == "__main__":
    verify_all()
