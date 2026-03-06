from fastapi import APIRouter

from app.core.response import success_response
from app.services.platforms import list_platforms

router = APIRouter(prefix="/platforms", tags=["platforms"])


@router.get("")
def get_platforms() -> dict:
    return success_response({"items": list_platforms()})
