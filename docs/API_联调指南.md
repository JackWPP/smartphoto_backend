# API 联调指南（以当前实现为准）

## 1. 基础约定

### 1.0 本轮联调重点
- 浏览器上传推荐改为：
  - `POST /uploads/presign`
  - 直传对象存储
  - `POST /uploads/complete`
- 当前实现已收口为纯图片 SaaS：
  - 所有图片主链路都要求 `X-App-Key`
  - 后端只认 `service_id + session_id`
  - `/auth/*`、`/account/*`、`/guest/*` 已下线并返回 `410 feature_removed`
  - 主图与详情页必须复用同一个 `session_id`
- 业务表中持久化的是稳定 `object_key`，接口返回的 `url/image_url/thumbnail_url` 已改为临时可访问 URL
- 主图与详情页结果接口都已支持：
  - `requested_version`
  - `available_versions`
  - `version_summaries`
- 单图重生接口 `POST /assets/{asset_id}/regenerate` 现在有两种 job_type：
  - 主图：`regenerate_asset`
  - 详情页 panel：`regenerate_detail_panel`
- Step 3 默认仍是单模型单次调用，当前默认模型由 `whatai_parameter_model` 控制，默认值为 `gemini-3-flash-preview`
- `GET /jobs/{job_id}` 已补 timing 字段，前端可直接展示任务总耗时和阶段耗时
- Apifox 请始终重新导入 `docs/openapi/smartphoto_backend_openapi.json`，不要手改字段定义

### 1.1 Base URL
- 前缀：`/api/v2`
- 健康检查：`GET /healthz`
- OpenAPI：`GET /openapi.json`
- Apifox 导入文件：`docs/openapi/smartphoto_backend_openapi.json`
- 图片主链路统一请求头：
  - `X-App-Key: <server-app-key>`
- 若前端与后端跨域部署，后端必须显式配置 `CORS_ALLOW_ORIGINS`，且前端请求需启用 credentials

### 1.1.1 OpenAPI 导出
```bash
./.venv/bin/python scripts/export_openapi.py
```

说明：
- 该命令会导出当前代码实现对应的 OpenAPI JSON
- 导出文件可直接导入 Apifox
- 若接口有变更，优先重新导出后再同步给联调方
- 建议联调流程：
  - 每次后端 schema/响应结构有调整，先重新导出 `docs/openapi/smartphoto_backend_openapi.json`
  - 在 Apifox 中直接重新导入同名文件覆盖接口定义
  - 不要手工在 Apifox 内维护字段，否则很容易和代码实现漂移

### 1.2 统一响应
成功：
```json
{
  "code": 0,
  "message": "success",
  "data": {}
}
```

失败：
```json
{
  "code": 40001,
  "message": "invalid_request",
  "data": null
}
```

### 1.3 关键状态与枚举
- Session 状态：`created` `images_uploaded` `analyzing` `analyzed` `platform_selected` `copy_ready` `strategy_ready` `generating` `completed` `failed`
- Job 状态：`queued` `running` `succeeded` `partial_succeeded` `failed`
- 通用任务事件：`job_queued` `job_started` `job_progress` `asset_ready` `job_partial_succeeded` `job_succeeded` `job_failed`
- 详情页专属事件：
  - `detail_strategy_ready`
  - `detail_panel_render_started`
  - `detail_panel_render_succeeded`
  - `detail_panel_render_failed`
  - `detail_stitched_ready`

### 1.4 常用错误码
- `40002` `invalid_session_status`
- `40003` `invalid_platform`
- `40004` `invalid_copy_field`
- `40005` `too_many_images`
- `40006` `unsupported_file_type`
- `40007` `file_too_large`
- `40008` `missing_required_images`
- `40101` `unauthorized`
- `41001` `feature_removed`
- `40401` `session_not_found`
- `40402` `job_not_found`
- `40403` `asset_not_found`
- `40901` `job_already_running`
- `40902` `duplicate_idempotency_key`
- `50201` `upstream_llm_error`
- `50202` `upstream_image_error`

## 2. 按 6 步流程联调

### Step 1 上传图片
- 前置状态：`created` 或 `images_uploaded`
- 接口：
  - `POST /sessions`
  - `POST /uploads/presign`
  - `POST /uploads/complete`
  - `POST /sessions/{session_id}/images`
  - `DELETE /sessions/{session_id}/images/{image_id}`
- 鉴权：
  - 所有以上接口都要求 `X-App-Key`
  - 同一 `session_id` 只能被同一个 `service_id` 访问
- 推荐生产模式：
  - 前端先调用 `POST /uploads/presign`
  - 再直传 OSS / S3 兼容对象存储
  - 最后调用 `POST /uploads/complete`
- `upload_kind`：
  - `session_image`
  - `detail_style_image`
  - `parameter_attachment`
  - `strategy_reference_image`
- 关键字段：
  - `slot_type`: `front | angle45 | side | extra`
  - `display_order`: 建议按前端展示顺序传入
- 校验规则（当前实现）：
  - MIME：`image/jpeg | image/png | image/webp`
  - 单图大小：<= 10MB
  - 单 session 最多 6 张
- 成功后：session 从 `created` 进入 `images_uploaded`
- 已进入后续步骤的 session 在商品图 upload/delete 后：
  - 不再自动触发 `analysis` job
  - 只会把 `analysis_snapshot.reanalysis_required=true`
  - 保留旧 `analysis_snapshot` 内容供排障，但不会递增 `analysis_version`，也不会改写 `analysis_updated_at`
  - 同时清空 `strategy_preview/detail_strategy_preview`
  - 需要前端显式再次调用 `POST /sessions/{session_id}/analysis`
- 常见错误：`40005` `40006` `40007`
- 并发/幂等：无 Idempotency-Key
- 兼容说明：
  - 旧的 multipart 上传接口仍保留给本地/dev fallback
  - 生产环境不建议继续让浏览器把大文件经 API 进程转发

### Step 2 分析
- 前置状态：建议至少 1 张未删除图片
- 接口：
  - `POST /sessions/{session_id}/analysis`
  - `GET /sessions/{session_id}/analysis`
