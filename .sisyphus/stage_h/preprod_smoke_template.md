# Stage H Pre-Prod Smoke Record

- Date:
- Environment:
- Operator:
- Base URL:
- Commit / Release ID:

## Required Samples

| session_type | session_id | app_key | historical_version | latest_pass | historical_pass | notes |
| --- | --- | --- | --- | --- | --- | --- |
| partial_main |  |  |  |  |  |  |
| partial_detail |  |  |  |  |  |  |
| carry_forward_or_restore_or_regenerate_main |  |  |  |  |  |  |
| carry_forward_or_restore_or_regenerate_detail |  |  |  |  |  |  |
| alibaba_main |  |  |  |  |  |  |
| text_edit_main |  |  |  |  |  |  |

## Verification Checklist

- `GET /api/v2/sessions/{session_id}/results` latest 可读
- `GET /api/v2/sessions/{session_id}/results?version=<historical>` historical 可读
- `GET /api/v2/sessions/{session_id}/detail-pages/results` latest 可读
- `GET /api/v2/sessions/{session_id}/detail-pages/results?version=<historical>` historical 可读
- `available_versions` 无漂移
- `version_summaries` 字段完整
- `missing_*` 不串版本
- `cover_asset_id / stitched_asset` 不串版本
- `carry_forward/source_version_no` 只反映被请求版本

## Blocking Findings

- None / list findings here

## Conclusion

- Smoke status:
- Follow-up owner:
