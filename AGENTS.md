# AGENTS.md — SmartPhoto Backend

> **调试与自主迭代系统** (v2.1.0 新增) → 见下方"调试工具包"章节
> **项目里程碑** → 见文件末尾"里程碑更新日志"

---

## 调试工具包（v2.1.0 新增）

### 核心接口

| 方法 | 路径 | 用途 |
|------|------|------|
| GET | `/api/v2/debug/sessions/{id}` | 全链路内部数据 |
| POST | `/api/v2/debug/prompt-diff` | 对比两个资产的 final_prompt |
| POST | `/api/v2/judge/text` | Vision LLM 评判单张图片文字一致性 |
| POST | `/api/v2/judge/session/{id}` | 评判整个 session 所有资产 |
| POST | `/api/v2/judge/session/{id}/compare` | 对比两个版本的文字匹配率 |
| GET | `/api/admin/v1/system/runtime` | 队列深度、并发配置 |
| POST | `/api/admin/v1/system/reload-config` | 清除 lru_cache，重读 .env |
| POST | `/api/admin/v1/system/reload-worker` | Celery pool_restart 广播 |

### 文案一致性诊断 SOP

```
1. POST /system/reload-config → 确保读到最新 .env
2. POST /system/reload-worker → 确保 worker 加载最新代码
3. GET  /debug/sessions/{id}  → 全链路数据（看 copy_blocks、final_prompt、sanitized_fields）
4. POST /judge/session/{id}   → Vision LLM 评判文字匹配率
5. POST /debug/prompt-diff    → 对比修复前后 prompt
6. POST /judge/session/{id}/compare → 对比版本间匹配率变化
```

### 文案流经关键点

```
confirmed_copy → build_copy_blocks() → design_main_copy_blocks(LLM)
→ strategy_overrides → compose_prompt() → sanitize → _brief_copy_text
→ 【可见文案区】文案候选（可改写）🔴 AI有改写自由 → 图片
```

### main gallery results 现在有 copy_blocks

`GET /sessions/{id}/results` 每个 asset 新增 `copy_blocks` 字段（详情图之前已支持）。

### 文案槽位一致性修复 (2026-05-14)

**问题**: prompt 【可见文案区】有文字，但 copy_blocks 槽位解析丢失——编辑框中没显示该行字。

**根因**: 
1. `_brief_copy_text` 会过滤/截断 copy_blocks 中的文字
2. 文字被扁平化为 `text1 | text2 | text3` 丢失槽位身份
3. AI 可能重新排列文字，前端用 copy_blocks 无法还原

**修复**:
1. `prompts.py` 新增 `parse_visible_copy_slots(final_prompt)` — 从 prompt 反向解析每个文字槽位
2. `pipeline_orchestration.py` 生成快照时存储 `visible_copy_slots` 
3. `compose_text_edit_prompt` 改为结构化槽位标签（主标题/副标题/标签1），不再过滤用户文字
4. `format_prompt_blocks` 改为"必须原样出现在图上，不许改写"

**结果**: `generation_snapshot.visible_copy_slots` 提供 prompt 中每个文字槽位到实际文字的 1:1 映射，前端可直接用此数据填充编辑框。

### 自助迭代闭环

```
发现 → debug/judge → 改代码/.env → reload-config → reload-worker → regenerate → judge验证
```

---

## 项目目标
- 项目名称：SmartPhoto Backend v2
- 当前目标：交付以 6 步前端流程为真相源的后端 API + 异步任务系统�?
- 版本范围：当前优先主图组生成闭环；不实现 success validator、平台合规自动校验�?

## 架构约束
- Web: FastAPI
- DB: PostgreSQL（开�?测试允许 SQLite 覆盖配置�?
- Queue: Celery + Redis
- 状态真相：`jobs` �?`sessions` 由数据库持久化；禁止仅依赖进程内内存状态�?
- 存储：通过 `StorageAdapter` 访问，本地实现为默认，后续可�?S3 兼容�?

## LLM �?Prompt 固定原则
- 视觉主链（`analysis` / 主图 planner / 详情�?planner / 视觉参数提取）默认保�?`WhatAI + Gemini`，不得因为引�?OpenRouter 就无说明替换稳定链路�?
- OpenRouter 的默认职责是文本辅助 Agent、多模型横向试配�?reviewer/rewrite，不是视觉主链替代者�?
- �?LLM 输出优先�?`prompt 围墙 + schema validator + 同模�?repair 1 �?+ fallback`，不要优先用 regex、业务硬编码�?normalize 偷改语义�?
- Step 2 品类识别优先消费后台“全局品类库”；客户新增品类时先配品类库，不要回�?analysis fallback 里硬编码�?

## 代码分层约定
- `app/api`: HTTP 路由层，仅处理请求解析与响应封装�?
- `app/services`: 业务服务层，含状态机、策略构建、幂等、锁、任务分发�?
- `app/workers`: Celery 执行入口，按 `job_type` 分派任务�?
- `app/models`: SQLAlchemy ORM 模型�?
- `app/db`: 数据库连接、会话与基类�?
- `alembic`: 迁移脚本�?

## 接口变更流程
- 所�?`/api/v2` 接口变更必须同时更新�?
  - `SmartPhoto_Backend_SPEC_v2 (1).md`（如涉及规范变更�?
  - `AGENTS.md` 里程碑日志（记录新增/修改接口�?
  - 对应集成测试
- �?job 型接口，必须明确�?
  - job_type
  - 幂等行为
  - 并发冲突行为�?0901/40902�?

## 文档维护规则
- 文档总入口：`Readme.md`
- 联调真相文档：`docs/API_联调指南.md`
- 生图执行语义文档：`docs/生图Agent协作逻辑.md`
- 原生部署真相文档：`docs/原生部署指南.md`
- 原生运维真相文档：`docs/原生运维指南.md`
- 生产上线总册：`docs/生产上线SOP.md`
- 运维与排障索引文档：`docs/运行与排障手�?md`
- 生产维护文档优先级固定为�?  1. `docs/原生部署指南.md`
  2. `docs/原生运维指南.md`
  3. `docs/生产上线SOP.md`
  4. `docs/运行与排障手�?md`
- 触发条件与责任：
  - 新增/修改路由、请求参数、响应结构：必须更新 `docs/API_联调指南.md`
  - 新增/修改 job_type、事件流、版本语义、锁策略：必须更�?`docs/生图Agent协作逻辑.md`
  - 新增/修改错误码、诊断路径、运行命令：必须更新 `docs/运行与排障手�?md`
  - 新增/修改首次部署、shared env、systemd、infra compose、原生目录约束：必须更新 `docs/原生部署指南.md`
  - 新增/修改日常巡检、发版、迁移、备份、回滚、救火命令：必须更新 `docs/原生运维指南.md`
  - 新增/修改标准上线流程总册、发包、预检、历史兼容或备用回滚路径：必须更�?`docs/生产上线SOP.md`
  - 若实现行为与 SPEC 不一致：必须更新 `docs/API_联调指南.md` 的“实�?vs SPEC 差距清单�?  - 完成上述更新后，再更�?`AGENTS.md` 里程碑日�?
## 生产上线固定约束
- 生产默认路径：`/opt/smartphoto_backend`
- 生产默认形态固定为�?  - `Postgres`：`docker-compose.infra.yml`
  - `Redis`：`docker-compose.infra.yml`
  - `API`：`systemd + .venv`
  - `Worker`：`systemd + .venv`
  - `Alembic`：`systemd + .venv`
- 原生服务固定读取：`/opt/smartphoto_backend/shared/.env.prod.native`
- 原生服务连接 DB/Redis 时，默认 host 必须�?`127.0.0.1`，禁止把 `postgres` / `redis` 当成原生默认 host
- 原生默认发布命令�?`./scripts/native-deploy.sh`
- 原生默认预检命令�?`./scripts/native-preflight.sh`
- �?Alembic migration 的发布必须先�?PostgreSQL 备份，再执行不带 `--skip-migrate` 的原生发�?- �?migration 的纯应用层发布才允许使用 `./scripts/native-deploy.sh --skip-migrate`
- 但只要代码包包含新的 Alembic revision，或线上日志已出�?`UndefinedTable/UndefinedColumn/relation does not exist`，就禁止继续使用 `--skip-migrate`
- Docker 全应用部署不再是默认建议，只保留为历史兼容、特殊环境或应急回滚备用路�?- 运维/上线指导默认提供完整、可直接复制执行的命令块，不提供省略版片�?- 发布后最少执行：
  - `curl http://127.0.0.1:8000/healthz`
  - `curl http://127.0.0.1:8000/api/admin/v1/auth/health`
  - CORS 预检
  - `journalctl -u smartphoto-api -n ...`
  - `journalctl -u smartphoto-worker -n ...`
