from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.admin_db.session import get_admin_db
from app.api.admin.utils import paginate, serialize_asset, serialize_job, serialize_session
from app.api.v2.sessions import (
    build_detail_strategy as public_build_detail_strategy,
    build_strategy as public_build_strategy,
    get_detail_page_results as public_get_detail_page_results,
    get_results as public_get_results,
    preview_detail_prompts as public_preview_detail_prompts,
    preview_prompts as public_preview_prompts,
)
from app.core.actors import RequestActor
from app.core.admin_deps import get_current_admin_user
from app.core.response import success_response
from app.db.session import get_db
from app.models.asset import AssetModel
from app.models.job import JobModel
from app.models.session import SessionModel
from app.schemas.admin import (
    AdminActionRequest,
    AdminCopyUpdateRequest,
    AdminParameterUpdateRequest,
    AdminSessionDetailData,
    AdminSessionListData,
    AdminStrategyOverridesUpdateRequest,
)
from app.schemas.common import APIResponse, OPENAPI_ERROR_RESPONSES
from app.schemas.results import DetailResultsData, ResultsData
from app.schemas.session import (
    DetailPromptPreviewData,
    DetailStrategyPreviewData,
    DetailStrategyPreviewRequest,
    GenericGenerationJobData,
    PromptPreviewData,
    PromptPreviewRequest,
    StrategyPreviewData,
    StrategyPreviewRequest,
)
from app.services.admin_audit import append_admin_audit_log, request_id_from_request
from app.services.dispatcher import dispatch_job
from app.services.guards import ensure_no_running_generation_jobs
from app.services.jobs import create_job
from app.services.locking import acquire_generation_locks
from app.services.parameter_snapshot import apply_parameter_snapshot_to_copy
from app.services.repo import get_session_or_404

router = APIRouter(prefix="/sessions", tags=["admin-sessions"])


def _session_actor(session: SessionModel) -> RequestActor:
    return RequestActor(kind="user" if session.user_id else "guest", user_id=session.user_id, guest_id=session.guest_id)


def _latest_jobs(db: Session, session_id: str) -> list[dict]:
    jobs = db.query(JobModel).filter(JobModel.session_id == session_id).order_by(JobModel.created_at.desc()).limit(10).all()
    return [serialize_job(job) for job in jobs]


def _latest_assets(db: Session, session_id: str) -> list[dict]:
    assets = db.query(AssetModel).filter(AssetModel.session_id == session_id).order_by(AssetModel.created_at.desc()).limit(20).all()
    return [serialize_asset(asset) for asset in assets]


def _admin_job_for_session(db: Session, session: SessionModel, job_type: str, input_payload: dict | None = None) -> dict:
    payload = dict(input_payload or {})
    if job_type in {"generate_gallery", "regenerate_gallery", "global_edit", "regenerate_asset"}:
        payload.setdefault("lock_keys", acquire_generation_locks(session.id, user_id=session.user_id, guest_id=session.guest_id))
    job = create_job(
        db,
        session_id=session.id,
        user_id=session.user_id,
        guest_id=session.guest_id,
        job_type=job_type,
        input_payload=payload,
    )
    db.commit()
    queue = "q.generation.main"
    if job_type in {"generate_detail_page", "regenerate_detail_panel"}:
        queue = "q.generation.detail"
    dispatch_job(job.id, queue=queue)
    return {"job_id": job.id, "job_type": job.job_type, "status": job.status}


