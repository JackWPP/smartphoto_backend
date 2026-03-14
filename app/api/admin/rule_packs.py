from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.api.admin.utils import serialize_rule_pack
from app.admin_db.session import get_admin_db
from app.core.admin_deps import get_current_admin_user
from app.core.errors import AppError
from app.core.response import success_response
from app.db.session import get_db
from app.models.rule_pack import RulePackModel
from app.models.rule_pack_version import RulePackVersionModel
from app.schemas.admin import AdminRulePackListData, AdminRulePackUpdateRequest, AdminRulePackUpsertRequest
from app.schemas.common import APIResponse, OPENAPI_ERROR_RESPONSES
from app.services.admin_audit import append_admin_audit_log, request_id_from_request
from app.services.rule_packs import ensure_system_rule_packs

router = APIRouter(prefix="/rule-packs", tags=["admin-rule-packs"])


def _get_rule_pack_or_404(db: Session, rule_pack_id: str) -> RulePackModel:
    rule_pack = db.query(RulePackModel).filter(RulePackModel.id == rule_pack_id).one_or_none()
    if not rule_pack:
        raise AppError("invalid_request", "rule pack not found", 404)
    return rule_pack


def _latest_version(db: Session, rule_pack_id: str) -> RulePackVersionModel | None:
    return db.query(RulePackVersionModel).filter(RulePackVersionModel.rule_pack_id == rule_pack_id).order_by(RulePackVersionModel.version_no.desc()).first()


@router.get("", response_model=APIResponse[AdminRulePackListData], operation_id="adminListRulePacks", responses={**OPENAPI_ERROR_RESPONSES})
def list_rule_packs(
    asset_family: str | None = None,
    platform_id: str | None = None,
    include_inactive: bool = Query(default=False),
    db: Session = Depends(get_db),
    _admin_user=Depends(get_current_admin_user),
) -> dict:
    ensure_system_rule_packs(db)
    query = db.query(RulePackModel)
    if asset_family:
        query = query.filter(RulePackModel.asset_family == asset_family)
    if platform_id:
        query = query.filter(RulePackModel.platform_id == platform_id)
    if not include_inactive:
        query = query.filter(RulePackModel.is_active.is_(True))
    items = query.order_by(RulePackModel.asset_family.asc(), RulePackModel.updated_at.desc()).all()
    return success_response({"items": [serialize_rule_pack(item, _latest_version(db, item.id)) for item in items], "total": len(items)})


@router.get("/{rule_pack_id}", operation_id="adminGetRulePack", responses={**OPENAPI_ERROR_RESPONSES})
def get_rule_pack(rule_pack_id: str, db: Session = Depends(get_db), _admin_user=Depends(get_current_admin_user)) -> dict:
    rule_pack = _get_rule_pack_or_404(db, rule_pack_id)
    versions = db.query(RulePackVersionModel).filter(RulePackVersionModel.rule_pack_id == rule_pack.id).order_by(RulePackVersionModel.version_no.desc()).all()
    return success_response({"rule_pack": serialize_rule_pack(rule_pack, versions[0] if versions else None), "versions": [serialize_rule_pack(rule_pack, item)["version"] for item in versions]})


@router.post("", operation_id="adminCreateRulePack", responses={**OPENAPI_ERROR_RESPONSES})
def create_rule_pack(req: AdminRulePackUpsertRequest, request: Request, db: Session = Depends(get_db), admin_db: Session = Depends(get_admin_db), admin_user=Depends(get_current_admin_user)) -> dict:
    rule_pack = RulePackModel(name=req.name, asset_family=req.asset_family, platform_id=req.platform_id, rule_pack_key=req.rule_pack_key, is_system=False, is_active=True, current_version_no=1, created_by=admin_user.id)
    db.add(rule_pack)
    db.flush()
    version = RulePackVersionModel(rule_pack_id=rule_pack.id, version_no=1, asset_family=req.asset_family, platform_id=req.platform_id, rule_pack_key=req.rule_pack_key, config_snapshot=req.config_snapshot, is_published=False, published_by=None)
    db.add(version)
    db.flush()
    append_admin_audit_log(admin_db, admin_user_id=admin_user.id, action="rule_pack.create", target_type="rule_pack", target_id=rule_pack.id, before_snapshot=None, after_snapshot=serialize_rule_pack(rule_pack, version), request_id=request_id_from_request(request))
    db.commit()
    admin_db.commit()
    return success_response({"rule_pack": serialize_rule_pack(rule_pack, version)})