- 具体命令真相源见�?  - 首次部署：`docs/原生部署指南.md`
  - 日常运维：`docs/原生运维指南.md`
  - 标准发布总册：`docs/生产上线SOP.md`

## 测试门禁
- 至少通过以下检查：
  - 核心链路集成测试通过
  - 关键错误码回归（40002/40901/40902�?
  - 任务事件序列可观测（job_queued/job_started/job_progress/asset_ready/job_succeeded|job_failed�?

## 里程碑更新日�?
- 2026-03-06 M0:
  - 初始�?FastAPI + Celery + SQLAlchemy + Alembic 工程骨架
  - 增加 docker-compose（Postgres + Redis）与本地启动脚本
- 2026-03-06 M1:
  - 完成核心表：sessions/session_images/jobs/job_events/assets/idempotency_records
  - 完成 Job 持久化、SSE 事件持久化、状态机校验基础
- 2026-03-06 M2-M5:
  - 完成 Step1~Step6 核心 API
  - 完成整组生图/整组重生�?全局修改/单图重生成的 job �?
  - 增加幂等记录与并发保护（DB 检�?+ Redis 锁降级）
- 2026-03-06 Docs:
  - 重构 `Readme.md` 为文档导航页
  - 新增 API 联调、Agent 协作、运行排障三份文�?
  - 建立“实�?vs SPEC 差距清单”集中维护机�?
- 2026-03-06 Ops:
  - WhatAI 上游默认 `WHATAI_API_BASE` 切换�?`https://api.whatai.cc`
  - `WhataiClient` 增加 `/v1` base path 归一化，兼容�?不带 `/v1` 的配�?
  - 同步更新 `.env.example`、`Readme.md`、`docs/运行与排障手�?md`、SPEC 中的上游地址说明
  - 上游 HTTP 失败日志追加响应正文，便于定�?WhatAI `400` 类配置错�?
  - `gemini-*` 文本模型改走 Gemini 官方 `generateContent` 协议，兼�?thinking 类模�?
  - 生图链路切换�?WhatAI 异步任务提交 + 结果轮询，优先补拿图片链接而不是重复提交生图请�?
  - 生图轮询窗口调整为约 8 分钟�?0 秒一次），兼�?WhatAI 后台已成功但结果 URL 延迟可见的情�?
  - `upstream_image_error` 默认不再触发 Celery 整任务重试，避免重复消耗上游额�?
- 2026-03-07 M6:
  - 主图�?prompt 体系重构为“角色规�?+ 结构�?blocks + final_prompt�?
  - `strategy_preview.asset_plan` 扩展�?5 个固定主图角色及�?prompt 元数�?
  - 新增只读接口 `POST /api/v2/sessions/{session_id}/prompts/preview`
  - 生成页增�?Prompt Debug 面板，支持查看当前预�?prompt 与最近一次真�?`prompt_snapshot`
  - 补充 prompt、策略预览、结果追溯相关集成测试与前端 API
- 2026-03-07 M7:
  - Step 2 分析链路改为真实携带 session 图片到上游，`analysis_snapshot` 新增 `reference_summary`
  - Step 5 `POST /api/v2/sessions/{session_id}/strategy/preview` 新增 `planner_instruction` 请求�?
  - Step 5 预览结果扩展�?`reference_manifest + prompt_plan + asset_plan`
  - 主图组默认顺序调整为 `hero -> white_bg -> selling_point -> scene -> detail`
  - 生图执行默认优先走参考图驱动�?`/v1/images/edits`，单 role 最多引�?2 张参考图，内部最大并�?`2`
  - `white_bg` 增加独立白底分支与轻量白底校验，仅对白底图内部重�?1 �?
  - `assets` 新增 `generation_snapshot` 追踪真实使用�?prompt blocks、参考图、上游端点与 planner 指令
  - Prompt Debug 返回 `reference_manifest`、`prompts[].reference_images_used`、`latest_assets[].generation_snapshot`
- 2026-03-07 Test:
  - 测试环境增加每用�?SQLite/Redis/存储目录重置，避免并发锁�?queued job 互相污染
  - `TASKS_EAGER=true` 时调度器改为保持异步接口语义：worker 失败记录�?job，但异常不直接冒�?HTTP 路由
- 2026-03-07 Ops:
  - `dev-api.sh` �?`dev-worker.sh` 启动前自动执�?`alembic upgrade head`，降低代码升级后遗漏迁移导致的运行时缺列风险
  - 运行排障手册补充 `assets.generation_snapshot does not exist` 的定位与修复路径
  - `/images/edits` 传输层断连时，优先做单请求重试与单资产内部重试，不触发整�?Celery 重跑
  - 补齐 FastAPI OpenAPI 元信息与导出脚本，生�?`docs/openapi/smartphoto_backend_openapi.json` �?Apifox 直接导入
- 2026-03-07 M8:
  - 新增详情页独立生成开关对应后端能力：`/detail-pages/style-images|strategy/preview|prompts/preview|generations|results|download`
  - `sessions` 增加 `detail_strategy_preview/latest_detail_generate_job_id/detail_generation_round/detail_latest_result_version`
  - `assets` 增加 `asset_family/main_gallery|detail_page` �?`asset_kind/panel|stitched`，主图与详情页结果隔�?
  - 新增 `detail_style_images` 表，支持可选风�?字体参考图上传，不混入商品图槽�?
  - 新增 `generate_detail_page` job：固定输�?8 �?`21:9` panel 图和 1 张竖向拼接长图，共用现有幂等与并发保�?
  - 补充详情页链路集成测试、OpenAPI 导出、API 联调指南、Agent 协作逻辑、运行排障手册与 Readme
- 2026-03-13 M9:
  - 主图策略升级为“平台规则包 + 槽位计划 + 表达方式模块”，`POST /api/v2/sessions/{session_id}/strategy/preview` 新增 `slot_preferences`
  - `strategy_preview.asset_plan/prompt_plan` 新增 `slot_id/expression_mode/copy_blocks/rule_modules_used/platform_overlay/resolved_constraints/platform_rule_pack` 等元数据
  - 新增阿里�?5 槽位规则�?`alibaba_core_5_slot`，覆�?`1688/taobao/alibaba_intl`
  - `assets` 增加 `slot_id/expression_mode/rule_pack_id` 持久化字段，结果接口�?Prompt Debug 接口同步回传
  - 详情页策略升级为 8 个动态槽�?+ 14 �?`panel_type`，`POST /api/v2/sessions/{session_id}/detail-pages/strategy/preview` 新增 `panel_preferences`
  - `detail_strategy_preview.panel_plan` 与详情页 Prompt/Results 增加 `slot_id/panel_type/panel_type_reason/layout_template/rule_modules_used`
  - 生图执行链路改为“批量提交上游异步任�?-> 集中轮询 -> 并发下载”，新增 `main_generation_concurrency/detail_generation_concurrency/generation_submit_concurrency/image_poll_profile/image_task_timeout_seconds`
  - 生成队列拆分�?`q.generation.main` �?`q.generation.detail`，`scripts/dev-worker.sh` 同步更新
  - 补充阿里规则、详情页偏好、批量提交顺序、能力标记白底校验等集成/单元测试
- 2026-03-14 M10:
  - `POST /api/v2/sessions/{session_id}/generations` 新增可�?`slot_ids`，支持只生成单个主图槽位用于调试
  - 前端主图调试页新�?“Generate This Slot�?按钮，直接按 `slot_id` 触发单槽位生�?
  - 前端主图/详情页结果面板补齐版本同步逻辑，避�?session 已完成但结果区未刷新到最新版�?