@router.get("", response_model=APIResponse[AdminSessionListData], operation_id="adminListSessions", responses={**OPENAPI_ERROR_RESPONSES})
def list_sessions(
    session_id: str | None = None,
    user_id: str | None = None,
    guest_id: str | None = None,
    platform_id: str | None = None,
    status: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    sort_by: str | None = Query(default="updated_at"),
    sort_order: str = Query(default="desc", pattern="^(asc|desc)$"),
    db: Session = Depends(get_db),
    _admin_user=Depends(get_current_admin_user),
) -> dict:
    query = db.query(SessionModel)
    if session_id:
        query = query.filter(SessionModel.id == session_id)
    if user_id:
        query = query.filter(SessionModel.user_id == user_id)
    if guest_id:
        query = query.filter(SessionModel.guest_id == guest_id)
    if platform_id:
        query = query.filter(SessionModel.active_platform_id == platform_id)
    if status:
        query = query.filter(SessionModel.status == status)
    sort_column = SessionModel.updated_at
    if sort_by == "created_at":
        sort_column = SessionModel.created_at
    elif sort_by == "current_step":
        sort_column = SessionModel.current_step
    elif sort_by == "latest_result_version":
        sort_column = SessionModel.latest_result_version
    query = query.order_by(sort_column.asc() if sort_order == "asc" else sort_column.desc())
    total = query.count()
    items = query.offset((page - 1) * page_size).limit(page_size).all()
    return success_response(
        {
            "items": [
                {
                    "session_id": item.id,
                    "user_id": item.user_id,
                    "guest_id": item.guest_id,
                    "owner_kind": "user" if item.user_id else "guest",
                    "owner_label": item.user_id or f"Guest {item.guest_id}",
                    "status": item.status,
                    "active_platform_id": item.active_platform_id,
                    "current_step": item.current_step,
                    "latest_result_version": item.latest_result_version,
                    "detail_latest_result_version": item.detail_latest_result_version,
                    "created_at": item.created_at.isoformat() if item.created_at else None,
                    "updated_at": item.updated_at.isoformat() if item.updated_at else None,
                }
                for item in items
            ],
            **paginate(total=total, page=page, page_size=page_size, sort_by=sort_by, sort_order=sort_order),
        }
    )


@router.get("/{session_id}", response_model=APIResponse[AdminSessionDetailData], operation_id="adminGetSession", responses={**OPENAPI_ERROR_RESPONSES})
def get_session(session_id: str, db: Session = Depends(get_db), _admin_user=Depends(get_current_admin_user)) -> dict:
    session = get_session_or_404(db, session_id)
    return success_response({"session": serialize_session(session), "recent_jobs": _latest_jobs(db, session.id), "recent_assets": _latest_assets(db, session.id)})


@router.put("/{session_id}/copy", operation_id="adminUpdateSessionCopy", responses={**OPENAPI_ERROR_RESPONSES})
def update_copy(
    session_id: str,
    req: AdminCopyUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
    admin_db: Session = Depends(get_admin_db),
    admin_user=Depends(get_current_admin_user),
) -> dict:
    session = get_session_or_404(db, session_id)
    before = dict(session.confirmed_copy or {})
    session.confirmed_copy = req.model_dump(exclude_none=False, exclude={"operator_note"})
    session.strategy_preview = None
    session.detail_strategy_preview = None
    append_admin_audit_log(
        admin_db,
        admin_user_id=admin_user.id,
        action="session.copy.update",
        module="sessions",
        risk_level="high",
        operator_note=req.operator_note,
        target_type="session",
        target_id=session.id,
        before_snapshot={"confirmed_copy": before},
        after_snapshot={"confirmed_copy": session.confirmed_copy},
        request_id=request_id_from_request(request),
    )
    db.commit()
    admin_db.commit()
    return success_response({"session": serialize_session(session)})


