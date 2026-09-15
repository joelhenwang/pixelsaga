"""Request correlation carrier (owned by S0-OPS-001).

One context-local request ID joins HTTP handling, structured logs, and
error envelopes. The HTTP boundary assigns it; anything downstream reads
it. No secrets ever flow through here.
"""

from __future__ import annotations

import contextvars

request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="")


def get_request_id() -> str:
    return request_id_var.get()
