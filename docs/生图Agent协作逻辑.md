# 生图 Agent 协作逻辑（当前实现映射）

## 1. 文档定位
本文档描述的是**逻辑 Agent 协作模型**，用于指导开发、联调和排障。

说明：当前系统并未拆成多进程独立 Agent 服务，而是通过 API + Worker + Pipeline 在代码层协作执行。

## 2. Agent 拆分与代码映射
| 逻辑 Agent | 职责 | 主要代码映射 |
|---|---|---|
| Session Orchestrator | 接收请求、做前置状态校验、创建 job、分发任务 | `app/api/v2/sessions.py`, `app/api/v2/assets.py` |
| Analysis Agent | 读取会话图片，产出 `analysis_snapshot` 与 copy 草稿 | `run_analysis_job` + `WhataiClient.analyze_images` |
| Copy Regen Agent | 按字段重写 copy 建议，不直接覆盖 confirmed_copy | `run_regenerate_copy_job` |
| Strategy Builder | 生成 `strategy_preview`、`reference_manifest`、`prompt_plan` 和可执行 `asset_plan` | `build_strategy_preview` |
| Prompt Composer | 按 role 输出结构化 prompt blocks 与最终 `final_prompt` | `compose_prompt` |
| Image Generation Agent | 基于参考图调用图片上游接口，产出图片字节 | `WhataiClient.generate_image` |
| Storage/Versioning Agent | 持久化原图/结果图/缩略图，维护版本与父子关系 | `LocalStorageAdapter` + `AssetModel` |
| Prompt Debug Agent | 只读预览当前 prompt、参考图引用和最近一次真实执行快照 | `POST /sessions/{id}/prompts/preview` |
| Event & Lock Agent | 任务事件流、幂等记录、并发锁与冲突控制 | `append_job_event` + idempotency + redis lock |

## 3. 各 Agent 输入/输出与状态责任

### 3.1 Session Orchestrator
- 输入：HTTP 请求（含 session_id、asset_id、instruction、Idempotency-Key）
- 输出：`job_id` 或同步业务数据
- 状态责任：
  - 校验 session 状态与前置条件
  - 创建 `jobs` 记录（`queued`）
  - 分发到 `q.analysis` / `q.copy` / `q.generation`
- 失败处理：返回 `40002/40003/40901/40902` 等
- 重试策略：由调用端按幂等策略重试

### 3.2 Analysis Agent
- 输入：session 可用图片 + active_platform（可空）
- 输出：`analysis_snapshot`、可选 copy 草稿初始化
- 状态变更：`images_uploaded -> analyzing -> analyzed`
- 失败处理：
  - 无图时写 `job_failed` 并抛 `40008`
  - 上游异常转 `50201`
- 重试策略：上游网络级异常会先做单请求重试；若仍失败，Celery 任务最多再重试 3 次（`max_retries=3`）
- 当前实现补充：
  - 上传商品图会以内联图像内容的方式发给上游，不再依赖 `localhost` URL
  - `analysis_snapshot` 包含 `reference_summary`，至少提炼主体形态、颜色、材质、结构与不可漂移点

### 3.3 Copy Regen Agent
- 输入：`targets` + `instruction` + 当前 copy
- 输出：`generated_fields`
- 状态变更：session 进入或保持 `copy_ready`
- 失败处理：非法字段 `40004`
- 重试策略：上游网络级异常可进入 Celery 任务重试，最多 3 次

### 3.4 Strategy Builder
- 输入：`confirmed_copy` + `active_platform_id` + session 图片 + 可选 `planner_instruction`
- 输出：`strategy_preview`（含 `asset_plan`、`reference_manifest`、`prompt_plan`）
- 状态变更：`copy_ready -> strategy_ready`
- 失败处理：copy 或平台缺失返回 `40002/40003`
- 重试策略：当前为同步接口流程，不走 Worker
- 额外约束：
  - 当前固定输出 5 张主图：`hero` `white_bg` `selling_point` `scene` `detail`
  - 每个 `asset_plan` 项都带 `role_label/goal/background_mode/text_policy/composition_hint/aspect_ratio`
  - 每个 `prompt_plan` 项都带 `reference_image_ids/must_keep/must_avoid/background_rule/composition_rule/lighting_rule/fidelity_rule/final_prompt_base`
  - 当前支持在 Step 5 通过 `planner_instruction` 对整组策略做一轮额外优化