- 成功后：
  - 生成 `analysis` job（队列 `q.analysis`）
  - session 状态：`analyzing -> analyzed`
  - 触发新一轮 `analysis` 时，后端会先清空旧 `parameter_snapshot`，避免 Step 3 继续读取上一轮参数结果
  - 若历史脏数据导致 session 仍停留在 `created`，当前实现会在触发分析时自动补正为 `images_uploaded -> analyzing`，避免 worker 侧再报 `cannot transition created -> analyzing`
  - 只有当新的 `analysis_snapshot` 已成功落库后，job 才会进入 `succeeded`
  - 自动写入 `analysis_snapshot`
  - `GET /sessions/{session_id}/analysis` 与 `GET /sessions/{session_id}` 现在都会同步返回 freshness 字段：
    - `analysis_version`
    - `analysis_updated_at`
    - `latest_analysis_job_id`
  - `analysis_version` 只在 analysis job 成功落库新结果时递增
  - `analysis_updated_at` 只在 analysis job 成功落库新结果时更新
  - 当前实现会把 session 上传图片以内联图像内容的方式发给上游分析模型，不再只传文本
  - 当前默认路由为：`analysis / 主图 planner / 详情页 planner / 参数提取 = WhatAI + Gemini`；OpenRouter 只保留给文本辅助任务或显式试模型
  - `analysis_snapshot` 额外包含：
    - `analysis_source`
    - `category_candidates[{category,confidence,reason}]`
    - `scene_tags`
    - `selling_point_entities`
    - `risk_flags`
    - `evidence_scores[{structure,proportion,scene,text}]`
    - `detected_view_slots`
    - `supplement_image_recommendations[{slot_type,label,reason,priority,upload_goal,must_show,framing_hint,example_caption,image_kind?}]`
    - `reanalysis_required`
    - `provider`
    - `model`
    - `prompt_version`
    - `repair_round`
    - `source`
  - `category_candidates` 现在优先从后台启用的“全局品类库”中选择；仅在确实无法归类时回退 `其他`
  - Step 2 的 `supplement_image_recommendations` 语义已收口为“建议补传什么图片”，不是抽象拍摄技巧：
    - `slot_type` 仍限制为 `front | angle45 | side | extra`
    - `extra` 允许额外细分 `image_kind`，当前至少支持：
      - `detail_closeup`
      - `water_tank`
      - `filter_structure`
      - `size_in_hand`
      - `use_scene_real`
    - `upload_goal` 描述这张补图要解决什么信息缺口
    - `must_show` 描述图片里必须出现的真实结构元素
    - `framing_hint` 描述前端可提示给用户的取景方式
    - `example_caption` 仅作为补图意图示例，不直接等价于最终上图文案
  - `analysis_snapshot` 额外包含 `reference_summary`：
    - `shape`
    - `colors`
    - `materials`
    - `structures`
    - `must_keep`
    - `proportion_note`
    - `control_panel_note`
    - `transparent_parts_note`
    - `structure_anchor_points`
    - `do_not_move_features`
    - `scene_fit_notes`
  - `selling_point_entities/risk_flags/evidence_scores` 会作为后续 Step 5 策略预览和生成阶段的 prompt/harness 约束输入：
    - `selling_point_entities` 用于绑定宠物、透明水箱、控制面板、滤芯、尺寸等真实卖点实体
    - `risk_flags` 用于提示结构敏感、比例敏感、场景落地敏感等风险
    - `evidence_scores` 用于控制保守表达和保真降级，不再在生成后触发逐张复检
  - 若 `confirmed_copy` 为空，自动写入草稿默认值
- 常见错误：`40008`（无可用图片）
- 幂等：支持 `Idempotency-Key`

### Step 3 选择平台
- 前置状态：`images_uploaded` / `analyzed` / `platform_selected`
- 接口：`PUT /sessions/{session_id}/platform-selection`
- 关键字段：
  - `selected_platform_ids`（至少一个）
  - `active_platform_id`（必须在选中列表内）
- 成功后：状态写为 `platform_selected`
- 若 `active_platform_id` 相比之前发生变化：
  - 后端会把旧 `analysis_snapshot` 标记为 `reanalysis_required=true`
  - 保留旧分析内容供前端/后台对比排障
  - 清空 `parameter_snapshot`
  - 清空 `strategy_preview/detail_strategy_preview`
  - 不会递增 `analysis_version`，也不会改写 `analysis_updated_at`
- 常见错误：`40003`
- 并发/幂等：无 Idempotency-Key

### Step 4 copy 确认与字段 regenerate
- 前置状态：建议 `platform_selected` 或 `analyzed`
- 接口：
  - `GET /sessions/{session_id}/copy`
  - `PUT /sessions/{session_id}/copy`
  - `POST /sessions/{session_id}/copy/regenerate`
  - `GET /sessions/{session_id}/copy/regenerate/{job_id}`
- Step 4 正式字段：
  - `product_name`
  - `category`
  - `hero_scene`
  - `core_selling_points`
  - `key_parameters`
  - `product_advantages`
  - `style_preset_id`
  - `style_custom`
- 兼容字段：
  - `style_choice`：deprecated，只兼容旧前端读写
  - `headline/selling_points/usage_scenes/specs`：legacy 输入，后端会转换成正式字段
- regenerate 支持字段：
  - 正式字段：`hero_scene` `core_selling_points` `key_parameters` `product_advantages`
  - legacy 字段：`headline` `selling_points` `usage_scenes` `specs`
- 语义：regenerate 结果写在 `job.result_payload.generated_fields`，**不会自动覆盖** `confirmed_copy`
- 常见错误：`40004` `40402`
- 幂等：`POST /copy/regenerate` 支持 `Idempotency-Key`

### Step 4.5 参数附件与参数提取
- 参数附件接口：
  - `POST /sessions/{session_id}/parameter-attachments`
  - `GET /sessions/{session_id}/parameter-attachments`
  - `DELETE /sessions/{session_id}/parameter-attachments/{attachment_id}`
  - 支持图片与 PDF；不相关内容会在后续提取结果中返回 `relevance_status=invalid`
- 参数提取接口：
  - `POST /sessions/{session_id}/parameters/extract`
  - `GET /sessions/{session_id}/parameters`
  - `PUT /sessions/{session_id}/parameters`
  - `POST /sessions/{session_id}/parameters/complete` 仅保留兼容，不再是默认前端流程
