# SHARED FILE — coordinate changes with all workstreams before modifying.
#
# Declarative base for SQLAlchemy models. All ORM models across
# workstreams should inherit from `Base` defined here.

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
