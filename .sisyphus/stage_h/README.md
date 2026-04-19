# Stage H Audit Workspace

本目录只存 Stage H 的模板、台账和可归档产物说明，不存真实生产样本。

## 文件约定

- `historical_audit_manifest.json`
  - 仓库内固定保留的 manifest 模板。
  - 不提交真实 pre-prod / production session 数据。
- `historical_audit_manifest.example.json`
  - 30-session 样本清单示例，展示推荐覆盖面与字段组织方式。
- `historical_audit_manifest_template.csv`
  - 适合人工整理样本表的 CSV 模板，可配合转换脚本生成真实 manifest。
- `preprod_smoke_template.md`
  - 预发布结果读冒烟记录模板。
- `release_window_observation_template.csv`
  - 发布窗口观察记录模板。

## 真实产物归档约定

真实环境跑出的以下文件不要提交回仓库，应归档到 release 附件、运维工单或受控目录：

- 真实 30-session manifest
- `historical_audit_report.json`
- `historical_audit_report.md`
- pre-prod smoke 执行记录
- release-window observation 记录表

## 推荐流程

1. 用 `historical_audit_manifest_template.csv` 或 `historical_audit_manifest.example.json` 整理真实 session。
2. 若先在 CSV 中整理样本，运行：
   - `python scripts/stage_h_manifest_builder.py --csv <csv-path> --output <manifest-json-path>`
3. 运行 `python scripts/stage_h_historical_audit.py ...` 生成报告。
4. 用 `preprod_smoke_template.md` 记录 latest/historical 结果读冒烟。
5. 用 `release_window_observation_template.csv` 维护发布窗口观察。
6. 只有在 30-session audit、pre-prod smoke、release-window evidence 全齐后，才进入 compat removal assessment。
