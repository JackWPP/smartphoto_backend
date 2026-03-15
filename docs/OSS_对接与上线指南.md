# OSS 对接与上线指南

## 1. 目标
- 线上存储默认建议切到 `S3` 兼容私有桶。
- 浏览器上传统一走 `presign -> 直传 -> complete`。
- 后端和 worker 负责生成结果写桶、签名读、ZIP 打包下载。

## 2. 必填环境变量
```bash
STORAGE_BACKEND=s3
S3_ENDPOINT=https://your-oss-endpoint
S3_REGION=auto
S3_BUCKET=smartphoto-private
S3_ACCESS_KEY=your-access-key
S3_SECRET_KEY=your-secret-key
S3_FORCE_PATH_STYLE=false
S3_SIGNED_URL_TTL_SECONDS=900
S3_PRESIGN_UPLOAD_TTL_SECONDS=900
S3_PREFIX_UPLOADS=uploads
S3_PREFIX_GENERATED=generated
```

说明：
- 本地开发继续使用 `STORAGE_BACKEND=local`。
- 线上建议私有桶，不要把结果图直接开放成公共读。
- `S3_PREFIX_UPLOADS` 用于用户上传原图、风格图、参数附件、策略参考图。
- `S3_PREFIX_GENERATED` 用于 worker 生成结果。

## 3. 桶策略建议
- 桶权限：私有。
- AccessKey 权限：最小权限，仅允许目标 bucket 的 `PutObject/GetObject/HeadObject/ListBucket`。
- 生命周期：
  - `uploads/` 可按业务需要保留或定期清理历史废弃对象。
  - `generated/` 建议长期保留，便于结果回溯与历史版本下载。
- CORS：
  - 允许前端域名对 `PUT`、`POST`、`GET`、`HEAD` 发起请求。
  - 允许头至少包含 `Content-Type`。
  - 允许暴露 `ETag` 便于后续排查。

## 4. 上传时序
```text
Frontend -> Backend: POST /api/v2/uploads/presign
Backend -> Frontend: upload_id + object_key + upload_url + headers
Frontend -> OSS: PUT object bytes
Frontend -> Backend: POST /api/v2/uploads/complete
Backend -> DB: 写入 session_images/detail_style_images/parameter_attachments/strategy_reference_images
Backend -> Frontend: 业务资源摘要
```

说明：
- 当前 `upload_id` 是带签名和过期时间的一次性票据，不额外落库。
- `complete` 会校验对象存在、大小和 MIME，再写业务表。
- Step 1 商品图在 `complete` 后仍会保留当前自动 reanalysis 语义。

## 5. 接口清单

### `POST /api/v2/uploads/presign`
请求字段：
- `session_id`
- `upload_kind`
- `original_name`
- `content_type`
- `size_bytes`
- `display_order`
- `slot_type`

返回字段：
- `upload_id`
- `object_key`
- `method`
- `upload_url`
- `headers`
- `form_fields`
- `expires_at`

### `POST /api/v2/uploads/complete`
请求字段：
- `upload_id`

返回字段：
- `upload_id`
- `session_id`
- `upload_kind`
- `object_key`
- `completed`
- `resource_id`
- `resource`

## 6. 读链路语义
- DB 中持久化的是稳定 `object_key`，不是可过期 URL。
- 用户侧接口返回的 `url/image_url/thumbnail_url` 都是临时签名读 URL。
- ZIP 下载仍由后端完成对象读取和打包，不做预生成 ZIP 回写 OSS。

## 7. 本地与线上切换

### 本地
```bash
STORAGE_BACKEND=local
STORAGE_ROOT=./storage
```

### 线上
```bash
STORAGE_BACKEND=s3
S3_ENDPOINT=...
S3_BUCKET=...
```

说明：
- 本地仍会挂载 `/storage/*` 静态目录，便于直接调试图片。
- 线上不要再依赖 `/storage/*` 作为真实持久化真相。

## 8. 验证清单
1. `POST /api/v2/uploads/presign` 能返回 `upload_url`。
2. 浏览器直传成功后，`POST /api/v2/uploads/complete` 返回 `completed=true`。
3. `GET /api/v2/sessions/{session_id}/images` 中 `url` 可访问。
4. `GET /api/v2/sessions/{session_id}/results` 中 `image_url/thumbnail_url` 可访问。
5. `GET /api/v2/sessions/{session_id}/download` 能正确返回 ZIP。

## 9. 常见报错

### 9.1 presign 成功，但直传报 CORS
- 检查 bucket CORS 是否放行前端域名。
- 检查是否允许 `PUT` 与 `Content-Type` 头。

### 9.2 complete 报 `uploaded object not found`
- 直传实际未成功。
- `upload_url` 已过期。
- bucket/key 配置错误。

### 9.3 complete 报大小或 MIME 不匹配
- 前端上传时改了 `Content-Type`。
- 浏览器或 SDK 自动把文件按其他 MIME 发送。

### 9.4 签名 URL 立即失效
- 检查 API 服务器与 OSS 的时钟偏移。
- 检查 `S3_SIGNED_URL_TTL_SECONDS` / `S3_PRESIGN_UPLOAD_TTL_SECONDS` 是否过短。
