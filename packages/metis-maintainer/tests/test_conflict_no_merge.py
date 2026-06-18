"""Conflicting evidence produces a tracked conflict, not a silent merge."""

from metis_maintainer.memory import ProfileBuilder
from metis_protocol import Claim, ClaimId, ProfileScope
from metis_protocol.examples import CLM1, CLM2, claim


def _claim(claim_id: ClaimId, text: str) -> Claim:
    return claim().model_copy(update={"id": claim_id, "text": text})  # same predicate role_of


async def test_conflicting_facts_are_kept_separate_and_flagged() -> None:
    ada = _claim(CLM1, "Ada is the CTO of Acme.")
    grace = _claim(CLM2, "Grace is the CTO of Acme.")

    result = ProfileBuilder().build(scope=ProfileScope.COMPANY, label="Acme", claims=[ada, grace])

    role_facts = [fact for fact in result.profile.facts if fact.key == "role_of"]
    assert len(role_facts) == 2  # both values survive — no silent merge
    assert all(fact.conflicting for fact in role_facts)
    assert {fact.value for fact in role_facts} == {ada.text, grace.text}

    # The conflict is surfaced as an explicit, claim-cited contradiction.
    assert len(result.contradictions) == 1
    cited = {str(ref.claim_id) for ref in result.contradictions[0].claims}
    assert cited == {str(CLM1), str(CLM2)}


async def test_agreeing_evidence_does_not_create_a_conflict() -> None:
    result = ProfileBuilder().build(
        scope=ProfileScope.COMPANY, label="Acme", claims=[_claim(CLM1, "Ada is the CTO of Acme.")]
    )
    role_facts = [fact for fact in result.profile.facts if fact.key == "role_of"]
    assert len(role_facts) == 1
    assert not role_facts[0].conflicting
    assert result.contradictions == ()
