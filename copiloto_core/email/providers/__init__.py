"""Adapters concretos del subsistema de email del core.

Re-exporta las clases públicas para `from copiloto_core.email.providers import X`.
"""
from copiloto_core.email.providers.base import (
    EmailMessage,
    EmailProvider,
    ProviderError,
    ProviderInvalidConfig,
    ProviderRateLimited,
    ProviderRejected,
    ProviderResult,
    ProviderUnavailable,
)

__all__ = [
    'EmailMessage',
    'EmailProvider',
    'ProviderError',
    'ProviderInvalidConfig',
    'ProviderRateLimited',
    'ProviderRejected',
    'ProviderResult',
    'ProviderUnavailable',
]
