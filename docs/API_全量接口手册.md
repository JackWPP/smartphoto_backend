# API 全量接口手册（当前实现）

本文档是面向研发、联调、测试和运营的“人类可读版”接口手册，覆盖当前代码实现中的两套接口：

- 用户侧：`/api/v2`
- 管理侧：`/api/admin/v1`

说明：

- 精确字段类型、可选性和 `operationId` 以 `docs/openapi/smartphoto_backend_openapi.json` 为准。
- 联调顺序、状态流和实现差异说明以 `docs/API_联调指南.md` 为准。
- 本文档重点是“全量覆盖 + 语义解释 + 调用要点”，适合做接口目录、测试清单和交付手册。

---

## 1. 基础约定

### 1.1 Base URL

- 用户侧前缀：`/api/v2`
- 管理侧前缀：`/api/admin/v1`
- 健康检查：`GET /healthz`
- OpenAPI：`GET /openapi.json`
- 导出文件：`docs/openapi/smartphoto_backend_openapi.json`

### 1.2 统一响应格式

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

### 1.3 鉴权约定

用户侧：

- Access Token：`Authorization: Bearer <access_token>`
- Refresh：`POST /api/v2/auth/refresh`
- Logout：`POST /api/v2/auth/logout`
- `dev` 环境允许 `ALLOW_DEV_AUTH_BYPASS=true` 时的开发用户回退

管理侧：

- Access Token：`Authorization: Bearer <admin_access_token>`
- Refresh：`POST /api/admin/v1/auth/refresh`
- Logout：`POST /api/admin/v1/auth/logout`
- 后台 bootstrap 管理员可通过 `ADMIN_BOOTSTRAP_USERNAME/PASSWORD` 自动补齐

### 1.4 常见全局约定

- 列表分页：
  - 用户侧部分接口支持 `page/page_size`
  - 管理侧列表接口统一支持 `page/page_size/sort_by/sort_order`
- 幂等：
  - 任务触发类接口默认优先支持 `Idempotency-Key`
- 高风险后台写操作：
  - 请求体统一支持 `operator_note`
  - 审计日志会记录 `module/risk_level/operator_note`
- 版本语义：
  - 主图和详情页结果都支持不可变版本快照
  - 结果接口支持 `requested_version/available_versions/version_summaries`

### 1.5 关键错误码

- `40002 invalid_session_status`
- `40003 invalid_platform`
- `40004 invalid_copy_field`
- `40005 too_many_images`
- `40006 unsupported_file_type`
- `40007 file_too_large`
- `40008 missing_required_images`
- `40201 insufficient_credits`
- `40401 session_not_found`
- `40402 job_not_found`
- `40403 asset_not_found`
- `40901 job_already_running`
- `40902 duplicate_idempotency_key`
- `50201 upstream_llm_error`
- `50202 upstream_image_error`

---

## 2. 用户侧接口 `/api/v2`

### 2.1 公共与平台信息

| 接口 | 作用 | 鉴权 | 关键说明 |
| --- | --- | --- | --- |
| `GET /platforms` | 读取平台列表与可选平台元数据 | 无 | Step 3 平台选择候选源 |

### 2.2 用户认证

| 接口 | 作用 | 鉴权 | 请求重点 | 响应重点 |
| --- | --- | --- | --- | --- |
| `POST /auth/register` | 用户注册并登录 | 无 | `email/password/display_name` | `access_token/user/me`，注册后自动赠送 `100` 点额度 |
| `POST /auth/login` | 用户登录 | 无 | `email/password` | `access_token/user` |
| `POST /auth/refresh` | 刷新 token | Refresh Cookie | 无 | 新 `access_token` |
| `POST /auth/logout` | 注销登录 | 用户 | 无 | 清理 refresh cookie |
| `GET /auth/me` | 读取当前登录用户 | 用户 | 无 | `user_id/email/display_name/status` |

