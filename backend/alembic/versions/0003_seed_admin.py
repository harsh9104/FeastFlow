"""seed admin user from ADMIN_EMAIL / ADMIN_PASSWORD

Revision ID: 0003
Revises: 0002
"""

import sqlalchemy as sa

from alembic import op
from app.core.config import get_settings
from app.core.security import hash_password

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    s = get_settings()
    if not (s.admin_email and s.admin_password):
        return
    op.get_bind().execute(
        sa.text(
            "INSERT INTO users (email, password_hash, full_name, role, subscription_tier) "
            "VALUES (:e, :p, 'Administrator', 'ADMIN', 'FREE') ON CONFLICT (email) DO NOTHING"
        ),
        {"e": s.admin_email.lower(), "p": hash_password(s.admin_password)},
    )


def downgrade() -> None:
    pass
