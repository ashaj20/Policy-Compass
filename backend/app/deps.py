"""Shared FastAPI dependencies, as Annotated aliases for use in route signatures."""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.db import get_db

DbSession = Annotated[Session, Depends(get_db)]
