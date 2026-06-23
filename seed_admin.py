"""
Create the first Super Admin account.
Usage:
    python seed_admin.py

Run once after first boot to set up initial access.
"""
import getpass
from werkzeug.security import generate_password_hash

from app import create_app
from app.db import get_db

app = create_app()

with app.app_context():
    db = get_db()

    existing = db.execute(
        "SELECT COUNT(*) FROM users WHERE role = 'super_admin'"
    ).fetchone()[0]
    if existing > 0:
        print("A Super Admin already exists. Aborting.")
    else:
        print("=== TCC — Create First Super Admin ===")
        full_name = input("Full name: ").strip()
        email     = input("Email:     ").strip().lower()
        password  = getpass.getpass("Login password (min 8 chars): ")
        mgr_pw    = getpass.getpass("Manager password (min 6 chars): ")

        if len(password) < 8 or len(mgr_pw) < 6:
            print("Passwords too short. Aborting.")
        else:
            db.execute(
                """INSERT INTO users
                   (full_name, email, password_hash, manager_password_hash, role, status)
                   VALUES (?,?,?,?,?,?)""",
                [
                    full_name, email,
                    generate_password_hash(password),
                    generate_password_hash(mgr_pw),
                    'super_admin', 'active',
                ],
            )
            db.commit()
            print(f"\nSuper Admin '{full_name}' created. You can now log in at http://localhost:5003")
