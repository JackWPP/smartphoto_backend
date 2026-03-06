# SmartPhoto Backend SPEC v2

> 版本：v2.0  
> 日期：2026-03-06  
> 状态：可作为 Claude Code / Codex 的直接开发输入  
> 文档定位：以后端 API 为中心，前端按本接口约定调整  
> 单一真相：当前前端 6 步流程 + 会议纪要 + 既有 SPEC 的可复用工程部分

---

## 1. 文档目标

本 SPEC 用于重定义 SmartPhoto 当前阶段的后端系统，目标不是继续兼容旧版“上传→识别→平台→主图+详情页”的抽象方案，而是**以当前前端真实 6 步流程为真相源**，输出一份可直接开工的后端实现规格。

本版明确解决以下问题：

1. 旧版 SPEC 与当前前端交互不完全一致。
2. 系统从第一天开始就要按**异步任务 / 队列化**方式设计，不能再依赖纯内存 BackgroundTasks 作为唯一真相。
3. Step 4 不只是“确认参数”，还要支持**字段级 regenerate**。
4. 结果页不是只读下载页，而是支持**全局修改 / 整组重生成 / 单图重生成**的操作页。
5. 当前版本**不做 success validator / 平台合规自动校验**，只保证图片生成链路跑通。

---

## 2. 当前版本的产品范围

### 2.1 当前版本要做什么

当前版本只聚焦于：

- 用户上传 1~6 张产品图
- AI 分析产品信息、图片质量、建议补充视角
- 用户选择平台
- 用户编辑/确认主图文案方案
- 用户在 Step 4 对指定字段触发 regenerate
- 后端生成“平台适配的一整组主图”
- 结果页查看整组结果
- 结果页执行全局修改、整组重生成、单图重生成
- 批量下载结果图
- 全流程异步任务化，支持后续接入 Redis/队列/多 worker

### 2.2 当前版本明确不做

以下功能不属于本版交付范围：

- 自动 success 校验 / 自动平台过审校验
- 白底检测、主体占比检测、自动违规检测
- 水印预览 / 防白嫖机制
- 支付后再出高清图
- 类似 Linkfox 的画布级文字直接编辑
- 详情页长图拼接生产级交付
- 多平台一次性批量生成多套结果

### 2.3 范围调整结论

旧版 SPEC 中“主图 + 详情页长图”属于早期设计。本版以后端落地优先，**当前阶段默认只交付主图组生成**。详情页长图、水印、高清图付费下载等能力保留在后续阶段。

---

## 3. 单一业务真相：以前端 6 步流程为准

当前真实流程定义为：

1. **上传图片**
2. **AI 分析**
3. **选择平台**
4. **确认主图文案方案**
5. **确认方案 / 生成策略预览**
6. **生成中 / 查看结果 / 二次修改**

### 3.1 每一步的业务含义

#### Step 1：上传图片

用户上传 1~6 张产品图，图片槽位具有业务语义：

- 正面图 `front`
- 45°图 `angle45`（推荐）
- 侧面图 `side`
- 补充图 `extra`

后端必须保留图片的：

- 槽位类型
- 显示顺序
- 原图尺寸
- 文件大小
- MIME 类型
- URL

#### Step 2：AI 分析

系统输出的不是单一结论，而是一份结构化分析结果，至少包括：

- 产品基础识别结果
- 图片质量评估
- 缺失视角建议
- 文案草稿 / 参数候选
- 建议补图提示

#### Step 3：选择平台

前端当前展示多个平台卡片。后端必须支持：

- 保存所选平台列表 `selected_platform_ids`
- 指定当前生成所使用的平台 `active_platform_id`

说明：

- 数据结构允许多选
- 当前版本只为 `active_platform_id` 生成一套结果
- 真正的“一次选多个平台、同时出多套图”不在本版范围内

#### Step 4：确认主图文案方案

本页是**结构化编辑页**，不是自由文本页。后端要支持字段级保存与字段级 regenerate。

本页核心字段：

- 产品名称 `product_name`
- 产品品类 `category`
- 主图标题文案 `headline`
- 核心卖点文案 `selling_points`
- 使用场景描述 `usage_scenes`
- 产品规格参数 `specs`
- 风格选择 `style_choice`
- 风格自定义 `style_custom`
- 可选参数候选 `key_parameters[]`

#### Step 5：确认方案 / 策略预览

本页展示的是**生成策略预览**，不是新的编辑主界面。其作用是：

- 汇总当前选择的产品信息和文案信息
- 汇总平台专属策略
- 让用户最终确认是否开始生成

本页不引入新的复杂 AI 流程。

#### Step 6：生成与结果页

本页承载三类状态：

- 生成中：显示进度与预计耗时
- 已完成：展示一整组结果图
- 修改中：对结果集做二次编辑/重生成

结果页支持：

- 整组重生成
- 全局修改后重生成
- 单图重生成
- 下载整组图片

结果页**不要求前端展示图片标签**。后端内部仍然需要保留图片角色，以便生成和重生成时稳定控制。

---

## 4. 关键架构决策

### 4.1 架构原则

1. **API 层和任务执行层解耦**。
2. 所有重任务必须是 **job-based**，不能靠同步长请求硬跑。
3. 任务状态必须有**持久真相**，不能只存内存。
4. 当前版本先不做 success validator，但任务体系必须能承接后续 validator。
5. 生成结果必须带版本信息，支持后续重生成追溯。

### 4.2 推荐技术栈

