"""JD 分析服务与 Provider 适配层。"""

from app.services.analysis.provider import AnalysisProvider, MockProvider, get_provider

__all__ = ["AnalysisProvider", "MockProvider", "get_provider"]
