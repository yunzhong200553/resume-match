"""分析适配层（模块 B 负责实现，这里只预留接口与 Mock）。

模块 A 的任何流程都不依赖本模块；``I-01`` 用例要求禁用分析能力后
模块 A 仍能创建、编辑和基础导出，因此这里不注册任何业务路由。
"""

from app.services.analysis.provider import AnalysisProvider, MockProvider, get_provider

__all__ = ["AnalysisProvider", "MockProvider", "get_provider"]
