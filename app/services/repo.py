from sqlalchemy import and_, desc
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models.asset import AssetModel
from app.models.detail_style_image import DetailStyleImageModel
from app.models.job import JobModel
from app.models.job_event import JobEventModel
from app.models.parameter_attachment import ParameterAttachmentModel
from app.models.prompt_preset import PromptPresetModel
from app.models.session import SessionModel
from app.models.session_image import SessionImageModel
from app.models.session_prompt_override import SessionPromptOverrideModel
from app.models.strategy_reference_image import StrategyReferenceImageModel


def get_session_or_404(
    db: Session,
    session_id: str,
    service_id: str | None = None,
    user_id: str | None = None,
    guest_id: str | None = None,
) -> SessionModel:
    query = db.query(SessionModel).filter(SessionModel.id == session_id)
    if service_id is not None:
        query = query.filter(SessionModel.service_id == service_id)
    elif user_id is not None:
        query = query.filter(SessionModel.user_id == user_id)
    elif guest_id is not None:
        query = query.filter(SessionModel.guest_id == guest_id)
    session = query.one_or_none()
    if not session:
        raise AppError("session_not_found", http_status=404)
    return session


def get_job_or_404(db: Session, job_id: str) -> JobModel:
    job = db.query(JobModel).filter(JobModel.id == job_id).one_or_none()
    if not job:
        raise AppError("job_not_found", http_status=404)
    return job


def get_job_for_user_or_404(db: Session, job_id: str, user_id: str) -> JobModel:
    job = db.query(JobModel).filter(JobModel.id == job_id, JobModel.user_id == user_id).one_or_none()
    if not job:
        raise AppError("job_not_found", http_status=404)
    return job


def get_job_for_actor_or_404(
    db: Session,
    job_id: str,
    *,
    service_id: str | None = None,
    user_id: str | None = None,
    guest_id: str | None = None,
) -> JobModel:
    query = db.query(JobModel).filter(JobModel.id == job_id)
    if service_id is not None:
        query = query.filter(JobModel.service_id == service_id)
    elif user_id is not None:
        query = query.filter(JobModel.user_id == user_id)
    elif guest_id is not None:
        query = query.filter(JobModel.guest_id == guest_id)
    job = query.one_or_none()
    if not job:
        raise AppError("job_not_found", http_status=404)
    return job


def get_asset_or_404(db: Session, asset_id: str) -> AssetModel:
    asset = db.query(AssetModel).filter(AssetModel.id == asset_id).one_or_none()
    if not asset:
        raise AppError("asset_not_found", http_status=404)
    return asset


def list_active_session_images(db: Session, session_id: str) -> list[SessionImageModel]:
    return (
        db.query(SessionImageModel)
        .filter(and_(SessionImageModel.session_id == session_id, SessionImageModel.is_deleted.is_(False)))
        .order_by(SessionImageModel.display_order.asc())
        .all()
    )


def list_active_detail_style_images(db: Session, session_id: str) -> list[DetailStyleImageModel]:
    return (
        db.query(DetailStyleImageModel)
        .filter(and_(DetailStyleImageModel.session_id == session_id, DetailStyleImageModel.is_deleted.is_(False)))
        .order_by(DetailStyleImageModel.display_order.asc())
        .all()
    )


def list_active_parameter_attachments(db: Session, session_id: str) -> list[ParameterAttachmentModel]:
    return (
        db.query(ParameterAttachmentModel)
        .filter(and_(ParameterAttachmentModel.session_id == session_id, ParameterAttachmentModel.is_deleted.is_(False)))
        .order_by(ParameterAttachmentModel.display_order.asc())
        .all()
    )


def list_active_strategy_reference_images(db: Session, session_id: str) -> list[StrategyReferenceImageModel]:
    return (
        db.query(StrategyReferenceImageModel)
        .filter(and_(StrategyReferenceImageModel.session_id == session_id, StrategyReferenceImageModel.is_deleted.is_(False)))
        .order_by(StrategyReferenceImageModel.display_order.asc())
        .all()
    )


def list_session_prompt_overrides(db: Session, session_id: str, *, asset_family: str = "main_gallery") -> list[SessionPromptOverrideModel]:
    return (
        db.query(SessionPromptOverrideModel)
        .filter(
            SessionPromptOverrideModel.session_id == session_id,
            SessionPromptOverrideModel.asset_family == asset_family,
        )
        .order_by(SessionPromptOverrideModel.slot_id.asc())
        .all()
    )



def get_prompt_preset_or_404(db: Session, preset_id: str, user_id: str | None = None) -> PromptPresetModel:
    query = db.query(PromptPresetModel).filter(PromptPresetModel.id == preset_id)
    if user_id is not None:
        query = query.filter((PromptPresetModel.is_system.is_(True)) | (PromptPresetModel.created_by == user_id))
    preset = query.one_or_none()
    if not preset:
        raise AppError("invalid_request", "prompt preset not found", 404)
    return preset


def get_prompt_preset_or_none(db: Session, preset_id: str | None, user_id: str | None = None) -> PromptPresetModel | None:
    if not preset_id:
        return None
    query = db.query(PromptPresetModel).filter(PromptPresetModel.id == preset_id)
    if user_id is not None:
        query = query.filter((PromptPresetModel.is_system.is_(True)) | (PromptPresetModel.created_by == user_id))
    return query.one_or_none()


def list_visible_prompt_presets_by_ids(db: Session, preset_ids: list[str], user_id: str | None = None) -> list[PromptPresetModel]:
    if not preset_ids:
        return []
    query = db.query(PromptPresetModel).filter(PromptPresetModel.id.in_(preset_ids))
    if user_id is not None:
        query = query.filter((PromptPresetModel.is_system.is_(True)) | (PromptPresetModel.created_by == user_id))
    return query.all()


def get_latest_job_by_type(db: Session, session_id: str, job_type: str) -> JobModel | None:
    return (
        db.query(JobModel)
        .filter(JobModel.session_id == session_id, JobModel.job_type == job_type)
        .order_by(desc(JobModel.created_at))
        .first()
    )


def list_job_events_after(db: Session, job_id: str, seq_no: int) -> list[JobEventModel]:
    return (
        db.query(JobEventModel)
        .filter(JobEventModel.job_id == job_id, JobEventModel.seq_no > seq_no)
        .order_by(JobEventModel.seq_no.asc())
        .all()
    )
