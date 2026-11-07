"""seed load-test customers (70 FREE, 30 PREMIUM) used by loadtest/locustfile.py

Revision ID: 0006
Revises: 0005
"""

import sqlalchemy as sa

from alembic import op
from app.core.config import get_settings, loadtest_password
from app.core.security import hash_password

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

DOMAIN = "loadtest.feastflow.app"


def upgrade() -> None:
    # Production seeds these accounts only when LOADTEST_PASSWORD is set (infra generates a random one);
    # the dev password is public, and the accounts are reachable through the public ALB.
    password = loadtest_password(get_settings())
    if password is None:
        return
    # Cost 4 keeps the migration fast; users log in once per simulated session anyway.
    pw = hash_password(password, rounds=4)
    conn = op.get_bind()
    rows = [(f"lt-free-{i:02d}", "FREE") for i in range(1, 71)] + [
        (f"lt-prem-{i:02d}", "PREMIUM") for i in range(1, 31)
    ]
    for local, tier in rows:
        conn.execute(
            sa.text(
                "INSERT INTO users (email, password_hash, full_name, role, subscription_tier) "
                "VALUES (:e, :p, :n, 'CUSTOMER', :t) ON CONFLICT (email) DO NOTHING"
            ),
            {"e": f"{local}@{DOMAIN}", "p": pw, "n": f"Load Test {local}", "t": tier},
        )


def downgrade() -> None:
    op.execute(f"DELETE FROM users WHERE email LIKE 'lt-%@{DOMAIN}'")
