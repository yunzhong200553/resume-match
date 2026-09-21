"""ID 生成。

对外 ID 一律为不透明字符串，格式与 README 示例保持一致：``resume_ab12cd34``。
"""

from __future__ import annotations

from uuid import uuid4

ID_HEX_LENGTH = 12


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:ID_HEX_LENGTH]}"


def new_request_id() -> str:
    return new_id("req")


def section_id(section_type: str, index: int) -> str:
    """同一类型出现多个模块时追加序号：section_project、section_project_2。"""

    return f"section_{section_type}" if index == 1 else f"section_{section_type}_{index}"


def item_id(section_type: str, index: int) -> str:
    return f"item_{section_type}_{index}"
