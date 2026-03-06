from sqlalchemy import and_, desc
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models.asset import AssetModel
from app.models.job import JobModel
from app.models.job_event import JobEventModel
from app.models.session import SessionModel
from app.models.session_image import SessionImageModel


def get_session_or_404(db: Session, session_id: str, user_id: str | None = None) -> SessionModel:
    query = db.query(SessionModel).filter(SessionModel.id == session_id)
    if user_id:
        query = query.filter(SessionModel.user_id == user_id)
    session = query.one_or_none()
    if not session:
        raise AppError("session_not_found", http_status=404)
    return session


def get_job_or_404(db: Session, job_id: str) -> JobModel:
    job = db.query(JobModel).filter(JobModel.id == job_id).one_or_none()
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
