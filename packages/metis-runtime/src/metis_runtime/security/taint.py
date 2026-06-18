"""Taint enforcement: a hardened, single chokepoint over the Stage 10 taint primitives.

Stage 10 ``agent.taint`` defines trusted/untrusted spans and ``control_text`` (which refuses
untrusted input). This hardens it into one enforcement surface that the loop and any future
control-plane code go through, so a new path cannot forget the boundary: :meth:`control` yields
text for a control decision (raising on untrusted), :meth:`data` yields text for the data
plane (fencing untrusted content via the injection defense), and :meth:`assert_trusted_only` guards
a batch of spans before they are allowed to drive anything.
"""

from __future__ import annotations

from collections.abc import Iterable

from metis_runtime.agent.taint import TaintedText, TaintViolationError, Trust, control_text
from metis_runtime.security.injection_defense import render_untrusted


class TaintBoundary:
    """The sanctioned accessors for crossing between the control and data planes."""

    @staticmethod
    def control(source: TaintedText) -> str:
        """Text for a control decision — raises ``TaintViolationError`` on an untrusted span."""
        return control_text(source)

    @staticmethod
    def data(source: TaintedText) -> str:
        """Text for the data plane — untrusted content is fenced, trusted passes through."""
        return render_untrusted(source)

    @staticmethod
    def assert_trusted_only(sources: Iterable[TaintedText]) -> None:
        """Fail closed if any span in a trusted-only context is untrusted."""
        for source in sources:
            if source.trust is not Trust.TRUSTED:
                raise TaintViolationError("untrusted span in a trusted-only context")
