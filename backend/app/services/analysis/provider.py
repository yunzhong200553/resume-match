"""分析提供方接口与 Mock 实现。

契约要点（README 7.3）：``overallScore`` 为 0-100 整数、``level`` 只能为
high/medium/low、引用的 sectionId/itemId 必须存在于输入版本、建议状态只能是
pending/accepted/rejected/edited。

Mock 的价值：没有 Coze 凭据也能跑通整条链路，契约测试可用固定 JSON 与 Mock
输出做双向校验。模块 B 接入真实 Coze 时只需实现同一个 Protocol。
"""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from app.core.config import settings
from app.core.errors import AppError, ErrorCode

MOCK_PAYLOAD_FILE = "analysis_sample.json"


@runtime_checkable
class AnalysisProvider(Protocol):
    """分析提供方必须实现的最小接口。"""

    name: str

    def analyze(self, *, document: dict[str, Any], jd_text: str) -> dict[str, Any]:
        """输入简历文档与 JD，返回符合 README 7.3 的标准分析结构。"""
        ...


class MockProvider:
    """返回固定结构的分析结果，不调用任何外部服务。"""

    name = "mock"

    def __init__(self, payload_path: Path | None = None) -> None:
        self.payload_path = payload_path or (settings.mock_dir / MOCK_PAYLOAD_FILE)

    def analyze(self, *, document: dict[str, Any], jd_text: str) -> dict[str, Any]:
        payload = deepcopy(self._load_payload())
        payload["jdText"] = jd_text
        self._bind_real_ids(payload, document)
        return payload

    def _load_payload(self) -> dict[str, Any]:
        if not self.payload_path.exists():
            raise AppError(
                ErrorCode.ANALYSIS_PROVIDER_ERROR,
                f"Mock 数据文件不存在：{self.payload_path}",
            )
        with self.payload_path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def _bind_real_ids(self, payload: dict[str, Any], document: dict[str, Any]) -> None:
        """把 Mock 结果里的示例 ID 替换为输入版本中真实存在的 ID。

        这样 Mock 输出同样满足「引用的条目必须存在」这条契约约束。
        """

        pairs: list[tuple[str, str]] = [
            (section.get("id", ""), item.get("id", ""))
            for section in document.get("sections", [])
            for item in section.get("items", [])
        ]
        if not pairs:
            return

        for index, match in enumerate(payload.get("itemMatches", [])):
            match["sectionId"], match["itemId"] = pairs[index % len(pairs)]
        for index, suggestion in enumerate(payload.get("suggestions", [])):
            suggestion["sectionId"], suggestion["itemId"] = pairs[index % len(pairs)]


def get_provider(name: str | None = None) -> AnalysisProvider:
    resolved = (name or settings.analysis_provider or "mock").lower()
    if resolved == "mock":
        return MockProvider()
    if resolved == "coze":
        raise AppError(
            ErrorCode.ANALYSIS_PROVIDER_ERROR,
            "Coze Provider 由模块 B 实现，当前尚未接入。",
            details={"provider": resolved},
        )
    raise AppError(
        ErrorCode.ANALYSIS_PROVIDER_ERROR,
        f"未知的分析提供方：{resolved}",
        details={"supported": ["mock", "coze"]},
    )
