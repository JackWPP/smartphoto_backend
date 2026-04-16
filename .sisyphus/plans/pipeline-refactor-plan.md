# SmartPhoto Backend Pipeline Refactor Plan

## Goal

Refactor the current generation system into a stable pipeline before any brand-memory work starts.

Target runtime architecture:

1. Input Preparation
2. Strategy Planning
3. Prompt Composition
4. Render Execution
5. Asset Persistence
6. Result Projection

Brand memory is explicitly out of scope until this plan completes through Stage H.

## Current-to-target responsibility mapping

### Input Preparation
- Current owners: `app/services/copy_normalization.py`, `app/services/parameter_snapshot.py`, `app/services/reference_images.py`
- Also includes input/session normalization logic currently scattered inside `strategy.py`, `detail_pages.py`, and `pipeline.py`
- Preserved cross-cutting concerns: request shape compatibility, session input normalization

### Strategy Planning
- Current owners: planner-facing logic in `app/services/strategy.py` and `app/services/detail_pages.py`
- Inputs come from rule packs, slot rules, panel rules, confirmed copy, analysis snapshot, parameter snapshot, reference manifests

### Prompt Composition
- Current owners: `app/services/prompts.py`, `app/services/prompt_safety.py`, `app/services/visible_copy_policy.py`
- Includes detail prompt assembly logic currently in `detail_pages.py`

### Render Execution
- Current owners: submit / poll / download responsibilities inside `app/services/pipeline.py`, `app/services/upstream.py`, `app/services/upstream_image.py`

### Asset Persistence
- Current owners: asset writes, versioning, carry-forward materialization, snapshot persistence, job result persistence inside `app/services/pipeline.py`

### Result Projection
- Current owners: result schemas and result/detail-result read paths in API/result serialization code

### Cross-cutting concerns preserved across all stages
- DB persistence semantics
- Async job/event semantics
- Idempotency semantics
- Locking / concurrency semantics
- `version_no` / `carry_forward` semantics
- Read compatibility during transition

## Global execution rules

### Fixed execution order
1. A Baseline Freeze
2. B Contract Stabilization
3. C Slot/Rule Single Source of Truth
4. D Prompt Pipeline Extraction
5. E Copy Flow Consolidation
6. F Hash Decoupling
7. G Pipeline Orchestration Decomposition
8. H Old Path Removal Assessment

### Dependency gates
- A is prerequisite for everything.
- B must complete before C-H because contracts must stabilize first.
- C must complete before D/E because rule inputs must have one source before prompt/copy layers are extracted.
- D must complete before E because copy consolidation depends on stable prompt consumption boundaries.
- E must complete before F/G because hash and orchestration depend on stable intermediate structures.
- F must complete before G because cache boundary changes must be isolated from orchestration changes.
- G must complete before H because old-path removal is evaluated only after dual-path parity under the new orchestration.

### Freeze rules during the refactor
- No brand-memory implementation before H completes.
- No new platform-specific hotfix branches in generation hot paths.
- No new patch-style env sprawl for planner/render flow.
- No removal of old serving path before H passes.

## Anti-collapse operating model

### Shadow rules
- Side-effect-free stages (`Input Preparation`, `Strategy Planning`, `Prompt Composition`, `Hash Decoupling`) use true in-memory dual execution on the same input.
- Side-effectful stages (`Render Execution`, `Asset Persistence`, job-event writes) never duplicate upstream submits, downloads, asset writes, or job-event writes.
- For side-effectful stages, shadow comparison uses captured old-path artifacts only: prompt payloads, upstream task metadata, poll/download metadata, normalized render outputs, persistence payload candidates, and result-projection payloads.
- Old path remains the sole serving path until cutover approval.

### Cross-cutting ownership
- Orchestration alone owns lock acquisition/release, idempotency checks and mutations, event sequencing/emission, and `pipeline_path` routing.
- Extracted stages are forbidden from independently acquiring locks, mutating idempotency records, or emitting job events.
- Render Execution owns submit/poll/download retry behavior only.
- Asset Persistence owns DB writes, `version_no` allocation, `carry_forward` materialization, snapshot persistence, and job result persistence only.
- Result Projection owns read-compat normalization adapters during transition.

### In-flight transition rules
- Old job old path; new job new path.
- Path choice is keyed by persisted `pipeline_path` marker plus the release snapshot used when the job entered the pipeline.
- No mid-flight path switching is allowed.

