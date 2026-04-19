# SmartPhoto Backend 更新总结

> 统计区间：`b490d86bb4e4e239a98d2d413a2367f447dbb2b8..HEAD`
> 更新时间：2026-04-20
> 覆盖提交：5 次
> 代码规模：102 个文件，`+26,006 / -9,310`

## 一、这轮后端更新的核心结论

这轮更新不是单点修修补补，而是一次比较完整的后端能力升级。整体上，我们把系统往三个方向明显推进了一步：

1. **把“生成链路”从能跑，升级到可验证、可追踪、可维护**
2. **把“品牌一致性”从人工经验，升级到系统级可沉淀资产**
3. **把“上线交付”从依赖人盯，升级到带预检、回滚、审计的工程化流程**

换句话说，这次后端工作既有面向业务结果的能力建设，也有面向稳定交付的底层重构。

## 二、按主题拆解的更新内容

### 1. 生成链路与 Prompt/规则系统完成一次体系化重构

这一轮最重的工作，是把原来耦合较深的 pipeline 逻辑拆成了更清晰的模块：

- `app/services/copy_resolution.py`
- `app/services/prompt_pipeline.py`
- `app/services/rule_resolution.py`
- `app/services/pipeline_orchestration.py`
- `app/services/pipeline_persistence.py`
- `app/services/pipeline_rendering.py`
- `app/services/pipeline_review.py`

这次拆分带来的实际价值包括：

- **文案来源更可控**：显式区分用户输入、参数快照推断、legacy 字段同步、兜底回退，并保留 attribution 元信息。
- **Prompt 生成更稳定**：主图与详情页的 prompt 构建都变成了“归一化 -> 清洗 -> 可见文案策略 -> blocks 组装 -> final prompt”的固定流水线。
- **规则系统更清楚**：平台规则、槽位规则、详情页 panel 规则、展示模块意图等都从“散落逻辑”收束成了显式解析层。
- **预览缓存更可靠**：补强了 preview hash 相关逻辑，减少重复构建，保证相同输入下结果更稳定。
- **运行时职责更清晰**：调度、持久化、渲染、质检从大文件中拆开，后续维护成本显著下降。

这部分工作的技术含量主要不在“新增几个接口”，而在于把复杂业务逻辑整理成了可以长期演进的后端骨架。

### 2. 契约校验补齐，生成数据从“尽量对”升级到“有边界地对”

新增了 `app/contracts/*` 与 `app/contracts/validation.py`，对多类关键 payload 做结构约束与校验告警，包括：

- 主图策略预览
- 详情页策略预览
- generation snapshot
- 参数快照
- copy payload

实际收益：

- 降低上游/中间层异常 payload 直接污染后续链路的概率
- 在不粗暴中断流程的前提下，把错误显式记录出来，便于定位
- 为后续前后端协作、问题复盘、接口扩展打基础

### 3. 品牌记忆（Brand Memory）一期正式落地

这是本轮最重要的业务能力新增之一。

新增模型与迁移：

- `Brand`
- `BrandProfile`
- `BrandMemoryItem`
- `BrandMemoryEvidence`
- Alembic 迁移 `20260419_0020_brand_memory_phase1.py`

新增后台管理能力：

- `GET /api/admin/v1/brands`
- `POST /api/admin/v1/brands`
- `PUT /api/admin/v1/brands/{brand_id}`
- `POST /api/admin/v1/brands/{brand_id}/archive`
- `POST /api/admin/v1/brands/{brand_id}/restore`
- `GET /api/admin/v1/brands/{brand_id}/profile`
- `PUT /api/admin/v1/brands/{brand_id}/profile`
- `GET /api/admin/v1/brands/{brand_id}/memory-items`
- `PUT /api/admin/v1/brands/{brand_id}/memory-items/{memory_item_id}`
- `GET /api/admin/v1/brands/{brand_id}/memory-items/{memory_item_id}/evidence`

新增业务侧接口：

- `GET /api/v2/brands`

新增的品牌记忆能力不只是“有个品牌列表”，而是完整闭环：

- session 可以绑定品牌
- 策略预览阶段可按 `platform/category/slot` 匹配品牌记忆
- 品牌记忆可反向注入 `copy_blocks / expression_mode / rule_modules`
- 生成成功且通过质量门的资产，可以自动沉淀为品牌记忆
- 每条品牌记忆都能追到 evidence，知道它来自哪次生成、哪个资产、哪个 job

这意味着系统开始具备“越用越懂某个品牌”的能力，而不是每次都从零开始生成。

### 4. 质量审核与品牌沉淀打通

`app/services/pipeline_review.py` 这轮不只是做异步质检，还把质检结果与品牌资产沉淀真正串起来了：

- 支持 `off / sample / full` 模式的异步质量审核
- 通过 fidelity、文本语言、颜色偏差、图像相似度等维度做检查
- 对失败资产可派发 retry job
- 对通过审核的资产，自动沉淀品牌记忆

业务意义很直接：

