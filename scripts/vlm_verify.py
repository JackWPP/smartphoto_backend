"""Use VLM to read actual text on generated image and compare with prompt parser."""
import sys, io, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from app.db.session import SessionLocal
from app.models.session import SessionModel
from app.models.asset import AssetModel
from app.services.upstream import WhataiClient
from app.services.storage import public_url_for

db = SessionLocal()
s = db.query(SessionModel).filter(
    SessionModel.latest_result_version > 0
).order_by(SessionModel.updated_at.desc()).first()

a = db.query(AssetModel).filter(
    AssetModel.session_id == s.id,
    AssetModel.version_no == s.latest_result_version,
    AssetModel.visibility_status == 'visible',
).first()

url = public_url_for(a.image_url) if a.image_url else None
if not url:
    print("No image URL found")
    db.close()
    sys.exit(1)

print(f"Asset: {a.id[:8]} slot={a.asset_role}")
print(f"URL: {url[:80]}...")

client = WhataiClient()
messages = [{
    "role": "user",
    "content": [
        {"type": "text", "text": (
            "请仔细读取这张电商图片上的所有可见文字。按视觉层级从大到小、从上到下返回。"
            '只返回JSON：{"largest_text":"最大最醒目的文字","second_largest":"第二醒目的文字",'
            '"small_labels":["所有小标签文字"],"all_text_by_size":["按视觉大小排序的所有文字片段"]}'
        )},
        {"type": "image_url", "image_url": {"url": url}},
    ],
}]

outcome = client._run_structured_task(
    task="analysis", messages=messages, temperature=0.0,
    error_key="t", prompt_version="t", validator=lambda p: [],
    fallback_result={},
)

result = outcome.get("result") or {}
print("\n=== VLM 读到的图中实际文字 ===")
print(f"最大文字: {result.get('largest_text', 'N/A')}")
print(f"第二醒目: {result.get('second_largest', 'N/A')}")
print(f"小标签: {result.get('small_labels', [])}")
print(f"按大小排序: {result.get('all_text_by_size', [])}")

# Compare
from app.services.prompts import parse_visible_copy_slots
fp = (a.generation_snapshot or {}).get('final_prompt', '')
slots = parse_visible_copy_slots(fp)

print(f"\n=== Prompt 解析槽位 ({len(slots)}) ===")
for s in slots:
    print(f"  {s['slot']}: '{s['text'][:60]}'")

# Cross-reference: which VLM text matches which slot?
all_vlm = " ".join(result.get('all_text_by_size', []))
print(f"\n=== 槽位匹配检查 ===")
for s in slots:
    txt = s['text'][:30]
    found = txt in all_vlm
    print(f"  {'MATCH' if found else 'MISS'}: {s['slot']}='{txt}'")

db.close()