| 层 | 选型 | 说明 |
|---|---|---|
| Web API | FastAPI | 继续使用，适合 REST + SSE |
| ORM | SQLAlchemy 2.x + Alembic | 标准迁移链路 |
| 主数据库 | PostgreSQL | 本版直接上 PG，不再用 SQLite 作为主库 |
| 队列 / 缓存 | Redis | 任务队列、进度缓存、幂等锁、限流计数 |
| Worker | Redis-backed Worker（实现可选 Celery / Dramatiq / ARQ） | 本 SPEC 约定抽象，不锁死某个框架 |
| 图片处理 | Pillow | 缩放、压缩、导出 |
| 存储 | OSS / COS / S3 兼容对象存储 | 不建议线上继续依赖本地磁盘 |
| 鉴权 | JWT | Bearer Token |
| SSE | sse-starlette 或 FastAPI 原生流式响应 | 推送任务进度 |
| LLM / Image API | whatai.cc | 沿用既有统一中转 |

### 4.3 逻辑部署形态

```text
[Client / Frontend]
        |
        v
[FastAPI API Service]
        |
        +--> PostgreSQL
        +--> Redis
        +--> Object Storage
        |
        v
[Worker Service(s)]
        |
        +--> whatai.cc /v1/chat/completions
        +--> whatai.cc /v1/images/generations
```

### 4.4 为什么这版不再接受“纯内存任务状态”

旧版的 `BackgroundTasks + 内存 task_states` 只适合 demo，不适合当前目标。

当前版本要求：

- 支持多 worker
- 支持排队
- 支持任务恢复/查询
- 支持后续扩展高并发

因此：

- 任务状态必须落 PostgreSQL
- 任务调度必须经过 Redis 或等价队列层
- SSE 只能读持久化状态或队列进度，不允许把进程内 dict 当真相

---

## 5. 核心对象模型

本版统一使用三层对象：

- **Session**：一次制作流程
- **Job**：一次异步动作
- **Asset**：一张生成结果图

### 5.1 Session

一个 Session 代表用户从上传到生成再到重生成的完整业务上下文。

```python
class Session:
    id: UUID
    user_id: UUID

    status: str                 # 见状态机
    current_step: int           # 1~6

    selected_platform_ids: list[str]   # 允许多选
    active_platform_id: str | None     # 当前生成使用的平台

    analysis_snapshot: dict | None     # Step 2 输出
    confirmed_copy: dict | None        # Step 4 用户确认后的结构化字段
    strategy_preview: dict | None      # Step 5 策略预览

    latest_analysis_job_id: UUID | None
    latest_copy_job_id: UUID | None
    latest_strategy_job_id: UUID | None
    latest_generate_job_id: UUID | None

    generation_round: int              # 第几轮出图，从1开始
    latest_result_version: int         # 当前结果版本号

    created_at: datetime
    updated_at: datetime
```

### 5.2 SessionImage

```python
class SessionImage:
    id: UUID
    session_id: UUID

    slot_type: str             # front | angle45 | side | extra
    display_order: int

    source_url: str
    width: int
    height: int
    mime_type: str
    file_size: int

    is_deleted: bool
    created_at: datetime
```

### 5.3 Job

```python
class Job:
    id: UUID
    session_id: UUID

    job_type: str              # analysis | regenerate_copy | build_strategy | generate_gallery | regenerate_gallery | regenerate_asset | global_edit
    status: str                # queued | running | succeeded | failed | canceled | partial_succeeded

    progress: int              # 0~100
    stage: str | None          # 例如 analyzing / composing_prompts / generating / storing

    input_payload: dict | None
    result_payload: dict | None

    retry_count: int
    priority: int
    idempotency_key: str | None

    error_code: str | None
    error_message: str | None

    queued_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime
```

### 5.4 Asset

```python
class Asset:
    id: UUID
    session_id: UUID
    job_id: UUID

    round_no: int              # 第几轮生成
    version_no: int            # 版本号
    parent_asset_id: UUID | None   # 单图重生成时指向原图

    platform_id: str
    asset_role: str            # hero | scene | selling_point | detail | lifestyle | comparison | white_bg | custom
    display_order: int

    image_url: str
    thumbnail_url: str | None
    width: int
    height: int
    mime_type: str
    file_size: int

    prompt_snapshot: str | None
    edit_instruction: str | None

    status: str                # ready | failed | superseded
    created_at: datetime
```

---

## 6. 结构化数据定义

### 6.1 Step 2 分析结果 schema

```json
{
  "recognized_product": {
    "product_name": "智能空气净化器",
    "category": "家电 > 空气净化器",
    "image_type": "实物图",
    "confidence": 0.82
  },
  "image_assessment": {
    "quality_score": 0.88,
    "lighting": "good",
    "clarity": "good",
    "background_cleanliness": "medium"
  },
  "missing_views": ["side"],
  "suggestions": [
    "图片质量良好，适合AI处理",
    "建议补充侧面图以获得更好的生成效果"
  ],
  "copy_draft": {
    "headline": "静享洁净呼吸",
    "selling_points": "除甲醛、低噪音、母婴可用",
    "usage_scenes": "客厅、卧室、母婴房",
    "specs": "CADR 500m³/h｜噪音≤33dB｜适用面积60m²"
  },
  "key_parameters": [
    {
      "key": "cadr",
      "label": "CADR值",
      "value": "500",
      "unit": "m³/h",
      "confidence": 0.72,
      "editable": true
    },
    {
      "key": "noise",
      "label": "噪音",
      "value": "33",
      "unit": "dB",
      "confidence": 0.68,
      "editable": true
    }
  ],
  "suggested_styles": ["现代简约", "科技感", "母婴温馨"]
}
```

### 6.2 Step 4 文案确认 schema

```json
{
  "product_name": "智能空气净化器",
  "category": "家电 > 空气净化器",
  "headline": "除甲醛99.9% 静享洁净呼吸",
  "selling_points": "四重过滤｜低噪音｜母婴适用",
  "usage_scenes": "客厅、卧室、母婴房",
  "specs": "CADR 500m³/h｜噪音≤33dB｜适用面积60m²",
  "style_choice": "现代简约",
  "style_custom": "柔和自然、浅色家居、干净高级感",
  "key_parameters": [
    {"key": "cadr", "label": "CADR值", "value": "500", "unit": "m³/h"},
    {"key": "noise", "label": "噪音", "value": "33", "unit": "dB"}
  ]
}
```

