from fastapi import APIRouter

from app.core.errors import AppError
from app.schemas.common import OPENAPI_ERROR_RESPONSES

router = APIRouter(prefix="/auth", tags=["auth"])


def _feature_removed() -> None:
    raise AppError("feature_removed", "auth surfaces moved out of smartphoto image saas", 410)


def _removed_auth_surface(path: str) -> None:
    _feature_removed()


@router.get("/{path:path}", operation_id="removedAuthGet", responses={**OPENAPI_ERROR_RESPONSES})
def removed_auth_get(path: str) -> None:
    _removed_auth_surface(path)


@router.post("/{path:path}", operation_id="removedAuthPost", responses={**OPENAPI_ERROR_RESPONSES})
def removed_auth_post(path: str) -> None:
    _removed_auth_surface(path)


@router.put("/{path:path}", operation_id="removedAuthPut", responses={**OPENAPI_ERROR_RESPONSES})
def removed_auth_put(path: str) -> None:
    _removed_auth_surface(path)


@router.patch("/{path:path}", operation_id="removedAuthPatch", responses={**OPENAPI_ERROR_RESPONSES})
def removed_auth_patch(path: str) -> None:
    _removed_auth_surface(path)


@router.delete("/{path:path}", operation_id="removedAuthDelete", responses={**OPENAPI_ERROR_RESPONSES})
def removed_auth_delete(path: str) -> None:
    _removed_auth_surface(path)