### Parity adjudication
- Required invariants:
  - result schema
  - event order semantics
  - `version_no` / `carry_forward` semantics
  - partial-success semantics
  - result readability
  - cache hit/miss intent
- Allowed diffs only:
  - non-functional debug metadata
  - order-insensitive timestamps/internal fields
  - known transitional adapter diffs
- Any other diff is unexplained by default.
- Review authority:
  - dev owner classifies the diff
  - QA owner reviews the classification
  - tech owner gives final approval
  - if there is no same-day agreement, progress is blocked

### Rollout and rollback thresholds
- Canary = internal traffic or <=5% eligible jobs.
- One release window = 7 consecutive days or 500 eligible jobs, whichever is later.
- Promotion from shadow to serving requires 100% baseline fixture pass and 0 unexplained diffs on required invariants.
- Rollback triggers:
  1. any unexplained result/event/version semantic drift
  2. 5xx increase >20% over prior 7-day baseline
  3. worker backlog increase >30% sustained for 30 minutes
  4. cache miss ratio increase >25% after Stage F without intentional invalidation
  5. `partial_succeeded` / failed ratio worsens >15% on same job class
  6. duplicate asset/event persistence threshold = 1 incident
- Rollback procedure timing:
  - freeze promotion within 15 minutes
  - cut back to old serving path within 30 minutes
  - incident note within 2 hours

### Promotion gate owners
- dev owner submits stage completion evidence
- QA owner executes stage test matrix
- platform/backend owner verifies invariants
- tech owner is sole cutover/rollback approver
- ops/oncall owner monitors 5xx, backlog, queue latency, and resources during G/H

## Stage plan

### A. Baseline Freeze

**Goal**
- Define the non-collapse baseline before any hot-path refactor.

**Scope**
- Tests, fixtures, baseline snapshots, observability only.

**Moved logic**
- None.

**Preserved logic**
- All current runtime behavior.

**Deleted logic**
- None.

**Frozen interfaces after completion**
- Current API result shapes
- worker event sequence semantics
- version semantics

**Provisional interfaces/components**
- None.

**Go / No-Go exit gate**
- Baseline fixtures exist for default main-gallery, Alibaba main-gallery, and detail-page flows.
- Snapshots cover `strategy_preview`, `prompt preview`, `results`, `detail results`, job events, and version semantics.

**Exact tests**
- API snapshot regression
- event sequence regression
- version / `carry_forward` regression

**QA procedure**
- Run: `pytest -q tests/test_pipeline_refactor_baseline.py`
- Fixtures under validation: default main-gallery baseline, Alibaba main-gallery baseline, detail-page baseline
- Pass conditions:
  - all tests pass
  - strategy preview / results / detail results / job-event invariants stay stable
  - no unexplained baseline drift

**Rollback posture**
- Test-only stage; direct revert if needed.

### B. Contract Stabilization

**Goal**
- Turn implicit inter-stage dicts into explicit contracts.

**Scope**
- Introduce explicit contracts for `AssetPlanItem`, `PromptPlanItem`, `DetailPanelPlanItem`, `CopyBlocks`, `GenerationSnapshot` payloads.

**Moved logic**
- Implicit dict structures become typed/validated contracts.

**Preserved logic**
- Behavior and payload meaning.

**Deleted logic**
- None yet; adapters stay.

**Frozen interfaces after completion**
- Inter-stage data contracts.

**Provisional interfaces/components**
- Adapters from old dict payloads.

**Go / No-Go exit gate**
- All inter-stage payloads validate against contracts and old fixtures remain 100% schema-compatible.

**Exact tests**
- schema round-trip tests
- serialization/deserialization tests
- backward-compat fixture tests

**QA procedure**
- Run: `pytest -q tests/test_pipeline_refactor_baseline.py tests/test_integration.py -k "strategy_preview or detail_strategy_preview or prompts_preview or results"`
- Fixtures under validation: Phase A baseline fixtures plus old payload-shape fixtures introduced in this stage
- Pass conditions:
  - all contracts validate
  - old payload shapes still deserialize without field loss
  - baseline fixtures remain schema-compatible

**Rollback posture**
- Keep adapters and old fields; revert contract entrypoints if required.

### C. Slot/Rule Single Source of Truth

**Goal**
- Make slot/panel/platform rule origin singular and traceable.

**Scope**
- Unify slot preset, overlay, and display mapping responsibilities behind one rule interpretation source.

