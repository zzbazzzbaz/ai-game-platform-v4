from __future__ import annotations

from typing import Any

from pydantic_ai.models import Model, infer_model
from pydantic_ai.providers import Provider
from pydantic_ai.providers.deepseek import DeepSeekProvider

from app.config import settings


class ConfiguredDeepSeekProvider(DeepSeekProvider):
    """使用显式 base URL 的 DeepSeek provider，保留官方 model profile。"""

    @property
    def base_url(self) -> str:
        return settings.deepseek_base_url


def provider_factory(name: str) -> Provider[Any]:
    if name != "deepseek":
        raise ValueError(f"不支持的模型提供方：{name}")
    return ConfiguredDeepSeekProvider(api_key=settings.deepseek_api_key)


def build_model() -> Model:
    return infer_model(settings.model, provider_factory=provider_factory)
