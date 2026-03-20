import sys

from sqlalchemy import text

from app.db.session import engine

# Add project root to path
backend_root = "/Users/dilukalahiru/Documents/Porjects/resource_iq-backend"
if backend_root not in sys.path:
    sys.path.append(backend_root)

# Mapping: Position ID -> List of emails
MAPPING = {
    13: [  # Senior Developer
        "diluka.20234038@iit.ac.lk",
        "senujajayasekara@gmail.com",
        "hirusha.git@gmail.com",
    ],
    14: [  # Project Manager
        "supuni.20234044@iit.ac.lk"
    ],
    15: [  # QA Engineer
        "nirodha.20234073@iit.ac.lk",
        "chasithgunathilaka@gmail.com",
    ],
}


def update_positions():
    print("Updating resource_profiles job positions...")
    with engine.connect() as conn:
        with conn.begin():
            for pos_id, emails in MAPPING.items():
                for email in emails:
                    print(f"  Assigning Position ID {pos_id} to {email}...")
                    # Update repo
                    conn.execute(
                        text("""
                        UPDATE resource_profiles 
                        SET position_id = :pos_id, updated_at = NOW()
                        WHERE user_id = (SELECT id FROM "user" WHERE email = :email)
                    """),
                        {"pos_id": pos_id, "email": email},
                    )
    print("Update completed successfully!")


if __name__ == "__main__":
    update_positions()
