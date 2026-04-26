# SmartPhoto 生图系统技术文档

## 目录
1. [系统概述](#1-系统概述)
2. [架构设计原则](#2-架构设计原则)
3. [整体流程](#3-整体流程)
4. [模型分工与职责边界](#4-模型分工与职责边界)
5. [平台规则体系](#5-平台规则体系)
6. [数据契约说明](#6-数据契约说明)
7. [性能优化策略](#7-性能优化策略)
8. [近期变更说明](#8-近期变更说明)

---

## 1. 系统概述

SmartPhoto 是一套**电商主图和详情页自动生成系统**，支持 1688、淘宝、天猫、Amazon、Temu、抖音、小红书等主流电商平台。

主要功能：
- 根据上传的商品图片，自动分析产品特征、提取关键参数
- 生成适合电商平台的主图（最多 7 张）和详情页（8 张 panel + 拼接长图）
- 支持平台专属风格规则，输出符合各平台审美和规范的视觉素材

---

## 2. 架构设计原则

### 2.1 Gemini 权威事实源

自 2026 年 4 月重构后，系统确立了以下核心原则：

> **Gemini 是唯一权威事实源。Doubao（豆包）是非权威补全模型。**

| 模型 | 职责 | 禁止事项 |
|------|------|---------|
| **Gemini** | 识别产品类型、颜色、结构、参数（事实层） | — |
| **Doubao** | 补充表达候选（inferred_ 前缀字段）| **不得覆盖** Gemini 已识别的事实字段 |

### 2.2 字段级优先级

```
explicit_input（用户手动填写）
    > evidence_backed（Gemini 视觉识别）
        > inferred（Doubao 补全推断）
            > defaults（系统兜底值）
```

每个字段的来源通过 `copy_meta` 中的 `source` 字段标注（`explicit_input` / `parameter_primary` / `parameter_inferred` / `analysis_default` / `sanitizer_fallback`）。

### 2.3 前端透明原则

所有架构重构对前端消费方**完全透明**：
- 接口路径和签名不变
- 行为变更通过内部守卫和元数据字段体现
- 新增字段均为可选，不影响旧数据读取

---

## 3. 整体流程

### 3.1 主图生成流程（Step 1 → Step 6）

```
Step 1  上传商品图片
         ↓
Step 2+3  图片分析 + 参数提取（Gemini 合并执行）
          ├─ 识别产品类型、颜色、结构、参数
          ├─ 写入 analysis_snapshot（事实层）
          ├─ 写入 parameter_snapshot（含 analysis_quality 标记）
          └─ 若 analysis_quality == "llm"：跳过 Step 3b，减少时延
         ↓
Step 3b  参数补全（Doubao，可选，analysis_quality == "fallback" 时触发）
          └─ 只写入 inferred_ 前缀字段，事实字段受守卫保护
         ↓
Step 4   文案填写（用户可编辑，explicit_input 优先级最高）
         ↓
Step 5   策略规划（Doubao/Gemini）
          └─ 为 5 个主图槽位规划风格、构图、参考图
         ↓
Step 6   图片生成（Gemini 图像模型）
          └─ 含保真度验证和文字语言审核
```

### 3.2 详情页生成流程（8 张 panel）

```
商品图片 + 风格参考图（可选）
         ↓
详情页叙事规划（Doubao）
  ├─ 根据平台规则包选择叙事模板
  ├─ 1688/淘宝：货架语义（首屏货架→理由卡→证据卡→场景利益卡→尾屏总结）
  └─ 其他平台：通用电商详情叙事结构
         ↓
8 个 panel 并发生成（Gemini 图像模型）
         ↓
自动横向拼接 → 输出长图
```

**1688/淘宝详情页 8 个 panel 规划（alibaba_detail_v1 规则包）：**

| Panel | 默认类型 | 内容说明 |
|-------|---------|---------|
| #1 | first_screen_shelf | 首屏货架图：品类定位 + 核心利益点，亮底短标题 |
| #2 | reason_why_card | 理由/机制卡：解释为什么有效，可用图解数据 |
| #3 | evidence_card | 卖点A证据：参数/认证/对比佐证 |
| #4 | scene_benefit_card | 卖点B场景：真实场景代入，场景利益 |
| #5 | feature_benefit | 使用场景可视化：体现人群和使用方式 |
| #6 | feature_compare | 差异化亮点：对比竞品或展示独有功能 |
| #7 | parameter_board | 参数/细节：结构化参数展示 |
| #8 | closing_summary | 尾屏总结：精简卖点矩阵 + 行动号召 |

---

## 4. 模型分工与职责边界

### 4.1 各任务模型分配

| 任务 | 模型 | 说明 |
|------|------|------|
| 商品图片分析（Step 2） | **Gemini** | 视觉识别唯一权威，产出事实层数据 |
| 参数提取（Step 3） | **Gemini**（与 Step 2 合并执行）| 结构化提取，analysis_quality 标记 |
| 参数补全（Step 3b） | **Doubao** | 仅在 fallback 时触发，只补充 inferred_ 字段 |
| 主图策略规划 | **Doubao** | 规划 5 个槽位的构图和文案策略 |
| 详情页叙事规划 | **Doubao** | 规划 8 个 panel 的叙事逻辑 |
| 主图生成 | **Gemini 图像模型** | 保真度验证 + 文字语言审核 |
| 详情页生成 | **Gemini 图像模型** | 含平台风格约束 |
| 文字审核 | **Doubao** | 审核生成文字是否合规 |

### 4.2 Doubao 事实守卫规则

以下字段 Doubao 绝对不能覆盖（由系统在合并阶段静默丢弃）：

```python
_FACT_FIELDS = frozenset({
    "hero_scene",         # Gemini 识别的核心使用场景
    "core_selling_points", # Gemini 识别的核心卖点
    "key_parameters",     # Gemini 识别的关键参数
    "product_advantages", # Gemini 识别的产品优势
    "feature_highlights", # Gemini 识别的功能亮点
    "analysis_quality",   # 事实层质量标记（只读）
})
```

Doubao 只能写入带 `inferred_` 前缀的字段：`inferred_core_selling_points`、`inferred_key_parameters`、`inferred_advantages`。

---

## 5. 平台规则体系

系统通过 **内建规则包（BUILTIN_RULE_PACKS）** 管理各平台的视觉和叙事规范。

### 5.1 主图规则包

| 规则包 ID | 适用平台 | 说明 |
|----------|---------|------|
| `default_main_gallery_v2` | 通用（Amazon/Temu 等） | 5 槽位：hero/白底/卖点/场景/细节 |
| `alibaba_core_5_slot` | 1688 / 淘宝 | 5 槽位：首图KV/理由图/佐证图/利益场景/尾屏卖点 |

### 5.2 详情页规则包

| 规则包 ID | 适用平台 | 说明 |
|----------|---------|------|
| `ecommerce_detail_v2` | 通用（Amazon/Temu/抖音等） | 通用电商详情页叙事 |
| `alibaba_detail_v1` | **1688 / 淘宝** | 1688 移动端货架风格：亮底、短文案、模块化卡片 |

### 5.3 alibaba_detail_v1 平台约束

- **背景风格**：亮底 / 白底 / 浅灰底，禁止暗黑调、赛博朋克、KV海报风格
- **主体占比**：≥ 55%（确保货架缩略图可读）
- **文案长度**：标题 ≤ 12 汉字，副文案 ≤ 20 汉字
- **版式风格**：模块化卡片设计，信息密度适中

---

## 6. 数据契约说明

### 6.1 analysis_snapshot 关键字段

```json
{
  "recognized_product": { "product_name": "...", "category": "...", "confidence": 0.9 },
  "analysis_source": "llm",        // "llm" 或 "fallback"
  "analysis_quality": "llm",       // 事实层溯源标记（新增）
  "evidence_scores": { "structure": 90, "proportion": 85 },
  "selling_point_entities": [...],
  "risk_flags": [...]
}
```

### 6.2 parameter_snapshot 关键字段

```json
{
  "hero_scene": "...",              // 事实字段，Gemini 写入，Doubao 不可改
  "core_selling_points": [...],     // 事实字段
  "key_parameters": [...],          // 事实字段
  "product_advantages": [...],      // 事实字段
  "inferred_core_selling_points": [...],  // 补全字段，Doubao 可写
  "inferred_key_parameters": [...],       // 补全字段
  "inferred_advantages": [...],           // 补全字段
  "analysis_quality": "llm",        // "llm" | "fallback"（新增）
  "skipped_completion": true,        // 补全被跳过时写入（新增）
  "skip_reason": "gemini_success"   // 跳过原因（新增）
}
```

### 6.3 copy_meta attribution source 取值

| source 值 | 含义 |
|-----------|------|
| `explicit_input` | 用户手动填写（最高优先级，不可被覆盖） |
| `parameter_primary` | Gemini 视觉识别（证据层） |
| `parameter_inferred` | Doubao 补全推断 |
| `analysis_default` | 分析阶段兜底写入 |
| `sanitizer_fallback` | 系统归一化兜底 |

---

## 7. 性能优化策略

### 7.1 跳过补全（Skip Completion）

当 Gemini 分析成功（`analysis_quality == "llm"`）时，`POST /parameters/complete` 接口**默认跳过 Doubao 补全调用**，直接返回现有快照。

- 节省约 1-2 秒的 Doubao API 调用时延
- 接口签名不变，对前端完全透明
- 用户传入 `completion_instruction` 时强制执行补全（忽略 skip 条件）
- 跳过时快照中写入 `skipped_completion: true, skip_reason: "gemini_success"` 供调试

### 7.2 ensure_system_rule_packs 按 key upsert

`ensure_system_rule_packs` 改为按 `rule_pack_key` 做 upsert（原来是检测 `is_system count > 0` 整体跳过），确保追加新内建规则包时不会遗漏。

---

## 8. 近期变更说明

### 8.1 2026年4月架构重构（当前版本）

| 变更项 | 变更内容 |
|-------|---------|
| Gemini 权威化 | 确立 Gemini 为唯一事实源，Doubao 被限制为补全模型 |
| 事实守卫 | `_merge_parameter_completion_snapshot` 加事实字段保护 |
| explicit_input 优先级 | `apply_parameter_snapshot_with_attribution` 用户手动字段不可被覆盖 |
| analysis_quality 标记 | 两个快照均写入 `analysis_quality: "llm"/"fallback"` |
| 跳过补全优化 | `analysis_quality == "llm"` 时自动跳过 Doubao 补全 |
| alibaba_detail_v1 | 新增 1688/淘宝专属详情页规则包（货架语义、亮底约束） |
| Amazon 语义清除 | `DETAIL_PAGE_USE_CASE` 从 `"amazon_detail"` 改为 `"ecommerce_detail"` |
| 1688 Prompt 约束 | detail planner 对 1688/淘宝平台注入货架风格约束 |
| ensure_system_rule_packs | 改为按 key upsert，支持安全追加新内建规则包 |

### 8.2 2026年4月初模型迁移

| 任务 | 变更前 | 变更后 |
|-----|-------|-------|
| 设计规划（主图） | Gemini 快速版 | Doubao |
| 设计规划（详情页） | Gemini 快速版 | Doubao |
| 参数补全 | OpenRouter 供应商 | Doubao |
| 文字审核 | OpenRouter 供应商 | Doubao |

---

*文档更新时间：2026年4月23日*