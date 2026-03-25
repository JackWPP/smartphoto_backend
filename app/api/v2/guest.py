from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from app.api.v2.sessions import _session_snapshot_payload
from app.core.actors import RequestActor
from app.core.config import get_settings
from app.core.deps import get_current_user
from app.core.errors import AppError
from app.core.response import success_response
from app.db.session import get_db
from app.models.session import SessionModel
from app.models.user import UserModel
from app.schemas.common import APIResponse, OPENAPI_ERROR_RESPONSES
from app.schemas.session import SessionSnapshotData
from app.services.guest_identities import (
    claim_guest_session,
    clear_guest_cookie,
    decode_guest_cookie_token,
    get_active_guest_identity_by_id,
)

router = APIRouter(prefix="/guest", tags=["sessions"])


@router.post(
    "/sessions/{session_id}/claim",
    response_model=APIResponse[SessionSnapshotData],
    summary="认领匿名会话",
    description="登录成功后显式认领当前浏览器 guest 关联的 session，并继续复用原 session_id。",
    operation_id="claimGuestSession",
    responses={**OPENAPI_ERROR_RESPONSES},
)
def claim_session(
    session_id: str,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
) -> dict:
    session = db.query(SessionModel).filter(SessionModel.id == session_id).one_or_none()
    if session is None:
        raise AppError("session_not_found", http_status=404)

    actor = RequestActor(kind="user", user_id=current_user.id)
    if session.user_id == current_user.id and session.guest_id is None:
        return success_response(_session_snapshot_payload(db, session, actor))

    guest_id = decode_guest_cookie_token(request.cookies.get(get_settings().guest_cookie_name))
    guest = get_active_guest_identity_by_id(db, guest_id)
    if guest is None:
        raise AppError("invalid_request", "active guest identity required for claim", 400)
    if not claim_guest_session(db, session_id=session_id, guest_id=guest.id, user_id=current_user.id):
        raise AppError("session_not_found", http_status=404)

    clear_guest_cookie(response)
    db.commit()
    claimed_session = db.query(SessionModel).filter(SessionModel.id == session_id).one()
    return success_response(_session_snapshot_payload(db, claimed_session, actor))