@router.put("/{session_id}/parameters", operation_id="adminUpdateSessionParameters", responses={**OPENAPI_ERROR_RESPONSES})
def update_parameters(
    session_id: str,
    req: AdminParameterUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
    admin_db: Session = Depends(get_admin_db),
    admin_user=Depends(get_current_admin_user),
) -> dict:
    session = get_session_or_404(db, session_id)
    before = dict(session.parameter_snapshot or {})
    session.parameter_snapshot = req.model_dump(exclude={"operator_note"})
    session.confirmed_copy = apply_parameter_snapshot_to_copy(session.confirmed_copy or {}, session.parameter_snapshot, overwrite=True)
    session.strategy_preview = None
    session.detail_strategy_preview = None
    append_admin_audit_log(
        admin_db,
        admin_user_id=admin_user.id,
        action="session.parameters.update",
        module="sessions",
        risk_level="high",
        operator_note=req.operator_note,
        target_type="session",
        target_id=session.id,
        before_snapshot={"parameter_snapshot": before},
        after_snapshot={"parameter_snapshot": session.parameter_snapshot, "confirmed_copy": session.confirmed_copy},
        request_id=request_id_from_request(request),
    )
    db.commit()
    admin_db.commit()
    return success_response({"session": serialize_session(session)})


@router.put("/{session_id}/strategy/overrides", operation_id="adminUpdateSessionStrategyOverrides", responses={**OPENAPI_ERROR_RESPONSES})
def update_strategy_overrides(
    session_id: str,
    req: AdminStrategyOverridesUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
    admin_db: Session = Depends(get_admin_db),
    admin_user=Depends(get_current_admin_user),
) -> dict:
    session = get_session_or_404(db, session_id)
    from app.models.session_prompt_override import SessionPromptOverrideModel

    existing = db.query(SessionPromptOverrideModel).filter(SessionPromptOverrideModel.session_id == session.id, SessionPromptOverrideModel.asset_family == "main_gallery").all()
    before = [item.slot_id for item in existing]
    for item in existing:
        db.delete(item)
    for item in req.overrides:
        db.add(
            SessionPromptOverrideModel(
                session_id=session.id,
                asset_family="main_gallery",
                slot_id=item.get("slot_id"),
                copy_blocks_override=item.get("copy_blocks_override") or {},
                raw_prompt_override=item.get("raw_prompt_override"),
                expression_mode_override=item.get("expression_mode_override"),
                applied_preset_id=item.get("applied_preset_id"),
                locked=bool(item.get("locked")),
            )
        )
    session.strategy_preview = None
    append_admin_audit_log(
        admin_db,
        admin_user_id=admin_user.id,
        action="session.strategy_overrides.update",
        module="sessions",
        risk_level="high",
        operator_note=req.operator_note,
        target_type="session",
        target_id=session.id,
        before_snapshot={"slot_ids": before},
        after_snapshot={"overrides": req.overrides},
        request_id=request_id_from_request(request),
    )
    db.commit()
    admin_db.commit()
    return success_response({"session": serialize_session(session)})


@router.put("/{session_id}/detail-pages/strategy/overrides", operation_id="adminUpdateDetailStrategyOverrides", responses={**OPENAPI_ERROR_RESPONSES})
def update_detail_strategy_overrides(
    session_id: str,
    req: AdminStrategyOverridesUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
    admin_db: Session = Depends(get_admin_db),
    admin_user=Depends(get_current_admin_user),
) -> dict:
    session = get_session_or_404(db, session_id)
    from app.models.session_prompt_override import SessionPromptOverrideModel

    existing = db.query(SessionPromptOverrideModel).filter(SessionPromptOverrideModel.session_id == session.id, SessionPromptOverrideModel.asset_family == "detail_page").all()
    before = [item.slot_id for item in existing]
    for item in existing:
        db.delete(item)
    for item in req.overrides:
        db.add(
            SessionPromptOverrideModel(
                session_id=session.id,
                asset_family="detail_page",
                slot_id=item.get("slot_id"),
                copy_blocks_override=item.get("copy_blocks_override") or {},
                raw_prompt_override=item.get("raw_prompt_override"),
                expression_mode_override=item.get("expression_mode_override"),
                applied_preset_id=item.get("applied_preset_id"),
                locked=bool(item.get("locked")),
            )
        )
    session.detail_strategy_preview = None
    append_admin_audit_log(
        admin_db,
        admin_user_id=admin_user.id,
        action="session.detail_strategy_overrides.update",
        module="sessions",
        risk_level="high",
        operator_note=req.operator_note,
        target_type="session",
        target_id=session.id,
        before_snapshot={"slot_ids": before},
        after_snapshot={"overrides": req.overrides},
        request_id=request_id_from_request(request),
    )
    db.commit()
    admin_db.commit()
    return success_response({"session": serialize_session(session)})


