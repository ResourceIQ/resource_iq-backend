# Import and re-export utility functions from the parent-level utils.py
import importlib.util
import sys
from pathlib import Path

# Add parent directory to path to import utils.py file
parent_path = str(Path(__file__).parent.parent)
if parent_path not in sys.path:
    sys.path.insert(0, parent_path)

# Import from the utils module at app level (the file, not this folder)
spec = importlib.util.spec_from_file_location(
    "email_utils", Path(__file__).parent.parent / "utils.py"
)
if spec is None or spec.loader is None:
    raise ImportError("Failed to load email_utils module")
email_utils = importlib.util.module_from_spec(spec)
spec.loader.exec_module(email_utils)

# Re-export the functions
generate_password_reset_token = email_utils.generate_password_reset_token
generate_reset_password_email = email_utils.generate_reset_password_email
send_email = email_utils.send_email
verify_password_reset_token = email_utils.verify_password_reset_token
generate_new_account_email = email_utils.generate_new_account_email
render_email_template = email_utils.render_email_template
generate_test_email = email_utils.generate_test_email

__all__ = [
    "generate_password_reset_token",
    "generate_reset_password_email",
    "send_email",
    "verify_password_reset_token",
    "generate_new_account_email",
    "render_email_template",
    "generate_test_email",
]