- 当前实现行为：
  - 提取 job_type 为 `extract_parameters`
  - Step 3 已收口为“单次调用的小型文案策划 Agent”，默认一次 `extract` 直接产出用户可编辑整页结果
  - 若刚刚重跑过 `analysis`，旧 `parameter_snapshot` 会先被清空；前端应重新调用一次 `POST /parameters/extract`
  - 参数提取模型默认由 `whatai_parameter_model` 控制，当前默认值为 `gemini-3-flash-preview`
  - 没有附件时：
    - 仍允许调用 `POST /parameters/extract`
    - 主要依据 `analysis_snapshot + 当前 session 商品图 + confirmed_copy`
    - 允许轻策划，但不能凭空创造 analysis 和图片里没有依据的功能/参数
  - 有附件时：
    - 附件优先级高于 analysis
    - 图片附件直接作为多模态输入喂给参数提取模型
    - PDF 附件先转成 markdown，再把 markdown 正文交给参数提取模型解释
    - 默认整页重算，允许覆盖旧的 analysis-only Step3 结果
  - 提取完成后会默认用 `replace_all` 模式覆盖 Step 4 正式字段：
    - `hero_scene`
    - `core_selling_points`
    - `key_parameters`
    - `product_advantages`
  - `parameter_snapshot` 至少包含：
    - `relevance_status`
    - `rejection_reason`
    - `hero_scene`
    - `core_selling_points`
    - `key_parameters`
    - `product_advantages`
    - `feature_highlights`
    - `source_mode`
    - `evidence_priority`
    - `evidence_summary`
    - `provider`
    - `model`
    - `prompt_version`
    - `source`
- 兼容说明：
  - `POST /sessions/{session_id}/parameters/complete` 仍然保留
  - 但它不再属于默认前端主链，应视为兼容增强，而不是 Step3 的必经步骤
- 补充说明：
  - 当前参数提取不走 OCR
  - 提取结果是“可用抽取 + 人工可改”，不会强承诺复杂图表/版面还原精度
  - `GET /sessions/{session_id}/parameters` 会同时返回 `applied_copy_fields`
  - 保存参数结果后会同步覆盖上述 4 个正式字段，并使 Step 5 策略预览失效，需要重新 build strategy

### Step 5 策略预览
- 前置状态：
  - `confirmed_copy` 已保存
  - `active_platform_id` 已设置
- 接口：`POST /sessions/{session_id}/strategy/preview`
- 请求体：
  - `planner_instruction: string | null`
  - `slot_preferences: [{slot_id, expression_mode, locked}]`
- 当前实现说明：
  - 该接口仍是同步接口，若配置了 WhatAI planner 且存在参考图，会在请求内同步调用上游 LLM
  - 若前端部署在带 15~30 秒超时的边缘函数/CDN Worker 前，不建议继续经该层代理此接口；应直连后端 Nginx 或使用更长超时
  - 对同一 session、同一份输入再次调用时，后端会直接复用已持久化的 `strategy_preview`，避免前端重试时重复触发长耗时 planner
  - 当前支持通过运行时配置切换 `planner_profile`：
    - `harness_first`：当前默认主/详情 planner 先走 `WhatAI + kimi-k2.5`（自动追加 `enable_thinking=true`），若命中 `429/超时` 再降级到 `WHATAI_PLANNER_LIGHT_MODEL`
    - `light_model`：切到轻量 planner 模型，用于压同步预览耗时
- 主图文字 override 接口：
  - `GET /sessions/{session_id}/strategy/overrides`
  - `PUT /sessions/{session_id}/strategy/overrides`
  - 用于保存 `copy_blocks_override/raw_prompt_override/expression_mode_override/applied_preset_id/locked`
- 当前实现行为：
  - 立即同步生成预览并落库
  - 创建 `build_strategy` job 记录，但不进队列
  - 对同一份输入再次调用时，会按 `input_hash` 直接复用已持久化的 `strategy_preview`
  - `strategy_preview` 现在会返回 `planner_profile`，以及 `planner_primary_* / planner_fallback_* / planner_attempt_count / planner_final_source`
  - Step 5 当前会结合 `confirmed_copy + active_platform_id + session 图片 + analysis.reference_summary` 做一轮槽位级 prompt planner
  - `strategy_preview.input_hash` 与正式构建共享同一批已加载 reference images，避免重复读图
  - `POST /sessions/{session_id}/generations` 现在会优先复用已持久化且 `input_hash` 未变化的 `strategy_preview`，不会在 worker 里再次补跑 planner
  - planner 当前允许由 LLM 主导输出 `expression_mode/copy_focus/focus_selling_point/reference_image_ids`，规则包只负责 guardrail 和 fallback
  - `main copy design agent` 当前默认关闭，不再作为主图预览默认时延来源
  - `strategy_preview.prompt_plan[*]` 现在还会补充：
    - `risk_flags`
    - `selling_point_binding`
    - `truth_contract`
  - `truth_contract` 至少包含：
    - `immutable_features`
    - `forbidden_drift`
    - `required_entities`
    - `evidence_level`
    - `allow_structure_extrapolation`
    - `scene_grounding_rule`
    - `scale_anchor`
  - 当证据不足时，主图策略会主动保真降级：
    - `detail/proof_authority` 不再默认走强结构拆解或机制示意
    - `scene/benefit_scene_or_compare` 会优先退回轻场景/利益场景，不强做人宠互动或夸张尺寸表达
  - 主图改为“平台规则包 + 槽位计划 + 表达方式模块”：
    - 默认平台仍输出 5 张：`hero` `white_bg` `selling_point` `scene` `detail`
    - 阿里系（`1688` / `taobao` / `alibaba_intl`）输出 5 个阿里槽位：`primary_kv` `reason_why` `proof_authority` `benefit_scene_or_compare` `closing_selling_point`
  - 每个 `asset_plan` 项都包含 prompt 可驱动元数据：
    - `role`
    - `slot_id`
    - `slot_label`
    - `slot_family`
    - `display_order`
    - `role_label`
    - `goal`
    - `background_mode`
    - `text_policy`
    - `composition_hint`
    - `aspect_ratio`
    - `expression_mode`
    - `expression_label`
    - `expression_reason`
    - `candidate_expression_modes`
    - `copy_blocks`
    - `copy_policy`
    - `layout_policy`
    - `proof_policy`
    - `visual_structure`
    - `copy_density`
    - `proof_mode`
    - `scene_mode`
    - `emphasis_style`
    - `requires_white_bg_validation`
    - `platform_rule_pack`
  - 阿里系 5 槽位当前收口为 PDF 式结构语义：
    - `primary_kv`：`标题区 + 产品主体 + 背景结构 + 底部利益点`
    - `reason_why`：`多理由卡 / 多场景小分镜 / 机制说明`
    - `proof_authority`：`参数佐证 / 证书资质 / 屏幕特写 / 局部结构放大`
    - `benefit_scene_or_compare`：`颜色强化 + 核心利益点 + 对比/场景二选一`
    - `closing_selling_point`：`优质场景 + 核心卖点 + 1-2 个辅助卖点`
  - `1688` / `taobao` 额外增加 visible copy 语言硬约束：
    - 新增图上文案必须为简体中文短句
    - 只允许阿拉伯数字、必要计量单位，以及用户已明确提供的型号/缩写白名单
    - 参考图中商品本体原有英文、型号、logo、按钮字样或铭牌丝印属于保真范围，应尽量保持，不要求翻译
    - `alibaba_intl` 保持英文站点语义，不受该中文约束影响
  - Prompt Matrix / Harness 当前新增一层非阻断式文案安全清洗：
    - analysis / planner / Step3 / render prompt 内部提示默认统一走中文表达
    - `copy_blocks/copy_lines` 会在 render 前过滤思考过程、推理标签、内部规划字段和流程说明
    - 前台可编辑默认值继续沿用现有 Step4/Step3 结构，但默认只暴露清洗后的最终候选文案
  - 同步返回并落库：
    - `platform_rule_pack`
    - `platform_overlay`
    - `slot_preferences`
    - `input_hash`
    - `reference_manifest`
    - `strategy_reference_manifest`
      - `image_id`
      - `slot_type`
      - `display_order`
      - `source_url`
      - `width`
      - `height`
      - `mime_type`
      - `file_size`
    - `prompt_plan`
      - `role`
      - `slot_id`
      - `slot_label`
      - `slot_family`
      - `display_order`
      - `expression_mode`
      - `expression_label`
      - `copy_blocks`
      - `raw_prompt_override`
      - `applied_preset_id`
      - `visual_structure`
      - `copy_density`
      - `proof_mode`
      - `scene_mode`
      - `emphasis_style`
      - `platform_overlay`
      - `platform_rule_pack`
      - `reference_image_ids`
      - `reference_slots`
      - `must_keep`
      - `must_avoid`
      - `slot_guardrails`
      - `background_rule`
      - `composition_rule`
      - `lighting_rule`
      - `fidelity_rule`
      - `final_prompt_base`
      - `planner_source`
      - `rule_modules_used`
      - `resolved_constraints`
      - `white_bg_mode`
      - `global_consistency_note`
  - `strategy_preview` 顶层还会回传：
    - `text_design_source`
  - `global_consistency_note` 用于约束局部图/结构图：
    - 只能放大解释参考图里可验证的结构
    - 不可杜撰不属于真实商品的内部结构