- 2026-03-14 M11:
  - 版本语义修复为不可变快照：历�?`version_no` 可回看；`regenerate_asset` 物化完整新版本并保留旧版本可�?
  - `GET /api/v2/sessions/{session_id}/results` �?`detail-pages/results` 增加 `requested_version/available_versions/version_summaries`
  - 新增 `prompt_presets`、`session_prompt_overrides`、`parameter_attachments`、`strategy_reference_images` 数据模型与迁�?
  - 新增 Prompt 仓库接口：`GET|POST|PUT /api/v2/prompt-presets`、`POST /api/v2/prompt-presets/{id}/archive|clone`
  - 新增主图 override 接口：`GET|PUT /api/v2/sessions/{session_id}/strategy/overrides`
  - 新增 Step3 参数附件接口：`POST|GET|DELETE /api/v2/sessions/{session_id}/parameter-attachments`
  - 新增 Step3 参数提取接口：`POST /api/v2/sessions/{session_id}/parameters/extract`、`GET|PUT /api/v2/sessions/{session_id}/parameters`
  - 商品图变更后自动失效下游快照并自动重触发 `analysis`，`analysis_snapshot` 补充 `reanalysis_required`
  - 调试前端新增风格预设套用、参数附件上传与提取、主图文�?Prompt override 编辑、模板保存与历史版本切换
- 2026-03-14 M12:
  - Step 4 copy 契约收口�?`product_name/category/hero_scene/core_selling_points/key_parameters/product_advantages/style_preset_id/style_custom`
  - `GET /api/v2/sessions/{session_id}/copy` 改为返回正式字段集合，`style_choice` 仅兼容读�?
  - `PUT /api/v2/sessions/{session_id}/copy` 支持 `style_preset_id` 正式写入；后端策略优先解�?preset，再兼容回退 `style_choice`
  - `POST|GET|PUT /api/v2/sessions/{session_id}/parameters*` 补充 `applied_copy_fields/overwrite_mode`，参数提取结果默�?`replace_all` 覆盖 Step 4 四个正式字段
  - 主图/详情页策略预览、Prompt 预览与真实生图快照统一消费并记�?`hero_scene/core_selling_points/key_parameters/product_advantages/style_preset_id/style_custom`
  - 调试前端 Step 4 改为正式字段编辑器，移除“风格预�?+ 风格选择”双入口，仅保留预设选择 + 自定义风格补�?
- 2026-03-14 M13:
  - 新增后台管理前缀 `/api/admin/v1`，补充管理员登录/刷新/退�?自检接口，后台账号与审计落独�?SQLite �?
  - 新增后台对象接口：`dashboard/sessions/jobs/assets/prompt-presets/rule-packs/audit-logs`
  - `assets` 增加 `visibility_status/archived_at/archived_by/archive_reason`，支持后台归�?恢复并默认从用户侧结果与下载中隐�?
  - 新增 `rule_packs/rule_pack_versions` 数据模型，平�?详情页规则包改为 DB 发布优先、代�?seed 兜底
  - 新增 `adminfront/` 最小可用后台，支持登录、Session 排障、Job/Asset 查看、模板与规则包管�?
- 2026-03-14 M14:
  - 新增前台用户体系：`users/user_refresh_tokens/user_settings/user_notifications/purchase_orders/credit_wallets/credit_transactions`
  - `/api/v2/auth` 补齐 `register/login/refresh/logout/me`，默�?Bearer + Refresh Cookie；`dev` 环境支持 `ALLOW_DEV_AUTH_BYPASS`
  - `/api/v2/account` 新增 `overview/profile/assets/notifications/security/settings/purchases/wallet` 全量账户中心接口
  - `/api/v2/jobs/{job_id}`、`/events` �?`/api/v2/prompt-presets*` 补齐用户归属校验；用户侧系统模板改为只读
  - `sessions` 增加 `product_name_cache/brand_name_cache/style_tag_cache/last_generated_at`，用于“我的资产”历史页检索与排序
  - 后台新增 `/api/admin/v1/users`、`/users/{id}`、`/users/{id}/orders`、`/users/{id}/wallet/adjust`，支持人工补单与额度调整
  - 生成成功/失败与额度入账新增站内通知；补充用户功能集成测试、OpenAPI 导出、API 联调指南与运行排障手�?
- 2026-03-15 M15:
  - `StorageAdapter` 正式升级�?`local + s3` 双实现，浏览器上传新�?`/api/v2/uploads/presign|complete`，线上可按私有桶 + 签名�?写接�?S3 兼容 OSS
  - DB 持久化从本地 `/storage/...` URL 语义收口为稳�?`object_key`，读接口统一返回临时可访�?URL；ZIP 下载、参考图读取�?worker 结果写盘均已适配
  - `/api/v2/account/pricing` 上线，生成类接口补齐 `charged_credits/balance_after/pricing_rule_id`
  - 生成接单前增加余额校验，新增错误�?`40201 insufficient_credits`
  - 额度台账补齐生成扣费与失败自动退款；`dev` 环境固定开发用户自动补测试额度便于本地调试
  - 新增 `docs/OSS_对接与上线指�?md`、`docs/生图提速优化报告_客户�?md`，并同步更新 Readme、API 联调指南、运行排障手册、SPEC �?OpenAPI
- 2026-03-19 Ops:
  - 新增生产部署工件 `Dockerfile`、`docker-compose.prod.yml` �?`.env.prod.example`，按单机 Docker Compose 运行 `api/worker/postgres/redis`
  - 新增显式迁移与生产启动脚本：`docker-api.sh`、`docker-worker.sh`、`docker-migrate.sh`
  - 新增镜像构建热更新脚本：`deploy-prod.sh`、`rollback-prod.sh`
  - 新增 `CORS_ALLOW_ORIGINS` allowlist 配置，覆�?`/api/v2`、`/api/admin/v1` �?SSE 跨域访问
  - 同步更新 `Readme.md`、`docs/API_联调指南.md`、`docs/运行与排障手�?md`
- 2026-03-22 Hotfix:
  - 修复 `regenerate_asset/regenerate_detail_panel` �?carry-forward 基线版本选择：改为继�?`parent_asset.version_no`
  - 主图与详情页新增“从历史版本发起单资产重生成”回归测试，覆盖 `generation_snapshot.source_version_no`
  - 更新 `docs/API_联调指南.md` �?`docs/生图Agent协作逻辑.md` 中的版本快照�?carry-forward 语义说明
- 2026-03-22 Ops Package:
  - 补齐生产部署工件：`Dockerfile`、`docker-compose.prod.yml`、`scripts/docker-{api,worker,migrate}.sh`
  - 新增镜像构建热更新脚本：`scripts/deploy-prod.sh`、`scripts/rollback-prod.sh`
  - 新增 `scripts/package-prod.sh` 生成不含 `.env.prod` 的部署包，并更新 `docs/运行与排障手�?md`
- 2026-03-23 Recovery:
  - 恢复发布基线到包�?`/api/v2/auth`、`/api/v2/account`、`/api/v2/uploads` 的完整用户版代码线，并保�?3/22 carry-forward hotfix
  - 新增 `GET /api/admin/v1/auth/health`、`/admin` 后台前端入口、自举管理员初始化逻辑与对应回归测�?
  - 新增 `scripts/preflight-prod.sh`，发布前固定检�?`.env.prod`、`alembic_version`、用户表�?`rule_pack*` schema，防止再把错误迁移链打进生产
  - 更新 `Readme.md`、`docs/API_联调指南.md`、`docs/运行与排障手�?md`，统一恢复发布与热更新说明
- 2026-03-23 Ops Hotfix:
  - `app.admin_db` 重新提供稳定导出入口，`app.admin_db.session` 新增 `engine = admin_engine` 兼容别名，避免旧发布目录残留模块导致 API 启动�?`ImportError`
  - `scripts/package-prod.sh` 改为仅打�?git-tracked 白名单文件，杜绝本地未跟踪源码或历史残留文件混入部署�?
  - `docs/运行与排障手�?md` �?`Readme.md` 明确将“新目录发布 + 固定 COMPOSE_PROJECT_NAME”设为默认流程，并补充旧目录覆盖解压的清理命�?
- 2026-03-23 Credits:
  - 新增 `20260323_0010` 迁移：PostgreSQL �?`users` 表增加注册赠送额�?trigger，新注册用户自动入账 `100` 点额度并写入 `credit_transactions`
  - 同一迁移对迁移前已存在用户一次性补�?`1000` 点额度，账本 `source=legacy_bonus_20260323`
  - SQLite/测试环境增加应用层回退逻辑，保�?`POST /api/v2/auth/register` 后钱包余额与流水语义�?PostgreSQL 保持一�?
  - 同步更新 `docs/API_联调指南.md`、`docs/运行与排障手�?md` 与用户额度回归测�?
