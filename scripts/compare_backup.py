import json
import uuid
import sys
import os
from datetime import datetime
from sqlmodel import Session, select

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.db.session import engine
from app.api.user.user_model import User
from app.api.profiles.profile_model import ResourceProfile

BACKUP_FILE = "/Users/dilukalahiru/Downloads/resourceiq_backup_20260318_191457.json"

def parse_datetime(dt_str: str | None) -> str | None:
    if not dt_str:
        return None
    # Normalize isoformat for comparison
    if "+" in dt_str:
        dt_str = dt_str.split("+")[0]
    try:
        dt = datetime.fromisoformat(dt_str)
        return dt.isoformat()
    except ValueError:
        return dt_str

def compare():
    with open(BACKUP_FILE, "r") as f:
        backup_data = json.load(f)

    with Session(engine) as session:
        # Compare Users
        print("--- Comparing Users ---")
        for u_json in backup_data.get("users", []):
            email = u_json["email"]
            db_user = session.exec(select(User).where(User.email == email)).first()
            if not db_user:
                print(f"[MISSING] User {email} not in DB")
                continue
            
            mismatches = []
            if str(db_user.id) != u_json["id"]: mismatches.append(f"id: {db_user.id} != {u_json['id']}")
            if db_user.hashed_password != u_json["hashed_password"]: mismatches.append("hashed_password mismatch")
            if db_user.is_active != u_json["is_active"]: mismatches.append("is_active mismatch")
            if db_user.is_superuser != u_json["is_superuser"]: mismatches.append("is_superuser mismatch")
            if db_user.full_name != u_json["full_name"]: mismatches.append(f"full_name: {db_user.full_name} != {u_json['full_name']}")
            if db_user.role != u_json["role"]: mismatches.append(f"role: {db_user.role} != {u_json['role']}")
            
            if mismatches:
                print(f"[MISMATCH] User {email}: {', '.join(mismatches)}")
            else:
                print(f"[OK] User {email} matches exactly.")

        # Compare Resource Profiles
        print("\n--- Comparing Resource Profiles ---")
        for p_json in backup_data.get("resource_profiles", []):
            email = p_json["user_email"]
            db_user = session.exec(select(User).where(User.email == email)).first()
            if not db_user:
                print(f"[SKIP] Profile for {email}: User not in DB")
                continue
            
            db_profile = session.exec(select(ResourceProfile).where(ResourceProfile.user_id == db_user.id)).first()
            if not db_profile:
                print(f"[MISSING] Profile for {email} not in DB")
                continue
            
            mismatches = []
            # Check fields
            if db_profile.phone_number != p_json.get("phone_number"): mismatches.append("phone_number")
            if db_profile.address != p_json.get("address"): mismatches.append("address")
            
            # Note: we renamed position_id to position in DB to match model
            if str(db_profile.position) != str(p_json.get("position_id")): 
                # Handle null vs None string
                if not (db_profile.position is None and p_json.get("position_id") is None):
                    mismatches.append(f"position: {db_profile.position} != {p_json.get('position_id')}")
            
            if db_profile.jira_account_id != p_json.get("jira_account_id"): mismatches.append("jira_account_id")
            if db_profile.jira_display_name != p_json.get("jira_display_name"): mismatches.append("jira_display_name")
            
            # Datetime comparison (normalized)
            db_jira_conn = db_profile.jira_connected_at.isoformat() if db_profile.jira_connected_at else None
            json_jira_conn = parse_datetime(p_json.get("jira_connected_at"))
            if db_jira_conn != json_jira_conn: mismatches.append(f"jira_connected_at: {db_jira_conn} != {json_jira_conn}")

            if db_profile.github_id != p_json.get("github_id"): mismatches.append("github_id")
            if db_profile.github_login != p_json.get("github_login"): mismatches.append("github_login")
            
            db_gh_conn = db_profile.github_connected_at.isoformat() if db_profile.github_connected_at else None
            json_gh_conn = parse_datetime(p_json.get("github_connected_at"))
            if db_gh_conn != json_gh_conn: mismatches.append(f"github_connected_at: {db_gh_conn} != {json_gh_conn}")

            if db_profile.skills != p_json.get("skills"): mismatches.append("skills")
            if db_profile.domains != p_json.get("domains"): mismatches.append("domains")
            if db_profile.jira_workload != p_json.get("jira_workload"): mismatches.append("jira_workload")
            if db_profile.github_workload != p_json.get("github_workload"): mismatches.append("github_workload")
            if db_profile.total_workload != p_json.get("total_workload"): mismatches.append("total_workload")

            if mismatches:
                print(f"[MISMATCH] Profile for {email}: {', '.join(mismatches)}")
            else:
                print(f"[OK] Profile for {email} matches exactly.")

if __name__ == "__main__":
    compare()