- 成功后：状态写为 `strategy_ready`
- 常见错误：`40002` `40003`
- 并发/幂等：无 Idempotency-Key

### Prompt 调试预览
- 前置状态：
  - `confirmed_copy` 已保存
  - `active_platform_id` 已设置
- 接口：`POST /sessions/{session_id}/prompts/preview`
- 请求体：
  - `instruction: string | null`
  - `include_latest_assets: boolean`
- 当前实现行为：
  - 只读接口，不创建 job，不写库
  - 即使 session 还没进入 `strategy_ready`，只要 copy 和平台已齐备，也会动态返回当前可计算的 prompt
  - 返回 `model`、`image_size`、`reference_manifest`、`prompts`、`latest_assets`
  - `prompts` 按当前 `asset_plan` 顺序返回，每项包含：
    - `role`
    - `slot_id`
    - `slot_label`
    - `slot_family`
    - `display_order`
    - `role_label`
    - `aspect_ratio`
    - `background_mode`
    - `text_policy`
    - `composition_hint`
    - `visual_structure`
    - `copy_density`
    - `proof_mode`
    - `scene_mode`
    - `emphasis_style`
    - `blocks`
    - `strategy_fields_used`
    - `prompt_sections_used`
    - `copy_policy_applied`
    - `slot_guardrails`
    - `reference_image_ids`
    - `reference_slots`
    - `reference_images_used`
    - `must_keep`
    - `must_avoid`
    - `planner_source`
    - `planner_base`
    - `copy_blocks`
    - `expression_mode`
    - `expression_label`
    - `rule_modules_used`
    - `platform_overlay`
    - `resolved_constraints`
    - `final_prompt`
  - `copy_policy_applied` 当前用于解释单图图上 copy 收口：
    - `headline_max_chars`
    - `supporting_max_lines`
    - `benefit_point_max`
    - `proof_tag_max`
    - `summary`
    - `degraded_to_minimal_copy`
    - `selected_visible_copy_count`
  - 当前实现补充：
    - `copy_blocks` 在进入 `final_prompt` 前会经过可见文案质量门禁，默认过滤占位词、低信息短句和假参数短语，例如 `核心功能突出/视觉清爽/参数A 100unit`
    - 若没有足够高质量的可见文案，`copy_policy_applied.degraded_to_minimal_copy=true`，单图会自动退化为少文案或仅保留产品识别标题
    - `must_keep/must_avoid/resolved_constraints` 会先做字符拆分修复与脏文本去噪，避免出现 `整；体；圆；柱...` 这类污染 prompt 的异常字符串
  - `blocks` 当前固定为：
    - `goal`
    - `subject`
    - `composition`
    - `background`
    - `style`
    - `selling_points`
    - `constraints`
    - `instruction`
  - `latest_assets` 返回最新结果版本中每张图的：
    - `asset_id`
    - `version_no`
    - `role`
    - `slot_id`
    - `display_order`
    - `prompt_snapshot`
    - `edit_instruction`
    - `generation_snapshot`
    - `reference_image_ids`
    - `upstream_endpoint`
    - `planner_instruction`
    - `expression_mode`
    - `rule_pack_id`
    - `raw_prompt_override`
    - `applied_preset_id`

### Prompt 仓库与风格预设
- 接口：
  - `GET /prompt-presets`
  - `POST /prompt-presets`
  - `PUT /prompt-presets/{preset_id}`
  - `POST /prompt-presets/{preset_id}/archive`
  - `POST /prompt-presets/{preset_id}/clone`
