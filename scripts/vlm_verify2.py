"""VLM verify — compare ALL assets in a session."""
import sys, io, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from app.db.session import SessionLocal
from app.models.session import SessionModel
from app.models.asset import AssetModel
from app.services.upstream import WhataiClient
from app.services.storage import public_url_for
from app.services.prompts import parse_visible_copy_slots

db = SessionLocal()
sessions = db.query(SessionModel).filter(
    SessionModel.latest_result_version > 0
).order_by(SessionModel.updated_at.desc()).limit(2).all()

client = WhataiClient()

for s in sessions:
    v = s.latest_result_version
    assets = db.query(AssetModel).filter(
        AssetModel.session_id == s.id, AssetModel.version_no == v,
        AssetModel.visibility_status == 'visible',
    ).order_by(AssetModel.display_order).all()

    print(f"\n{'='*60}")
    print(f"Session {s.id[:8]} v{v} platform={s.active_platform_id} assets={len(assets)}")

    # Check first asset only to save API calls
    a = assets[0]
    fp = (a.generation_snapshot or {}).get('final_prompt', '')
    slots = parse_visible_copy_slots(fp)
    slot_texts = [s['text'][:40] for s in slots]
    print(f"[{a.asset_role}] Prompt slots: {slot_texts}")

    url = public_url_for(a.image_url) if a.image_url else None
    if url:
        messages = [{"role":"user","content":[
            {"type":"text","text": '读取图上所有中文文字。只返回JSON：{"all_text":["每段文字"]}'},
            {"type":"image_url","image_url":{"url":url}},
        ]}]
        out = client._run_structured_task(
            task="analysis", messages=messages, temperature=0.0,
            error_key="t", prompt_version="t", validator=lambda p:[], fallback_result={},
        )
        vlm_texts = (out.get("result") or {}).get("all_text", [])
        print(f"[{a.asset_role}] VLM reads: {vlm_texts}")

        # Check overlap
        prompt_words = set(" ".join(slot_texts))
        vlm_words = set(" ".join(vlm_texts))
        overlap = prompt_words & vlm_words
        print(f"[{a.asset_role}] Word overlap: {len(overlap)} chars -> {overlap}")
    else:
        print(f"[{a.asset_role}] No image URL")

db.close()