@router.post("/{session_id}/strategy/preview", response_model=APIResponse[StrategyPreviewData], operation_id="adminBuildStrategyPreview", responses={**OPENAPI_ERROR_RESPONSES})
def build_strategy_preview(
    session_id: str,
    req: StrategyPreviewRequest | None = None,
    db: Session = Depends(get_db),
    _admin_user=Depends(get_current_admin_user),
) -> dict:
    session = get_session_or_404(db, session_id)
    return public_build_strategy(session_id=session.id, req=req, db=db, actor=_session_actor(session))


@router.post("/{session_id}/detail-pages/strategy/preview", response_model=APIResponse[DetailStrategyPreviewData], operation_id="adminBuildDetailStrategyPreview", responses={**OPENAPI_ERROR_RESPONSES})
def build_detail_strategy_preview(
    session_id: str,
    req: DetailStrategyPreviewRequest | None = None,
    db: Session = Depends(get_db),
    _admin_user=Depends(get_current_admin_user),
) -> dict:
    session = get_session_or_404(db, session_id)
    return public_build_detail_strategy(session_id=session.id, req=req, db=db, user_id=session.user_id)


@router.post("/{session_id}/prompts/preview", response_model=APIResponse[PromptPreviewData], operation_id="adminPreviewPrompts", responses={**OPENAPI_ERROR_RESPONSES})
def preview_prompts(
    session_id: str,
    req: PromptPreviewRequest,
    db: Session = Depends(get_db),
    _admin_user=Depends(get_current_admin_user),
) -> dict:
    session = get_session_or_404(db, session_id)
    return public_preview_prompts(session_id=session.id, req=req, db=db, actor=_session_actor(session))


@router.post("/{session_id}/detail-pages/prompts/preview", response_model=APIResponse[DetailPromptPreviewData], operation_id="adminPreviewDetailPrompts", responses={**OPENAPI_ERROR_RESPONSES})
def preview_detail_prompts(
    session_id: str,
    req: PromptPreviewRequest,
    db: Session = Depends(get_db),
    _admin_user=Depends(get_current_admin_user),
) -> dict:
    session = get_session_or_404(db, session_id)
    return public_preview_detail_prompts(session_id=session.id, req=req, db=db, user_id=session.user_id)


@router.get("/{session_id}/results", response_model=APIResponse[ResultsData], operation_id="adminGetSessionResults", responses={**OPENAPI_ERROR_RESPONSES})
def get_results(
    session_id: str,
    version: int | None = Query(default=None),
    db: Session = Depends(get_db),
    _admin_user=Depends(get_current_admin_user),
) -> dict:
    session = get_session_or_404(db, session_id)
    return public_get_results(session_id=session.id, version=version, db=db, actor=_session_actor(session))


@router.get("/{session_id}/detail-pages/results", response_model=APIResponse[DetailResultsData], operation_id="adminGetDetailPageResults", responses={**OPENAPI_ERROR_RESPONSES})
def get_detail_results(
    session_id: str,
    version: int | None = Query(default=None),
    db: Session = Depends(get_db),
    _admin_user=Depends(get_current_admin_user),
) -> dict:
    session = get_session_or_404(db, session_id)
    return public_get_detail_page_results(session_id=session.id, version=version, db=db, user_id=session.user_id)