### 6.3 Step 5 策略预览 schema

```json
{
  "product_name": "智能空气净化器",
  "core_selling_point": "除甲醛 + 低噪音 + 母婴适用",
  "core_scene": "卧室 / 客厅 / 母婴房",
  "core_performance": "CADR 500m³/h, 噪音≤33dB",
  "headline": "除甲醛99.9% 静享洁净呼吸",
  "style_summary": "现代简约 + 柔和自然",
  "platform_strategy": "Temu 跨境主图标准，输出 5 张主图，其中 1 张白底图",
  "asset_plan": [
    {"role": "hero", "display_order": 1},
    {"role": "selling_point", "display_order": 2},
    {"role": "scene", "display_order": 3},
    {"role": "detail", "display_order": 4},
    {"role": "white_bg", "display_order": 5}
  ]
}
```

---

## 7. 状态机

### 7.1 Session 状态

```text
created
  -> images_uploaded
  -> analyzing
  -> analyzed
  -> platform_selected
  -> copy_ready
  -> strategy_ready
  -> generating
  -> completed
  -> failed
```

### 7.2 Session 状态定义

| 状态 | 含义 |
|---|---|
| created | 会话已创建，尚未上传图片 |
| images_uploaded | 已上传至少 1 张图片 |
| analyzing | 正在执行分析任务 |
| analyzed | Step 2 结果已产出 |
| platform_selected | 平台已选择 |
| copy_ready | Step 4 文案已保存 |
| strategy_ready | Step 5 预览已准备完成 |
| generating | 正在生成图库 |
| completed | 当前轮次结果已产出 |
| failed | 当前主流程失败 |

### 7.3 重要语义约束

1. `completed` 只表示**生成流程完成并产出结果**。
2. `completed` **不表示**平台合规校验通过。
3. `completed` **不表示**电商平台审核成功。
4. 当前版不引入 `validation_passed` / `validation_failed` 概念。

### 7.4 Job 状态

| 状态 | 含义 |
|---|---|
| queued | 已入队，尚未执行 |
| running | 执行中 |
| succeeded | 执行成功 |
| partial_succeeded | 部分成功，至少有部分结果可用 |
| failed | 执行失败 |
| canceled | 已取消 |

---

## 8. 平台与图片输出策略

### 8.1 平台支持分层

本版定义三类平台支持级别：

#### A. Tuned（当前重点适配）

- `1688`
- `taobao`
- `amazon`
- `douyin`
- `temu`

#### B. Generic（使用通用模板）

- `alibaba_intl`
- `jd`
- `pdd`
- `xiaohongshu`
- `tiktok`
- `official_site`

#### C. Custom

- `custom`

### 8.2 当前版本只生成“主图组”

当前版本的图库结果是一个**有顺序的一整组主图**，默认按平台输出 5~7 张。

### 8.3 推荐输出数量

| 平台 | 输出数量 | 默认比例 | 说明 |
|---|---:|---|---|
| 1688 | 5 | 1:1 | 包含白底图 |
| taobao | 5 | 1:1 | 包含白底图 |
| douyin | 5 | 1:1 | 电商主图组 |
| temu | 5 | 1:1 | 跨境通用主图组 |
| amazon | 7 | 1:1 | 跨境主图组，含白底图 |
| generic_cn | 5 | 1:1 | 国内平台通用 |
| generic_cross_border | 5~7 | 1:1 | 跨境通用 |

### 8.4 Asset Role（内部角色）

结果页不强制展示标签，但后端必须保留角色。

推荐角色枚举：

- `hero`
- `selling_point`
- `scene`
- `detail`
- `lifestyle`
- `comparison`
- `white_bg`
- `custom`

### 8.5 角色模板建议

#### 5 张模板

1. `hero`
2. `selling_point`
3. `scene`
4. `detail`
5. `white_bg`

#### 7 张模板

1. `hero`
2. `selling_point`
3. `scene`
4. `detail`
5. `lifestyle`
6. `comparison`
7. `white_bg`

---

## 9. Prompt 与生成策略

### 9.1 当前版的总原则

Prompt 系统要兼顾可控性和工程复杂度，因此本版采用：

- **分析阶段**：使用多模态 LLM
- **Step 4 regenerate**：使用 LLM
- **Step 5 策略预览**：确定性拼装，不再额外依赖 LLM
- **生成前 prompt 组装**：以模板为主，可保留 `PromptPolishService` 作为可选增强层

### 9.2 推荐生成链路

```text
Step 2 Analysis Job
  -> 提取产品信息 / 参数候选 / 文案草稿 / 图片建议

Step 4 Copy Regenerate Job（可选）
  -> 按目标字段重写 headline / selling_points / usage_scenes / specs

Step 5 Strategy Preview
  -> 按 platform profile + confirmed_copy + asset plan 生成预览摘要

Step 6 Generate Gallery Job
  -> PromptComposer 为每个 asset_role 生成 prompt
  -> 调用图片模型并发生成
  -> 下载、后处理、存储
  -> 记录 assets
```

### 9.3 为什么 Step 5 不再做第二轮复杂 AI

理由：

1. 避免旧版 SPEC 中“Step 4/5 到底调几次 LLM”的歧义。
2. 保持 Step 5 为稳定可预览的确认层。
3. 减少额外耗时，提高队列吞吐能力。

### 9.4 PromptComposer 输入

- `confirmed_copy`
- `strategy_preview`
- `platform profile`
- `asset_role`
- `reference images`

### 9.5 当前版不做的 Prompt 事情

