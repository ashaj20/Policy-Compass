"""What Policy Compass keeps and for how long (US-035B). Read-only, for signed-in users."""

from fastapi import APIRouter
from pydantic import BaseModel

from app.deps import CurrentUser
from app.retention import rules_as_dicts

router = APIRouter(tags=["retention"])


class RuleOut(BaseModel):
    data: str
    period: str
    detail: str


@router.get("/retention")
def retention_rules(_: CurrentUser) -> list[RuleOut]:
    return [RuleOut(**r) for r in rules_as_dicts()]
