from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import AsyncIterator, ClassVar, Generic, Mapping, Protocol, TypeVar, cast

from domain.models import PriceQuote
from domain.repositories import PriceFeedRepository

TConfig = TypeVar("TConfig")
Factory = Callable[[], TConfig]


class PriceFeedClientProtocol(Protocol):
    """Protocol describing the minimal websocket client behaviour we rely on."""

    def __init__(self, config: object) -> None: ...

    def stream_ticker_prices(self, symbols: Iterable[str]) -> AsyncIterator[PriceQuote]:
        """Return an async iterator that yields `PriceQuote` instances."""
        raise NotImplementedError


class ContractTypeResolver(Generic[TConfig]):
    """Utility for normalising and resolving connector contract type configurations."""

    def __init__(
        self,
        canonical_factories: Mapping[str, TConfig | Callable[[], TConfig]],
        *,
        aliases: Mapping[str, str] | None = None,
        default_key: str | None = None,
        normalizer: Callable[[str], str] | None = None,
        error_message: str | None = None,
        missing_message: str | None = None,
    ) -> None:
        normalizer_fn: Callable[[str], str] = normalizer or (
            lambda value: value.lower()
        )
        self._normalizer = normalizer_fn

        factories: dict[str, Factory] = {}
        for key, value in canonical_factories.items():
            if callable(value):
                factories[key] = cast(Factory, value)
            else:
                factories[key] = cast(Factory, lambda v=value: v)
        self._factories = factories
        self._aliases = {
            self._normalizer(alias): target for alias, target in (aliases or {}).items()
        }
        self._default_key = default_key
        self._error_message = error_message
        self._missing_message = missing_message

        if default_key is not None and default_key not in self._factories:
            raise ValueError(
                f"default_key '{default_key}' is not present in canonical factories"
            )

    def resolve(self, contract_type: str | None) -> TConfig:
        """Resolve a contract type string (with aliases) into the configured value."""
        if contract_type is None:
            if self._default_key is None:
                message = self._missing_message or "Contract type is required"
                raise ValueError(message)
            key = self._default_key
            original = key
        else:
            normalized = self._normalizer(contract_type)
            key = self._aliases.get(normalized, normalized)
            original = contract_type

        factory = self._factories.get(key)
        if factory is None:
            normalized = self._normalizer(original)
            canonical = self._aliases.get(normalized, normalized)
            message = self._error_message or "Unsupported contract type: {value}"
            raise ValueError(
                message.format(
                    value=contract_type,
                    normalized=normalized,
                    canonical=canonical,
                    choices=", ".join(sorted(self._factories)),
                )
            )

        return factory()

    @property
    def choices(self) -> list[str]:
        """Return the sorted list of canonical contract type keys."""
        return sorted(self._factories)


class WebSocketPriceFeedRepository(Generic[TConfig], PriceFeedRepository):
    """Template for repositories that delegate to a websocket streaming client."""

    client_cls: ClassVar[type[PriceFeedClientProtocol]]

    def __init__(self, contract_type: str | None = None) -> None:
        config = self._build_config(contract_type)
        self._config = config
        self._client = self._build_client(config)

    def stream_quotes(self, symbols: Iterable[str]) -> AsyncIterator[PriceQuote]:
        return self._client.stream_ticker_prices(symbols)

    def _build_config(self, contract_type: str | None) -> TConfig:
        raise NotImplementedError

    def _build_client(self, config: TConfig) -> PriceFeedClientProtocol:
        return self.client_cls(config)


class RegistryBackedPriceFeedRepository(WebSocketPriceFeedRepository[TConfig]):
    """Repository relying on a `ContractTypeResolver` to build configuration objects."""

    resolver: ClassVar[ContractTypeResolver[TConfig]]

    def _build_config(self, contract_type: str | None) -> TConfig:
        return self.resolver.resolve(contract_type)