- 不做 success validator 驱动的 prompt 自动重试
- 不做基于检测器的 prompt 纠偏
- 不做自动平台过审闭环

---

## 10. 异步任务与队列设计

### 10.1 必须异步化的任务

以下动作一律走 Job：

- 图片分析 `analysis`
- 文案 regenerate `regenerate_copy`
- 策略构建 `build_strategy`（可实现为轻任务）
- 整组生图 `generate_gallery`
- 整组重生成 `regenerate_gallery`
- 单图重生成 `regenerate_asset`
- 全局修改 `global_edit`

### 10.2 队列分层建议

建议至少分三类队列：

- `q.analysis`
- `q.copy`
- `q.generation`

### 10.3 Worker 并发建议

建议参数：

- 分析任务并发：`2~4`
- 文案 regenerate 并发：`2~4`
- 图片生成任务并发：`2~6`
- 单个图库任务内图片并发：`2~4`

### 10.4 并发控制原则

1. 限制“单用户同时运行中的生成任务数”。
2. 限制“全局同时调用图片模型的请求数”。
3. 结果页再次发起 generate / regenerate 时必须做幂等保护或排它锁。

### 10.5 最低可接受约束

| 项目 | 建议值 |
|---|---:|
| 单用户同时运行中的图库任务 | 1 |
| 全局图片模型调用并发 | 3 |
| 分析任务超时 | 60s |
| 文案 regenerate 超时 | 60s |
| 图库生成任务超时 | 300s |
| 任务最大重试次数 | 2 |

### 10.6 进度推送原则

SSE 推送的是 **Job 状态变化**，而不是前端自己拼状态。

支持事件：

- `job_queued`
- `job_started`
- `job_progress`
- `asset_ready`
- `job_partial_succeeded`
- `job_succeeded`
- `job_failed`

---

## 11. Regenerate 语义定义

这是本版最容易被做乱的地方，必须单独定义。

### 11.1 Step 4 字段级 regenerate

用途：用户还没开始生成图片，只想重新生成某些文案字段。

特点：

- 作用对象是 `confirmed_copy`
- 不产生图片
- 不增加 generation_round
- 可只 regenerate 指定字段

目标字段：

- `headline`
- `selling_points`
- `usage_scenes`
- `specs`

### 11.2 整组重生成 `regenerate_gallery`

用途：用户对当前整组结果不满意，直接重新出一套。

特点：

- 使用当前 `confirmed_copy`
- 生成新的 `round_no`
- 旧结果保留，不覆盖物理文件
- `latest_result_version` 指向最新一轮

### 11.3 全局修改 `global_edit`

用途：用户在结果页输入一句全局修改意见，例如：

- 让画面更温馨一些
- 增加宠物元素
- 改成小红书风格
- 整体色调偏暖

特点：

- 面向当前整组或指定若干图
- 会生成新版本
- 修改意见需记录到 `Job.input_payload.instruction`

### 11.4 单图重生成 `regenerate_asset`

用途：用户只想重做某一张图。

特点：

- 仅针对一个 `asset_id`
- 新图的 `parent_asset_id` 指向旧图
- 需要保持与当前图库风格一致
- 不要求前端做画布编辑，只做“指令驱动重生图”

---

## 12. API Contract

Base URL：`/api/v2`

统一响应：

```json
{
  "code": 0,
  "message": "success",
  "data": {}
}
```

错误响应：

```json
{
  "code": 40001,
  "message": "error message",
  "data": null
}
```

### 12.1 Auth

#### POST `/auth/register`

#### POST `/auth/login`

#### GET `/auth/me`

> 认证部分可沿用旧版实现，不再展开。

---

### 12.2 Platform

#### GET `/platforms`

返回平台注册表。

```json
{
  "code": 0,
  "data": {
    "items": [
      {
        "id": "temu",
        "name": "Temu",
        "support_level": "tuned",
        "default_image_count": 5,
        "default_aspect_ratio": "1:1"
      }
    ]
  }
}
```

---

### 12.3 Session

#### POST `/sessions`

创建会话。

```json
{
  "code": 0,
  "data": {
    "session_id": "uuid",
    "status": "created",
    "current_step": 1
  }
}
```

#### GET `/sessions/{session_id}`

获取会话聚合快照，供前端页面刷新和恢复。

```json
{
  "code": 0,
  "data": {
    "session_id": "uuid",
    "status": "copy_ready",
    "current_step": 4,
    "selected_platform_ids": ["temu"],
    "active_platform_id": "temu",
    "analysis_snapshot": {},
    "confirmed_copy": {},
    "strategy_preview": {},
    "latest_generate_job_id": null,
    "generation_round": 0,
    "latest_result_version": 0
  }
}
```

---

### 12.4 Session Images

#### POST `/sessions/{session_id}/images`

上传单张图片，前端按槽位逐张调用更清晰。

`multipart/form-data`

字段：

- `file`
- `slot_type` = `front | angle45 | side | extra`
- `display_order`

返回：

```json
{
  "code": 0,
  "data": {
    "image_id": "uuid",
    "session_id": "uuid",
    "status": "images_uploaded",
    "uploaded_images": [
      {
        "image_id": "uuid",
        "slot_type": "front",
        "display_order": 1,
        "url": "https://..."
      }
    ]
  }
}
```

校验规则：

- JPG / PNG / WEBP（如前端只传 JPG/PNG，也可先限制）
- 单图 ≤ 10MB
- 建议尺寸 ≥ 1000x1000
- 单 session 最多 6 张

#### DELETE `/sessions/{session_id}/images/{image_id}`

删除某张已上传图片。

---

### 12.5 Analysis

#### POST `/sessions/{session_id}/analysis`

触发分析任务。

请求体可为空。

```json
{
  "code": 0,
  "data": {
    "job_id": "uuid",
    "session_id": "uuid",
    "job_type": "analysis",
    "status": "queued"
  }
}
```

