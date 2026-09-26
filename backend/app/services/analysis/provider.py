"""双分析 Provider 接口与 Mock 实现。"""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Literal, Protocol, runtime_checkable

from app.core.config import settings
from app.core.errors import AppError, ErrorCode

ProviderName = Literal["scoreAgent", "suggestionAgent"]
MOCK_PAYLOAD_FILE = "analysis_sample.json"


@runtime_checkable
class AnalysisProvider(Protocol):
    """单个分析智能体必须实现的接口。"""

    name: ProviderName

    def analyze(self, *, document: dict[str, Any], jd_text: str) -> dict[str, Any]: ...


class MockProvider:
    """从固定 JSON 中读取一个智能体的输出。"""

    def __init__(self, name: ProviderName, payload_path: Path | None = None) -> None:
        self.name = name
        self.payload_path = payload_path or (settings.mock_dir / MOCK_PAYLOAD_FILE)

    def analyze(self, *, document: dict[str, Any], jd_text: str) -> dict[str, Any]:
        del jd_text
        payload = deepcopy(self._load_payload()[self.name])
        self._bind_real_items(payload, document)
        return payload

    def _load_payload(self) -> dict[str, Any]:
        if not self.payload_path.exists():
            raise AppError(
                ErrorCode.ANALYSIS_PROVIDER_ERROR,
                f"Mock 数据文件不存在：{self.payload_path}",
            )
        with self.payload_path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        if self.name not in payload or not isinstance(payload[self.name], dict):
            raise AppError(
                ErrorCode.ANALYSIS_PROVIDER_ERROR,
                "Mock 数据缺少智能体输出。",
                details={"provider": self.name},
            )
        return payload

    def _bind_real_items(
        self, payload: dict[str, Any], document: dict[str, Any]
    ) -> None:
        items = [
            (section.get("id", ""), item)
            for section in document.get("sections", [])
            for item in section.get("items", [])
        ]
        if not items:
            return

        for index, match in enumerate(payload.get("itemMatches", [])):
            section_id, item = items[index % len(items)]
            match["sectionId"] = section_id
            match["itemId"] = item.get("id", "")

        content_items = [(section_id, item) for section_id, item in items if item.get("content")]
        for index, suggestion in enumerate(payload.get("suggestions", [])):
            if not content_items:
                break
            section_id, item = content_items[index % len(content_items)]
            suggestion["sectionId"] = section_id
            suggestion["itemId"] = item.get("id", "")
            suggestion["original"] = item.get("content", "")


def get_providers(name: str | None = None) -> tuple[AnalysisProvider, AnalysisProvider]:
    resolved = (name or settings.analysis_provider or "mock").lower()
    if resolved == "mock":
        return MockProvider("scoreAgent"), MockProvider("suggestionAgent")
    if resolved == "coze":
        raise AppError(
            ErrorCode.ANALYSIS_PROVIDER_ERROR,
            "Coze Provider 尚未接入。",
            details={"provider": resolved},
        )
    raise AppError(
        ErrorCode.ANALYSIS_PROVIDER_ERROR,
        f"未知的分析提供方：{resolved}",
        details={"supported": ["mock", "coze"]},
    )