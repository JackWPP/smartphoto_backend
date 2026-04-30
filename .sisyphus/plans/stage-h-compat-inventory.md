# Stage H Compat Inventory

目的：在真正做 residual compat/legacy adapter 删除决策前，先把当前仓库里仍在使用或仍需观察的兼容点做成可审计台账。

状态定义：
- `保留到 H 后`：当前读写路径仍依赖，在 30-session audit、pre-prod smoke、release-window evidence 齐全前不进入删除评估。
- `满足条件后可删`：当前看起来已接近 compat boundary，仅在 Stage H 证据齐全且删除前提满足后才允许进入 removal assessment。
- `仍需更多样本确认`：当前用途成立，但删除影响面需要真实样本或更强测试后才能下结论。

## 1. copy legacy field sync
- 状态：`保留到 H 后`
- 模块：
  - `app/services/copy_normalization.py`
  - `app/services/copy_resolution.py`
  - `app/services/strategy.py`
  - `app/services/main_gallery_rules.py`
- 当前用途：
  - 继续维护 `headline/selling_points/usage_scenes/specs/style_choice` 与正式字段的双向兼容。
  - 避免旧前端输入、旧策略分支或历史 session snapshot 读到空值或脏值。
- 影响路径：
  - 写路径：`PUT /api/v2/sessions/{id}/copy`
  - 写路径：Step 3 参数回写 copy
  - 读路径：copy/result preview 的 resolved copy
  - 写路径：主图/详情页策略预览与 prompt compose
- 现有测试保护：
  - `tests/test_integration.py::test_put_parameters_updates_hero_prompt_and_syncs_legacy_copy_fields`
  - `tests/test_integration.py::test_copy_form_normalizes_legacy_list_fields`
  - `tests/test_parameter_snapshot.py`
  - `tests/test_upstream.py::test_hero_scene_prompt_prioritizes_formal_field_over_stale_legacy_scene`
- 删除前还缺的 Stage H 证据：
  - 30-session audit 中至少包含历史 copy/restore/regenerate session 样本
  - pre-prod smoke 抽样确认历史 session 重新 preview / regenerate 不丢 legacy 镜像字段
- 当前结论：
  - 不能删。先作为 Stage H 读写兼容保留。

## 2. detail visible-copy / strategy normalization
- 状态：`保留到 H 后`
- 模块：
  - `app/services/detail_pages.py::normalize_detail_strategy_preview`
  - `app/api/v2/sessions.py`
  - `app/api/v2/assets.py`
- 当前用途：
  - 规范化历史详情页 preview 结构，补齐 panel plan 的显示字段与排序。
  - 防止旧 preview 数据把结构化字段漏给结果接口或资产动作接口。
- 影响路径：
  - 读路径：`GET /api/v2/sessions/{id}/detail-pages/results`
  - 读路径：`POST /detail-pages/prompts/preview`
  - 写路径：detail regenerate / restore 时对历史 panel plan 的消费
- 现有测试保护：
  - `tests/test_integration.py::test_detail_page_results_history_preserves_panel_order_and_stitched_asset`
  - `tests/test_stage_h_historical_read_compat.py`
- 删除前还缺的 Stage H 证据：
  - 30-session audit 中 detail / partial-detail / restore-detail / carry-forward-detail 样本全覆盖
  - pre-prod smoke 中抽样确认 `panel_label/display_tags/display_module_*` 在历史读取下完整
- 当前结论：
  - 不能删。detail 历史读兼容仍依赖它。

## 3. result read-side historical compatibility helpers
- 状态：`保留到 H 后`
- 模块：
  - `app/api/v2/sessions.py`
  - `_available_versions`
  - `_version_summaries`
  - `_main_gallery_version_expectation`
  - `_detail_page_version_expectation`
- 当前用途：
  - 统一 latest/historical 结果投影。
  - 从 `job.result_payload` 回投 `expected_* / missing_* / partial summary`。
  - 防止历史版本读取时串到最新版本的 cover/missing/stitch 状态。
- 影响路径：
  - 读路径：public results/detail-results
  - 读路径：admin results/detail-results wrapper
- 现有测试保护：
  - `tests/test_pipeline_refactor_baseline.py`
  - `tests/test_integration.py`
  - `tests/test_stage_h_historical_read_compat.py`
  - `tests/test_stage_h_audit_script.py`
- 删除前还缺的 Stage H 证据：
  - 30-session audit 全量通过
  - pre-prod smoke 无 latest/historical 漂移
  - release-window 内无 `missing_* / cover_asset_id / stitched_asset / carry_forward` 串版本告警