- 当前实现行为：
  - 系统会自动 seed 一批内置预设到数据库
  - `preset_type` 当前支持：
    - `style`
    - `slot_recipe`
    - `raw_prompt`
  - Step 4 风格正式契约已经收口为：
    - `style_preset_id`
    - `style_custom`
    - `style_choice` 仅兼容读取/legacy 写入，文档视为 deprecated
  - 调试台当前支持：
    - Step 4 套用风格预设
    - Step 5 把单槽位 override 显式保存为模板
- 常见错误：`40002` `40003`
- 并发/幂等：无 Idempotency-Key

### 详情页独立生成出口
- 定位：
  - 与主图 `/generations` 分开
  - 由前端开关决定本次走主图还是详情页
  - 详情页生成不会触发主图 5 张策略预览和生图
- 前置状态：
  - `confirmed_copy` 已保存
  - `active_platform_id` 已设置
  - 至少 1 张商品图
- 详情页风格图接口：
  - `POST /sessions/{session_id}/detail-pages/style-images`
  - `GET /sessions/{session_id}/detail-pages/style-images`
  - `DELETE /sessions/{session_id}/detail-pages/style-images/{image_id}`
  - 当前只接收 `display_order`，不要求 `slot_type`
  - 最多 4 张，可为空
  - 详情页策略预览：
  - 接口：`POST /sessions/{session_id}/detail-pages/strategy/preview`
  - 请求体：
    - `planner_instruction: string | null`
    - `panel_preferences: [{slot_id, panel_type, display_order, locked}]`
  - 同步落库到 `session.detail_strategy_preview`
  - 对同一份输入再次调用时，会优先复用已持久化的 `detail_strategy_preview`
  - 但若 `input_hash` 失配、`language_policy_version` 落后、`detail_policy_version` 落后、用户侧 `display_module_*` 字段缺失，或中文站 panel 中仍残留英文营销文案/内部规划标签，后端会自动重建 `detail_strategy_preview`
  - `POST /sessions/{session_id}/detail-pages/generations` 现在也会优先复用已持久化且仍有效的 `detail_strategy_preview`，不会在 worker 里无意义地再次补跑详情页 planner
  - 固定返回：
    - `use_case = amazon_detail`
    - `aspect_ratio = 21:9`
    - `panel_count = 8`
    - `input_hash`
    - `detail_story_brief`
    - `platform_overlay`
    - `copy_language`
    - `language_policy_version`
    - `detail_policy_version`
    - `detail_rule_pack`
    - `product_reference_manifest`
    - `style_reference_manifest`
    - `panel_plan`
  - 当前默认主链已把 reviewer 能力并回 `detail_planner`，因此 `detail_reviewer_ms` 仅作兼容返回，默认固定为 `0`
  - 详情页 planner 当前会显式复用同一 `session_id` 下的：
    - `analysis_snapshot`
    - 商品图
    - `parameter_snapshot`
  - 详情页当前也接入平台语言策略：
    - `1688/淘宝/京东/拼多多/抖音/小红书/自定义中文站` 的新增 panel 文案必须为简体中文
    - 商品本体原有英文、型号、logo、按钮字样和铭牌丝印允许保留，不要求汉化
    - `use_case = amazon_detail` 仅为兼容字段，不再代表详情页默认走英文语义
  - 但主图与详情页仍保持分链：
    - 主图是 `5` 槽位、conversion-first
    - 详情页是 `8` panel、narrative-first
  - `panel_plan` 每项至少包含：
    - `slot_id`
    - `panel_id`
    - `panel_label`
    - `display_tags`
    - `display_module_title`
    - `display_module_kind`
    - `display_module_intent`
    - `display_order`
    - `narrative_section`
    - `panel_goal`
    - `copy_focus`
    - `panel_type`
    - `panel_type_label`
    - `panel_type_reason`
    - `candidate_panel_types`
    - `layout_template`
    - `copy_policy`
    - `planner_prompt_base`
    - `copy_lines`
    - `layout_notes`
    - `planner_source`
    - `product_reference_ids`
    - `style_reference_ids`
    - `rule_modules_used`
    - `visual_truth_mode`
    - `origin_note`
  - 未上传风格图时，planner 自动退回 `style_preset_id(style_summary/name) + style_custom`；若缺失再兼容回退 `style_choice`
  - 详情页 override 接口：
    - `GET /sessions/{session_id}/detail-pages/strategy/overrides`
    - `PUT /sessions/{session_id}/detail-pages/strategy/overrides`
    - override 字段与主图一致，但作用域固定为 `asset_family=detail_page`
- 详情页 Prompt 预览：
  - 接口：`POST /sessions/{session_id}/detail-pages/prompts/preview`
  - 请求体：
    - `instruction: string | null`
    - `include_latest_assets: boolean`
  - 返回：
    - `use_case`
    - `aspect_ratio`
    - `panel_count`
    - `image_size = 1792x768`
    - `product_reference_manifest`
    - `style_reference_manifest`
    - `detail_policy_version`
    - `prompts`
    - `latest_assets`
  - `prompts` 固定按 8 个 panel 顺序返回，每项包含：
    - `panel_id`
    - `slot_id`
    - `panel_label`
    - `display_tags`
    - `display_module_title`
    - `display_module_kind`
    - `display_module_intent`
    - `display_order`
    - `narrative_section`
    - `panel_goal`
    - `copy_focus`
    - `blocks`
    - `copy_blocks`
    - `raw_prompt_override`
    - `applied_preset_id`
    - `panel_type`
    - `panel_type_reason`
    - `layout_template`
    - `product_reference_ids`
    - `style_reference_ids`
    - `product_reference_images_used`
    - `style_reference_images_used`
    - `planner_source`
    - `planner_base`
    - `rule_modules_used`
    - `platform_overlay`
    - `copy_language`
    - `final_prompt`
  - 详情页 prompt 现已收口为业务语义合同：
    - `final_prompt` 不再显式拼入 `Panel 类型 / 布局模板 / 内部规划语义仅用于推理`
    - 内部 planner 字段会先归并成 `visual_contract / copy_contract / truth_contract` 再参与 prompt 组装
    - 用户侧可见标题默认应优先消费 `display_module_title`，不要再直接渲染旧 `panel_label`
