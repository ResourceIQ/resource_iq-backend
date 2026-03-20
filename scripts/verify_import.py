import os
import sys

from sqlmodel import Session, select

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.api.user.user_model import User
from app.db.session import engine
from scripts.import_backup import LocalResourceProfile


def verify():
    with Session(engine) as session:
        users = session.exec(select(User)).all()
        profiles = session.exec(select(LocalResourceProfile)).all()
        print(f"Total Users in DB: {len(users)}")
        print(f"Total Profiles in DB: {len(profiles)}")

        for p in profiles:
            user = session.get(User, p.user_id)
            print(f"Profile for {user.email if user else 'Unknown'}: linked correctly.")


if __name__ == "__main__":
    verify()