#### GET `/sessions/{session_id}/analysis`

返回最新分析结果。

```json
{
  "code": 0,
  "data": {
    "status": "analyzed",
    "analysis_snapshot": {
      "recognized_product": {
        "product_name": "智能空气净化器",
        "category": "家电 > 空气净化器"
      },
      "suggestions": [
        "图片质量良好，适合AI处理",
        "建议补充侧面图以获得更好的生成效果"
      ],
      "missing_views": ["side"]
    }
  }
}
```

---

### 12.6 Platform Selection

#### PUT `/sessions/{session_id}/platform-selection`

```json
{
  "selected_platform_ids": ["temu"],
  "active_platform_id": "temu"
}
```

返回：

```json
{
  "code": 0,
  "data": {
    "session_id": "uuid",
    "status": "platform_selected",
    "selected_platform_ids": ["temu"],
    "active_platform_id": "temu"
  }
}
```

规则：

- `selected_platform_ids` 至少 1 个
- `active_platform_id` 必须属于 `selected_platform_ids`
- 当前版本允许多选保存，但生成时只使用 `active_platform_id`

---

### 12.7 Step 4: Copy Form

#### GET `/sessions/{session_id}/copy`

获取当前文案表单默认值。

```json
{
  "code": 0,
  "data": {
    "product_name": "智能空气净化器",
    "category": "家电 > 空气净化器",
    "headline": "静享洁净呼吸",
    "selling_points": "四重过滤｜低噪音｜母婴适用",
    "usage_scenes": "客厅、卧室、母婴房",
    "specs": "CADR 500m³/h｜噪音≤33dB｜适用面积60m²",
    "style_choice": "现代简约",
    "style_custom": "柔和自然",
    "key_parameters": []
  }
}
```

#### PUT `/sessions/{session_id}/copy`

保存 Step 4 用户编辑结果。

```json
{
  "product_name": "智能空气净化器",
  "category": "家电 > 空气净化器",
  "headline": "除甲醛99.9% 静享洁净呼吸",
  "selling_points": "四重过滤｜低噪音｜母婴适用",
  "usage_scenes": "客厅、卧室、母婴房",
  "specs": "CADR 500m³/h｜噪音≤33dB｜适用面积60m²",
  "style_choice": "现代简约",
  "style_custom": "柔和自然、浅色家居",
  "key_parameters": []
}
```

返回：

```json
{
  "code": 0,
  "data": {
    "session_id": "uuid",
    "status": "copy_ready"
  }
}
```

#### POST `/sessions/{session_id}/copy/regenerate`

字段级 regenerate。

```json
{
  "targets": ["headline", "selling_points"],
  "instruction": "更偏跨境电商风格，语言更直接一些",
  "based_on_current_values": true
}
```

返回 job：

```json
{
  "code": 0,
  "data": {
    "job_id": "uuid",
    "job_type": "regenerate_copy",
    "status": "queued"
  }
}
```

#### GET `/sessions/{session_id}/copy/regenerate/{job_id}`

获取 regenerate 结果。

```json
{
  "code": 0,
  "data": {
    "job_id": "uuid",
    "status": "succeeded",
    "generated_fields": {
      "headline": "Quiet, Clean, Ready for Every Room",
      "selling_points": "H13 filtration｜low noise｜pet-friendly"
    }
  }
}
```

说明：

- regenerate 结果默认**不自动覆盖** `confirmed_copy`
- 前端确认后再调用 `PUT /copy` 保存

---

### 12.8 Step 5: Strategy Preview

#### POST `/sessions/{session_id}/strategy/preview`

根据当前 `confirmed_copy + active_platform_id` 生成策略预览。

```json
{
  "code": 0,
  "data": {
    "session_id": "uuid",
    "status": "strategy_ready",
    "strategy_preview": {
      "product_name": "智能空气净化器",
      "core_selling_point": "除甲醛 + 低噪音 + 母婴适用",
      "core_scene": "卧室 / 客厅 / 母婴房",
      "core_performance": "CADR 500m³/h, 噪音≤33dB",
      "headline": "除甲醛99.9% 静享洁净呼吸",
      "platform_strategy": "Temu 跨境主图标准，输出 5 张主图",
      "asset_plan": [
        {"role": "hero", "display_order": 1},
        {"role": "selling_point", "display_order": 2},
        {"role": "scene", "display_order": 3},
        {"role": "detail", "display_order": 4},
        {"role": "white_bg", "display_order": 5}
      ]
    }
  }
}
```

---

### 12.9 Generate Gallery

#### POST `/sessions/{session_id}/generations`

开始生成整组主图。

Header 可选：

- `Idempotency-Key`

请求：

```json
{
  "instruction": null
}
```

返回：

```json
{
  "code": 0,
  "data": {
    "job_id": "uuid",
    "job_type": "generate_gallery",
    "status": "queued",
    "session_id": "uuid",
    "generation_round": 1
  }
}
```

#### GET `/jobs/{job_id}`

```json
{
  "code": 0,
  "data": {
    "job_id": "uuid",
    "job_type": "generate_gallery",
    "status": "running",
    "progress": 52,
    "stage": "generating",
    "estimated_seconds": 45,
    "error_code": null,
    "error_message": null
  }
}
```

#### GET `/jobs/{job_id}/events`

SSE：

```text
data: {"event":"job_started","job_id":"uuid"}

data: {"event":"job_progress","progress":20,"stage":"composing_prompts"}

data: {"event":"asset_ready","asset_id":"uuid","display_order":1}

data: {"event":"job_succeeded","job_id":"uuid"}
```

---

### 12.10 Results

#### GET `/sessions/{session_id}/results`

返回当前最新版本结果集。