- 2026-03-23 Admin Console:
  - 后台控制台从单页 JSON dump 原型升级为路由化 `adminfront`，固定模块为 `Overview / Users / Sessions / Jobs / Assets / Prompts / Rule Packs / Audit / System`
  - `/api/admin/v1` 新增 `dashboard/overview|trends|business`、`system/runtime|pricing`、`users/{id}/notifications`、`jobs/{id}/events/history`、`sessions/{id}/results`、`sessions/{id}/detail-pages/results` 与四�?session preview 包装接口
  - 后台列表接口统一支持 `page/page_size/sort_by/sort_order`，审计日志扩�?`module/risk_level/operator_note`
  - 额度调整、手工补单、Prompt/Rule Pack 变更、Session 干预、资产归�?恢复/重生成、Job 重试统一写后台审计备�?
  - 新增后台控制台集成测试，覆盖 Dashboard、System、用户通知、Session 预览/结果、Job 事件历史与审计留�?
- 2026-03-23 API Reliability:
  - `POST /api/v2/sessions/{session_id}/analysis` �?session 仍为 `created` 但已存在上传图片时，会自动补正到 `images_uploaded -> analyzing`，避�?worker 侧再�?`cannot transition created -> analyzing`
  - `run_analysis_job` 同步补充兜底修复，兼容历史脏状态任�?
  - `POST /api/v2/sessions/{session_id}/strategy/preview` 对同一份输入新增缓存复用：�?`input_hash` 未变化，直接返回已持久化�?`strategy_preview`，减少前端超时重试时重复触发同步 planner
  - 同步更新 `docs/API_联调指南.md`、`docs/运行与排障手�?md` 与回归测�?
- 2026-03-24 Oncall:
  - `POST /api/v2/sessions/{session_id}/copy/regenerate` 扩展为新旧字段双兼容：正式字�?`hero_scene/core_selling_points/key_parameters/product_advantages` �?legacy `headline/selling_points/usage_scenes/specs` 都可下发�?worker，避�?`invalid_copy_field`
  - `run_regenerate_copy_job` 对列�?结构化参数字段先规范化成可重写文本，再交给上�?copy regenerate，防�?`key_parameters/core_selling_points` 直接�?list/dict 进重写器
  - 运行排障手册补充生产上传链路建议：前端若位于 ESA / CDN Worker 后，应优先走 `/api/v2/uploads/presign|complete`，避免二进制 multipart 经边缘代理返�?`524`
- 2026-03-24 Guest Trial:
  - 新增 `guest_identities` 模型�?`20260324_0011` 迁移；`sessions/jobs/idempotency_records` 改为 `user_id/guest_id` 二选一归属，并增加所有权约束
  - 新增 `RequestActor` �?guest cookie 识别逻辑：未登录浏览器可匿名完成 `POST /api/v2/sessions`、Step1~Step5 和首�?`POST /api/v2/sessions/{session_id}/generations`
  - `GET /api/v2/sessions/{session_id}` 与首轮生成响应新�?`auth_mode/guest_quota_remaining/login_required_actions/guest_trial/login_required_after_result`
  - guest 首轮主图生成默认每浏览器 3 次；�?4 次返�?`40302 guest_trial_exhausted`；下载、全局修改、重生成、详情页生成等结果后动作返回 `40102 login_required`
  - `POST /api/v2/auth/register|login` 现在会自动认领当前浏览器 guest �?`sessions/jobs/idempotency_records`，登录后结果页与账户历史无缝续接
  - 后台 `sessions/jobs` 列表与序列化兼容 guest owner，新�?`guest_id/owner_kind/owner_label` 字段
- 2026-03-25 Guest Alignment:
  - guest 能力扩展到详情页真实链路：`detail-pages/style-images|strategy/overrides|prompts/preview|generations|results` 全部支持 `RequestActor(kind=guest)`
  - 新增显式认领接口 `POST /api/v2/guest/sessions/{session_id}/claim`；与登录/注册自动认领共用同一�?guest 迁移逻辑，并保持�?`session_id` 不变
  - guest 门禁收口为“下载与结果后二次编辑再登录”：`download/detail-pages/download/results/global-edit/results/regenerate/assets/{id}/regenerate` 仍返�?`40102 login_required`
  - guest 配额升级为主图与详情页共用同一浏览�?`3` 次匿名整组生成；`generate_detail_page` 响应同步补齐 `guest_trial/guest_quota_remaining/login_required_after_result`
  - `GUEST_COOKIE_TTL_DAYS` 默认收口�?`1`�?4 小时软失效），guest 过期后不可继续创作或认领
  - 同步更新 `Readme.md`、`docs/API_联调指南.md`、`docs/API_全量接口手册.md`、`docs/生图Agent协作逻辑.md`、`docs/运行与排障手�?md`、OpenAPI 导出�?guest 回归测试
- 2026-03-25 Guest First:
  - guest 门禁进一步收口为“仅下载与历史要求登录”：当前 session 内的主图/详情页生成、全局修改、整组重生成、单图重生成全部�?guest 放开
  - `POST /api/v2/auth/register|login` 不再自动认领当前浏览�?guest 资源；前端需在登录后显式调用 `POST /api/v2/guest/sessions/{session_id}/claim`
  - `POST /api/v2/guest/sessions/{session_id}/claim` 改为只迁移当�?session 及其关联 jobs / idempotency_records，不再认领整浏览�?guest 身份
  - `GET /api/v2/sessions/{session_id}` �?guest 响应改为 `can_continue_editing=true`、`login_required_actions=["download","save_history"]`、`guest_quota_remaining=null`
  - guest 产品级配额关闭；生成响应中的 `guest_trial/guest_quota_remaining/login_required_after_result` 仅保留兼容字段，固定返回 `false/null/false`
  - 同步更新 `Readme.md`、`docs/API_联调指南.md`、`docs/API_全量接口手册.md`、`docs/生图Agent协作逻辑.md`、`docs/运行与排障手�?md`、SPEC、OpenAPI 导出�?guest 回归测试
- 2026-03-25 Ops SOP:
  - 新增 `docs/生产上线SOP.md`，固化单�?Docker Compose 生产发包、备份、预检、发布、冒烟、回滚和常见坑位
  - `AGENTS.md` 新增生产上线固定约束，后�?session 默认�?`COMPOSE_PROJECT_NAME=smartphoto_backend + �?release 目录` 路径执行
  - `Readme.md` �?`scripts/package-prod.sh` 同步挂入上线 SOP 文档入口，确保部署包内也包含该文�?
- 2026-03-26 Ops Lessons:
  - 生产上线 SOP 与运行排障手册补充“`--skip-migrate` 前必须核�?alembic_version”和“误跳过 migration 后的补救命令�?
  - 新增构建阶段网络慢时的完整替代命令：临时 Dockerfile 同时切换 `npm/apt/pip` 到国内镜像源
  - 新增 CORS `Disallowed CORS origin`、`guest_identities does not exist`、`POSTGRES_USER unbound variable`、`FileNotFoundError: Dockerfile` 的标准排障命�?
  - Readme 明确 `.env.prod` 中的 `PIP_*` 不会自动影响 `docker build`，默认引导到 `docs/生产上线SOP.md` 的完整命令块
- 2026-03-26 Upload Reliability:
  - 前端 `uploadWithPresign` 新增 `10MB` 本地预校验，超过上限直接返回 `40007 file_too_large`，避免用户在边缘层长时间等待后才看到 `524/504`
  - 本地 `PUT /api/v2/uploads/direct/{upload_id}` 改为流式写盘，不�?`await request.body()` 一次性读完整文件，降�?local storage 部署下的大图上传超时与内存峰值风�?
  - 本地上传完成后的图片探测改为优先按文件路径读取，减少 `complete_upload` 阶段对本地大文件的额外全量读内存
  - 运行排障手册补充“上�?`524/504` 时如何区分旧前端 multipart、local 伪直传与真实 S3/OSS 直传”的标准排查命令
