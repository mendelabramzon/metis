"""Source ACL/sensitivity propagates into derived artifacts (and gates external-model egress).

If a private Slack channel or a user-restricted Drive file normalized to the same policy as public
content, restricted data would leak downstream — so the connector maps ACL to ``Sensitivity`` and
stamps it on both the raw artifact and the normalized doc, and a restricted source also forbids
external models.
"""

from metis_ingestion.connectors import (
    ConnectorRegistry,
    GoogleDriveConnector,
    RecordedTransport,
    SlackConnector,
)
from metis_protocol import Sensitivity


async def test_channel_acl_maps_to_sensitivity(connectors_root, workspace) -> None:
    connector = SlackConnector(
        workspace_id=workspace, transport=RecordedTransport(connectors_root / "slack")
    )
    by_locator = {ref.locator: ref for ref in await connector.discover(None)}

    private_raw, _ = await connector.fetch_with_bytes(by_locator["founders"])
    assert private_raw.policy.sensitivity is Sensitivity.CONFIDENTIAL  # private channel
    assert connector.normalize(private_raw).policy.sensitivity is Sensitivity.CONFIDENTIAL

    public_raw, _ = await connector.fetch_with_bytes(by_locator["general"])
    assert public_raw.policy.sensitivity is Sensitivity.INTERNAL  # public channel, connector floor


async def test_drive_restricted_file_is_confidential(connectors_root, workspace) -> None:
    connector = ConnectorRegistry.with_defaults().create(
        "gdrive", workspace_id=workspace, transport=RecordedTransport(connectors_root / "gdrive")
    )
    by_locator = {ref.locator: ref for ref in await connector.discover(None)}

    restricted_raw, _ = await connector.fetch_with_bytes(by_locator["file-comp"])  # user-only ACL
    assert restricted_raw.policy.sensitivity is Sensitivity.CONFIDENTIAL

    domain_raw, _ = await connector.fetch_with_bytes(by_locator["file-roadmap"])  # domain ACL
    assert domain_raw.policy.sensitivity is Sensitivity.INTERNAL


async def test_restricted_source_forbids_external_models(connectors_root, workspace) -> None:
    # A source configured RESTRICTED stamps allow_external_models=False onto its artifacts, and that
    # propagates into the normalized doc (so restricted data can never reach an external provider).
    connector = GoogleDriveConnector(
        workspace_id=workspace,
        transport=RecordedTransport(connectors_root / "gdrive"),
        sensitivity=Sensitivity.RESTRICTED,
    )
    ref = (await connector.discover(None))[0]
    raw, _ = await connector.fetch_with_bytes(ref)

    assert raw.policy.sensitivity is Sensitivity.RESTRICTED
    assert raw.policy.allow_external_models is False
    assert connector.normalize(raw).policy.allow_external_models is False
