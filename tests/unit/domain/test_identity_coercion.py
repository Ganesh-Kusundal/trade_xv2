"""Unit tests for the tightened ``coerce_identity_provider`` (Plan §7.4).

The duck-typed fallback (any object with ``.resolve`` and
``.get_by_security_id``) used to be the default behaviour. That masked
test fixtures that were *meant* to bypass the provider — any MagicMock
that happened to expose those methods would be wrapped as a real
provider, silently hiding a missing dependency.

The contract change:

- Default (``allow_duck=False``): only ``DhanIdentityProvider``,
  ``SymbolResolver``, or objects exposing ``.resolver`` are accepted.
  A bare duck-typed object raises ``TypeError``.
- Opt-in (``allow_duck=True``): the legacy duck-typed fallback is
  available so test fixtures can explicitly enable it.

These tests pin both behaviours so a regression that re-enables the
fallback by default is caught immediately.
"""

from __future__ import annotations

from unittest import mock

import pytest

from brokers.providers.dhan.identity import (
    DhanIdentityProvider,
    SymbolResolver,
    coerce_identity_provider,
)


class TestCoerceIdentityProviderStrict:
    """The default behaviour — no duck-typing."""

    def test_returns_dhan_identity_provider_as_is(self):
        provider = DhanIdentityProvider(mock.MagicMock(spec=SymbolResolver))
        assert coerce_identity_provider(provider) is provider

    def test_wraps_plain_symbol_resolver(self):
        resolver = mock.MagicMock(spec=SymbolResolver)
        out = coerce_identity_provider(resolver)
        assert isinstance(out, DhanIdentityProvider)
        assert out.resolver is resolver

    def test_wraps_object_exposing_resolver_attr(self):
        resolver = mock.MagicMock(spec=SymbolResolver)
        holder = mock.MagicMock()
        holder.resolver = resolver
        out = coerce_identity_provider(holder)
        assert isinstance(out, DhanIdentityProvider)
        assert out.resolver is resolver

    def test_rejects_bare_duck_typed_object_by_default(self):
        """A MagicMock that quacks like a resolver is REJECTED by default.

        This is the key behaviour change called out in §5.6 of the plan:
        the previous default silently wrapped any quacking object,
        masking test fixtures that should have raised.
        """
        quacker = mock.MagicMock()
        quacker.resolve = mock.MagicMock()
        quacker.get_by_security_id = mock.MagicMock()
        with pytest.raises(TypeError, match="allow_duck=True"):
            coerce_identity_provider(quacker)

    def test_rejects_random_object_by_default(self):
        with pytest.raises(TypeError, match="DhanIdentityProvider or SymbolResolver"):
            coerce_identity_provider(object())

    def test_error_message_mentions_allow_duck(self):
        """SREs reading the traceback must see how to opt in."""
        quacker = mock.MagicMock()
        quacker.resolve = mock.MagicMock()
        quacker.get_by_security_id = mock.MagicMock()
        with pytest.raises(TypeError) as exc_info:
            coerce_identity_provider(quacker)
        assert "allow_duck=True" in str(exc_info.value)


class TestCoerceIdentityProviderAllowDuck:
    """The opt-in duck-typed fallback — for test fixtures."""

    def test_allows_duck_typed_object_when_opted_in(self):
        quacker = mock.MagicMock()
        quacker.resolve = mock.MagicMock(return_value="resolved")
        quacker.get_by_security_id = mock.MagicMock(return_value="by_sid")
        out = coerce_identity_provider(quacker, allow_duck=True)
        assert isinstance(out, DhanIdentityProvider)
        # The wrapper holds the duck-typed object as the underlying resolver.
        assert out.resolver is quacker

    def test_still_rejects_truly_invalid_object_with_allow_duck(self):
        """``allow_duck=True`` does not bypass the resolver interface check —
        an object without ``.resolve`` / ``.get_by_security_id`` is still rejected.
        """
        with pytest.raises(TypeError, match="DhanIdentityProvider or SymbolResolver"):
            coerce_identity_provider(object(), allow_duck=True)


class TestCoerceIdentityProviderRealWorldInvariants:
    """End-to-end: an object that genuinely is a SymbolResolver works
    with or without ``allow_duck=True`` (because the explicit
    SymbolResolver branch comes first).
    """

    def test_symbol_resolver_works_without_allow_duck(self):
        resolver = mock.MagicMock(spec=SymbolResolver)
        out = coerce_identity_provider(resolver)
        assert isinstance(out, DhanIdentityProvider)

    def test_symbol_resolver_works_with_allow_duck(self):
        resolver = mock.MagicMock(spec=SymbolResolver)
        out = coerce_identity_provider(resolver, allow_duck=True)
        assert isinstance(out, DhanIdentityProvider)