**Moved logic**
- Duplicate runtime rule ownership moves into one resolver/source.

**Preserved logic**
- Effective business behavior on baseline fixtures.

**Deleted logic**
- Duplicate runtime rule ownership only after parity is proven.

**Frozen interfaces after completion**
- Rule resolution interface.

**Provisional interfaces/components**
- Legacy resolver behind feature flag.

**Go / No-Go exit gate**
- For any `platform_id + asset_family + slot_id/panel_type`, one can identify a single rule source.
- Baseline fixture parity for `slot_id` / `expression_mode` / `panel_type` / `rule_pack_id` is 100%.

**Exact tests**
- rule parity tests
- overlay regression tests
- Chinese visible-copy policy regression

**QA procedure**
- Run: `pytest -q tests/test_pipeline_refactor_baseline.py tests/test_integration.py -k "alibaba or strategy_preview or detail-pages/strategy/preview or prompt_preview"`
- Fixtures under validation: default main-gallery, Alibaba main-gallery, detail-page rule-resolution fixtures
- Pass conditions:
  - every tested slot/panel resolves to a single rule source
  - `slot_id` / `expression_mode` / `panel_type` / `rule_pack_id` outputs match baseline expectations exactly
  - Chinese visible-copy policy behavior does not drift

**Rollback posture**
- Keep legacy resolver serving behind flag.

### D. Prompt Pipeline Extraction

**Goal**
- Extract prompt building into explicit deterministic stages.

**Scope**
- `normalize -> sanitize -> visible-copy policy -> compose blocks -> final prompt` chain.

**Moved logic**
- Prompt assembly responsibilities move out of mixed branches into explicit composer stages.

**Preserved logic**
- Final prompt semantics on baseline fixtures.

**Deleted logic**
- None until parity is proven.

**Frozen interfaces after completion**
- Prompt composer stage boundaries.

**Provisional interfaces/components**
- Old composer path for parity.

**Go / No-Go exit gate**
- Same input produces deterministic prompt output across repeated runs.
- Visible-copy and sanitize regressions are zero on baseline fixtures.

**Exact tests**
- golden prompt-block tests
- prompt text regression
- sanitize regression
- detail prompt regression

**QA procedure**
- Run: `pytest -q tests/test_pipeline_refactor_baseline.py tests/test_upstream.py tests/test_integration.py -k "prompt or sanitize or visible"`
- Fixtures under validation: main prompt baseline, detail prompt baseline, visible-copy samples, sanitize samples
- Pass conditions:
  - same input yields deterministic prompt output
  - prompt blocks match golden expectations
  - sanitize/visible-copy outputs do not regress on baseline fixtures

**Rollback posture**
- Keep old composer path available for parity and rollback.

### E. Copy Flow Consolidation

**Goal**
- Unify copy precedence and source attribution.

**Scope**
- Consolidate precedence among explicit session input, parameter-derived values, planner-enriched values, and sanitizer fallback.

**Moved logic**
- Distributed copy merge logic moves into one merge policy.

**Preserved logic**
- Baseline text meaning and slot/panel copy intent.

**Deleted logic**
- Duplicate copy rewrites only after parity is proven.

**Frozen interfaces after completion**
- Copy merge policy and source-attribution contract.

**Provisional interfaces/components**
- Old merge path behind switch.

**Go / No-Go exit gate**
- Every user-visible text field has source attribution.
- No field is rewritten in multiple places without the single merge policy.

**Exact tests**
- copy merge matrix
- char-limit tests
- zh/en copy policy tests
- source-attribution tests

**QA procedure**
- Run: `pytest -q tests/test_parameter_snapshot.py tests/test_integration.py -k "copy or parameters or headline"`
- Fixtures under validation: explicit-copy, parameter-derived copy, planner-enriched copy, bilingual copy samples
- Pass conditions:
  - merge precedence matches the single policy
  - every user-visible field has source attribution
  - char limits and zh/en copy behavior remain stable

**Rollback posture**
- Keep old merge path behind a switch.

### F. Hash Decoupling

**Goal**
- Decouple cache invalidation into layered hashing.

**Scope**
- Split strategy/detail hash into config/input/reference layers.

**Moved logic**
- Deep-object cache invalidation moves into layered hashing.

**Preserved logic**
- Cache correctness and preview reuse semantics.

**Deleted logic**
- Old monolithic hash only after hit/miss parity is proven.