### 3.5 Prompt Composer + Image Generation Agent
- 输入：copy、strategy、asset_role、可选 instruction、参考图
- 输出：单图结构化 prompt 预览与图片字节
- 状态变更：job `running`，逐图产出 `asset_ready`
- 失败处理：上游失败 `50202`，任务写 `job_failed`
- 重试策略：
  - 当前主图组默认优先走 `/v1/images/edits`，把参考图以 multipart 形式上传到上游
  - `/images/edits` 若在提交阶段出现传输层断连，会先做请求级重试；若仍失败，只对当前单张图做内部重试
  - 当上游返回 `task_id` 时，会基于同一个 `task_id` 轮询结果接口拿最终图片链接
  - 图片下载遇到传输层异常时，会做请求级重试
  - 生图链路默认不再因为 `upstream_image_error` 进入 Celery 整任务重试，避免重复消费上游额度
- 参考图选择规则：
  - 参考图优先级：`front > angle45 > side > extra`
  - `hero` / `white_bg` / `selling_point` / `scene`：优先 `front + angle45`
  - `detail`：优先 `front + side`，没有 `side` 时退回 `angle45`
  - 单个 role 最多引用 2 张参考图
- 并发规则：
  - 整组生图内部最大并发数为 `2`
  - 即使内部并发执行，Asset 最终持久化顺序仍按 `display_order`
- Prompt 结构：
  - `blocks.goal`
  - `blocks.subject`
  - `blocks.composition`
  - `blocks.background`
  - `blocks.style`
  - `blocks.selling_points`
  - `blocks.constraints`
  - `blocks.instruction`
- 一期角色约束：
  - `hero`：主体与第一卖点优先，背景简洁，不做海报拼贴
  - `white_bg`：独立白底分支，纯白无缝背景，单产品完整展示，无人物无道具无场景
  - `selling_point`：只聚焦单一卖点，不依赖图中文字
  - `scene`：强调真实使用场景，环境不抢主体
  - `detail`：强调局部结构、材质和纹理
- 白底分支额外规则：
  - 生成后执行轻量白底校验：边缘白色占比、外环白色占比、主体连通域数量
  - 若校验失败，只对白底图内部追加更强白底约束再尝试 1 次
  - 若二次仍失败，整 job 直接 `job_failed`，不产出 `partial_succeeded`

### 3.6 Storage/Versioning Agent
- 输入：图片字节、session_id、round/version、role/order
- 输出：`image_url`、`thumbnail_url`、图片元数据
- 一致性规则：
  - 每次生成都新写文件，不覆盖旧文件
  - `version_no` 单调递增
  - 单图重生成写 `parent_asset_id`
  - 被替代图标记为 `superseded`

### 3.7 Event & Lock Agent
- 输入：job 生命周期与任务上下文
- 输出：`job_events`（SSE 数据源）+ 锁控制结果
- 事件：`job_queued/job_started/job_progress/asset_ready/job_succeeded/job_failed`
- 并发规则：
  - 同 session 同时最多 1 个生图任务
  - 同 user 同时最多 1 个生图任务
  - Redis 不可用时降级到 DB 检查

## 4. 三类 regenerate 语义对比
| 类型 | 入口 | 作用范围 | round_no | version_no | parent_asset_id |
|---|---|---|---|---|---|
| `global_edit` | `POST /sessions/{id}/results/global-edit` | 当前实现按整组重做 | +1 | +1 | 否 |
| `regenerate_gallery` | `POST /sessions/{id}/results/regenerate` | 整组重做 | +1 | +1 | 否 |
| `regenerate_asset` | `POST /assets/{id}/regenerate` | 单图重做 | 不变 | +1 | 是 |