### 2.3 账户中心

| 接口 | 作用 | 鉴权 | 请求重点 | 响应重点 |
| --- | --- | --- | --- | --- |
| `GET /account/overview` | 账户首页概览 | 用户 | 无 | 钱包余额、最近资产、最近通知、未读数 |
| `GET /account/profile` | 读取个人资料 | 用户 | 无 | 个人资料 |
| `PUT /account/profile` | 更新个人资料 | 用户 | 昵称等资料字段 | 更新后的资料 |
| `GET /account/assets` | 我的资产历史 | 用户 | `q/platform_id/image_type/style_tag/brand_name/page/page_size` | 按 session 聚合的资产历史卡片 |
| `GET /account/notifications` | 站内通知列表 | 用户 | `page/page_size` | 通知列表、未读数 |
| `POST /account/notifications/{notification_id}/read` | 标记单条通知已读 | 用户 | 无 | 已读状态 |
| `POST /account/notifications/read-all` | 全部通知已读 | 用户 | 无 | 已读结果 |
| `POST /account/security/change-password` | 修改密码 | 用户 | `old_password/new_password` | 成功标记 |
| `GET /account/settings` | 读取用户设置 | 用户 | 无 | 当前设置 |
| `PUT /account/settings` | 更新用户设置 | 用户 | 设置字段 | 更新后的设置 |
| `GET /account/purchases` | 购买记录 | 用户 | `page/page_size` | 订单列表 |
| `GET /account/wallet` | 钱包信息 | 用户 | 无 | `balance` |
| `GET /account/wallet/transactions` | 额度流水 | 用户 | `page/page_size` | `credits_delta/balance_after/source/note` |
| `GET /account/pricing` | 价格规则 | 用户 | 无 | 当前扣费规则 |

### 2.4 浏览器上传与对象存储

| 接口 | 作用 | 鉴权 | 请求重点 | 响应重点 |
| --- | --- | --- | --- | --- |
| `POST /uploads/presign` | 申请直传签名 | 用户 | `upload_kind/content_type/file_name` | 上传 URL、表单字段、`object_key` |
| `POST /uploads/complete` | 确认上传完成 | 用户 | `upload_kind/object_key` + 业务归属字段 | 可被业务表引用的上传结果 |

`upload_kind` 当前支持：

- `session_image`
- `detail_style_image`
- `parameter_attachment`
- `strategy_reference_image`

### 2.5 Session 主流程

#### 2.5.1 Session 基础

| 接口 | 作用 | 鉴权 | 请求重点 | 响应重点 |
| --- | --- | --- | --- | --- |
| `POST /sessions` | 创建 Session | 用户 | 可选初始字段 | `session_id/status/current_step` |
| `GET /sessions/{session_id}` | 读取 Session | 用户 | 无 | Session 完整状态与快照 |

#### 2.5.2 商品图上传

| 接口 | 作用 | 鉴权 | 请求重点 | 响应重点 |
| --- | --- | --- | --- | --- |
| `GET /sessions/{session_id}/images` | 读取商品图列表 | 用户 | 无 | 图片列表 |
| `POST /sessions/{session_id}/images` | 关联/上传商品图 | 用户 | `slot_type/display_order` + 文件或 `object_key` | 新图片记录 |
| `DELETE /sessions/{session_id}/images/{image_id}` | 删除商品图 | 用户 | 无 | 删除结果 |

#### 2.5.3 分析

| 接口 | 作用 | 鉴权 | 请求重点 | 响应重点 |
| --- | --- | --- | --- | --- |
| `POST /sessions/{session_id}/analysis` | 触发分析 job | 用户 | 可带 `Idempotency-Key` | `job_id/status` |
| `GET /sessions/{session_id}/analysis` | 读取分析快照 | 用户 | 无 | `analysis_snapshot/reference_summary` |

#### 2.5.4 平台选择

