from datetime import datetime

from sqlalchemy import DateTime
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    # All timestamps are timestamptz, matching the Alembic migrations.
    type_annotation_map = {datetime: DateTime(timezone=True)}
