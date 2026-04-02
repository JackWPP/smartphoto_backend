from fastapi import APIRouter

from app.core.errors import AppError
from app.schemas.common import OPENAPI_ERROR_RESPONSES

router = APIRouter(prefix="/guest", tags=["sessions"])


def _feature_removed() -> None:
    raise AppError("feature_removed", "guest surfaces moved out of smartphoto image saas", 410)


def _removed_guest_surface(path: str) -> None:
    _feature_removed()


@router.get("/{path:path}", operation_id="removedGuestGet", responses={**OPENAPI_ERROR_RESPONSES})
def removed_guest_get(path: str) -> None:
    _removed_guest_surface(path)


@router.post("/{path:path}", operation_id="removedGuestPost", responses={**OPENAPI_ERROR_RESPONSES})
def removed_guest_post(path: str) -> None:
    _removed_guest_surface(path)


@router.put("/{path:path}", operation_id="removedGuestPut", responses={**OPENAPI_ERROR_RESPONSES})
def removed_guest_put(path: str) -> None:
    _removed_guest_surface(path)


@router.patch("/{path:path}", operation_id="removedGuestPatch", responses={**OPENAPI_ERROR_RESPONSES})
def removed_guest_patch(path: str) -> None:
    _removed_guest_surface(path)


@router.delete("/{path:path}", operation_id="removedGuestDelete", responses={**OPENAPI_ERROR_RESPONSES})
def removed_guest_delete(path: str) -> None:
    _removed_guest_surface(path)