| 接口 | 作用 | 鉴权 | 请求重点 | 响应重点 |
| --- | --- | --- | --- | --- |
| `PUT /sessions/{session_id}/platform-selection` | 保存选中平台 | 用户 | `selected_platform_ids/active_platform_id` | 更新后的 session |

#### 2.5.5 Copy

| 接口 | 作用 | 鉴权 | 请求重点 | 响应重点 |
| --- | --- | --- | --- | --- |
| `GET /sessions/{session_id}/copy` | 读取 Step 4 copy | 用户 | 无 | 正式 copy 字段 |
| `PUT /sessions/{session_id}/copy` | 保存 Step 4 copy | 用户 | `product_name/category/hero_scene/core_selling_points/key_parameters/product_advantages/style_preset_id/style_custom` | 更新后的 copy |
| `POST /sessions/{session_id}/copy/regenerate` | 局部字段重写 | 用户 | `fields` | `job_id` |
| `GET /sessions/{session_id}/copy/regenerate/{job_id}` | 查询字段重写结果 | 用户 | 无 | `generated_fields` |

#### 2.5.6 参数附件与参数提取

| 接口 | 作用 | 鉴权 | 请求重点 | 响应重点 |
| --- | --- | --- | --- | --- |
| `GET /sessions/{session_id}/parameter-attachments` | 读取参数附件 | 用户 | 无 | 附件列表 |
| `POST /sessions/{session_id}/parameter-attachments` | 添加参数附件 | 用户 | 文件或 `object_key` | 附件记录 |
| `DELETE /sessions/{session_id}/parameter-attachments/{attachment_id}` | 删除参数附件 | 用户 | 无 | 删除结果 |
| `POST /sessions/{session_id}/parameters/extract` | 触发参数提取 | 用户 | 可选策略参数 | `job_id` |
| `GET /sessions/{session_id}/parameters` | 读取参数快照 | 用户 | 无 | `parameter_snapshot/applied_copy_fields` |
| `PUT /sessions/{session_id}/parameters` | 覆盖参数快照 | 用户 | `hero_scene/core_selling_points/key_parameters/product_advantages/...` | 更新后的参数 |

#### 2.5.7 策略参考图与主图策略

| 接口 | 作用 | 鉴权 | 请求重点 | 响应重点 |
| --- | --- | --- | --- | --- |
| `GET /sessions/{session_id}/strategy-reference-images` | 读取策略参考图 | 用户 | 无 | 参考图列表 |
| `POST /sessions/{session_id}/strategy-reference-images` | 添加策略参考图 | 用户 | 文件或 `object_key` | 参考图记录 |
| `DELETE /sessions/{session_id}/strategy-reference-images/{image_id}` | 删除策略参考图 | 用户 | 无 | 删除结果 |
| `POST /sessions/{session_id}/strategy/preview` | 构建主图策略预览 | 用户 | `planner_instruction/slot_preferences` | `strategy_preview/asset_plan/prompt_plan` |
| `GET /sessions/{session_id}/strategy/overrides` | 读取主图 override | 用户 | 无 | override 列表 |
| `PUT /sessions/{session_id}/strategy/overrides` | 保存主图 override | 用户 | `overrides` | 更新后的 override |
| `POST /sessions/{session_id}/prompts/preview` | 预览主图 prompt | 用户 | `instruction/include_latest_assets` | prompt 列表、reference 使用情况 |

#### 2.5.8 主图生成与结果

| 接口 | 作用 | 鉴权 | 请求重点 | 响应重点 |
| --- | --- | --- | --- | --- |
| `POST /sessions/{session_id}/generations` | 触发主图生成 | 用户 | `instruction/slot_ids` | `job_id/charged_credits/balance_after/pricing_rule_id` |
| `GET /sessions/{session_id}/results` | 读取主图结果 | 用户 | `version` | 当前版本、可用版本、资产列表 |
| `POST /sessions/{session_id}/results/regenerate` | 整组重新生成 | 用户 | 生成指令 | `job_id` |
| `POST /sessions/{session_id}/results/global-edit` | 批量属性修改 | 用户 | 编辑指令 | `job_id` |
| `GET /sessions/{session_id}/download` | 下载主图 ZIP | 用户 | `version` | ZIP 文件流 |