- 好结果不会只是“一次性成功”，而是能反哺下一次生成
- 质量门不再只是拦截器，也成为品牌资产积累的入口

### 5. 生产运维脚本补齐，交付能力明显提升

新增了一套完整的 PowerShell 脚本，覆盖开发、打包、预检、发布、回滚：

- `scripts/dev-up.ps1`
- `scripts/dev-api.ps1`
- `scripts/dev-worker.ps1`
- `scripts/package-prod.ps1`
- `scripts/preflight-prod.ps1`
- `scripts/deploy-prod.ps1`
- `scripts/rollback-prod.ps1`

这部分的价值不是“多几个脚本”，而是把后端交付流程标准化了：

- 发布前先预检环境、数据库 schema、关键配置
- 发布时按固定流程更新镜像和服务
- 出问题时保留明确回滚入口
- 本地开发与生产交付的命令面更统一

对甲方来说，这代表项目不是“只能开发环境跑”，而是更接近可持续上线维护的服务系统。

### 6. Stage H 历史审计/发布保障链路补齐

新增：

- `scripts/stage_h_manifest_builder.py`
- `scripts/stage_h_historical_audit.py`
- `.sisyphus/stage_h/*` 相关模板与示例清单

其中 manifest builder 支持把 CSV 工作表转成结构化 JSON manifest，用于历史版本检查和发布窗口核对。

这部分虽然不直接体现在用户页面，但对项目质量非常关键：

- 让历史版本比对更系统
- 让发布前检查有模板、有输入格式、有验证逻辑
- 降低线上变更“说不清、查不全、回不去”的风险

### 7. 测试覆盖显著加强

这轮新增/加强的测试范围非常广，不是只补了 happy path：

- `tests/test_contracts.py`
- `tests/test_pipeline_refactor_baseline.py`
- `tests/test_copy_resolution.py`
- `tests/test_preview_hashes.py`
- `tests/test_prompt_pipeline.py`
- `tests/test_rule_resolver.py`
- `tests/test_stage_h_audit_script.py`
- `tests/test_stage_h_historical_read_compat.py`
- `tests/test_stage_h_manifest_builder.py`
- `tests/test_worker_tasks.py`
- `tests/test_admin_console.py`
- `tests/test_integration.py`
- `tests/test_upstream.py`

测试重点覆盖了：

- copy 解析与来源归因
- 主图/详情页 prompt pipeline 的确定性
- 规则解析与平台适配
- 品牌管理接口
- worker 任务与生成链路
- 历史兼容与 Stage H 审计脚本

这一块说明后端这轮不是“先堆功能再说”，而是同步补齐了可验证性。

## 三、对业务侧最直接的价值

如果从业务效果看，这轮后端更新可以概括成四个结果：

1. **生成更稳**
   Prompt、规则、copy、预览缓存、契约校验都更清楚，异常更容易兜住。

2. **风格更一致**
   品牌记忆引入后，同品牌的历史优质结果能沉淀复用，不用每次重做。

3. **问题更容易查**
   从 brand memory evidence 到 contract warning，再到更细的测试和审计脚本，定位链路更完整。

4. **交付更能上生产**
   有预检、有打包、有部署、有回滚，项目从“开发完成”进一步走向“可交付运维”。

## 四、建议对外汇报时的口径

如果需要对甲方或管理侧汇报，建议用下面这条主线：

> 这轮后端更新，我们不是只加了几个接口，而是把 SmartPhoto 的生成中台做得更像一个可持续演进的生产系统：前面补齐了品牌记忆和策略复用，后面补齐了质量审核、历史审计、预检发布和回滚能力，中间把 Prompt/规则/文案解析链路做了工程化拆分。这样既能提高生成一致性，也能支撑后续更稳定地扩功能、跑交付、做排障。

## 五、可直接提炼给甲方的亮点关键词

- 品牌资产沉淀
- 生成链路稳定性升级
- Prompt 工程化重构
- 质量审核闭环
- 发布预检与回滚能力
- 历史审计与可追溯性
- 后端中台化建设

## 六、涉及的代表性文件

- `app/services/copy_resolution.py`
- `app/services/prompt_pipeline.py`
- `app/services/rule_resolution.py`
- `app/services/pipeline_orchestration.py`
- `app/services/pipeline_persistence.py`
- `app/services/pipeline_rendering.py`
- `app/services/pipeline_review.py`
- `app/services/brand_memory.py`
- `app/services/brand_memory_scoring.py`
- `app/api/admin/brands.py`
- `app/api/v2/brands.py`
- `app/contracts/validation.py`
- `scripts/preflight-prod.ps1`
- `scripts/deploy-prod.ps1`
- `scripts/rollback-prod.ps1`
- `scripts/stage_h_manifest_builder.py`
- `scripts/stage_h_historical_audit.py`

## 七、总结一句话

从 `b490d86` 以来，后端完成的是一轮“业务能力 + 工程能力”双线升级：既把品牌记忆、规则解析、Prompt 流水线这些核心能力做深了，也把测试、预检、部署、审计、回滚这些生产级基础设施补实了。