@router.post("/{session_id}/actions/reanalyze", response_model=APIResponse[GenericGenerationJobData], operation_id="adminReanalyzeSession", responses={**OPENAPI_ERROR_RESPONSES})
def reanalyze(
    session_id: str,
    req: AdminActionRequest,
    request: Request,
    db: Session = Depends(get_db),
    admin_db: Session = Depends(get_admin_db),
    admin_user=Depends(get_current_admin_user),
) -> dict:
    session = get_session_or_404(db, session_id)
    result = _admin_job_for_session(db, session, "analysis")
    append_admin_audit_log(
        admin_db,
        admin_user_id=admin_user.id,
        action="session.reanalyze",
        module="sessions",
        risk_level="high",
        operator_note=req.operator_note,
        target_type="session",
        target_id=session.id,
        before_snapshot=None,
        after_snapshot=result,
        request_id=request_id_from_request(request),
    )
    admin_db.commit()
    return success_response(result)


@router.post("/{session_id}/actions/extract-parameters", response_model=APIResponse[GenericGenerationJobData], operation_id="adminExtractParameters", responses={**OPENAPI_ERROR_RESPONSES})
def extract_parameters(
    session_id: str,
    req: AdminActionRequest,
    request: Request,
    db: Session = Depends(get_db),
    admin_db: Session = Depends(get_admin_db),
    admin_user=Depends(get_current_admin_user),
) -> dict:
    session = get_session_or_404(db, session_id)
    result = _admin_job_for_session(db, session, "extract_parameters")
    append_admin_audit_log(
        admin_db,
        admin_user_id=admin_user.id,
        action="session.extract_parameters",
        module="sessions",
        risk_level="high",
        operator_note=req.operator_note,
        target_type="session",
        target_id=session.id,
        before_snapshot=None,
        after_snapshot=result,
        request_id=request_id_from_request(request),
    )
    admin_db.commit()
    return success_response(result)


@router.post("/{session_id}/actions/regenerate-main", response_model=APIResponse[GenericGenerationJobData], operation_id="adminRegenerateMainGallery", responses={**OPENAPI_ERROR_RESPONSES})
def regenerate_main(
    session_id: str,
    req: AdminActionRequest,
    request: Request,
    db: Session = Depends(get_db),
    admin_db: Session = Depends(get_admin_db),
    admin_user=Depends(get_current_admin_user),
) -> dict:
    session = get_session_or_404(db, session_id)
    ensure_no_running_generation_jobs(db, session.id, user_id=session.user_id, guest_id=session.guest_id)
    result = _admin_job_for_session(db, session, "generate_gallery", {"instruction": req.instruction, "slot_ids": req.slot_ids})
    append_admin_audit_log(
        admin_db,
        admin_user_id=admin_user.id,
        action="session.regenerate_main",
        module="sessions",
        risk_level="critical",
        operator_note=req.operator_note,
        target_type="session",
        target_id=session.id,
        before_snapshot=None,
        after_snapshot=result,
        request_id=request_id_from_request(request),
    )
    admin_db.commit()
    return success_response(result)


@router.post("/{session_id}/actions/regenerate-detail", response_model=APIResponse[GenericGenerationJobData], operation_id="adminRegenerateDetailPage", responses={**OPENAPI_ERROR_RESPONSES})
def regenerate_detail(
    session_id: str,
    req: AdminActionRequest,
    request: Request,
    db: Session = Depends(get_db),
    admin_db: Session = Depends(get_admin_db),
    admin_user=Depends(get_current_admin_user),
) -> dict:
    session = get_session_or_404(db, session_id)
    ensure_no_running_generation_jobs(db, session.id, user_id=session.user_id, guest_id=session.guest_id)
    result = _admin_job_for_session(db, session, "generate_detail_page", {"instruction": req.instruction})
    append_admin_audit_log(
        admin_db,
        admin_user_id=admin_user.id,
        action="session.regenerate_detail",
        module="sessions",
        risk_level="critical",
        operator_note=req.operator_note,
        target_type="session",
        target_id=session.id,
        before_snapshot=None,
        after_snapshot=result,
        request_id=request_id_from_request(request),
    )
    admin_db.commit()
    return success_response(result)
