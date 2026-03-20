"""Seed initial users on first startup."""

from app.auth import hash_password
from app.config import settings
from app.db.models import create_user, user_count


def seed_users():
    """Create initial users if the users table is empty."""
    if user_count() > 0:
        return

    print("Seeding initial users...")

    create_user(
        email=settings.admin_email,
        name="Emil",
        password_hash=hash_password(settings.admin_password),
        is_admin=True,
    )

    create_user(
        email="ta@vatnsvirkinn.is",
        name="Þorsteinn Árnason",
        password_hash=hash_password(settings.user_password),
        is_admin=False,
    )

    print("  Created 2 users (Emil as admin, Þorsteinn as user)")