```json
{
  "code": 0,
  "data": {
    "session_id": "uuid",
    "status": "completed",
    "generation_round": 2,
    "latest_result_version": 3,
    "summary": {
      "total_count": 5,
      "ready_count": 5
    },
    "assets": [
      {
        "asset_id": "uuid-1",
        "display_order": 1,
        "image_url": "https://...",
        "thumbnail_url": "https://...",
        "width": 1000,
        "height": 1000,
        "version_no": 3
      }
    ]
  }
}
```

说明：

- 默认返回最新版本
- 前端不用展示 `asset_role`
- 后端内部必须保留 `asset_role`、`prompt_snapshot`

---

### 12.11 Global Edit

#### POST `/sessions/{session_id}/results/global-edit`

```json
{
  "instruction": "让画面更温馨一些，整体偏暖色调",
  "scope": "all",
  "asset_ids": []
}
```

返回：

```json
{
  "code": 0,
  "data": {
    "job_id": "uuid",
    "job_type": "global_edit",
    "status": "queued"
  }
}
```

规则：

- `scope = all` 表示整组重做
- `scope = selected` 时必须传 `asset_ids`

---

### 12.12 Gallery Regenerate

#### POST `/sessions/{session_id}/results/regenerate`

```json
{
  "reason": "not_satisfied",
  "instruction": null
}
```

返回新 job。

---

### 12.13 Asset Regenerate

#### POST `/assets/{asset_id}/regenerate`

```json
{
  "instruction": "保留主体结构，换成更生活化的家庭场景",
  "keep_style_consistency": true
}
```

返回：

```json
{
  "code": 0,
  "data": {
    "job_id": "uuid",
    "job_type": "regenerate_asset",
    "status": "queued"
  }
}
```

---

### 12.14 Download

#### GET `/sessions/{session_id}/download`

下载当前最新版本整组图片 ZIP。

Query：

- `version` 可选，不传默认最新

返回：ZIP 文件流。

---

## 13. 任务执行规则

### 13.1 Analysis Job

输入：

- session images
- active platform（可为空）

输出：

- `analysis_snapshot`
- Session 状态更新为 `analyzed`

### 13.2 Copy Regenerate Job

输入：

- 当前分析结果
- 当前 confirmed_copy
- `targets`
- `instruction`

输出：

- 仅返回字段建议
- 不直接覆盖 `confirmed_copy`

### 13.3 Build Strategy Job / Preview

输入：

- `confirmed_copy`
- `active_platform_id`

输出：

- `strategy_preview`
- Session 状态更新为 `strategy_ready`

### 13.4 Generate Gallery Job

输入：

- `confirmed_copy`
- `strategy_preview`
- session images
- active platform

输出：

- 一组 assets
- Session 状态更新为 `completed`
- `generation_round += 1`

### 13.5 Global Edit Job

输入：

- 当前版本 assets
- 全局修改指令

输出：

- 新版本 assets

### 13.6 Asset Regenerate Job

输入：

- 指定 asset
- 指令
- 当前图库上下文

输出：

- 一个新 asset version
- 旧 asset 标记为 superseded（可选）

---

## 14. 幂等、锁与并发安全

### 14.1 必须加幂等的接口

- `POST /sessions/{id}/analysis`
- `POST /sessions/{id}/copy/regenerate`
- `POST /sessions/{id}/generations`
- `POST /sessions/{id}/results/global-edit`
- `POST /sessions/{id}/results/regenerate`
- `POST /assets/{id}/regenerate`

### 14.2 推荐策略

- 支持 `Idempotency-Key`
- 若同一个 session 已有运行中的图库任务，再次触发图库类任务应返回 `409`
- 使用 Redis 锁：`lock:session:{session_id}:generation`

### 14.3 同时运行限制

- 一个 session 同时最多 1 个运行中的图库任务
- 一个用户同时最多 1 个运行中的图库任务
- 分析任务与图库任务可以并行限制更宽松，但默认也建议按 session 串行

---

## 15. 错误码建议

| 错误码 | 含义 |
|---|---|
| 40001 | invalid_request |
| 40002 | invalid_session_status |
| 40003 | invalid_platform |
| 40004 | invalid_copy_field |
| 40005 | too_many_images |
| 40006 | unsupported_file_type |
| 40007 | file_too_large |
| 40008 | missing_required_images |
| 40101 | unauthorized |
| 40301 | forbidden |
| 40401 | session_not_found |
| 40402 | job_not_found |
| 40403 | asset_not_found |
| 40901 | job_already_running |
| 40902 | duplicate_idempotency_key |
| 42201 | copy_validation_failed |
| 42901 | rate_limited |
| 50001 | internal_error |
| 50201 | upstream_llm_error |
| 50202 | upstream_image_error |
| 50301 | queue_unavailable |

---

## 16. 非功能需求

### 16.1 性能目标（当前版）

| 指标 | 目标 |
|---|---|
| 上传图片接口 P95 | < 2s（不含大文件网络传输） |
| 分析任务完成时间 | 10~30s |
| 文案 regenerate 完成时间 | 10~30s |
| 5 张图库生成完成时间 | 30~120s |
| 任务状态查询接口 P95 | < 300ms |

### 16.2 可扩展目标

系统必须满足：

- API 服务和 Worker 服务可独立横向扩容
- Redis 队列可承接多 worker 消费
- Job 状态与结果存储不依赖单实例内存

### 16.3 监控指标

至少记录：

- job 数量
- job 成功率 / 失败率
- 各 job 类型平均耗时
- 图片模型调用耗时
- LLM 调用耗时
- 每个 session 平均重生成次数
- 每个平台平均输出数量

---

## 17. 开发优先级

### P0：必须先做

- Auth 基础能力
- Session / SessionImage / Job / Asset 四张核心表
- 图片上传
- 分析任务
- 平台选择
- Step 4 文案保存
- Step 4 字段级 regenerate
- Step 5 策略预览
- Step 6 整组生图
- Job 状态查询 + SSE
- 结果页查询
- 批量下载

