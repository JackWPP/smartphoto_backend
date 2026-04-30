# Pipeline Improvement 分支 — 后端改动完整说明 & 前端对接指南

> 分支: `pipeline_improvement`
> 基线提交: `0418f07661cdff7dcca55ff0ffbfcaa32a928efc`
> 生成日期: 2026-04-07
> 包含: 已提交的 7 个 commit + 当前未提交的 working tree 改动

---

## 目录

1. [素材反馈系统 (Asset Feedback)](#一素材反馈系统-asset-feedback)
2. [素材版本历史 & 回滚](#二素材版本历史--回滚)
3. [质量门禁管线 (Quality Gate)](#三质量门禁管线-quality-gate)
4. [质量看板 (Quality Dashboard)](#四质量看板-quality-dashboard)
5. [平台配置管理 (Platform Configs)](#五平台配置管理-platform-configs)
6. [平台表达方式查询 API](#六平台表达方式查询-api)
7. [Truth Contract v2 & Prompt 增强](#七truth-contract-v2--prompt-增强)
8. [品类目录增强](#八品类目录增强)
9. [Admin 前端改动](#九admin-前端改动)
10. [配置项 & 环境变量](#十配置项--环境变量)
11. [数据库迁移](#十一数据库迁移)
12. [前端对接优先级建议](#十二前端对接优先级建议)

---

## 一、素材反馈系统 (Asset Feedback)

### 1.1 提交反馈

```
POST /v2/assets/{asset_id}/feedback
```

**请求体:**

```json
{
  "rating": 3,
  "issue_tags": ["deformed", "wrong_color"],
  "comment": "产品颜色偏了"
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `rating` | int | 是 | 1=差, 2=一般, 3=好 (范围 1-3) |
| `issue_tags` | string[] | 否 | 问题标签，允许值见下表 |
| `comment` | string | 否 | 自由文本，最长 500 字 |

**允许的 issue_tags 值:**

| 值 | 含义 |
|----|------|
| `deformed` | 产品变形 |
| `wrong_color` | 颜色不对 |
| `bad_text` | 文字问题 |
| `wrong_style` | 风格不对 |
| `platform_violation` | 平台违规 |
| `low_fidelity` | 保真度低 |
| `other` | 其他 |

**请求头:**

| Header | 必填 | 说明 |
|--------|------|------|
| `X-User-Id` | 否 | 用户标识，可选 |
| `Authorization` | 是 | Service Principal |

**返回体:**

```json
{
  "code": 0,
  "data": {
    "id": "uuid",
    "asset_id": "uuid",
    "session_id": "uuid",
    "user_id": "string",
    "rating": 3,
    "issue_tags": ["deformed", "wrong_color"],
    "comment": "产品颜色偏了",
    "created_at": "2026-04-07T12:00:00Z"
  }
}
```

### 1.2 获取反馈列表

```
GET /v2/assets/{asset_id}/feedback
```

**返回体:**

```json
{
  "code": 0,
  "data": [
    {
      "id": "uuid",
      "asset_id": "uuid",
      "session_id": "uuid",
      "user_id": "string",
      "rating": 3,
      "issue_tags": ["deformed"],
      "comment": "...",
      "created_at": "ISO8601"
    }
  ]
}
```

### 前端需要的改动

- 素材预览/详情页添加反馈入口（星级评分 1-3 + 多选问题标签 + 文字评论）
- 调用 `POST` 提交反馈，调用 `GET` 展示历史反馈列表

---

## 二、素材版本历史 & 回滚

### 2.1 获取版本历史

```
GET /v2/assets/{asset_id}/history
```

**返回体:**

```json
{
  "code": 0,
  "data": [
    {
      "asset_id": "uuid",
      "version_no": 3,
      "round_no": 1,
      "image_url": "https://...",
      "thumbnail_url": "https://...",
      "width": 1024,
      "height": 1024,
      "status": "ready",
      "quality_status": "passed",
      "visibility_status": "visible",
      "edit_instruction": "保持产品外观不变，只改背景为纯白",
      "created_at": "2026-04-07T12:00:00Z"
    },
    {
      "asset_id": "uuid",
      "version_no": 2,
      "round_no": 1,
      "image_url": "https://...",
      "thumbnail_url": "https://...",
      "width": 1024,
      "height": 1024,
      "status": "superseded",
      "quality_status": "passed",
      "visibility_status": "visible",
      "edit_instruction": null,
      "created_at": "2026-04-07T11:00:00Z"
    }
  ]
}
```

> 按版本号降序排列，第一个元素即当前版本。

### 2.2 回滚到历史版本

```
POST /v2/assets/{asset_id}/restore
```

无请求体。`asset_id` 传入想恢复到的**目标历史版本的 asset ID**（不是当前版本的 ID）。

**返回体:**

```json
{
  "code": 0,
  "data": {
    "restored_asset_id": "uuid",
    "previous_asset_id": "uuid",
    "slot_id": "hero"
  }
}
```

**逻辑说明:**
- 后端会克隆目标版本的图片到新版本号，同时将当前版本标记为 `superseded`
- 回滚操作不影响其他槽位（只替换对应 slot 的当前图）
- 如果目标版本已经是当前版本，返回 `400 invalid_request: 该版本已是当前版本`

### 前端需要的改动

- 素材预览页增加"版本历史"入口，展示历史缩略图列表
- 历史卡片上提供"恢复此版本"按钮，调用 `restore` API
- 展示每次版本的 `edit_instruction` 让用户知道修改了什么

---

## 三、质量门禁管线 (Quality Gate)

### 3.1 Asset Model 新增字段

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `quality_status` | string | `"unchecked"` | 质量状态，见下表 |
| `quality_scores` | JSON | null | 各项质检分数详情 |
| `quality_review_job_id` | string? | null | 异步审查任务的 Job ID |
| `failure_reason` | string? | null | 质量不通过原因（中文，用户可读） |

### 3.2 quality_status 状态流转

```
unchecked → pending_async_review → passed
                                → async_failed
          → sync_failed
          → generation_failed
```

| 状态 | 含义 | 前端展示建议 |
|------|------|-------------|
| `unchecked` | 未质检（老数据） | 不展示状态 |
| `pending_async_review` | 异步审查中 | "质检中" 旋转图标 |
| `passed` | 质检通过 | 绿色"通过"标签 |
| `sync_failed` | 同步质检失败（空白/黑图/尺寸不足） | 红色"生成失败"+ failure_reason |
| `async_failed` | 异步质检失败（保真度/语言/颜色） | 橙色"质量不达标"+ failure_reason |
| `generation_failed` | 生成过程失败（下载失败/超时） | 红色"生成失败"+ 重试按钮 |

### 3.3 quality_scores 结构示例

```json
{
  "sync_check": {
    "passed": true,
    "checks": {
      "decodable": true,
      "size_ok": true,
      "not_blank": true,
      "sufficient_entropy": true
    },
    "entropy": 5.82,
    "pixel_std": 68.3,
    "width": 1024,
    "height": 1024
  },
  "async_check": {
    "fidelity": { "passed": true },
    "text_language": { "passed": true },
    "color_fidelity": { "passed": true, "violations": [] },
    "image_similarity": { "ssim": 0.85, "psnr": 28.5 }
  }
}
```

### 3.4 failure_reason 常见值

| failure_reason | 含义 | 前端建议 |
|----------------|------|----------|
| 图片文件损坏，无法解码 | 下载的文件不是合法图片 | 显示"生成失败，请重试" |
| 图片尺寸不足 (512×512，要求 ≥ 1024×1024) | 生成图太小 | 显示具体尺寸 |
| 图片几乎全白，疑似空白输出 | AI 生成了空白图 | 显示"生成异常，请重试" |
| 图片几乎全黑，疑似渲染失败 | AI 生成了黑图 | 显示"渲染失败，请重试" |
| 白底图背景不够纯白 | 白底检测未通过 | 显示"白底不达标" |
| 产品保真度不足 | 产品外观与参考图差异过大 | 显示"产品外观偏差过大" |
| 文字语言不合规 | 出现了不该有的语言文字 | 显示"文字语言不合规" |
| 产品颜色偏差过大 | 产品颜色与参考图色差过大 | 显示"颜色偏差过大" |
| 该图生成失败，请点击重试 | 通用生成失败 | 通用重试提示 |
| 生成超时，请稍后重试 | 生成过程超时 | 显示超时提示 |
| 服务繁忙，请稍后重试 | 触发限流 | 显示繁忙提示 |
| 图片内容未通过安全审核 | 触发内容安全策略 | 显示审核提示 |

### 3.5 生成失败占位素材

生成失败的素材现在会创建占位记录：

```json
{
  "id": "uuid",
  "status": "failed",
  "quality_status": "generation_failed",
  "failure_reason": "生成超时，请稍后重试",
  "image_url": "",
  "width": 0,
  "height": 0
}
```

### 前端需要的改动

- 素材卡片/列表展示 `quality_status` 状态标签
- 展示 `failure_reason` 中文原因
- `image_url` 为空且 `status=failed` 的素材显示占位卡片 + 重试按钮
- 可通过轮询 Job 状态跟踪 `pending_async_review` 的素材

---

## 四、质量看板 (Quality Dashboard)

### 4.1 质量总览

```
GET /admin/dashboard/quality?days=7
```

**返回体:**

```json
{
  "code": 0,
  "data": {
    "window_days": 7,
    "quality_gate": {
      "total_reviewed": 120,
      "passed": 100,
      "sync_failed": 5,
      "async_failed": 8,
      "generation_failed": 7,
      "pass_rate": 0.8333
    },
    "feedback": {
      "total": 30,
      "avg_rating": 2.4,
      "bad_count": 5,
      "bad_rate": 0.1667
    }
  }
}
```

### 4.2 质量分组明细

```
GET /admin/dashboard/quality/breakdown?days=7&dimension=platform
```

**参数:**

| 参数 | 说明 |
|------|------|
| `days` | 统计天数 (1-30，默认 7) |
| `dimension` | 分组维度: `platform` / `category` / `slot` |

**返回体:**

```json
{
  "code": 0,
  "data": {
    "window_days": 7,
    "dimension": "platform",
    "items": [
      {
        "key": "taobao",
        "total": 50,
        "passed": 42,
        "sync_failed": 2,
        "async_failed": 4,
        "generation_failed": 2,
        "pass_rate": 0.84
      }
    ]
  }
}
```

### 4.3 问题标签排行

```
GET /admin/dashboard/quality/issue-tags?days=7
```

**返回体:**

```json
{
  "code": 0,
  "data": {
    "window_days": 7,
    "items": [
      { "tag": "wrong_color", "count": 12 },
      { "tag": "deformed", "count": 8 },
      { "tag": "low_fidelity", "count": 5 }
    ]
  }
}
```

### 4.4 生成 & 质检耗时统计

```
GET /admin/dashboard/quality/timing?days=7
```

**返回体:**

```json
{
  "code": 0,
  "data": {
    "window_days": 7,
    "generation": {
      "p50_seconds": 35.2,
      "p95_seconds": 82.1,
      "sample_count": 500
    },
    "quality_review": {
      "p50_seconds": 12.4,
      "p95_seconds": 28.7,
      "sample_count": 480
    }
  }
}
```

### 前端需要的改动

- 管理后台新增质量看板页面，包含:
  - 质检通过率趋势图
  - 用户反馈评分分布
  - 按平台/品类/槽位的分组明细表
  - 问题标签排行（柱状图/词云）
  - 生成 & 质检耗时 P50/P95 指标

---

## 五、平台配置管理 (Platform Configs)

### 5.1 API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/admin/platform-configs?include_inactive=false` | 列出配置 |
| `GET` | `/admin/platform-configs/{platform_id}` | 获取单个 |
| `POST` | `/admin/platform-configs` | 创建配置 |
| `PUT` | `/admin/platform-configs/{platform_id}` | 更新配置 |
| `DELETE` | `/admin/platform-configs/{platform_id}` | 删除配置 |

### 5.2 数据结构

```json
{
  "config_id": "uuid",
  "platform_id": "taobao",
  "name": "淘宝",
  "locale": "zh-CN",
  "copy_language": "zh",
  "allow_dense_copy": false,
  "allow_certificate_elements": false,
  "allow_compare_overlay": false,
  "hero_text_overlay": "minimal",
  "white_bg_mandatory": false,
  "default_image_count": 5,
  "default_aspect_ratio": "1:1",
  "main_rule_pack_id": "default_main_gallery_v2",
  "detail_rule_pack_id": "ecommerce_detail_v2",
  "prohibited_elements": ["侵权品牌商标"],
  "negative_prompt_additions": ["不要生成牛皮癣式密集促销贴纸"],
  "constraints": ["文案应保持短句，避免信息卡海报化"],
  "is_active": true,
  "created_by": "admin_id",
  "operator_note": "根据平台新规调整文字策略",
  "created_at": "ISO8601",
  "updated_at": "ISO8601"
}
```

### 5.3 字段说明

| 字段 | 类型 | 说明 | 前端组件建议 |
|------|------|------|-------------|
| `platform_id` | string | 平台标识，创建后不可改 | 文本输入（创建态），只读（编辑态） |
| `name` | string | 显示名称 | 文本输入 |
| `locale` | string | 语区标识 | 文本输入，提示 `zh-CN` 或 `en-US` |
| `copy_language` | string | 文案语言 | 文本输入，提示 `zh` 或 `en` |
| `hero_text_overlay` | string | 首图文字策略 | 下拉选择：`forbidden`/`minimal`/`allowed`/`dense` |
| `white_bg_mandatory` | bool | 是否强制白底 | 开关 |
| `allow_dense_copy` | bool | 允许密集文案 | 开关 |
| `allow_certificate_elements` | bool | 允许证书/背书元素 | 开关 |
| `allow_compare_overlay` | bool | 允许对比覆层 | 开关 |
| `default_image_count` | int | 默认生成张数 (1-20) | 数字输入 |
| `default_aspect_ratio` | string | 默认宽高比 | 文本输入 |
| `prohibited_elements` | string[] | 禁止元素列表 | 标签编辑器（每行一项） |
| `negative_prompt_additions` | string[] | 追加负向约束 | 文本列表编辑器（每行一项） |
| `constraints` | string[] | 平台级约束规则 | 文本列表编辑器（每行一项） |
| `is_active` | bool | 是否启用 | 开关 |
| `operator_note` | string | 修改备注（审计用） | 文本输入，**必填** |

### 5.4 创建请求体

```json
{
  "platform_id": "temu",
  "name": "TEMU",
  "locale": "en-US",
  "copy_language": "en",
  "hero_text_overlay": "forbidden",
  "white_bg_mandatory": true,
  "default_image_count": 5,
  "default_aspect_ratio": "1:1",
  "prohibited_elements": ["中文文案", "domestic_badges"],
  "negative_prompt_additions": ["Do NOT include any Chinese text"],
  "constraints": ["All text must be English only"],
  "is_active": true,
  "operator_note": "新增TEMU平台配置"
}
```

### 5.5 更新请求体

所有字段可选，只传需要修改的字段：

```json
{
  "hero_text_overlay": "dense",
  "operator_note": "根据运营反馈调整为密集展示"
}
```

### 5.6 自动初始化

首次访问 `/admin/platform-configs` 时，后端会自动从硬编码预设创建缺失的平台配置（带并发安全处理），确保管理面板始终能展示完整的平台列表。

### 前端需要的改动

- 已有 `PlatformConfigsView.vue` 页面（已实现大部分功能）
- 确保对接以上 CRUD 接口
- 确保创建/编辑时 `operator_note` 为必填项
- 表格中 `hero_text_overlay` 展示中文标签（forbidden→禁止文字, minimal→极少点缀, allowed→常规允许, dense→密集展示）

---

## 六、平台表达方式查询 API

### 6.1 获取槽位表达方式列表

```
GET /v2/platforms/{platform_id}/expression-modes
```

**返回体:**

```json
{
  "code": 0,
  "data": {
    "platform_id": "taobao",
    "slots": [
      {
        "slot_id": "hero",
        "slot_label": "首图/主视觉",
        "candidates": [
          {
            "mode": "white_bg",
            "label": "白底直拍",
            "description": "纯白背景产品展示",
            "layout_strategy": "centered",
            "copy_strategy": "no_text",
            "prompt_modules": ["goal", "fidelity", "background", "style"]
          },
          {
            "mode": "scene",
            "label": "生活场景",
            "description": "产品在真实场景中的使用展示",
            "layout_strategy": "rule_of_thirds",
            "copy_strategy": "minimal",
            "prompt_modules": ["goal", "fidelity", "background", "scene", "style"]
          }
        ]
      }
    ]
  }
}
```

### 前端需要的改动

- 可用于策略预览页面展示每个槽位的可选表达方式
- 用户选择表达方式后可在策略定制中使用

---

## 七、Truth Contract v2 & Prompt 增强

> 本节改动均为后端逻辑变更，不涉及新 API 端点，但会影响生成结果质量。

### 7.1 保真度分层 (fidelity_tier)

上游分析新增 `fidelity_tier` 字段，自动判断产品需要的保真等级：

| 等级 | 适用产品 | 后端行为 |
|------|----------|----------|
| `critical` | 控制面板、精密结构、透明部件、机械组件 | 最大参考图数量 4 张，追加"绝对禁止重建外观"约束 |
| `high` | 普通家电/日用品 | 参考图数量 3 张，严格保真约束 |
| `standard` | 简单造型产品 | 参考图数量 2 张，标准约束 |
| `creative` | 纯设计/艺术类 | 宽松约束 |

### 7.2 组件锁定 (component_locks)

上游分析新增 `component_registry` 输出，自动识别产品关键部件（如控制面板、透明水箱、滤芯），对每个部件生成位置锁定约束。

### 7.3 颜色保持 (color_palette_hex)

自动提取产品主体色 HEX 色号，注入 prompt 约束："产品颜色必须保持为 #RRGGBB..."。

异步质检阶段新增颜色验证（CIE76 Delta-E），检测产品颜色是否偏移。

### 7.4 品牌标识保持 (brand_marks_preserve)

自动识别并保护产品上的品牌标识，防止 AI 删除或替换。

### 7.5 语言硬约束

Prompt 最前方注入不可妥协的语言约束：
- 中文平台（淘宝/1688/拼多多）：所有新增文案只能是简体中文
- 英文平台（Amazon/TEMU）：所有新增文案必须是英文

### 7.6 卖点独占分配

多张图的卖点不再重复。每张图自动分配不同的卖点子集，避免主图组中出现相同卖点。

### 7.7 结构化编辑约束 (edit_constraints)

重生成 API 新增 `edit_constraints` 字段，支持结构化控制重生成行为：

```json
{
  "instruction": "把背景改成纯白",
  "keep_style_consistency": true,
  "edit_constraints": {
    "keep": ["product_identity", "color"],
    "change": { "background": "pure_white" },
    "remove": ["visible_text"]
  }
}
```

**keep 允许值:** `product_identity`, `composition`, `style`, `text`, `background`, `color`

**change 允许值:** `pure_white`, `dark`, `real_scene`, `gradient`, `no_text`, `minimal_text`, `dense_text`, `enlarge`, `shrink`

**remove 允许值:** `visible_text`, `watermark`, `background_elements`, `reflection`, `shadow`

### 7.8 约束升级记忆 (Constraint Escalation Memory)

后端新增"约束升级记忆"机制：
- 异步质检不通过时，自动重生成一次（可配置，默认关闭）
- 重生成通过后，将有效的约束指令保存到 session 级别记忆
- 后续同 slot 重生成时自动加载历史有效约束
- 每个记忆条目记录 `slot_id` + `instruction` + `asset_id`，最多保留 10 条

### 7.9 其他 Prompt 改进

- **背景描述升级：** 从"简洁干净"改为具体的"棚拍无缝背景纸效果"描述
- **三点布光法：** style block 新增专业光影设计（阴影 ≤15%，主体占画面 50-65%）
- **no_text 策略强化：** 从一句话扩展为三条明确禁令
- **平台禁止元素注入：** `prohibited_elements` 中的元素会作为"平台禁止元素"约束注入 prompt
- **参考图数量动态调整：** 根据 fidelity_tier 自动决定参考图数量（critical=4, high=3, standard=2）
- **上游分析新增输出字段：** `fidelity_tier`, `product_identity_anchor`, `component_registry`, `image_semantic_tags`

### 前端可能需要关注的

- 生成效果更稳定，保真度更高
- 文案语言不再出现中英混淆
- 重生成时可以提供更精细的控制选项（keep/change/remove）
- `AssetRegenerateRequest` 新增 `edit_constraints` 可选字段

---

## 八、品类目录增强

### 新增字段

`CategoryCatalogModel` 和品类种子数据新增：

| 字段 | 类型 | 说明 |
|------|------|------|
| `confusion_pairs` | string[] | 容易混淆的品类列表（如空气净化器→加湿器、除湿机） |
| `expected_components` | string[] | 该品类产品应有的典型部件列表（如空气净化器→HEPA滤网、出风口、进风口、控制面板、滤芯舱） |

### 前端需要的改动

- 品类选择/展示时可以展示 `expected_components` 辅助用户确认品类判断
- 品类推荐时可以利用 `confusion_pairs` 做"你可能想找的是..."提示

---

## 九、Admin 前端改动

### 9.1 PlatformConfigsView 页面升级

- 表单分组布局（基本信息 / 首图及主体约束 / 生成约束规则 / 状态与备注）
- 每个字段增加 `field-hint` 中文说明
- `hero_text_overlay` 展示中文标签映射
- 前端表单验证（平台 ID 必填、名称必填、修改备注必填）
- 错误码中文映射（`duplicate_platform_config` → "该平台 ID 已存在配置"等）
- 错误展示改为 `error-banner` 样式（红色背景条）
- 空状态提示改为"系统将在首次加载时自动初始化预设配置"

### 9.2 JsonEditor 组件升级

- 新增 JSON 格式实时校验（输入时检测）
- 无效 JSON 时输入框变红 + 显示 "JSON 格式有误，请检查语法" 提示
- 新增 `valid` 事件，父组件可监听校验状态

### 9.3 全局样式 & 中文化

- Admin 前端全局中文化 + 主题刷新（在之前的 commit 中完成）

---

## 十、配置项 & 环境变量

新增环境变量（`app/core/config.py`）：

| 变量 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `COLOR_VALIDATION_ENABLED` | bool | `false` | 是否启用颜色保真验证 |
| `COLOR_VALIDATION_DELTA_E_THRESHOLD` | float | `25.0` | 颜色偏差容忍度（CIE76 Delta-E） |
| `ASYNC_QUALITY_RETRY_ENABLED` | bool | `false` | 质检不通过时是否自动重试生成 |
| `ASYNC_QUALITY_RETRY_MAX_PER_SESSION` | int | `3` | 每个 session 最大自动重试次数 |

> 这些功能默认关闭，需要通过环境变量显式开启。

---

## 十一、数据库迁移

本次改动涉及以下迁移：

### 575351136703_add_asset_quality_and_feedback

- `assets` 表新增: `quality_status`, `quality_scores`, `quality_review_job_id`, `failure_reason`
- 新建 `asset_feedback` 表

### 57aaaca5967c_add_platform_configs_table

- 新建 `platform_configs` 表

### 额外迁移（未提交改动需要）

- `category_catalogs` 表新增: `confusion_pairs` (JSON), `expected_components` (JSON)

---

## 十二、前端对接优先级建议

### P0 — 必须对接

| 改动 | 说明 | 涉及 API |
|------|------|----------|
| 素材状态展示 | 展示 `quality_status` + `failure_reason` | Asset 字段变更 |
| 生成失败占位 | `image_url=""` 的素材展示占位卡片+重试 | Asset 字段变更 |
| 版本历史 | 素材历史列表 + 回滚按钮 | `GET /assets/{id}/history`, `POST /assets/{id}/restore` |
| 素材反馈 | 评分+问题标签提交 | `POST /assets/{id}/feedback`, `GET /assets/{id}/feedback` |

### P1 — 建议对接

| 改动 | 说明 | 涉及 API |
|------|------|----------|
| 质量看板 | 管理后台新增质量指标页 | `/admin/dashboard/quality/*` |
| 平台配置完善 | 确保所有字段正确展示和编辑 | `/admin/platform-configs` |
| 表达方式查询 | 策略预览展示可选表达方式 | `GET /platforms/{id}/expression-modes` |

### P2 — 可选优化

| 改动 | 说明 |
|------|------|
| 结构化编辑约束 | 重生成时提供 keep/change/remove 选项 |
| 品类增强 | 展示 expected_components 和 confusion_pairs |
| 参考图上限提升 | 支持最多 8 张参考图（之前 2 张） |
| 质检轮询 | 展示 `pending_async_review` 状态的实时变化 |

---

## 附录: 错误码新增

| 错误码 | HTTP 状态 | 说明 |
|--------|----------|------|
| `duplicate_platform_config` | 409 | 平台配置已存在 |
| `platform_config_not_found` | 404 | 平台配置未找到 |

---

## 附录: 完整提交记录

```
4884af8 refactor: update tests for v2 contracts and add upstream facade modules
2cc4391 feat: admin frontend Chinese localization, theme refresh, and platform configs page
741fabc feat: add asset feedback API and quality dashboard endpoint
e0c2135 feat: add sync quality gate and async LLM vision review pipeline
cb2fad3 feat: add DB-driven platform config system with admin CRUD
c523ef2 feat: truth contract v2 with component locks, selling point allocation, and prompt refinement
8d682c1 feat: expand platform overlays, add language constraints, and DB-first config lookup
```

加上当前未提交的改动（版本历史/回滚、颜色验证、结构化编辑约束、约束升级记忆、质量分析明细 API、表达方式 API、品类增强、Admin 前端完善）。
