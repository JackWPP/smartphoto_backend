"""User feedback API for per-asset quality ratings."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.actors import ServicePrincipal
from app.core.deps import get_service_principal
from app.core.errors import AppError
from app.db.session import get_db
from app.models.asset import AssetModel
from app.models.asset_feedback import AssetFeedbackModel
from app.services.jobs import now_utc

router = APIRouter(prefix="/assets", tags=["feedback"])

ALLOWED_ISSUE_TAGS = {
    # existing
    "deformed", "wrong_color", "bad_text", "wrong_style",
    "platform_violation", "low_fidelity", "other",
    # layout issues
    "weak_frame_structure", "not_platform_native", "too_photographic",
    "insufficient_title_zone", "lack_of_proof_blocks",
    "layout_too_empty", "layout_too_busy",
    # fidelity issues
    "logo_moved", "product_text_changed", "color_shifted",
}


class FeedbackRequest(BaseModel):
    rating: int = Field(..., ge=1, le=3, description="1=bad, 2=ok, 3=good")
    issue_tags: list[str] | None = Field(default=None, description="Issue tags from allowed set")
    comment: str | None = Field(default=None, max_length=500)


class FeedbackResponse(BaseModel):
    id: str
    asset_id: str
    rating: int
    issue_tags: list[str] | None
    comment: str | None
    created_at: str


def _serialize_feedback(fb: AssetFeedbackModel) -> dict[str, Any]:
    return {
        "id": fb.id,
        "asset_id": fb.asset_id,
        "session_id": fb.session_id,
        "user_id": fb.user_id,
        "rating": fb.rating,
        "issue_tags": fb.issue_tags,
        "comment": fb.comment,
        "created_at": fb.created_at.isoformat() if fb.created_at else None,
    }


@router.post("/{asset_id}/feedback")
def submit_feedback(
    asset_id: str,
    body: FeedbackRequest,
    db: Session = Depends(get_db),
    principal: ServicePrincipal = Depends(get_service_principal),
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
) -> dict[str, Any]:
    """Submit quality feedback for a generated asset."""
    asset = db.query(AssetModel).filter(AssetModel.id == asset_id).one_or_none()
    if not asset:
        raise AppError("asset_not_found", http_status=404)

    # Validate issue tags
    clean_tags = None
    if body.issue_tags:
        clean_tags = [tag for tag in body.issue_tags if tag in ALLOWED_ISSUE_TAGS]

    feedback = AssetFeedbackModel(
        asset_id=asset_id,
        session_id=asset.session_id,
        user_id=x_user_id or "",
        rating=body.rating,
        issue_tags=clean_tags,
        comment=body.comment,
    )
    db.add(feedback)
    db.commit()
    db.refresh(feedback)

    return {"code": 0, "data": _serialize_feedback(feedback)}


@router.get("/{asset_id}/feedback")
def get_feedback(
    asset_id: str,
    db: Session = Depends(get_db),
    principal: ServicePrincipal = Depends(get_service_principal),
) -> dict[str, Any]:
    """Get all feedback for an asset."""
    feedbacks = (
        db.query(AssetFeedbackModel)
        .filter(AssetFeedbackModel.asset_id == asset_id)
        .order_by(AssetFeedbackModel.created_at.desc())
        .all()
    )
    return {"code": 0, "data": [_serialize_feedback(fb) for fb in feedbacks]}
