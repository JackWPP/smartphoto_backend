from fastapi import APIRouter

from app.core.errors import AppError
from app.schemas.common import OPENAPI_ERROR_RESPONSES

router = APIRouter(prefix="/account", tags=["account"])


def _feature_removed() -> None:
    raise AppError("feature_removed", "account surfaces moved out of smartphoto image saas", 410)


def _removed_account_surface(path: str) -> None:
    _feature_removed()


@router.get("/{path:path}", operation_id="removedAccountGet", responses={**OPENAPI_ERROR_RESPONSES})
def removed_account_get(path: str) -> None:
    _removed_account_surface(path)


@router.post("/{path:path}", operation_id="removedAccountPost", responses={**OPENAPI_ERROR_RESPONSES})
def removed_account_post(path: str) -> None:
    _removed_account_surface(path)


@router.put("/{path:path}", operation_id="removedAccountPut", responses={**OPENAPI_ERROR_RESPONSES})
def removed_account_put(path: str) -> None:
    _removed_account_surface(path)


@router.patch("/{path:path}", operation_id="removedAccountPatch", responses={**OPENAPI_ERROR_RESPONSES})
def removed_account_patch(path: str) -> None:
    _removed_account_surface(path)


@router.delete("/{path:path}", operation_id="removedAccountDelete", responses={**OPENAPI_ERROR_RESPONSES})
def removed_account_delete(path: str) -> None:
    _removed_account_surface(path)