#### 2.5.9 详情页策略、样式图、生成与结果

| 接口 | 作用 | 鉴权 | 请求重点 | 响应重点 |
| --- | --- | --- | --- | --- |
| `GET /sessions/{session_id}/detail-pages/style-images` | 读取详情页风格图 | 用户 | 无 | 风格图列表 |
| `POST /sessions/{session_id}/detail-pages/style-images` | 添加详情页风格图 | 用户 | 文件或 `object_key` | 风格图记录 |
| `DELETE /sessions/{session_id}/detail-pages/style-images/{image_id}` | 删除详情页风格图 | 用户 | 无 | 删除结果 |
| `POST /sessions/{session_id}/detail-pages/strategy/preview` | 构建详情页策略预览 | 用户 | `panel_preferences/planner_instruction` | `panel_plan` |
| `GET /sessions/{session_id}/detail-pages/strategy/overrides` | 读取详情页 override | 用户 | 无 | override 列表 |
| `PUT /sessions/{session_id}/detail-pages/strategy/overrides` | 保存详情页 override | 用户 | `overrides` | 更新后的 override |
| `POST /sessions/{session_id}/detail-pages/prompts/preview` | 预览详情页 prompt | 用户 | `instruction/include_latest_assets` | panel prompt 列表 |
| `POST /sessions/{session_id}/detail-pages/generations` | 触发详情页生成 | 用户 | `instruction` | `job_id/charged_credits/balance_after/pricing_rule_id` |
| `GET /sessions/{session_id}/detail-pages/results` | 读取详情页结果 | 用户 | `version` | panel 列表、stitched 结果、版本列表 |
| `GET /sessions/{session_id}/detail-pages/download` | 下载详情页 ZIP | 用户 | `version` | ZIP 文件流 |

### 2.6 Job 与 Asset

| 接口 | 作用 | 鉴权 | 请求重点 | 响应重点 |
| --- | --- | --- | --- | --- |
| `GET /jobs/{job_id}` | 读取 job 状态 | 用户 | 无 | `status/progress/error/timing` |
| `GET /jobs/{job_id}/events` | 读取 job 事件流 | 用户 | SSE | `job_queued/job_started/job_progress/asset_ready/job_succeeded/job_failed` |
| `POST /assets/{asset_id}/regenerate` | 单资产重生成 | 用户 | `instruction/keep_style_consistency` | `job_id`，主图与详情页 panel 共用 |

### 2.7 用户侧 Prompt Preset

| 接口 | 作用 | 鉴权 | 请求重点 | 响应重点 |
| --- | --- | --- | --- | --- |
| `GET /prompt-presets` | 查询系统模板 + 用户模板 | 用户 | 过滤条件 | 模板列表 |
| `POST /prompt-presets` | 新建用户模板 | 用户 | 模板字段 | 新模板 |
| `PUT /prompt-presets/{preset_id}` | 更新用户模板 | 用户 | 模板字段 | 更新后的模板 |
| `POST /prompt-presets/{preset_id}/archive` | 归档模板 | 用户 | 无 | 归档结果 |
| `POST /prompt-presets/{preset_id}/clone` | 克隆模板 | 用户 | 无 | 克隆结果 |

---

## 3. 管理侧接口 `/api/admin/v1`

### 3.1 后台认证