**Frozen interfaces after completion**
- Hash layer boundaries.

**Provisional interfaces/components**
- Old hash path for compare.

**Go / No-Go exit gate**
- Expected cache-hit and expected cache-miss scenarios behave exactly as specified.
- No unrelated-field cache invalidation remains.

**Exact tests**
- cache hit/miss behavior tests
- hash-layer isolation tests

**QA procedure**
- Run: `pytest -q tests/test_integration.py -k "cached_snapshot or input_hash or reuses_cached_snapshot"`
- Fixtures under validation: unchanged-input cache fixtures, changed-copy fixtures, changed-platform fixtures, changed-reference fixtures
- Pass conditions:
  - intended hit cases hit
  - intended invalidation cases miss
  - unrelated-field changes do not invalidate cache

**Rollback posture**
- Keep old hash path available until parity is proven.

### G. Pipeline Orchestration Decomposition

**Goal**
- Split the monolithic pipeline into explicit orchestration stages.

**Scope**
- `prepare_inputs`, `plan_strategy`, `compose_prompts`, `submit_render`, `poll_download`, `persist_assets`, `finalize_results`.

**Moved logic**
- Orchestration responsibilities move out of monolithic `pipeline.py` into explicit steps.

**Preserved logic**
- job semantics, events, retries, partial success, and persistence behavior.

**Deleted logic**
- Old monolithic orchestration only after dual-path parity is proven.

**Frozen interfaces after completion**
- Orchestration step interfaces.

**Provisional interfaces/components**
- Old pipeline path kept serving while new path shadows.

**Go / No-Go exit gate**
- New orchestration in shadow mode matches old path on events, assets, results, and version semantics across baseline and pre-release suites.

**Exact tests**
- job integration tests
- single-slot generation tests
- partial-success tests
- detail full-chain tests
- retry/timeout semantics tests
- result compatibility tests
- failure-injection coverage for upstream timeout / partial failure / retry semantics

**QA procedure**
- Run: `pytest -q tests/test_pipeline_refactor_baseline.py tests/test_worker_tasks.py tests/test_integration.py`
- Fixtures under validation: baseline generation sessions, partial-failure sessions, retry/timeout monkeypatch scenarios, historical version/carry-forward scenarios
- Pass conditions:
  - new orchestration shadow outputs match old-path artifacts on required invariants
  - no duplicate submit/write/event side effects occur in shadow mode
  - version, carry-forward, partial-success, and retry semantics match baseline

**Rollback posture**
- Old pipeline path remains serving until cutover approval.

### H. Old Path Removal Assessment

**Goal**
- Decide whether the old serving path can be removed.

**Scope**
- No new architecture work. Validation and removal decision only.

**Moved logic**
- None.

**Preserved logic**
- New path serving behavior.

**Deleted logic**
- Old path only if all invariants hold over one release window.

**Frozen interfaces after completion**
- New pipeline path as sole path.

**Provisional interfaces/components**
- None if removal passes; adapters remain if not.

**Go / No-Go exit gate**
- One release window passes with zero rollback triggers hit.
- Historical-read compatibility passes for at least 30 sessions across default main / Alibaba main / detail / partial / `carry_forward` cases, with 100% field completeness and no semantic drift in `asset_count`, `ready_count`, `available_versions`, `cover_asset_id`, `missing_*` outputs.

**Exact tests**
- dual-path parity review
- pre-prod smoke
- production canary observation
- historical compatibility verification across at least 30 sessions

**QA procedure**
- Run locally/pre-prod: `pytest -q tests/test_pipeline_refactor_baseline.py tests/test_integration.py tests/test_worker_tasks.py`
- Run pre-prod smoke:
  - `curl http://127.0.0.1:8000/healthz`
  - `curl -H "X-App-Key: <app-key>" http://127.0.0.1:8000/api/v2/sessions/<session_id>/results`
  - `curl -H "X-App-Key: <app-key>" http://127.0.0.1:8000/api/v2/sessions/<session_id>/detail-pages/results`
- Historical validation dataset: at least 30 sessions spanning default main / Alibaba main / detail / partial / `carry_forward`
- Pass conditions:
  - full release-window gates pass
  - historical sessions read through the new projection path with 100% field completeness
  - no semantic drift in `asset_count`, `ready_count`, `available_versions`, `cover_asset_id`, `missing_*`

**Rollback posture**
- Do not remove old path or compatibility adapters unless all H gates pass.