- 2026-03-26 M16:
  - 新增 `LLMRouter` �?`LLM_PROVIDER/OPENROUTER_API_*/LLM_*` 配置，analysis / 主图 planner / 详情�?planner / 参数提取支持按任务切 OpenRouter 模型；WhatAI 继续负责图片生成链路
  - Step 2 `analysis_snapshot` 扩展 `analysis_source/category_candidates/scene_tags/detected_view_slots/supplement_image_recommendations/reanalysis_required`，fallback 默认类目改为 `其他`，不再把 `家居用品` 当成默认结论
  - 商品�?upload/delete �?`/api/v2/uploads/complete` 改为“只失效不自动分析”：仅置 `analysis_snapshot.reanalysis_required=true` 并清�?`strategy_preview/detail_strategy_preview`，分析改为必须显式调�?`POST /api/v2/sessions/{session_id}/analysis`
  - 主图策略预览新增共享 reference load �?`input_hash` 复用；详情页策略预览新增 `detail_story_brief`、`panel_plan.narrative_section/panel_goal/copy_focus/product_reference_ids/style_reference_ids` �?`input_hash` 缓存复用
  - 详情页执行链路改为优先消�?panel 级参考图，`assets.generation_snapshot` 记录 `effective_reference_image_ids`，grid 只作为辅�?fallback
  - 参数提取与分析链路增加受控尺寸图片加载，上传完成对非本地存储优先�?object metadata/head，减少重复读图和远端整文件回�?
  - 同步更新 `.env.example`、`.env.prod.example`、`Readme.md`、`docs/API_联调指南.md`、`docs/API_全量接口手册.md`、`docs/生图Agent协作逻辑.md`、`docs/运行与排障手�?md`、`docs/OSS_对接与上线指�?md`、`docs/生产上线SOP.md`、OpenAPI 导出与相关集成测�?
- 2026-03-27 M17:
  - 系统定位收口为纯图片 SaaS：图片主链路统一通过 `X-App-Key` 鉴权，新�?`ServicePrincipal(app_id)`，`sessions/jobs/idempotency_records` 持久�?`service_id`
  - `/api/v2/auth/*`、`/api/v2/account/*`、`/api/v2/guest/*` 下线�?`410 feature_removed`；图片接口继续保留在 `/api/v2`
  - `sessions/jobs/uploads/assets/prompt-presets` 主链路全部按 `service_id + session_id` 做隔离，移除 user/guest owner 依赖；上传票据、幂等和下载全部改成服务端调用语�?
  - 主图与详情页统一复用同一�?`session_id`；详情页链路不再要求重复上传商品�?
  - 后台裁剪为图片运维台：移�?admin users、business/pricing 视角，Overview 改为 `runtime_cards/ops_cards/config_cards`，列表与序列化统一返回 `service_id`
  - 新增 `20260327_0012_image_saas_decouple` 迁移，补�?`service_id/session_id` 字段并移�?owner-xor 约束
  - 同步更新 `Readme.md`、`docs/API_联调指南.md`、`docs/生图Agent协作逻辑.md`、`docs/运行与排障手�?md`、`docs/生产上线SOP.md`、SPEC、OpenAPI 导出、后台前端测试与图片 SaaS 相关回归测试
- 2026-03-27 Dev DX:
  - `scripts/dev-api.sh` 改为本地开发稳态入口：启动前自动迁移、热更新仅监�?`app/scripts/alembic`、默认排�?`runtime/storage/.git`
  - `scripts/dev-api.sh` 新增端口自检与自动顺延逻辑；当 `8000` �?Docker 或其他本地服务占用时，会自动回退到后续空闲端口并打印实际监听地址
  - `Readme.md` �?`docs/运行与排障手�?md` 补充“无 Docker 本地开发”指南，明确 `SQLite + TASKS_EAGER=true` 轻量模式�?`PostgreSQL + Redis + Worker` 真实异步模式
- 2026-03-27 M18:
  - LLM 路由改为按任务显式选择：视觉主链默�?`WhatAI + Gemini`，OpenRouter 只保留给文本辅助任务
  - `WhataiClient` �?`analysis / 主图 planner / 详情�?planner / 参数提取` 新增 prompt-first validator+repair 流程：先 schema 校验，再同模型重�?1 次，仍失败才 fallback
  - `analysis_snapshot / strategy_preview / detail_strategy_preview / parameter_snapshot` 补充 `provider/model/prompt_version/repair_round/source` 调试元数�?
  - 新增全局品类�?`category_catalogs`、后台管理接�?`/api/admin/v1/category-catalog*` 与后台页面，Step 2 analysis prompt 改为显式消费启用品类�?
  - fallback 默认类目继续保持 `其他`，不再把 `家居用品` 当成弱默认兜底；analysis 输出非法 `priority/slot_type/category` 时优�?repair，不再直接打�?worker
- 2026-03-27 M19:
  - Step 2 `supplement_image_recommendations` 升级为“建议补传什么图片”的结构化清单，新增 `upload_goal/must_show/framing_hint/example_caption/image_kind`
  - Step 3 新增同步二次补全接口 `POST /api/v2/sessions/{session_id}/parameters/complete`，参数链路改�?`extract -> complete` 两段式；`parameter_snapshot` 新增 `completion_status/completion_source/inferred_* / confidence_notes`
  - 主图策略预览新增文本�?`main copy design agent`，为每个槽位补充 `headline/supporting/proof_lines/matrix_lines/text_density/visual_emphasis`，并引入 `global_consistency_note` 约束局部图不得杜撰结构
  - 详情页策略预览新增文本侧 `detail copy reviewer agent`，`panel_plan` 与结果补�?`visual_truth_mode/origin_note`，用于区分真实局部图与机制示意图
  - 详情�?worker 事件流补�?`detail_strategy_ready/detail_panel_render_started/detail_panel_render_succeeded/detail_stitched_ready`，后�?runtime 卡片单独暴露 detail 队列运行�?
  - `SmartPhoto/dev2` 前端同步适配：AnalyzeStep 直接消费后端补图建议，UploadStep 展示补传卡片，GenerateStep 顺序调用 `extract -> complete`，详情页确认/结果页展�?`panel_goal/copy_focus/narrative_section/visual_truth_mode/origin_note`
  - 同步更新 `Readme.md`、`docs/API_联调指南.md`、`docs/生图Agent协作逻辑.md`、`docs/运行与排障手�?md`、OpenAPI 导出�?Step2/Step3/详情页相关回归测�?
- 2026-03-27 M20:
  - 不再使用 `xiaomi/mimo` 作为默认 OpenRouter 文本模型；文本辅助默认收口为 `deepseek + minimax`
  - 为避免额外时延与过度设计，`llm_route_main_copy_design` �?`llm_route_detail_copy_review` 默认改为 `disabled`
  - 视觉主链模型不因这次文本 Agent 收口而变更；Step 3 二次补全仍保留为唯一默认开启的 OpenRouter 文本链路
- 2026-03-28 M21:
  - Step 3 职责重定义为“单次调用的小型文案策划 Agent”：默认前端主链只使�?`POST /api/v2/sessions/{session_id}/parameters/extract`
  - `POST /api/v2/sessions/{session_id}/parameters/extract` 不再要求必须先上传参数附件；无附件时改为基于 `analysis_snapshot + 当前 session 商品�?+ confirmed_copy` 生成可编辑整页结�?
  - `parameter_snapshot` 收口�?Step 3 最终结果源，固定承�?`hero_scene/core_selling_points/key_parameters/product_advantages/feature_highlights`，并补充 `source_mode/evidence_priority/evidence_summary`
  - `POST /api/v2/sessions/{session_id}/parameters/complete` 保留兼容，但退出默认前端流�?
  - `SmartPhoto` Step 3 页默认不再自动调�?`parameters/complete`，首次进入和补传附件后都只重跑一�?`parameters/extract`
  - Step 3 本地/样例环境变量统一显式收口：`WHATAI_PARAMETER_MODEL` 默认改为 `gemini-3-flash-preview`，避免再出现实现与规划不一�?
- 2026-03-28 M22:
  - Step 5 策略预览新增运行�?`planner_profile`，当前支�?`harness_first|light_model` 两档；`strategy_preview/detail_strategy_preview` 与对�?`input_hash` 均会记录当前 profile/provider/model
  - 主图/详情�?planner 默认模型收口�?`WHATAI_PLANNER_MODEL=gemini-3.1-pro-preview-thinking-high`，轻量档默认 `WHATAI_PLANNER_LIGHT_MODEL=gemini-3-flash-preview`，OpenRouter 轻量备选为 `moonshotai/kimi-k2.5`
  - 图片生成默认模型切换�?`WHATAI_IMAGE_MODEL=gemini-3.1-flash-image-preview-2k`
  - `job status` 接口新增返回 `result_payload`；当上游返回 `429` 时，worker 会显式写�?`rate_limited (42901)` �?`upstream_http_status/upstream_reason`
  - `SmartPhoto` 主图/详情页结果页新增“上游限流”错误映射，不再�?`429` 一律展示成 `Job timed out`