- 详情页生成/结果/下载：
  - 首次生成：`POST /sessions/{session_id}/detail-pages/generations`
  - 结果查询：`GET /sessions/{session_id}/detail-pages/results`
  - 下载：`GET /sessions/{session_id}/detail-pages/download`
  - `job_type`：`generate_detail_page`
  - 当前 worker / admin 可观测的详情页专属事件：
    - `detail_strategy_ready`
    - `detail_panel_render_started`
    - `detail_panel_render_succeeded`
    - `detail_panel_render_failed`
    - `detail_stitched_ready`
  - 单 panel 重生：`POST /assets/{asset_id}/regenerate`
    - 当 `asset_family=detail_page` 且 `asset_kind=panel` 时，会转成 `job_type=regenerate_detail_panel`
    - carry-forward 基线取 `parent_asset.version_no`；未改动 panel 与最终 stitched 长图都按该版本物化
  - 默认完整产出：
    - 8 张 `panel`
    - 1 张竖向拼接长图 `stitched`
  - 当前实现补充：
    - 若提交阶段或下载阶段只有部分 panel 失败，但当前版本仍有 ready panel，则 job 会写成 `partial_succeeded`
    - `GET /sessions/{id}/detail-pages/results` 会返回 `expected_panel_ids / missing_panel_ids / summary.expected_panel_count`
    - `partial_succeeded` 的详情页版本允许 `stitched_asset=null`；只有 panel 全齐时才会产出 stitched
    - 前端应把 `missing_panel_ids` 当作当前版本仍待补齐的真相源，不要把 `stitched_asset=null` 误判成接口异常
  - 结果里的每个 panel 当前会额外回传：
    - `display_tags`
    - `display_module_title`
    - `display_module_kind`
    - `display_module_intent`
    - `narrative_section`
    - `panel_goal`
    - `copy_focus`
    - `panel_type`
    - `visual_truth_mode`
    - `origin_note`
  - 结果顶层还会回传：
    - `detail_policy_version`
  - `visual_truth_mode` 用于区分：
    - 真实局部放大
    - 机制示意
    - 结构解释图
    前端应把这个语义透出，避免误解成对实物细节的 1:1 还原
  - 详情页执行阶段当前优先消费 panel 级 `product_reference_ids/style_reference_ids`；grid 只作为辅助 fallback，不再作为所有 panel 的唯一参考
  - 独立版本字段：
    - `detail_generation_round`
    - `detail_latest_result_version`
  - 主图版本字段 `generation_round/latest_result_version` 不会被详情页生成改写
  - 并发保护：
    - 详情页与主图共用 generation 并发锁
    - 冲突仍返回 `40901`
  - 幂等：
    - `POST /detail-pages/generations` 支持 `Idempotency-Key`
    - 相同 key + 相同 payload 命中幂等；不同 payload 返回 `40902`
  - 服务端调用补充：
    - 详情页 `style-images/strategy/overrides/prompts/generations/results/download` 全部统一要求 `X-App-Key`
    - 详情页与主图必须复用同一个 `session_id`，不要重复上传商品图

### Step 6 生成/结果/重生成/下载
- 前置状态：
  - 首次生成：session 必须是 `strategy_ready` 或 `completed`
  - 全局修改/整组重生成/单图重生成：已有结果版本
- 接口：
  - 首次生成：`POST /sessions/{session_id}/generations`
  - 结果查询：`GET /sessions/{session_id}/results`
  - 整组修改：`POST /sessions/{session_id}/results/global-edit`
  - 整组重生成：`POST /sessions/{session_id}/results/regenerate`
  - 单图重生成：`POST /assets/{asset_id}/regenerate`
  - 下载：`GET /sessions/{session_id}/download`
- 首次生成请求体补充：
  - `instruction: string | null`
  - `slot_ids: string[]`
    - 为空时生成整组
    - 传入时只生成指定槽位，适合单张调试
- 服务端生成语义：
  - 主图整组生成、详情页整组生成、全局修改、整组重生成、单图重生成和下载全部统一使用 `X-App-Key`
  - 不再区分 user/guest，也不再返回 guest 兼容字段
- 结果集字段补充：
  - `requested_version`
  - `available_versions`
  - `version_summaries`
  - `version_summaries[*].created_at/job_type/is_partial/cover_asset_id/cover_thumbnail_url/missing_slot_ids/missing_panel_ids`
  - `assets[].role`
  - `assets[].slot_id`
  - `assets[].expression_mode`
  - `assets[].rule_pack_id`
  - `assets[].status`
  - `assets[].display_order`
  - `assets[].version_no`
  - `assets[].render_total_ms`
  - `assets[].carry_forward`
  - `assets[].source_version_no`
  - `assets[].fidelity_validation_status`
- 版本规则：
  - `generate_gallery` / `global_edit` / `regenerate_gallery`：`round_no + 1` 且 `version_no + 1`
  - `regenerate_asset`：`version_no + 1`，`round_no` 保持当前轮次，且写 `parent_asset_id`