- 当前结论：
  - 这是 Stage H 的核心保护层；在 removal assessment 前一律保留。

## 4. rule 层 compat_role 映射
- 状态：`仍需更多样本确认`
- 模块：
  - `app/services/main_gallery_rules.py`
  - `app/services/rule_packs.py`
  - `app/services/rule_resolution.py`
  - `app/api/v2/platforms.py`
  - `app/services/strategy.py`
- 当前用途：
  - 在新 `slot_id` 体系与旧 `role` 命名之间保留映射。
  - 支撑 Temu 五槽位与 Alibaba 五槽位的同构消费。
- 影响路径：
  - 读路径：平台规则读取、策略预览、results 中 `role/slot_id` 对照
  - 写路径：planner 输出归一化、slot preference 锁定
- 现有测试保护：
  - `tests/test_integration.py` 中的 Alibaba 规则与 preview 用例
  - `tests/test_rule_resolver.py`
- 删除前还缺的 Stage H 证据：
  - 30-session audit 中 Alibaba main 真实样本通过
  - pre-prod smoke 抽样确认 Alibaba historical 读取下 `version_summaries` / slot 对照不漂移
- 当前结论：
  - 先不删。需要更多真实 Alibaba 样本再评估。

## 5. pipeline compat wrappers
- 状态：`满足条件后可删`
- 模块：
  - `app/services/pipeline.py` 中的 compat wrappers
- 当前用途：
  - 主要用于 monkeypatch 测试与 worker entrypoint 兼容边界。
- 影响路径：
  - 写路径：worker hot path 仍通过 wrapper 注入依赖。
- 现有测试保护：
  - `tests/test_worker_tasks.py`
- 删除前提：
  - `tests/test_worker_tasks.py` 不再依赖 `app.services.pipeline.*` monkeypatch
  - repo 内外没有内部脚本直接 import 这些 helper
  - Stage H 证据已证明读侧与 worker hot path 都稳定
- 当前结论：
  - 这类属于“可删候选”，但必须等 Stage H 证据闭环后再动。

## 6. 文档中残留的 old-path / shadow 表述
- 状态：`满足条件后可删`
- 模块：
  - `.sisyphus/plans/pipeline-refactor-plan.md`
  - 若干历史文档条目
- 当前用途：
  - 历史计划描述，不是运行时行为。
- 影响路径：
  - 认知路径，不影响代码执行。
- 现有测试保护：
  - 无
- 删除前提：
  - Stage H 现行目标已稳定为“历史读兼容审计 + inventory + release observation”
  - compat removal decision 已形成，不再需要旧措辞辅助过渡
- 当前结论：
  - 可以继续收敛文档表述，但不作为 Stage H 的核心交付物。

## 7. 历史 `job.result_payload` 依赖强度
- 状态：`仍需更多样本确认`
- 模块：
  - `app/api/v2/sessions.py`
- 当前用途：
  - `missing_slot_ids/missing_panel_ids/expected_*` 优先从 `job.result_payload` 回投。
- 影响路径：
  - 历史 partial-success 读取
  - restore/regenerate 后旧版本回看
- 现有测试保护：
  - `tests/test_stage_h_historical_read_compat.py`
  - `tests/test_pipeline_refactor_baseline.py`
  - `tests/test_stage_h_audit_script.py`
- 删除前还缺的 Stage H 证据：
  - 30-session audit 中必须覆盖 partial main / partial detail / restore / regenerate 样本
  - pre-prod smoke 抽样确认历史 partial 读取与 `jobs.result_payload` 一致
- 当前结论：
  - 保留现有 fallback；样本不足前不下删除结论。

## 8. text-edit 历史版本读侧稳定性
- 状态：`仍需更多样本确认`
- 模块：
  - `app/api/v2/assets.py`
  - `app/services/pipeline_orchestration.py`
  - `app/services/pipeline_persistence.py`
  - `app/api/v2/sessions.py`
- 当前用途：
  - 允许基于已有主图做 `edit-text` 并物化新版本。
- 影响路径：
  - 主图历史版本读取
  - `version_summaries.job_type`
  - `generation_snapshot.edit_mode/source_asset_id/source_version_no`
- 现有测试保护：
  - `tests/test_stage_h_historical_read_compat.py`
- 删除前还缺的 Stage H 证据：
  - 30-session audit 中至少一个真实 `text_edit_main` 样本通过
  - pre-prod smoke 抽样确认 public/admin 对 text-edit 历史版本读取一致
- 当前结论：
  - 现有覆盖仍偏最小，发布前需要真实样本补证。
