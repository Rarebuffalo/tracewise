"""Provider continuation state (O-5): bound, size-limited, verified, never shown.

Some providers require state they issued to come back verbatim on later turns: OpenAI reasoning items (R-10), Gemini
signed model turns (N-15 to N-17). Later, Anthropic thinking blocks and DeepSeek `reasoning_content` will too, on
every assistant turn. That state is protocol data, not evidence. The loop never reads it, and it is never logged,
rendered, persisted or returned as a tool result.

The investigation loop owns one `ReplayLedger` per investigation:
  * `seal(items)` wraps what a provider step returned in a `ReplayEnvelope` bound to the `ReplayContext`: provider,
    model, installation, job, job attempt and a random investigation id. It is checked against the per-envelope and
    per-conversation byte caps, and fingerprinted (SHA-256 of a canonical encoding). Oversized or malformed state is
    refused (`ReplayError`), never truncated.
  * `open(envelopes)` is called only to build the next request. An envelope from another context, one this ledger
    did not seal, or one whose items changed since sealing, is refused.
A refusal ends the investigation as `provider_failed`, which is inconclusive and never a guessed diagnosis (P10).
Opaque state stays opaque: items are fingerprinted and passed back, never parsed or rewritten here (P2, P9). A codec
may add its own authentication on top (the Gemini codec's HMAC). Lifetime: one `investigate()` call. Envelopes refuse
pickling and copying (P8), and their `repr` names only the provider and the size (P5).

Which assistant turns carry state is the provider's `replay_scope` (`tool_turns` or `all_turns`). The loop applies
it without provider-specific branches.
"""

from __future__ import annotations

import hashlib
import json
import secrets
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

# P7 starting points (O-5 §6), inside the 256 KiB request cap of the model mode. Owner-adjustable constants.
MAX_ENVELOPE_BYTES = 64 * 1024
MAX_CONVERSATION_BYTES = 192 * 1024


class ReplayError(Exception):
    """Continuation state refused. The message is a fixed reason code: it never carries the state itself."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class ReplayContext:
    """What continuation state is bound to. `investigation` is random per `investigate()` call, so state can never
    cross into another investigation, even of the same job attempt."""

    provider: str
    model: str
    installation_id: int | None = None
    job_id: int | None = None
    attempt: int | None = None
    investigation: str = field(default_factory=lambda: secrets.token_hex(16))


def _canonical(item: Any) -> bytes:
    """Bytes that identify an item exactly. A codec's own opaque type provides `__replay_bytes__`; plain provider
    items must be JSON objects. Anything else is malformed."""
    own = getattr(type(item), "__replay_bytes__", None)
    if own is not None:
        b = own(item)
        if not isinstance(b, bytes):
            raise ReplayError("malformed")
        return b
    if not isinstance(item, dict):
        raise ReplayError("malformed")
    try:
        return json.dumps(item, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()
    except (TypeError, ValueError):
        raise ReplayError("malformed") from None


class ReplayEnvelope:
    """One provider step's continuation state. Opaque to everything but `ReplayLedger.open`."""

    __slots__ = ("_ctx", "_digest", "_items", "_seq", "_size")

    def __init__(self, ctx: ReplayContext, seq: int, items: tuple[Any, ...], digest: bytes, size: int) -> None:
        self._ctx, self._seq, self._items, self._digest, self._size = ctx, seq, items, digest, size

    @property
    def size(self) -> int:
        return self._size

    def __repr__(self) -> str:
        return f"ReplayEnvelope(<{self._ctx.provider} continuation state hidden, {self._size} bytes>)"

    __str__ = __repr__

    def __reduce_ex__(self, protocol: object) -> Any:  # pickle, copy and deepcopy all go through here
        raise TypeError("ReplayEnvelope cannot be serialised or copied")


def _fingerprint(items: tuple[Any, ...]) -> tuple[bytes, int]:
    h, size = hashlib.sha256(), 0
    for it in items:
        b = _canonical(it)
        size += len(b)
        h.update(len(b).to_bytes(8, "big"))
        h.update(b)
    return h.digest(), size


class ReplayLedger:
    def __init__(
        self, ctx: ReplayContext, *, max_envelope: int = MAX_ENVELOPE_BYTES, max_total: int = MAX_CONVERSATION_BYTES
    ) -> None:
        self.ctx, self.max_envelope, self.max_total = ctx, max_envelope, max_total
        self.total = 0
        self.largest = 0  # the biggest envelope sealed so far (bytes): sizes only, for observability
        self._sealed: dict[int, bytes] = {}  # seq -> digest, for every envelope this ledger issued

    @property
    def sealed(self) -> int:
        return len(self._sealed)

    def seal(self, items: Iterable[Any]) -> ReplayEnvelope:
        got = tuple(items)
        if not got:
            raise ReplayError("missing")
        digest, size = _fingerprint(got)
        if size > self.max_envelope:
            raise ReplayError("envelope_too_large")
        if self.total + size > self.max_total:
            raise ReplayError("conversation_too_large")
        seq = len(self._sealed) + 1
        self._sealed[seq] = digest
        self.total += size
        self.largest = max(self.largest, size)
        return ReplayEnvelope(self.ctx, seq, got, digest, size)

    def open(self, envelopes: Iterable[Any]) -> tuple[Any, ...]:
        out: list[Any] = []
        for env in envelopes:
            if not isinstance(env, ReplayEnvelope):
                raise ReplayError("not_sealed")
            if env._ctx != self.ctx:
                raise ReplayError("context_mismatch")  # another provider, model, tenant, job, attempt or investigation
            if self._sealed.get(env._seq) != env._digest:
                raise ReplayError("unknown_envelope")  # not issued by this ledger
            if _fingerprint(env._items)[0] != env._digest:
                raise ReplayError("modified")  # items changed after sealing: never sent back altered
            out.extend(env._items)
        return tuple(out)