- 2026-03-28 M23:
  - `POST /api/v2/sessions/{session_id}/generations` 进入 worker 后，会优先复�?session 上已持久化且 `input_hash` 未变化的 `strategy_preview`，不再为了正式生成再重跑 Step 5 planner
  - `POST /api/v2/sessions/{session_id}/detail-pages/generations` 同样优先复用已持久化�?`input_hash` 未变化的 `detail_strategy_preview`
  - 该改动用于消除“策略页已经成功，但正式生成时又�?planner 限流卡住”的重复耗时与重复失败源
- 2026-03-28 M24:
  - 主图/详情�?planner 默认临时切到 `WhatAI + kimi-k2.5`，并�?`kimi-k2.5` 请求自动追加 `enable_thinking=true`
  - planner 命中 `429/超时` 时新增“一次轻量降级补救”：自动切到 `PLANNER_FALLBACK_ROUTE + WHATAI_PLANNER_LIGHT_MODEL` 再试 1 次，不做同模型多轮重�?
  - `strategy_preview/detail_strategy_preview` 新增 `planner_primary_* / planner_fallback_* / planner_attempt_count / planner_final_source` 调试元数据；job failure payload 增加 `planner_stage`
  - 详情�?prompt 组装新增“planning context vs visible copy”隔离，过滤 `Proof/panel_goal/copy_focus/设计证明/�?..】` 等内部规划标签，避免泄露到最终成�?
  - 修复 detail worker 复用预览时误�?`product_manifest` 字段的问题，确保 `detail_strategy_preview` 命中同一 `input_hash` 时不再重�?planner/reviewer
  - 生产 `docker-compose.prod.yml` 改为通过 `bash ./scripts/docker-{api,worker,migrate}.sh` 启动，避免容器内直接执行脚本时因执行位异常导�?`permission denied`
- 2026-03-30 Hotfix:
  - `1688/taobao` 主图 prompt 新增“图�?visible copy 必须为简体中文”的硬约束；`alibaba_intl` 继续保持英文站点语义
  - 主图下载后、落库前新增图中文字语言验收：默认允许简体中文、数字、必要计量单位和 `confirmed_copy` 推导出的型号/缩写白名�?
  - �?`1688/taobao` 结果图识别到非白名单英文，只对当前单图补�?1 次；二次仍失败时�?`assets.generation_snapshot.language_validation` 写入 `retry_applied/soft_failed/disallowed_latin_tokens`
  - 同步更新 `docs/API_联调指南.md`、`docs/生图Agent协作逻辑.md`、`docs/运行与排障手�?md` 与阿里平�?prompt/worker 回归测试
- 2026-03-30 Hardening:
  - `1688/taobao` visible copy 策略收口为“prompt-first + validator 兜底”：国内平台 prompt 明确要求中文短句、少字、不要英文营销词；若中文不稳，宁可少字或无�?
  - visible copy 白名单仅保留 `confirmed_copy.product_name + key_parameters` 推导出的型号/缩写，不再从 headline / selling points / specs 自动放行英文营销�?
  - 图中文字验收改为“双层软补救”：先补 1 次更强中文约束，再补 1 次“少�?必要时无字”保守版本；两次后仍失败只写 `retry_applied/rescue_stage/soft_failed/reason` 留痕，不整组打挂
  - 同步更新 `docs/API_联调指南.md`、`docs/生图Agent协作逻辑.md`、`docs/运行与排障手�?md` �?visible copy 相关回归测试
- 2026-03-30 Analysis Freshness:
  - `sessions` 新增 `analysis_version/analysis_updated_at`，`GET /api/v2/sessions/{session_id}` �?`GET /api/v2/sessions/{session_id}/analysis` 统一返回 freshness 契约
  - analysis worker 仅在�?`analysis_snapshot` �?freshness 字段成功落库后才�?job `succeeded`，并�?`job.result_payload` 回传本轮 freshness 元数�?
  - 商品�?upload/delete、`/api/v2/uploads/complete`、平台切换与显式重跑 analysis 改为统一清理下游陈旧产物：保留旧快照、置 `reanalysis_required=true`、清�?`parameter_snapshot/strategy_preview/detail_strategy_preview`
  - Step 3 参数提取改为不再把旧 `parameter_snapshot` 合并回自己的输入；旧 session 回到 `2 -> 3` 时不会再被上一轮参数结果自我污�?
  - 补充�?session 重跑分析、平台切换失效、图片补传失效与 Step 3 去旧值回归测试，并同步更�?API 联调、Agent 协作、运行排障文档与 OpenAPI 导出
- 2026-03-30 Prompt Matrix:
  - 新增统一 `prompt_safety` 层，形成 `Agent Prompt / Planner Prompt / Render Prompt / Sanitize/Validation Prompt` 四层 Prompt Matrix
  - analysis / 主图 planner / 详情�?planner / Step3 / copy regenerate 的内部提示默认统一走中文表述，并补充“不输出思考过程、内部规划字段、流程说明”的共用约束
  - 主图 `copy_blocks`、详情页 `copy_lines/copy_blocks`、Step3/Step4 默认编辑值、copy regenerate 返回值统一走清洗，过滤 `panel_goal/copy_focus/narrative_section/origin_note/visual_truth_mode/Proof/设计证明/规则模块/布局模板/�?..�?思考过程`
  - 主图与详情页 `generation_snapshot` 新增 `sanitized_fields/copy_safety_notes` 轻量调试痕迹；继续保持非阻断式治理，不新增整任务硬失�?
  - 同步更新 `docs/提示词汇�?md`、`docs/API_联调指南.md`、`docs/生图Agent协作逻辑.md`、`docs/运行与排障手�?md` 与相关回归测�?
- 2026-03-30 Performance Restore:
  - 主图生成热路径明确保持“批量提交全部任�?-> 集中轮询 -> 并发下载结果”，不再在下载后、落库前追加图中文字语言验收或单图补救重�?
  - `1688/taobao` 中文 visible copy 改回�?prompt-first：继续通过规则包、策略预览和最�?render prompt 强化“简体中文短句、若不稳宁可少字或无字、不要英文营销词、不要内部规划标签�?
  - 保留 `prompt_safety` 的文案清洗与白底能力标记校验，但不再为了语言审核拖慢整组主图生成时长
  - 同步更新 `docs/API_联调指南.md`、`docs/生图Agent协作逻辑.md`、`docs/运行与排障手�?md` 与主�?worker 回归测试
- 2026-03-30 Reliability Hotfix:
  - `analysis / main_planner / detail_planner / Step3` 命中 `429` 时改为先做单请求内短退避重试；planner 若仍失败优先 fallback，不再直接进入整 job 长退�?
  - 主图下载阶段改为“单槽位补救优先”：单张失败先重试该槽位；若仍失败，当前版本允许�?`partial_succeeded` 落库，不再让整组结果归零
  - `GET /api/v2/sessions/{session_id}/results` 新增 `summary.expected_count`、`expected_slot_ids`、`missing_slot_ids`，前端可直接复用 `slot_ids` 补齐缺失槽位
  - 主图 `generation_snapshot` 新增 `download_retry_count / download_rescued / download_rescue_reason`，运行排障手册同步补�?`429` 与缺图排查口�?
- 2026-03-30 Prompt Refinement:
  - 详情页默认链路移除独�?`detail copy reviewer` 调用，`copy_focus/panel_goal/visual_truth_mode/origin_note` 改为�?`detail_planner` 一次性产出，详情页默�?LLM 调用数减�?1 �?
  - `1688/taobao` visible copy 规则收口为“新增海报文案必须中文化，但商品本体原有英文、型号、logo、按钮字样和铭牌丝印属于保真范围，应尽量保留�?
  - 主图阿里 5 槽位约束进一步强化为“短而有信息密度”：首图强调主利益点，理由图至少 2 个理由维度，佐证图优先参�?部件/结构证据，场景图强调明确收益，尾屏负责总结收口
  - Prompt Debug �?`blocks.constraints/final_prompt`、提示词总表、API 联调指南、Agent 协作文档与运行排障手册同步更新到新口径，并补充主�?详情页定向回归测�?
