from __future__ import annotations

from pydantic import Field

from app.contracts.common import ContractModel, KeyParameter


class ParameterSnapshotPayload(ContractModel):
    hero_scene: str = ""
    core_selling_points: list[str] = Field(default_factory=list)
    key_parameters: list[KeyParameter] = Field(default_factory=list)
    product_advantages: list[str] = Field(default_factory=list)
    feature_highlights: list[str] = Field(default_factory=list)
    inferred_core_selling_points: list[str] = Field(default_factory=list)
    inferred_key_parameters: list[KeyParameter] = Field(default_factory=list)
    inferred_advantages: list[str] = Field(default_factory=list)
    source_mode: str | None = None
    evidence_priority: str | None = None
    evidence_summary: list[dict] = Field(default_factory=list)
    completion_status: str | None = None
    completion_source: str | None = None
    confidence_notes: list[str] = Field(default_factory=list)
    # 事实层溯源标记：由 Gemini analysis 写入，Doubao completion 不得修改
    # 取值：'llm'（Gemini 正常分析）| 'fallback'（Gemini 未识别，走兜底）
    analysis_quality: str | None = None
    # 跳过补全时由 sessions.py 写入的调试元数据
    skipped_completion: bool | None = None
    skip_reason: str | None = None