@router.put("/{rule_pack_id}", operation_id="adminUpdateRulePack", responses={**OPENAPI_ERROR_RESPONSES})
def update_rule_pack(rule_pack_id: str, req: AdminRulePackUpdateRequest, request: Request, db: Session = Depends(get_db), admin_db: Session = Depends(get_admin_db), admin_user=Depends(get_current_admin_user)) -> dict:
    rule_pack = _get_rule_pack_or_404(db, rule_pack_id)
    before = serialize_rule_pack(rule_pack, _latest_version(db, rule_pack.id))
    payload = req.model_dump(exclude_unset=True)
    latest = _latest_version(db, rule_pack.id)
    if "name" in payload:
        rule_pack.name = payload["name"]
    if "platform_id" in payload:
        rule_pack.platform_id = payload["platform_id"]
    if "is_active" in payload:
        rule_pack.is_active = payload["is_active"]
    if payload.get("config_snapshot") is not None:
        next_version_no = (latest.version_no if latest else rule_pack.current_version_no) + 1
        latest = RulePackVersionModel(rule_pack_id=rule_pack.id, version_no=next_version_no, asset_family=rule_pack.asset_family, platform_id=rule_pack.platform_id, rule_pack_key=rule_pack.rule_pack_key, config_snapshot=payload["config_snapshot"], is_published=False, published_by=None)
        db.add(latest)
    db.flush()
    append_admin_audit_log(admin_db, admin_user_id=admin_user.id, action="rule_pack.update", target_type="rule_pack", target_id=rule_pack.id, before_snapshot=before, after_snapshot=serialize_rule_pack(rule_pack, latest), request_id=request_id_from_request(request))
    db.commit()
    admin_db.commit()
    return success_response({"rule_pack": serialize_rule_pack(rule_pack, latest)})


@router.post("/{rule_pack_id}/publish", operation_id="adminPublishRulePack", responses={**OPENAPI_ERROR_RESPONSES})
def publish_rule_pack(rule_pack_id: str, request: Request, db: Session = Depends(get_db), admin_db: Session = Depends(get_admin_db), admin_user=Depends(get_current_admin_user)) -> dict:
    rule_pack = _get_rule_pack_or_404(db, rule_pack_id)
    latest = _latest_version(db, rule_pack.id)
    if latest is None:
        raise AppError("invalid_request", "rule pack version not found", 404)
    before = serialize_rule_pack(rule_pack, latest)
    db.query(RulePackVersionModel).filter(RulePackVersionModel.rule_pack_id == rule_pack.id).update({"is_published": False})
    latest.is_published = True
    latest.published_by = admin_user.id
    rule_pack.current_version_no = latest.version_no
    append_admin_audit_log(admin_db, admin_user_id=admin_user.id, action="rule_pack.publish", target_type="rule_pack", target_id=rule_pack.id, before_snapshot=before, after_snapshot=serialize_rule_pack(rule_pack, latest), request_id=request_id_from_request(request))
    db.commit()
    admin_db.commit()
    return success_response({"rule_pack": serialize_rule_pack(rule_pack, latest)})


@router.post("/{rule_pack_id}/clone", operation_id="adminCloneRulePack", responses={**OPENAPI_ERROR_RESPONSES})
def clone_rule_pack(rule_pack_id: str, request: Request, db: Session = Depends(get_db), admin_db: Session = Depends(get_admin_db), admin_user=Depends(get_current_admin_user)) -> dict:
    rule_pack = _get_rule_pack_or_404(db, rule_pack_id)
    latest = _latest_version(db, rule_pack.id)
    if latest is None:
        raise AppError("invalid_request", "rule pack version not found", 404)
    clone = RulePackModel(name=f"{rule_pack.name} Copy", asset_family=rule_pack.asset_family, platform_id=rule_pack.platform_id, rule_pack_key=f"{rule_pack.rule_pack_key}_copy", is_system=False, is_active=True, current_version_no=1, created_by=admin_user.id)
    db.add(clone)
    db.flush()
    version = RulePackVersionModel(rule_pack_id=clone.id, version_no=1, asset_family=clone.asset_family, platform_id=clone.platform_id, rule_pack_key=clone.rule_pack_key, config_snapshot=latest.config_snapshot, is_published=False, published_by=None)
    db.add(version)
    db.flush()
    append_admin_audit_log(admin_db, admin_user_id=admin_user.id, action="rule_pack.clone", target_type="rule_pack", target_id=clone.id, before_snapshot=serialize_rule_pack(rule_pack, latest), after_snapshot=serialize_rule_pack(clone, version), request_id=request_id_from_request(request))
    db.commit()
    admin_db.commit()
    return success_response({"rule_pack": serialize_rule_pack(clone, version)})


@router.post("/{rule_pack_id}/archive", operation_id="adminArchiveRulePack", responses={**OPENAPI_ERROR_RESPONSES})
def archive_rule_pack(rule_pack_id: str, request: Request, db: Session = Depends(get_db), admin_db: Session = Depends(get_admin_db), admin_user=Depends(get_current_admin_user)) -> dict:
    rule_pack = _get_rule_pack_or_404(db, rule_pack_id)
    before = serialize_rule_pack(rule_pack, _latest_version(db, rule_pack.id))
    rule_pack.is_active = False
    append_admin_audit_log(admin_db, admin_user_id=admin_user.id, action="rule_pack.archive", target_type="rule_pack", target_id=rule_pack.id, before_snapshot=before, after_snapshot=serialize_rule_pack(rule_pack, _latest_version(db, rule_pack.id)), request_id=request_id_from_request(request))
    db.commit()
    admin_db.commit()
    return success_response({"rule_pack": serialize_rule_pack(rule_pack, _latest_version(db, rule_pack.id))})
