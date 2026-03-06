# API 联调指南（以当前实现为准）

## 1. 基础约定

### 1.1 Base URL
- 前缀：`/api/v2`
- 健康检查：`GET /healthz`

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
- Job 状态：`queued` `running` `succeeded` `failed`
- 任务事件：`job_queued` `job_started` `job_progress` `asset_ready` `job_succeeded` `job_failed`

### 1.4 常用错误码
- `40002` `invalid_session_status`
- `40003` `invalid_platform`
- `40004` `invalid_copy_field`
- `40005` `too_many_images`
- `40006` `unsupported_file_type`
- `40007` `file_too_large`
- `40008` `missing_required_images`
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
  - `POST /sessions/{session_id}/images`
  - `DELETE /sessions/{session_id}/images/{image_id}`
- 关键字段：
  - `slot_type`: `front | angle45 | side | extra`
  - `display_order`: 建议按前端展示顺序传入
- 校验规则（当前实现）：
  - MIME：`image/jpeg | image/png | image/webp`
  - 单图大小：<= 10MB
  - 单 session 最多 6 张
- 成功后：session 从 `created` 进入 `images_uploaded`
- 常见错误：`40005` `40006` `40007`
- 并发/幂等：无 Idempotency-Key

### Step 2 分析
- 前置状态：建议至少 1 张未删除图片
- 接口：
  - `POST /sessions/{session_id}/analysis`
  - `GET /sessions/{session_id}/analysis`
- 成功后：
  - 生成 `analysis` job（队列 `q.analysis`）
  - session 状态：`analyzing -> analyzed`
  - 自动写入 `analysis_snapshot`
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
- 常见错误：`40003`
- 并发/幂等：无 Idempotency-Key

### Step 4 copy 确认与字段 regenerate
- 前置状态：建议 `platform_selected` 或 `analyzed`
- 接口：
  - `GET /sessions/{session_id}/copy`
  - `PUT /sessions/{session_id}/copy`
  - `POST /sessions/{session_id}/copy/regenerate`
  - `GET /sessions/{session_id}/copy/regenerate/{job_id}`
- regenerate 支持字段：`headline` `selling_points` `usage_scenes` `specs`
- 语义：regenerate 结果写在 `job.result_payload.generated_fields`，**不会自动覆盖** `confirmed_copy`
- 常见错误：`40004` `40402`
- 幂等：`POST /copy/regenerate` 支持 `Idempotency-Key`

### Step 5 策略预览
- 前置状态：
  - `confirmed_copy` 已保存
  - `active_platform_id` 已设置
- 接口：`POST /sessions/{session_id}/strategy/preview`
- 当前实现行为：
  - 立即同步生成预览并落库
  - 创建 `build_strategy` job 记录，但不进队列
- 成功后：状态写为 `strategy_ready`
- 常见错误：`40002` `40003`
- 并发/幂等：无 Idempotency-Key

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
- 版本规则：
  - `generate_gallery` / `global_edit` / `regenerate_gallery`：`round_no + 1` 且 `version_no + 1`
  - `regenerate_asset`：`version_no + 1`，`round_no` 保持当前轮次，且写 `parent_asset_id`
- 并发保护：
  - 同 session 或同 user 同时只允许 1 个运行中生图任务
  - 冲突返回 `40901`
- 幂等：上述 4 个 POST 都支持 `Idempotency-Key`

## 3. 任务状态与事件流

### 3.1 轮询状态
- 接口：`GET /jobs/{job_id}`
- 用途：展示 `status/progress/stage/error_code/error_message`

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
  - 图片任务结果当前按同一 `task_id` 约每 20 秒轮询一次，最长约 8 分钟；前端若见到 job 长时间停在 `generating`，不应立刻重复触发生图

### 3.3 前端消费建议
- 建议同时使用：
  - SSE 实时展示阶段进度与单图就绪
  - Job 轮询兜底（SSE 中断或网络抖动）

## 4. 实现 vs SPEC 差距清单（集中维护）
1. 鉴权接口（`/auth/register` `/auth/login` `/auth/me`）未实现，当前固定测试用户。
2. `build_strategy` 当前为同步执行，不走 Worker 队列。
3. `WhataiClient.analyze_images` 与 `regenerate_copy` 当前返回占位结果，尚未解析上游真实输出。
4. `global_edit` 的 `scope=selected` 参数已接收，但执行时仍按整组处理。
5. Job 状态虽然定义了 `partial_succeeded`/`canceled`，当前实现不会产出这两种状态。
6. 上传图片未实现“建议尺寸 >= 1000x1000”的强校验。

## 5. 联调最短路径
1. `POST /sessions`
2. `POST /sessions/{id}/images`
3. `POST /sessions/{id}/analysis`
4. `PUT /sessions/{id}/platform-selection`
5. `PUT /sessions/{id}/copy`
6. `POST /sessions/{id}/strategy/preview`
7. `POST /sessions/{id}/generations`
8. `GET /jobs/{job_id}` 或 `GET /jobs/{job_id}/events`
9. `GET /sessions/{id}/results`
10. `GET /sessions/{id}/download`
