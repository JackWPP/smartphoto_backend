# Brand Memory Phase 1 Handoff

## 1. Current Objective

This handoff documents the current status of the `brand memory` Phase 1 work for SmartPhoto Backend v2.

Scope frozen for this phase:

- main gallery only
- brand memory is optional
- hook point is `strategy_preview`
- deterministic scoring only
- no vector DB
- no detail-page integration
- no account/package binding in this phase

Primary business goal:

- improve same-brand main-image stability and reuse without violating platform-commercial quality requirements

## 2. What Is Already Implemented

### Data model and migration

Added:

- `app/models/brand.py`
- `app/models/brand_profile.py`
- `app/models/brand_memory_item.py`
- `app/models/brand_memory_evidence.py`
- `alembic/versions/20260419_0020_brand_memory_phase1.py`

Updated:

- `app/models/session.py`
- `app/models/__init__.py`
- `alembic/env.py`

Current schema additions:

- `sessions.brand_id`
- `sessions.brand_memory_enabled`
- `brand_memory_items` uses a natural-key unique constraint on:
  - `service_id`
  - `brand_id`
  - `platform_id`
  - `category`
  - `slot_id`
  - `memory_type`
  - `source_kind`

### API surface

Business API:

- `PUT /api/v2/sessions/{session_id}/brand`
  - bind/unbind session to a brand
  - toggle `brand_memory_enabled`

Main strategy / prompt flow:

- `POST /api/v2/sessions/{session_id}/strategy/preview`
  - accepts `brand_memory_enabled`
  - returns:
    - `brand_id`
    - `brand_memory_enabled`
    - `brand_memory_applied`
    - `brand_memory_item_ids`
    - `brand_memory_trace`

- `POST /api/v2/sessions/{session_id}/prompts/preview`
  - top-level returns:
    - `brand_id`
    - `brand_memory_enabled`
    - `brand_memory_applied`
    - `brand_memory_trace`
  - `prompts[*]` returns:
    - `brand_memory_trace`

- `GET /api/v2/sessions/{session_id}`
  - now includes:
    - `brand_id`
    - `brand_memory_enabled`

- `GET /api/v2/sessions/{session_id}/results`
  - `assets[*]` now includes:
    - `brand_memory_trace`

Admin API:

- `GET /api/admin/v1/brands`
- `POST /api/admin/v1/brands`
- `PUT /api/admin/v1/brands/{brand_id}`
- `POST /api/admin/v1/brands/{brand_id}/archive`
- `POST /api/admin/v1/brands/{brand_id}/restore`
- `GET /api/admin/v1/brands/{brand_id}/profile`
- `PUT /api/admin/v1/brands/{brand_id}/profile`
- `GET /api/admin/v1/brands/{brand_id}/memory-items`
- `PUT /api/admin/v1/brands/{brand_id}/memory-items/{memory_item_id}`
- `GET /api/admin/v1/brands/{brand_id}/memory-items/{memory_item_id}/evidence`

### Services and runtime behavior

Added:

- `app/services/brand_memory.py`
- `app/services/brand_memory_scoring.py`

Updated:

- `app/services/strategy.py`
- `app/services/prompts.py`
- `app/services/pipeline_orchestration.py`
- `app/services/pipeline_review.py`
- `app/services/preview_hashing.py`
- `app/api/admin/utils.py`
- `app/api/admin/router.py`
- `app/schemas/admin.py`
- `app/schemas/session.py`
- `app/schemas/results.py`
- `app/contracts/strategy.py`
- `app/contracts/generation.py`

Implemented behavior:

- brand memory is matched during `strategy_preview`
- prompt preview and generation reuse the persisted strategy preview
- generation snapshots carry brand-memory trace metadata
- memory sedimentation is delayed until assets are `quality_status == "passed"`
- `quality_review_mode=sample/off` still sediments passed skipped assets
- natural-key writes use dialect-specific upsert for SQLite/Postgres

## 3. Verification Already Completed

### Compile / syntax

Passed:

```powershell
python -m py_compile app/models/brand.py app/models/brand_profile.py app/models/brand_memory_item.py app/models/brand_memory_evidence.py alembic/versions/20260419_0020_brand_memory_phase1.py app/services/brand_memory.py app/services/brand_memory_scoring.py app/api/admin/brands.py app/api/admin/router.py app/api/admin/utils.py app/api/v2/sessions.py app/services/strategy.py app/services/prompts.py app/services/pipeline_orchestration.py app/services/pipeline_review.py app/services/preview_hashing.py app/schemas/admin.py app/schemas/session.py app/schemas/results.py app/contracts/strategy.py app/contracts/generation.py tests/test_integration.py tests/test_admin_console.py tests/test_worker_tasks.py
```

