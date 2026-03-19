import sys
import os
from sqlmodel import Session

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.db.session import engine
from app.api.dashboard.dashboard_service import get_dashboard_data

def verify():
    with Session(engine) as session:
        try:
            data = get_dashboard_data(session)
            print("Dashboard data retrieved successfully!")
            print(f"Total Members: {data.team_members.total}")
            print(f"New this month: {data.team_members.new_this_month}")
        except Exception as e:
            print(f"Error retrieving dashboard data: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)

if __name__ == "__main__":
    verify()