### P1：紧接着做

- 全局修改
- 整组重生成
- 单图重生成
- 监控日志完善
- Redis 锁 / 幂等保护完善

### P2：后续阶段

- success validator
- 白底检测 / 主体占比检测
- 水印预览
- 支付后高清图
- 画布式文本编辑
- 真正多平台批量生成
- 详情页长图

---

## 18. 对 Claude Code / Codex 的实现约束

1. **不要把任务状态存在内存 dict 里作为唯一真相**。
2. 任何“生成图片”的动作都必须建 `Job` 记录。
3. `completed` 不等于平台校验通过。
4. Step 4 regenerate 只改字段建议，不直接改库里的 `confirmed_copy`。
5. 结果图必须版本化，不能直接物理覆盖旧图。
6. API 必须围绕当前 6 步流程设计，不要回退到旧版“主图+详情页双主线”。
7. 当前版生成的是**一整组主图**，不是生产级详情页长图。
8. 平台结构允许多选保存，但当前实际只生成 `active_platform_id` 的一套结果。

---

## 19. 本版最终结论

这份 v2 SPEC 的核心目的不是“把旧文档写得更完整”，而是**把当前真实前端流程和后端可扩展架构对齐**。

本版的最终立场是：

- 以前端 6 步流程为准
- 以后端 job-based 异步架构为基础
- 当前版本优先交付主图组生成闭环
- 当前版本明确不做 success validator
- Step 4 和结果页都支持 regenerate，但语义不同
- 系统从第一天就为 Redis / 队列 / 多 worker 预留扩展能力


---

## 20. Prompt Contract（本版补齐，可直接实现）

这一节用于避免“提示词只是思路，没有落成实现合同”的问题。

### 20.1 分析任务 Prompt Contract

#### 输入

- `session_id`
- `active_platform_id`（可为空）
- `images[]`
  - `slot_type`
  - `url`
  - `width`
  - `height`
- `language`，默认 `zh-CN`

#### 系统提示词模板

```text
你是电商商品图片分析助手。你的任务不是写长篇描述，而是输出严格 JSON。
你需要基于用户上传的商品图片，完成：
1. 识别商品名称与品类
2. 提取可见卖点、场景、规格候选
3. 评估图片质量与视角完整度
4. 给出是否建议补图
5. 生成可供 Step 4 直接编辑的字段草稿

要求：
- 只能输出 JSON，不要输出 Markdown，不要解释
- 如果不确定，使用 null 或低置信度，不要编造品牌/参数
- 规格参数只提取图片中可以合理推断或清晰可见的内容
- selling_points、usage_scenes、key_parameters 均输出数组
```

#### 用户提示词模板

```text
请分析这组商品图片，并返回以下 JSON：
{
  "recognized_product": {
    "product_name": "string|null",
    "category": "string|null",
    "image_type": "real_product|render|unknown",
    "confidence": 0.0
  },
  "copy_draft": {
    "headline": "string|null",
    "selling_points": ["string"],
    "usage_scenes": ["string"],
    "specs": ["string"],
    "style_choice": "minimal|premium|warm|xiaohongshu|professional|null",
    "key_parameters": [
      {"name": "string", "value": "string", "confidence": 0.0}
    ]
  },
  "image_assessment": {
    "quality_score": 0,
    "lighting": "good|fair|poor",
    "clarity": "good|fair|poor",
    "background_cleanliness": "good|fair|poor",
    "view_completeness": "good|fair|poor"
  },
  "missing_views": ["front", "angle45", "side"],
  "suggestions": [
    {"type": "quality|view|copy", "message": "string"}
  ]
}
```

#### 落库规则

- 原始模型响应保存到 `job.raw_output`
- 解析后的结构化结果保存到 `session.analysis_snapshot`
- `copy_draft` 不直接视为用户确认结果，前端仍需在 Step 4 编辑后再写入 `confirmed_copy`

### 20.2 Step 4 文案 Regenerate Prompt Contract

#### 输入

- `confirmed_copy` 当前值
- `targets[]`，允许值：`headline` / `selling_points` / `usage_scenes` / `specs`
- `user_instruction`，可为空
- `analysis_snapshot.copy_draft`
- `active_platform_id`

#### 系统提示词模板

```text
你是电商商品文案优化助手。你只负责重写指定字段，不要改动未指定字段。
输出必须是 JSON。
文案要求：
- 中文简洁，适合商品主图/电商展示
- 不要出现夸张承诺、极限词、医疗功效暗示
- 如果用户给了风格要求，优先遵守
- headline 控制在 8~20 个汉字优先
- selling_points 每条控制在 6~18 个汉字优先
- usage_scenes 用短语，不写长句
- specs 保持参数化表达，不写营销口吻
```

#### 用户提示词模板

```text
请仅重写 targets 指定的字段，并返回 JSON：
{
  "headline": "string|null",
  "selling_points": ["string"],
  "usage_scenes": ["string"],
  "specs": ["string"]
}

上下文：
- current_confirmed_copy: {{confirmed_copy_json}}
- draft_from_analysis: {{copy_draft_json}}
- targets: {{targets_json}}
- platform: {{active_platform_id}}
- user_instruction: {{user_instruction}}
```

#### 返回处理规则

- 只允许覆盖 `targets` 中声明的字段
- 返回值先挂在 regenerate job 结果中
- 前端确认后，再调用 `PUT /sessions/{session_id}/copy` 覆盖正式 `confirmed_copy`

### 20.3 Step 5 Strategy Preview 拼装合同

Step 5 默认不再调第二轮复杂 LLM，而是后端确定性拼装：

输入：
- `confirmed_copy`
- `active_platform_id`
- `platform_profile`
- `asset_plan`