| 接口 | 作用 | 鉴权 | 请求重点 | 响应重点 |
| --- | --- | --- | --- | --- |
| `GET /auth/health` | 后台自检与 bootstrap 管理员补齐 | 无 | 无 | SQLite 可用性、初始化结果 |
| `POST /auth/login` | 管理员登录 | 无 | `username/password` | `access_token/admin_user` |
| `POST /auth/refresh` | 刷新管理员 token | Refresh Cookie | 无 | 新 token |
| `POST /auth/logout` | 管理员退出登录 | 管理员 | 无 | 清理 cookie |
| `GET /auth/me` | 当前管理员信息 | 管理员 | 无 | 当前管理员 |

### 3.2 Dashboard

| 接口 | 作用 | 鉴权 | 请求重点 | 响应重点 |
| --- | --- | --- | --- | --- |
| `GET /dashboard/summary` | 轻量总览计数 | 管理员 | 无 | Session/Job/Asset/Prompt/Rule Pack 汇总 |
| `GET /dashboard/overview` | 正式控制台总览 | 管理员 | 无 | `runtime_cards/business_cards/config_cards/recent_failed_jobs/recent_high_risk_actions` |
| `GET /dashboard/trends` | 近期趋势 | 管理员 | `days` | 按天统计的 jobs/assets/users/orders 趋势点 |
| `GET /dashboard/business` | 经营指标聚合 | 管理员 | 无 | 新增用户、订单、额度、活跃 session 等 |

### 3.3 System

| 接口 | 作用 | 鉴权 | 请求重点 | 响应重点 |
| --- | --- | --- | --- | --- |
| `GET /system/runtime` | 运行时只读视图 | 管理员 | 无 | `queue_stats/worker_queues/storage_backend/public_base_url/cors/image_poll_profile` |
| `GET /system/pricing` | 定价规则只读视图 | 管理员 | 无 | 当前 pricing rules |

### 3.4 用户运营

| 接口 | 作用 | 鉴权 | 请求重点 | 响应重点 |
| --- | --- | --- | --- | --- |
| `GET /users` | 用户列表 | 管理员 | `q/status/page/page_size/sort_by/sort_order` | 用户分页列表 |
| `GET /users/{user_id}` | 用户详情 | 管理员 | 无 | 用户基础信息、钱包、统计、最近订单、最近流水 |
| `GET /users/{user_id}/notifications` | 用户通知 | 管理员 | `page/page_size` | 通知列表、未读数 |
| `POST /users/{user_id}/orders` | 手工补单 | 管理员 | `plan_name/amount/currency/credits_delta/source/operator_note` | 新订单、审计留痕 |
| `POST /users/{user_id}/wallet/adjust` | 调整额度 | 管理员 | `credits_delta/note/operator_note` | 新流水、审计留痕 |

### 3.5 Session 排障与干预

