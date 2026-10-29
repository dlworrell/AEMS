# Omnibus manifests

Each `<id>.json` here lists pull requests the owner approves as one batch
(Catylist ADR-0016). Merging the pull request that adds a manifest is the
approval; `catylist-ring-0` then merges the listed pull requests in order, at
the listed commits. Manifests are never edited after approval: to change a
batch, add a new manifest with a new id.

See `docs/engineering/omnibus-merge.md`.
