# ADR 0007: ID strategy — typed, prefixed UUIDv7

- Status: Accepted
- Date: 2026-06-18
- Deciders: Metis maintainers

## Context

Every artifact in Metis carries an ID, and provenance chains hop across artifact
types (raw → span → claim → memcell → wiki → answer). IDs need to be: globally
unique, debuggable (you can tell an artifact's type by glancing at its ID),
time-sortable (for index locality and human-readable ordering), and safe to use as
external string keys. This is decided in Stage 0 because Stages 1–2 build schemas
and storage on top of it.

## Decision

IDs are **strings of the form `<prefix>_<uuid7>`**, where the prefix encodes the
artifact type (`art_` RawArtifact, `clm_` Claim, `ent_` Entity, `evt_` Event,
`mc_` MemCell, and so on) and the body is a **UUIDv7** (time-ordered). They are
treated as opaque typed references at the type level (distinct `NewType`/branded
types per artifact kind in `metis-protocol`, Stage 1), not as bare `str`.

## Consequences

- UUIDv7's leading timestamp gives index locality and natural chronological
  ordering without a separate sort key.
- The prefix makes logs, audit events, and provenance chains self-describing and
  catches "right ID, wrong type" mistakes at boundaries.
- Typed references prevent passing a claim ID where an entity ID is expected.
- The generator and prefix registry live in `metis-protocol`; storage treats IDs
  as opaque strings.

## Alternatives considered

- **Bare UUIDv4**: unique but not sortable and not self-describing.
- **Auto-increment integers**: leak volume, aren't globally unique across stores,
  and are poor external keys.
- **Prefix + UUIDv4**: self-describing but loses time-ordering; UUIDv7 keeps both.