- 当前实现补充：
  - 任何 `version_no` 都按不可变快照保留，历史版本允许回看与下载
  - `regenerate_asset` 会物化成完整新版本：新图 + `parent_asset.version_no` 对应版本的其余图
  - 主图组与详情页当前会先按批次提交上游异步任务，再延迟启动轮询，再并发下载结果
  - 默认平台按 `hero -> white_bg -> selling_point -> scene -> detail` 生成
  - 阿里系平台按 `primary_kv -> reason_why -> proof_authority -> benefit_scene_or_compare -> closing_selling_point` 生成
  - 每个槽位默认会从 session 图片中选最多 2 张参考图，并优先走 `/v1/images/edits`
  - 参考图优先级：`front > angle45 > side > extra`
  - `detail`/`proof_authority` 默认优先 `front + side`，其余槽位默认优先 `front + angle45`
  - 并发与轮询改为配置化：
    - `generation_submit_concurrency`
    - `detail_generation_submit_concurrency`
    - `main_generation_concurrency`
    - `detail_generation_concurrency`
    - `image_submit_batch_size`
    - `detail_image_submit_batch_size`
    - `image_submit_batch_interval_seconds`
    - `image_poll_initial_delay_seconds`
    - `image_poll_profile`
    - `image_task_timeout_seconds`
    - `whatai_image_edit_timeout_seconds`
  - `429` 不再默认直接把整条文本链路打挂：
    - `analysis / main_planner / detail_planner / parameters / copy regenerate` 会先在单请求内做短退避重试
    - planner 若本地短重试后仍失败，会直接回退 rule-based/fallback，不再触发 `30/60/120s` 的整 job 级长等待
  - 白底校验改为能力标记驱动：仅 `requires_white_bg_validation=true` 的槽位会触发白底校验与单槽位补提
  - `1688` / `taobao` 当前改回 prompt-first：国内站中文 visible copy 主要依赖策略预览、规则包和最终 render prompt 的前置约束，不再在主图下载后追加热路径语言验收或补救重生
    - 默认要求图上若出现文字，只能是简体中文短句；不要出现英文标题、英文副文案、自由英文营销词、思考过程或内部规划标签
    - 若中文短句不稳，宁可少字或无字，不再为了语言审核额外串行补跑单图
  - 主图下载阶段若只有部分槽位失败：
    - 当前版本允许先落 ready 资产，不再让 1 张失败拖垮整组
    - job 状态会写成 `partial_succeeded`
    - `GET /sessions/{id}/results` 会返回 `expected_slot_ids / missing_slot_ids / summary.expected_count`
    - 前端后续可直接复用 `POST /sessions/{id}/generations` 的 `slot_ids` 补齐缺失槽位
  - 详情页当前也允许部分成功：
    - 提交阶段或下载阶段只要还有 ready panel，job 会写成 `partial_succeeded`
    - `GET /sessions/{id}/detail-pages/results` 会返回 `expected_panel_ids / missing_panel_ids / summary.expected_panel_count`
    - `detail_panel_render_failed` 会写入失败 panel 的 `slot_id/display_order/failure_stage/upstream_http_status`
    - `stitched_asset` 仅在 panel 全齐时生成；partial 版本下载 ZIP 只包含 ready panel
  - 主图与详情页 `generation_snapshot` 现在还会补充：
    - `sanitized_fields`
    - `copy_safety_notes`
    - `truth_contract`
    - `risk_flags`
    - `selling_point_binding`
    - `fidelity_validation`
    - `download_retry_count`
    - `download_rescued`
    - `download_rescue_reason`
    - `submission_batch_no`
    - `submission_batch_size`
    - `submit_strategy_version`
    - `timing.poll_started_after_ms`
  - 实际提交给上游的快照会落到 `assets.generation_snapshot`
  - `truth_contract/risk_flags/selling_point_binding` 当前用于生成前约束与结果追溯，不再在下载后串行触发逐张 `fidelity_validation` 或补救重生
  - `fidelity_validation` 与 `assets[].fidelity_validation_status` 当前仅保留兼容字段，默认可能为 `null`
- 并发保护：
  - 同 session 同时只允许 1 个运行中生图任务
  - 冲突返回 `40901`
- 幂等：上述 4 个 POST 都支持 `Idempotency-Key`

## 3. 任务状态与事件流

### 3.1 轮询状态
- 接口：`GET /jobs/{job_id}`
- 用途：展示 `status/progress/stage/error_code/error_message`
- 当前还会返回：
  - `queued_at`
  - `started_at`
  - `finished_at`
  - `queue_wait_ms`
  - `total_duration_ms`
  - `current_stage_elapsed_ms`
  - `stage_timings`
- 前端联调建议：
  - `regenerate_detail_panel` 也属于 generation 类任务，前端不要只按 `regenerate_asset` 单一 job_type 判断
  - JobMonitor 的事件展示要兼容 SSE 里的 `event` 字段，不要只读 `event_type`

### 3.2 SSE 事件
- 接口：`GET /jobs/{job_id}/events`
- 事件样例：
```text
data: {"event":"job_started","job_id":"..."}

data: {"event":"asset_ready","asset_id":"...","display_order":1}

data: {"event":"job_succeeded","job_id":"..."}
```
- 补充说明：
  - 生图链路当前改为异步提交 WhatAI 任务后轮询结果，因此单次接口抖动不一定意味着上游未生成
  - 图片任务结果当前按“批次提交 + 首轮延迟 + `image_poll_profile`”执行：
    - 默认每批最多 `5` 个
    - 批间隔 `5s`
    - 首轮轮询延迟 `45s`
    - 默认轮询节奏为 `10s x 6 + 15s x 8 + 20s x 10`
  - 主图与详情页分别走 `q.generation.main` / `q.generation.detail`
  - Prompt 预览建议走独立的 `POST /sessions/{id}/prompts/preview`，不要从 `GET /results` 推导 prompt

### 3.3 前端消费建议
- 建议同时使用：
  - SSE 实时展示阶段进度与单图就绪
  - Job 轮询兜底（SSE 中断或网络抖动）
  - Prompt Debug 面板单独调 `POST /sessions/{id}/prompts/preview`，避免结果接口变重

### 3.4 纯图片 SaaS 服务鉴权
- 图片主链路统一要求：
  - 请求头带 `X-App-Key: <server-app-key>`
  - 后端据此解析 `service_id`
  - session/job/upload/download 全部按 `service_id` 隔离
- 公开接口：
  - `/platforms`
  - `/healthz`
  - `/openapi.json`
- 已下线接口：
  - `GET|POST|PUT|PATCH|DELETE /auth/*`
  - `GET|POST|PUT|PATCH|DELETE /account/*`
  - `GET|POST|PUT|PATCH|DELETE /guest/*`
- 下线接口统一返回：
  - HTTP `410`
  - 业务码 `41001 feature_removed`
- Prompt Preset：
  - 用户模板语义已收口为接入方模板
  - `created_by` 与可见性过滤当前使用 `service_id`

### 3.5 后台管理接口
- 管理前缀：`/api/admin/v1`
- 后台前端入口：`GET /admin`
- 后台登录接口：
  - `GET /auth/health`
  - `POST /auth/login`
  - `POST /auth/refresh`
  - `POST /auth/logout`
  - `GET /auth/me`
- `GET /auth/health` 会校验后台 SQLite 是否可写、自动初始化 schema，并在配置了 `ADMIN_BOOTSTRAP_USERNAME/PASSWORD` 时自动补齐 bootstrap 管理员
- 若后台前端和后端跨域，同样受 `CORS_ALLOW_ORIGINS` allowlist 控制
- 后台列表接口统一约定：
  - 支持 `page/page_size/sort_by/sort_order`
  - 响应统一返回分页元数据：`items/page/page_size/total/total_pages/has_next/has_prev`
  - 当前已覆盖：`sessions/jobs/assets/audit-logs/prompt-presets/category-catalog/rule-packs`
- 后台高风险写接口统一约定：
  - 请求体支持 `operator_note`
  - 审计日志会记录 `module/risk_level/operator_note/before_after_snapshot`
  - 当前已覆盖：Prompt/Rule Pack 变更、Session copy/parameters/overrides 干预、Session 重跑、资产归档/恢复/重生成、Job 重试