## 5. 时序图

### 5.1 首次生图链路
```mermaid
sequenceDiagram
    participant FE as Frontend
    participant API as Session Orchestrator
    participant DB as PostgreSQL
    participant W as Worker
    participant U as whatai
    participant S as Storage

    FE->>API: POST /sessions/{id}/generations
    API->>DB: 创建 job(generate_gallery, queued)
    API->>DB: 写 job_queued
    API->>W: dispatch q.generation
    W->>DB: job running + job_started
    W->>U: POST /images/generations?async=true
    U-->>W: task_id
    loop 轮询同一个 task_id
        W->>U: GET /images/tasks/{task_id}
        U-->>W: NOT_START/IN_PROGRESS/SUCCESS
    end
    W->>U: GET image_url
    U-->>W: image bytes
    W->>S: save_generated_image
    S-->>W: image_url + thumbnail_url
    W->>DB: 写 asset + asset_ready
    W->>DB: session.completed + version更新
    W->>DB: job_succeeded
    FE->>API: GET /jobs/{job_id}/events
    API-->>FE: SSE 持续推送
```

### 5.2 全局修改链路
```mermaid
sequenceDiagram
    participant FE as Frontend
    participant API as Session Orchestrator
    participant DB as PostgreSQL
    participant W as Worker

    FE->>API: POST /sessions/{id}/results/global-edit
    API->>DB: 并发检查 + 锁 + 创建 job(global_edit)
    API->>W: dispatch q.generation
    W->>DB: 旧版本 assets 标记 superseded
    W->>DB: 生成新版本 assets
    W->>DB: version_no + 1, job_succeeded
```

### 5.3 单图重生成链路
```mermaid
sequenceDiagram
    participant FE as Frontend
    participant API as Session Orchestrator
    participant DB as PostgreSQL
    participant W as Worker

    FE->>API: POST /assets/{asset_id}/regenerate
    API->>DB: 创建 job(regenerate_asset), 写 parent_asset_id
    API->>W: dispatch q.generation
    W->>DB: 原 asset 标记 superseded
    W->>DB: 创建新 asset(version+1, parent_asset_id=旧图)
    W->>DB: job_succeeded
```

## 6. 一致性与可追溯约束
1. Job 是唯一执行真相：任何生图动作都必须先建 job。
2. Event 可重放：前端状态应由 job + job_events 驱动。
3. 版本不可回退：`latest_result_version` 仅向前增长。
4. 父子可追溯：单图重生成必须保存 `parent_asset_id`。
5. 失败可定位：失败必须写 `job_failed` 且带错误信息。
6. Prompt 可追溯：最终写入 `assets.prompt_snapshot` 的是实际提交给上游的 `final_prompt`。
7. 引用可追溯：`assets.generation_snapshot` 必须记录 `reference_image_ids/reference_slots/upstream_endpoint/planner_instruction/size`。

## 6.1 Prompt Debug 只读接口
- 入口：`POST /sessions/{session_id}/prompts/preview`
- 作用：
  - 查看“当前 copy + 当前平台 + 当前 instruction”算出来的 prompt
  - 查看当前计划会使用哪些参考图
  - 对比最近一版已生成资产上的 `prompt_snapshot + generation_snapshot`
- 只读约束：
  - 不创建 job
  - 不写库
  - 不请求上游生图
- 返回重点：
  - `prompts[]`：当前预览 prompt
  - `reference_manifest[]`：当前可用参考图清单
  - `latest_assets[]`：最近真实出图时保存的 prompt 快照与执行快照

## 7. 当前实现边界
- 当前仅实现“逻辑 Agent 协作”，不是独立 Agent 微服务编排。
- success validator、平台合规检测、自动纠偏链路尚未接入。
- `scope=selected` 的局部全局修改尚未在执行层生效（当前按整组处理）。
