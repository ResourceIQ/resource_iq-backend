import os
import sys

from sqlalchemy import text

from app.db.session import engine

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def fix_schema():
    print("Fixing resource_profiles schema...")
    with engine.connect() as connection:
        with connection.begin():
            # Drop the foreign key constraint first
            try:
                connection.execute(
                    text(
                        "ALTER TABLE resource_profiles DROP CONSTRAINT IF EXISTS resource_profiles_position_id_fkey"
                    )
                )
                print("Dropped constraint resource_profiles_position_id_fkey.")
            except Exception as e:
                print(f"Warning: Could not drop constraint: {e}")

            # Rename position_id to position
            connection.execute(
                text(
                    "ALTER TABLE resource_profiles RENAME COLUMN position_id TO position"
                )
            )
            # Change type from integer to varchar
            connection.execute(
                text(
                    "ALTER TABLE resource_profiles ALTER COLUMN position TYPE VARCHAR USING position::VARCHAR"
                )
            )
            print(
                "Successfully renamed position_id to position and changed type to VARCHAR."
            )


if __name__ == "__main__":
    try:
        fix_schema()
    except Exception as e:
        print(f"Error fixing schema: {e}")
        sys.exit(1)