- 2026-03-30 Detail Chinese Fix:
  - 详情页中文站链路正式接入平台语言策略：`1688/淘宝/京东/拼多�?抖音/小红�?自定义中文站` 的新�?panel 文案、可编辑文案�?prompt 可见文案默认收口为简体中�?
  - 详情�?rule-based fallback 不再优先透传 legacy `selling_points/usage_scenes/specs`；改为优先消�?`hero_scene/core_selling_points/product_advantages/key_parameters`，并�?legacy 英文营销文案做过滤与降级
  - `detail_strategy_preview` 新增 `platform_overlay/copy_language/language_policy_version` 元数据；旧英�?preview 若命中语言策略版本落后或中文站仍残留英文营销文案，会在再次预览或正式生成时自动重�?
  - `detail-pages/prompts/preview.prompts[*]` 新增 `platform_overlay/copy_language`，同步更�?API 联调指南、运行排障手册、Agent 协作文档、提示词总表与详情页中英文回归测�?
- 2026-03-30 Timeout Tuning:
  - `WHATAI_REQUEST_TIMEOUT_SECONDS` 默认值从 `180s` 收紧�?`90s`，并�?`/v1/images/edits` �?multipart 请求同样走该配置
  - 保持 `IMAGE_EDIT_REQUEST_ATTEMPTS=4` 和现�?1/2/4s 短退避不变，仅缩短单次同步阻塞时间，降低 `read operation timed out` 的单次等待成�?
  - 同步更新 `.env.example`、`.env.prod.example`、`Readme.md`、`docs/运行与排障手�?md`、`docs/生图流程文档.md`、`docs/生图提速优化报告_客户�?md` 与相关回归测�?
- 2026-03-30 Detail Prompt Matrix:
  - 详情�?render prompt 去规划化：`final_prompt` 不再直接暴露 `Panel 类型 / 布局模板 / 内部规划语义仅用于推理`，改为先归并�?`visual_contract / copy_contract / truth_contract`
  - `detail_strategy_preview`、`detail-pages/prompts/preview` �?`detail-pages/results` 新增 `detail_policy_version` �?`display_module_title/display_module_kind/display_module_intent`，作为用户侧详情模块展示真相�?
  - 详情页进一步补�?`display_tags`，供前端直接展示中文 chip，不再渲�?`panel_type / narrative_section / visual_truth_mode` 原始内部�?
  - 详情�?`copy_lines/copy_blocks` �?sanitize 进一步增强，额外过滤 `卖点槽位 / 场景卖点 / 产品类型 / 模块 / product_type / feature_* / parameter_* / kv_* / icon_*` 等内部模板词，优先重写为业务短句，无法稳定重写时直接降级为空
  - `key_parameters` 若只有机�?key 没有正式 label，不再把 `product_type` 这类 schema key 直接拼进详情页可见文案；同时 `copy_lines` 会做去重与低信息降级，减少重复短�?
  - 旧详情页 preview 的自动重建判定扩展到 `detail_policy_version`、`display_module_*` 缺失和内部模板词残留；再次访�?preview 或正式生成时会自动升级并持久�?
  - 同步更新 `docs/API_联调指南.md`、`docs/生图Agent协作逻辑.md`、`docs/运行与排障手�?md`、`docs/提示词汇�?md` 与详情页定向回归测试
- 2026-03-30 Submit Cadence Hotfix:
  - 主图与详情页�?`/images/edits` 链路改为“每批最�?5 个、批间隔 5 秒、提交后�?45 秒再开始轮询”，避免一次性把所有同步长请求同时打到上游
  - 新增 `WHATAI_IMAGE_EDIT_TIMEOUT_SECONDS=120`，图片编辑请求不再与文本链路共用 `WHATAI_REQUEST_TIMEOUT_SECONDS=90`
  - `IMAGE_POLL_PROFILE` 默认节奏改为 `10s x 6 + 15s x 8 + 20s x 10`；`generation_submit_concurrency` 收口为单批内部并发上�?
  - `generation_snapshot` �?`job_progress` 新增 `submission_batch_no/submission_batch_size/submit_strategy_version/poll_started_after_ms` 等留痕，便于验收和排障确认后端已按新节奏执行
  - 同步更新 `.env.example`、`.env.prod.example`、`docs/API_联调指南.md`、`docs/生图Agent协作逻辑.md`、`docs/运行与排障手�?md` 与提交节奏相关回归测�?
- 2026-04-02 Detail Partial Success:
  - 详情�?submit 阶段�?fail-fast 改为“聚合成�?panel + 记录失败 panel”：单个 `/images/edits` 提交失败不再直接打崩整组 detail job
  - `generate_detail_page/regenerate_detail_panel` 现在允许在仍�?ready panel 时写 `partial_succeeded`，并�?`job.result_payload` �?`GET /api/v2/sessions/{session_id}/detail-pages/results` 回传 `expected_panel_ids/missing_panel_ids/expected_panel_count`
  - 详情页新增事�?`detail_panel_render_failed`；partial 版本不再生成 stitched 长图，`stitched_asset` 显式允许为空
  - 主图 submit 阶段失败也并入现�?`missing_slot_ids` 语义，不再因为单�?submit 失败跳过整版落库
  - 新增 `DETAIL_GENERATION_SUBMIT_CONCURRENCY=4`、`DETAIL_IMAGE_SUBMIT_BATCH_SIZE=4`，后�?`/api/admin/v1/system/runtime` 同步暴露 detail 专属 submit 节奏
  - 同步更新 `SmartPhoto_Backend_SPEC_v2 (1).md`、`docs/API_联调指南.md`、`docs/生图Agent协作逻辑.md`、`docs/运行与排障手�?md`、OpenAPI 导出与详情页/主图回归测试
- 2026-04-02 Quality Hardening:
  - `analysis_snapshot` 新增 `selling_point_entities/risk_flags/evidence_scores`，`reference_summary` 扩展比例、面板、透明件、结构锚点与场景适配信息
  - 主图 `strategy_preview.prompt_plan` 新增 `truth_contract/risk_flags/selling_point_binding`，结构敏感槽位会自动保真降级
  - 主图与详情页 render prompt 统一补充“主体不可漂�?/ 关键结构不可换位 / 比例按参考图 / 证据不足时保守降级”的保真约束
  - `GET /api/v2/sessions/{session_id}/results` �?`detail-pages/results` �?`version_summaries` 扩展 `created_at/job_type/is_partial/cover_asset_id/cover_thumbnail_url/missing_*`
  - 结果资产项扩�?`carry_forward/source_version_no/fidelity_validation_status`
  - 后台 SQLite 新增 `quality_feedback_cases`，并开�?`POST|GET /api/admin/v1/assets/{asset_id}/quality-feedback` 作为轻量质量反馈闭环
- 2026-04-02 Generation Hotpath Simplify:
  - 主图与详情页生成链路移除下载后的逐张 `fidelity_validation` 与单槽位补救重生，job 在图片下载完成后直接进入收尾落库
  - `truth_contract/risk_flags/selling_point_binding` 继续保留�?planner �?render prompt 的前置约束，不再作为热路径复检触发�?
  - `assets.generation_snapshot.fidelity_validation` 与结果接�?`fidelity_validation_status` 保留兼容字段，当前默认返�?`null`
- 2026-04-07 Reliability Fixes:
  - 新增 Alembic 迁移 `20260407_0017`，为 `category_catalogs` 补齐 `confusion_pairs/expected_components`，修复模型字段与生产 schema 漂移
  - 平台配置初始化改为幂等补齐缺失项并在读取入口持久化，避免 `GET /api/admin/v1/platform-configs` 仅单请求可见
  - 质量复审重试任务统一派发�?`q.generation.main`，并在重�?job 显式继承 `service_id`（同时透传 `user_id/guest_id`�?
  - `POST /api/v2/assets/{asset_id}/restore` 改为“以当前版本为基线物化完整新版本”，修复历史回滚导致结果版本不完整的问题
  - 新增回归测试覆盖：平台配置持久化、质量重试队列与租户继承、主�?详情�?restore 新版本语�?
  - 同步更新 `docs/API_联调指南.md`、`docs/生图Agent协作逻辑.md`、`docs/运行与排障手�?md`
