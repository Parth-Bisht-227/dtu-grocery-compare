"""Small provider contract and shared configuration helpers."""

from __future__ import annotations

import os
from abc import ABC, abstractmethod

from models import Product, Provider


class ProviderError(RuntimeError):
    """A recoverable marketplace-specific failure."""


def environment_flag(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().casefold() in {"1", "true", "yes", "on"}


class ProductProvider(ABC):
    provider: Provider

    @abstractmethod
    def search(self, query: str) -> list[Product]:
        raise NotImplementedError

