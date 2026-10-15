"""Admin-only visibility for the HRM integration readiness blocker."""
from fastapi import APIRouter, Request

from ..hrm_integration import get_hrm_status
from ..security import require_role

router = APIRouter(prefix="/api/integrations/hrm", tags=["HRM Integration"])


@router.get("/status")
def get_status(request: Request):
    """Report readiness only; never return secrets or simulate a provider call."""
    require_role(request, "Admin")
    return get_hrm_status()