输出：

```json
{
  "product_name": "智能空气净化器",
  "headline": "除甲醛99.9% 静享净化",
  "core_selling_point": ["H13级滤网", "低噪运行"],
  "core_scene": ["客厅", "卧室"],
  "core_performance": ["CADR 500m³/h", "噪音≤33dB"],
  "platform_strategy": {
    "platform_id": "temu",
    "tone": "clean_commerce",
    "image_count": 7,
    "must_have_roles": ["hero", "scene", "selling", "detail", "white_bg"]
  }
}
```

### 20.4 图库生成 PromptComposer 合同

PromptComposer 必须是纯后端组件，不允许把 prompt 拼装逻辑散落在 controller 里。

#### 输入

- `platform_profile`
- `strategy_preview`
- `confirmed_copy`
- `asset_role`
- `reference_images`
- `global_instruction`（可为空）
- `consistency_seed`（可为空）

#### 输出

- `positive_prompt`
- `negative_prompt`
- `render_params`

#### 推荐正向 Prompt 结构

```text
[商品主体]
{{product_name}}，保留原始商品外观特征，基于参考图生成

[图片角色]
当前目标图片类型：{{asset_role}}

[核心卖点]
{{headline}}
{{selling_points_joined}}

[使用场景 / 规格]
{{usage_scenes_joined}}
{{specs_joined}}

[平台风格要求]
适配 {{platform_name}} 电商主图风格：{{platform_tone}}

[构图要求]
{{composition_rule}}

[画面要求]
高质量商品摄影感，主体清晰，避免多余杂物，避免错误结构，保持与参考图一致的产品形态和颜色

[补充指令]
{{global_instruction_optional}}
```

#### 推荐负向 Prompt 结构

```text
low quality, blurry, extra objects, duplicated product, broken structure,
warped geometry, wrong material, deformed edges, unreadable text,
watermark, logo distortion, extra hands, cropped product, severe shadow,
excessive reflections, cluttered background
```

### 20.5 角色级 Prompt 差异规则

| asset_role | 必须强调 | 必须避免 |
|---|---|---|
| `hero` | 主体居中、卖点聚焦、商业主图感 | 过强背景、杂乱道具 |
| `scene` | 合理生活/使用场景 | 背景喧宾夺主 |
| `selling` | 卖点视觉化表达 | 无关元素堆砌 |
| `detail` | 结构与细节特写 | 主体过远、分辨率不足 |
| `lifestyle` | 氛围感与人群关联 | 误导性人设或过强剧情 |
| `comparison` | 对比关系清晰 | 虚假夸张对比 |
| `white_bg` | 纯净背景、主体完整 | 阴影脏污、彩色背景 |

### 20.6 图片模型调用参数合同

当前版统一通过 Adapter 暴露以下字段：

```python
class ImageGenerationRequest:
    positive_prompt: str
    negative_prompt: str | None
    reference_image_urls: list[str]
    aspect_ratio: str
    width: int
    height: int
    num_images: int = 1
    seed: int | None = None
    extra: dict | None = None
```

#### 最低实现要求

- 每个 asset 生成时必须落 `prompt_snapshot`
- 必须记录 `request_payload` 与上游返回 `response_payload`
- 失败时要带 `provider_error_code` 与 `provider_error_message`

### 20.7 全局修改与重生成 Prompt 合同

#### 全局修改 `global_edit`

输入：
- 当前结果集的 `prompt_snapshot`
- 用户指令 `instruction`
- 选中的 `asset_ids` 或 `all`

处理原则：
- 不是从零重新理解商品，而是在原 prompt 基础上叠加“风格/氛围/颜色/元素”修改
- 不允许偏离商品主体形态

#### 单图重生成 `regenerate_asset`

输入：
- 目标 `asset.prompt_snapshot`
- `asset_role`
- `instruction`
- 同轮结果中其他图片的风格摘要（可选）

处理原则：
- 保持与同轮图库风格一致
- 仅对单图做定向重生成

---

## 21. 开工就绪边界（实话版）

这一节不是功能描述，而是对“能不能直接开工”的边界说明。

### 21.1 现在可以直接开工的部分

以下内容已经足够直接编码：

- 数据库表结构
- Session / Job / Asset 状态机
- 图片上传与对象存储
- 分析任务
- Step 4 文案保存与字段级 regenerate
- Step 5 策略预览拼装
- Step 6 图库生成任务
- 结果查询
- 全局修改 / 整组重生成 / 单图重生成
- SSE 任务进度推送
- Redis 队列与 Worker 抽象
- PromptComposer 与 Adapter 层骨架

### 21.2 仍然不能“绝对保证”的部分

以下内容不是 SPEC 不完整，而是模型系统天然存在不确定性：

- 某条 prompt 是否一定产出你想要的视觉效果
- 某平台最终审核是否一定通过
- 某类商品在所有场景下都能稳定识别正确
- 上游模型供应商的稳定性与成本波动

因此，本 SPEC 能保证的是：

- 主链路工程可直接开工
- API、数据模型、任务模型、Prompt 合同已经闭合
- 开发不会因为“Step 4/5 到底怎么调模型”这种规格歧义卡住

本 SPEC 不能保证的是：

- 视觉效果一次到位
- 所有 prompt 无需调参
- 所有商品类目零回归

### 21.3 对项目经理的最终判断

如果你的目标是：

- 今天就让 Claude Code / Codex 开始搭后端骨架
- 让后端按当前前端 6 步流程落地
- 不再被旧版 SPEC 的歧义拖住

那么这份 v2 可以直接作为开工文档。

如果你的目标是：

- 保证上线后无需再调 prompt
- 保证所有商品图都出得漂亮
- 保证各电商平台一次性过审

那任何 SPEC 都不能给这种保证，因为那不是规格问题，而是模型效果与业务验证问题。