- 2026-04-07 Native Deploy:
  - 新增半原生生产部署能力：`docker-compose.infra.yml` 只托�?`postgres/redis` 并通过 `127.0.0.1` 暴露给宿主机进程
  - 新增 `.env.prod.native.example`、`deploy/systemd/smartphoto-{api,worker,migrate}.service` �?`scripts/native-*`，支�?git 同步代码、宿主机 `.venv` 运行 API/Worker/Alembic
  - `scripts/package-prod.sh` 白名单补入半原生部署工件，避免发布包漏带 infra compose �?systemd unit
  - 同步更新 `Readme.md`、`docs/生产上线SOP.md`、`docs/运行与排障手�?md`
- 2026-04-07 Native Deploy Docs:
  - 新增 `docs/原生部署指南.md`，用人话版流程说明半原生部署的目录结构、备份、infra compose、原�?env、storage 拷贝、systemd、迁移、发版、回滚和常见问题
  - `Readme.md` �?`docs/生产上线SOP.md` 补充该指南入�?
- 2026-04-07 Native Ops Docs:
  - 新增 `docs/原生运维指南.md`，面向日常巡检、发版、迁移、Redis/DB/storage 运维、API/Worker 救火与发版前后检�?
  - `Readme.md`、`docs/生产上线SOP.md` �?`scripts/package-prod.sh` 补充该运维指南入�?
- 2026-04-13 Hero Scene Fix:
  - 修复 Step3 `PUT /api/v2/sessions/{session_id}/parameters` 手动改意图后，主图首图未稳定跟随�?`hero_scene` 的问�?
  - `apply_parameter_snapshot_to_copy` 改为在覆盖正式字段时同步镜像 `usage_scenes/selling_points/specs`，避免旧字段残留把策略拉回历史�?
  - 主图策略与首�?prompt 收口为正式字段优先，`hero_scene` 现在会直接约束首张主�?(`hero` / `primary_kv`) 的场景表达；`white_bg` 不消费该场景锚点
  - 补充参数镜像、首图场景锚点与 prompt preview 回归测试，并同步更新 `docs/API_联调指南.md`、`docs/生图Agent协作逻辑.md`、`docs/运行与排障手�?md`
- 2026-04-17 Windows Dev Worker:
  - `scripts/dev-worker.ps1` 默认改为 `--pool=solo --concurrency=1` 启动 Celery，避�?Windows �?`billiard` 默认多进程池触发 `WinError 5/6` �?`SpawnPoolWorker` 崩溃
  - `scripts/dev-worker.ps1` �?`scripts/dev-worker.sh` 统一支持 `CELERY_WORKER_POOL`、`CELERY_WORKER_CONCURRENCY`、`CELERY_QUEUES` 覆盖启动参数，并补齐 `q.quality` 队列
  - `Readme.md` �?`docs/运行与排障手�?md` 补充 Windows 本地 Worker 启动约束、覆盖方式与排障路径
- 2026-04-18 Stage H:
  - Stage H 目标收口为“历史结果读兼容审计 + residual compat inventory + release-window observation”，不再假设仓库内仍存在 active dual-path/shadow worker serving
  - 新增 `tests/test_stage_h_historical_read_compat.py`，覆�?main/detail latest �?historical 读取、partial-success、carry-forward、restore/regenerate、text-edit，以�?admin/public results 包装一致�?  - 新增 `.sisyphus/plans/stage-h-compat-inventory.md`，按“保�?/ 待删候�?/ 待确认”整�?copy legacy sync、detail preview normalization、results read-side helpers、rule `compat_role` 等兼容残留点
  - 更新 `.sisyphus/plans/pipeline-refactor-plan.md` �?Stage H 条目，明确当前阶段以验证、inventory 与发布观察为主，而不是继续推进不存在�?worker 双路径切�?  - 更新 `docs/运行与排障手�?md`、`docs/生产上线SOP.md`，补�?Stage H smoke checklist�?0-session historical audit checklist �?canary observation checklist
- 2026-04-19 Native Ops Consolidation:
  - 原生生产路径收口为默认主路径：Docker 只跑 `Postgres/Redis`，`API/Worker/Alembic` 统一改为 `systemd + .venv`
  - `scripts/native-preflight.sh` 增加阻塞式校验：明确拦截 `postgres/redis` Docker 主机名、相�?sqlite 路径、缺�?storage 目录、DB/Redis 连通性失败与 systemd/.venv 缺失
  - `scripts/native-deploy.sh` 发布前强制执行原生预检，后台前端依赖安装优先使�?`npm ci`
  - 重写 `docs/原生部署指南.md` �?`docs/原生运维指南.md` 为主要生产维护文�?  - `docs/生产上线SOP.md` 收口为标准发布总册，`docs/运行与排障手�?md` 收口为问题定位索引，`Readme.md` �?`AGENTS.md` 同步明确文档优先级与原生优先原则
- 2026-04-19 LLM Latency:
  - ���� `doubao_text` ·�ɣ�����ɽ Ark Responses API `/responses` ���룬֧�� `DOUBAO_API_KEY` �� `ARK_API_KEY`�������� `openai_compatible_text` ͨ��·��
  - �Ӿ������������� `analysis/parameter visual = WhatAI + Gemini`����ͼ planner������ҳ planner��������ȫ���ı����Ĭ�Ͽ��߶�����planner ʧ�ܰ� `PLANNER_FALLBACK_ROUTE=whatai_gemini` ����
  - ��ͼ planner ֧��һ���Է��� `copy_blocks/text_density/visual_emphasis/global_consistency_note`��Ĭ�ϲ�����Ҫ�������� `main_copy_design`
  - `strategy_preview/detail_strategy_preview` ���� `planner_ms/planner_fallback_reason` �۲��ֶΣ����ڶԱȶ����� fallback ��ʱ
  - ���� `QUALITY_REVIEW_MODE=off|sample|full`��Ĭ�� `sample`���첽�ʼ�ɳ���ر��Խ��ͺ�̨ LLM ������
  - ͬ������ `.env.example`��`.env.prod.example`��API ����ָ�ϡ�Agent Э���߼������������ֲ�����ػع����
- 2026-04-19 LLM Compression:
  - Step2/Step3 Ĭ����·���� `PARAMETER_EXTRACTION_MODE=combined`��`POST /api/v2/sessions/{session_id}/analysis` �ֿ�һ��д�� `analysis_snapshot + parameter_snapshot`
  - `parameter_snapshot` ���� `source_stage/analysis_version/input_image_ids/input_hash/parameter_source_job_id`�����ڸ��� freshness �ж�
  - `POST /api/v2/sessions/{session_id}/parameters/extract` �������� combined ����ʱ���ٵ������� LLM�����ݷ��سɹ� job �븴�ñ��
  - ���� `PARAMETER_EXTRACTION_MODE=separate` ���˿��أ��и���ʱ�����߶���������ȡ��·

- 2026-04-19 Brand Memory Phase 1:
  - Added Phase 1 brand-memory core models and migration: brands / brand_profiles / brand_memory_items / brand_memory_evidence, plus sessions.brand_id / sessions.brand_memory_enabled
  - Added session-level brand binding endpoint `PUT /api/v2/sessions/{session_id}/brand`
  - Main-gallery strategy preview now accepts `brand_memory_enabled` and returns `brand_memory_applied / brand_memory_item_ids / brand_memory_trace`
  - Prompt preview and main-gallery generation snapshot now expose brand-memory trace fields for debugging and result tracing
  - Added admin brand management surface `/api/admin/v1/brands*` for brand CRUD, profile upsert, memory item enable/disable, and evidence inspection
  - Brand memory now sediments only after assets reach `quality_status=passed`, including sample/off review paths, and uses a natural-key upsert to avoid duplicate rows under concurrency

- 2026-04-19 Brand Memory Frontend Handoff:
  - Added business-side brand selector endpoint GET /api/v2/brands so external frontend can fetch current service-scoped active brands without reusing admin auth
  - Locked the session-brand frontend truth source to GET /api/v2/sessions/{session_id} and documented bind/switch/unbind invalidation semantics for strategy_preview
  - Expanded docs/API_����ָ��.md with executable frontend handoff guidance covering timing, UI state sync, prompt/result trace fields, and a full bind -> preview -> prompt -> generation flow
  - Added integration and OpenAPI regression coverage for brand list discovery and session-level brand-memory handoff flow