| 接口 | 作用 | 鉴权 | 请求重点 | 响应重点 |
| --- | --- | --- | --- | --- |
| `GET /sessions` | Session 列表 | 管理员 | `session_id/user_id/platform_id/status/page/page_size/sort_by/sort_order` | Session 分页列表 |
| `GET /sessions/{session_id}` | Session 详情 | 管理员 | 无 | Session、最近 jobs、最近 assets |
| `PUT /sessions/{session_id}/copy` | 改 Step 4 copy | 管理员 | 正式 copy 字段 + `operator_note` | 更新后的 session |
| `PUT /sessions/{session_id}/parameters` | 改参数快照 | 管理员 | 参数字段 + `operator_note` | 更新后的 session |
| `PUT /sessions/{session_id}/strategy/overrides` | 改主图 override | 管理员 | `overrides/operator_note` | 更新后的 session |
| `PUT /sessions/{session_id}/detail-pages/strategy/overrides` | 改详情页 override | 管理员 | `overrides/operator_note` | 更新后的 session |
| `POST /sessions/{session_id}/strategy/preview` | 重建主图策略预览 | 管理员 | 同用户侧 preview 参数 | 策略预览 |
| `POST /sessions/{session_id}/detail-pages/strategy/preview` | 重建详情页策略预览 | 管理员 | 同用户侧 preview 参数 | 详情页策略预览 |
| `POST /sessions/{session_id}/prompts/preview` | 主图 prompt 预览 | 管理员 | 同用户侧 prompt preview 参数 | prompt 预览 |
| `POST /sessions/{session_id}/detail-pages/prompts/preview` | 详情页 prompt 预览 | 管理员 | 同用户侧 prompt preview 参数 | prompt 预览 |
| `GET /sessions/{session_id}/results` | 主图结果 | 管理员 | `version` | 主图版本结果 |
| `GET /sessions/{session_id}/detail-pages/results` | 详情页结果 | 管理员 | `version` | 详情页版本结果 |
| `POST /sessions/{session_id}/actions/reanalyze` | 重跑分析 | 管理员 | `instruction/operator_note` | `job_id` |
| `POST /sessions/{session_id}/actions/extract-parameters` | 重跑参数提取 | 管理员 | `instruction/operator_note` | `job_id` |
| `POST /sessions/{session_id}/actions/regenerate-main` | 重跑主图 | 管理员 | `instruction/slot_ids/operator_note` | `job_id` |
| `POST /sessions/{session_id}/actions/regenerate-detail` | 重跑详情页 | 管理员 | `instruction/operator_note` | `job_id` |

### 3.6 Job 排障

| 接口 | 作用 | 鉴权 | 请求重点 | 响应重点 |
| --- | --- | --- | --- | --- |
| `GET /jobs` | Job 列表 | 管理员 | `session_id/status/job_type/page/page_size/sort_by/sort_order` | Job 分页列表 |
| `GET /jobs/{job_id}` | Job 详情 | 管理员 | 无 | Job 详情 |
| `GET /jobs/{job_id}/events` | Job 事件流 | 管理员 | SSE | 实时事件 |
| `GET /jobs/{job_id}/events/history` | Job 历史事件 | 管理员 | `page/page_size` | 事件历史分页 |
| `POST /jobs/{job_id}/retry` | 重试任务 | 管理员 | `operator_note` | 新的 `job_id` 或重试结果 |

### 3.7 资产治理

| 接口 | 作用 | 鉴权 | 请求重点 | 响应重点 |
| --- | --- | --- | --- | --- |
| `GET /assets` | 资产列表 | 管理员 | `session_id/asset_family/visibility_status/status/page/page_size/sort_by/sort_order` | 资产分页列表 |
| `GET /assets/{asset_id}` | 资产详情 | 管理员 | 无 | 资产详情、`generation_snapshot` |
| `POST /assets/{asset_id}/archive` | 归档资产 | 管理员 | `reason/operator_note` | 归档结果 |
| `POST /assets/{asset_id}/restore` | 恢复资产 | 管理员 | `reason/operator_note` | 恢复结果 |
| `POST /assets/{asset_id}/actions/regenerate` | 单资产重生成 | 管理员 | `instruction/operator_note` | `job_id` |

### 3.8 Prompt Preset 后台

| 接口 | 作用 | 鉴权 | 请求重点 | 响应重点 |
| --- | --- | --- | --- | --- |
| `GET /prompt-presets` | 模板列表 | 管理员 | `q/preset_type/asset_family/platform_id/slot_family/include_inactive/page/page_size/sort_by/sort_order` | 模板分页列表 |
| `POST /prompt-presets` | 新建模板 | 管理员 | 模板字段 + `operator_note` | 新模板 |
| `GET /prompt-presets/{preset_id}` | 模板详情 | 管理员 | 无 | 模板完整详情 |
| `PUT /prompt-presets/{preset_id}` | 更新模板 | 管理员 | 模板字段 + `operator_note` | 更新后的模板 |
| `POST /prompt-presets/{preset_id}/archive` | 归档模板 | 管理员 | `operator_note` | 归档结果 |
| `POST /prompt-presets/{preset_id}/clone` | 克隆模板 | 管理员 | `operator_note` | 克隆结果 |