- 后台管理对象：
  - Dashboard：
    - `GET /dashboard/overview`
    - `GET /dashboard/trends`
  - System：
    - `GET /system/runtime`
  - Sessions：
    - `GET /sessions`
    - `GET /sessions/{id}`
    - `PUT /sessions/{id}/copy`
    - `PUT /sessions/{id}/parameters`
    - `PUT /sessions/{id}/strategy/overrides`
    - `PUT /sessions/{id}/detail-pages/strategy/overrides`
    - `POST /sessions/{id}/actions/reanalyze|extract-parameters|regenerate-main|regenerate-detail`
    - `GET /sessions/{id}/results`
    - `GET /sessions/{id}/detail-pages/results`
    - `POST /sessions/{id}/strategy/preview`
    - `POST /sessions/{id}/detail-pages/strategy/preview`
    - `POST /sessions/{id}/prompts/preview`
    - `POST /sessions/{id}/detail-pages/prompts/preview`
  - Jobs：
    - `GET /jobs`
    - `GET /jobs/{id}`
    - `GET /jobs/{id}/events`
    - `GET /jobs/{id}/events/history`
    - `POST /jobs/{id}/retry`
  - Assets：
    - `GET /assets`
    - `GET /assets/{id}`
    - `POST /assets/{id}/archive`
    - `POST /assets/{id}/restore`
    - `POST /assets/{id}/actions/regenerate`
  - Prompts：
    - `GET|POST /prompt-presets`
    - `GET|PUT /prompt-presets/{id}`
    - `POST /prompt-presets/{id}/archive`
    - `POST /prompt-presets/{id}/clone`
  - Category Catalog：
    - `GET|POST /category-catalog`
    - `GET|PUT /category-catalog/{id}`
    - `POST /category-catalog/{id}/archive`
    - `POST /category-catalog/{id}/restore`
  - Rule Packs：
    - `GET|POST /rule-packs`
    - `GET|PUT /rule-packs/{id}`
    - `POST /rule-packs/{id}/publish`
    - `POST /rule-packs/{id}/clone`
    - `POST /rule-packs/{id}/archive`
  - Audit：
    - `GET /audit-logs`
- 资产归档语义：
  - 图片 SaaS 侧 `/api/v2/sessions/{id}/results|download` 默认隐藏 `visibility_status=archived` 资产
  - 后台侧可按 `visibility_status` 查看全部资产
- 后台前端当前信息架构：
  - `Overview / Sessions / Jobs / Assets / Prompts / Rule Packs / Audit / System`
  - 统一采用“列表 + 右侧详情工作台/抽屉”的操作模型，不再停留在 JSON dump 原型页

## 4. 实现 vs SPEC 差距清单（集中维护）
1. `build_strategy` 当前为同步执行，不走 Worker 队列。
2. `regenerate_copy` 仍返回占位重写结果，尚未解析上游真实输出。
3. `global_edit` 的 `scope=selected` 参数已接收，但执行时仍按整组处理。
4. 当前已实现“风格参考图单独上传 + 详情页独立首次生成 + 动态 panel_type 推荐/覆盖”，但未实现详情页 `global_edit`、单 panel 重生成、ComfyUI 节点级调试信息。
5. 当前实现已经会产出 `partial_succeeded`（主图缺槽位、详情页缺 panel 时）；`canceled` 仍未实现。
6. 上传图片未实现“建议尺寸 >= 1000x1000”的强校验。
7. 阿里规则当前支持短 headline / supporting / proof lines 的 prompt 级植入，并已为 `1688/taobao` 增加更强的中文 visible copy 前置约束；当前仍不包含画布级文字编辑器。
8. `adminfront/` 已升级为可运营、可排障、可配置的后台控制台；当前仍未做 RBAC、多级审批流、运行时敏感配置在线编辑和任务强制取消。
9. 当前实现已从“用户产品后端”收口为“纯图片 SaaS 后端”：`/api/v2/auth/*`、`/api/v2/account/*`、`/api/v2/guest/*` 已下线并返回 `41001 feature_removed`。
10. 当前图片主链路统一使用 `X-App-Key` 鉴权，并按 `service_id` 隔离 session/job/upload/download；旧 SPEC 中的 `user_id/guest_id/claim` 语义已失效。
11. 当前实现已改为“商品图变更只置 `analysis_snapshot.reanalysis_required=true`，不再自动重触发 `analysis`”；若旧 SPEC 仍描述自动 reanalysis，以当前实现为准。
12. 当前实现已收口为“任务级 LLM 路由 + prompt-first repair”：视觉主链默认 `WhatAI + Gemini`，OpenRouter 主要承担文本辅助任务；若旧 SPEC 仍写死全局 `LLM_PROVIDER` 切换，以当前实现为准。
13. 生成、分析和 Session 快照响应已移除 `auth_mode/guest_quota_remaining/login_required_actions/can_download/charged_credits/balance_after/pricing_rule_id` 等用户版字段。
14. 后台管理台已裁剪为图片运维台；旧文档中 `Users/Wallet/Pricing/Business` 相关描述不再适用。

## 5. 联调最短路径
前置：所有请求统一带 `X-App-Key`。

1. `POST /sessions`
2. `POST /sessions/{id}/images`
3. `POST /sessions/{id}/analysis`
4. `PUT /sessions/{id}/platform-selection`
5. `PUT /sessions/{id}/copy`
6. `POST /sessions/{id}/strategy/preview`
7. `POST /sessions/{id}/prompts/preview`（可选，用于调 prompt）
8. `POST /sessions/{id}/generations`
9. `GET /jobs/{job_id}` 或 `GET /jobs/{job_id}/events`
10. `GET /sessions/{id}/results`
11. `GET /sessions/{id}/download`

详情页最短路径（可替代 6~11）：
1. `POST /sessions/{id}/detail-pages/style-images`（可选）
2. `POST /sessions/{id}/detail-pages/strategy/preview`
3. `POST /sessions/{id}/detail-pages/prompts/preview`（可选）
4. `POST /sessions/{id}/detail-pages/generations`
5. `GET /jobs/{job_id}` 或 `GET /jobs/{job_id}/events`
6. `GET /sessions/{id}/detail-pages/results`
7. `GET /sessions/{id}/detail-pages/download`
