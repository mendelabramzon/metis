"""Diagnostic probes catch a dropped supported fact and the refine loop recovers."""

from collections.abc import Sequence

from metis_maintainer.wiki import ErrorBook, WikiCompiler, compile_with_refine, probe_patch
from metis_protocol import Claim, WikiPage, WikiPatch
from metis_protocol.examples import CLM2, claim

_SLUG = "entity/ada"


def _two_claims() -> list[Claim]:
    return [claim(), claim().model_copy(update={"id": CLM2, "text": "Ada chairs the Acme board."})]


async def test_probes_pass_for_complete_compilation() -> None:
    claims = _two_claims()
    patch = await WikiCompiler().compile(title="Ada", slug=_SLUG, claims=claims)
    probe = probe_patch(patch, claims)
    assert probe.complete
    assert probe.loss == 0.0


async def test_probes_detect_a_dropped_fact() -> None:
    claims = _two_claims()
    full = await WikiCompiler().compile(title="Ada", slug=_SLUG, claims=claims)
    lossy = full.model_copy(
        update={
            "claims": full.claims[:1],
            "body_markdown": full.body_markdown.replace(str(CLM2), ""),
        }
    )
    probe = probe_patch(lossy, claims)
    assert not probe.complete
    assert str(CLM2) in probe.dropped


class _FlakyCompiler:
    """Drops the last claim on the first attempt, then compiles completely (models retry gain)."""

    def __init__(self) -> None:
        self._real = WikiCompiler()
        self._calls = 0

    async def compile(
        self, *, title: str, slug: str, claims: Sequence[Claim], existing: WikiPage | None = None
    ) -> WikiPatch:
        self._calls += 1
        patch = await self._real.compile(title=title, slug=slug, claims=claims, existing=existing)
        if self._calls == 1:
            dropped = str(patch.claims[-1].claim_id)
            return patch.model_copy(
                update={
                    "claims": patch.claims[:-1],
                    "body_markdown": patch.body_markdown.replace(dropped, ""),
                }
            )
        return patch


async def test_refine_recovers_and_records_the_drop() -> None:
    claims = _two_claims()
    book = ErrorBook()
    result = await compile_with_refine(
        _FlakyCompiler(), title="Ada", slug=_SLUG, claims=claims, error_book=book
    )
    assert result.probe.complete  # the second round recovered the dropped fact
    assert result.rounds == 2
    assert len(book) == 1  # the first-round drop was recorded for feedback