### 3.9 Rule Pack 后台

| 接口 | 作用 | 鉴权 | 请求重点 | 响应重点 |
| --- | --- | --- | --- | --- |
| `GET /rule-packs` | 规则包列表 | 管理员 | `q/asset_family/platform_id/include_inactive/page/page_size/sort_by/sort_order` | 规则包分页列表 |
| `POST /rule-packs` | 新建规则包 | 管理员 | `name/asset_family/platform_id/rule_pack_key/config_snapshot/operator_note` | 新规则包 |
| `GET /rule-packs/{rule_pack_id}` | 规则包详情 | 管理员 | 无 | 规则包、版本历史、当前版本 |
| `PUT /rule-packs/{rule_pack_id}` | 更新规则包草稿 | 管理员 | `config_snapshot/operator_note` | 更新后的规则包 |
| `POST /rule-packs/{rule_pack_id}/publish` | 发布规则包 | 管理员 | `operator_note` | 发布结果 |
| `POST /rule-packs/{rule_pack_id}/clone` | 克隆规则包 | 管理员 | `operator_note` | 克隆结果 |
| `POST /rule-packs/{rule_pack_id}/archive` | 归档规则包 | 管理员 | `operator_note` | 归档结果 |

### 3.10 审计日志

| 接口 | 作用 | 鉴权 | 请求重点 | 响应重点 |
| --- | --- | --- | --- | --- |
| `GET /audit-logs` | 审计日志列表 | 管理员 | `target_type/target_id/action/module/risk_level/admin_user_id/page/page_size/sort_by/sort_order` | 审计分页列表 |

审计日志重点字段：

- `module`
- `risk_level`
- `operator_note`
- `before_snapshot`
- `after_snapshot`
- `request_id`

---

## 4. 推荐联调与验收顺序

### 4.1 用户侧最短链路

1. `POST /api/v2/auth/register`
2. `POST /api/v2/sessions`
3. `POST /api/v2/uploads/presign`
4. `POST /api/v2/uploads/complete`
5. `POST /api/v2/sessions/{session_id}/images`
6. `POST /api/v2/sessions/{session_id}/analysis`
7. `PUT /api/v2/sessions/{session_id}/platform-selection`
8. `PUT /api/v2/sessions/{session_id}/copy`
9. `POST /api/v2/sessions/{session_id}/strategy/preview`
10. `POST /api/v2/sessions/{session_id}/prompts/preview`
11. `POST /api/v2/sessions/{session_id}/generations`
12. `GET /api/v2/jobs/{job_id}` 或 `GET /api/v2/jobs/{job_id}/events`
13. `GET /api/v2/sessions/{session_id}/results`
14. `GET /api/v2/account/wallet`

### 4.2 管理侧最短链路

1. `GET /api/admin/v1/auth/health`
2. `POST /api/admin/v1/auth/login`
3. `GET /api/admin/v1/dashboard/overview`
4. `GET /api/admin/v1/system/runtime`
5. `GET /api/admin/v1/users`
6. `POST /api/admin/v1/users/{user_id}/wallet/adjust`
7. `GET /api/admin/v1/audit-logs?module=users`
8. `GET /api/admin/v1/sessions/{session_id}`
9. `POST /api/admin/v1/sessions/{session_id}/prompts/preview`
10. `GET /api/admin/v1/jobs/{job_id}/events/history`

---

## 5. 补充说明

- 当前后台是一套“单一超管”控制台，不做 RBAC、不做审批流。
- `adminfront` 当前已具备正式运营与排障能力，但编辑器仍为项目内 JSON editor，不是 Monaco。
- 若要做机器可消费的精确 SDK/Schema 对接，请直接读取 `docs/openapi/smartphoto_backend_openapi.json`。