### Targeted regression suite

Passed:

```powershell
python -m pytest tests/test_integration.py tests/test_admin_console.py tests/test_worker_tasks.py -k "brand_memory or bind_session_brand or brand_crud_profile_memory or quality_review_job_off_marks_assets_passed or quality_review_job_sample_reviews_one_preferred_asset or sediments_passed_skipped_assets or prefers_specific_slot_over_generic or upserts_existing_natural_key or concurrent_writers" -q
```

Observed result:

- `9 passed`

### What these tests prove

- session brand bind round-trip works
- admin brand/profile/memory/evidence flows work
- strategy preview and prompt preview expose brand-memory trace
- no memory is sedimented before async review completion
- sample/off review paths still sediment passed assets
- specific memory outranks generic memory
- upsert keeps one row for the natural key
- concurrent writers collapse to one memory row

## 4. Full Test Suite Status

`python -m pytest -q` is not currently a reliable completion gate for this work.

Known unrelated repo-wide issues:

- `tests/test_stage_h_audit_script.py`
- `tests/test_stage_h_historical_read_compat.py`

Both fail at collection time with:

- `ModuleNotFoundError: No module named 'tests.test_integration'`

This is a pre-existing test-organization problem, not specific evidence that the brand-memory implementation is broken.

There are also long-running / unrelated suite failures outside the brand-memory scope, which makes full-suite execution a poor feedback loop for this task.

Recommendation:

- treat the targeted brand-memory suite above as the completion gate for this feature
- open a separate follow-up task for repo-wide test-suite stabilization

## 5. Documentation Already Updated

Updated:

- `docs/API_联调指南.md`
- `docs/生图Agent协作逻辑.md`
- `docs/运行与排障手册.md`
- `AGENTS.md`

These updates cover:

- new session brand binding endpoint
- new strategy/prompt/result fields
- admin brand endpoints
- sedimentation rules
- troubleshooting notes
- milestone log

## 6. Final Architect Review Status

Architect-style review was run multiple times during implementation.

All previously raised blockers were addressed in code and then covered by direct regression tests:

1. specific vs generic precedence
2. sedimentation timing after async quality review
3. duplicate natural-key concurrency behavior
4. sample/off-mode skipped-assets sedimentation coverage

The final spawned architect re-review did not return before timeout in the last attempt, but all previously identified blockers are now directly regression-covered.

## 7. Files Most Relevant For Next Conversation

If the next conversation needs fast context, read these first:

- `docs/brand-memory-phase1-handoff.md`
- `.omx/specs/deep-interview-brand-memory.md`
- `.omx/plans/prd-brand-memory-phase1.md`
- `.omx/plans/test-spec-brand-memory-phase1.md`
- `.omx/plans/implementation-plan-brand-memory-phase1.md`

Then inspect implementation hotspots:

- `app/api/v2/sessions.py`
- `app/api/admin/brands.py`
- `app/services/strategy.py`
- `app/services/brand_memory.py`
- `app/services/pipeline_review.py`
- `tests/test_integration.py`
- `tests/test_admin_console.py`
- `tests/test_worker_tasks.py`

## 8. Recommended Next Steps

If continuing feature work, the next logical options are:

1. build `adminfront` pages for brand/profile/memory management
2. add frontend session-level brand bind + brand-memory toggle UI
3. add metrics/dashboard surfaces for:
   - memory item counts
   - hit rates
   - same-brand first-pass usability
4. do repo-wide full-test stabilization as a separate task

## 9. Recommended Prompt For New Conversation

Use this as the new conversation opener if needed:

```text
Continue from docs/brand-memory-phase1-handoff.md.

Brand memory Phase 1 for main_gallery is already implemented and targeted tests pass.
Do not re-plan the feature.
First read:
- docs/brand-memory-phase1-handoff.md
- .omx/specs/deep-interview-brand-memory.md
- .omx/plans/prd-brand-memory-phase1.md
- .omx/plans/test-spec-brand-memory-phase1.md
- .omx/plans/implementation-plan-brand-memory-phase1.md

Then continue with: <your next concrete task here>.
```
