import sys
from datetime import datetime, timedelta
from sqlmodel import Session, select

# Add project root to sys.path
sys.path.append('/Users/dilukalahiru/Documents/Porjects/resource_iq-backend')

from app.db.session import engine
from app.api.profiles.profile_model import ResourceProfile

def seed_data():
    with Session(engine) as session:
        # Get all profiles
        profiles = session.exec(select(ResourceProfile)).all()
        
        if not profiles:
            print("No profiles found to update.")
            return
            
        print(f"Updating {len(profiles)} profiles with creation dates...")
        
        # Set most profiles to January 2026
        old_date = datetime(2026, 1, 15)
        for i, profile in enumerate(profiles):
            if i < len(profiles) - 2:
                profile.created_at = old_date
            else:
                # Set the last 2 profiles to March 2026 (this month)
                profile.created_at = datetime.utcnow()
                print(f"Profile for user {profile.user_id} set to 'created this month'")
                
        session.commit()
        print("Data seeded successfully! Dashboard should now show '+2' for team members.")

if __name__ == "__main__":
    seed_data()
