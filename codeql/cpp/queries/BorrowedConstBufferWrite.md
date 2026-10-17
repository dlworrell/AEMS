# Write through a borrowed const pointer

AES-SEC-002: this write destination flows from a borrowed const pointer. Do not erase or mutate caller-owned const storage. Review ownership and use project-owned mutable storage.

This query supports AES-SEC-002 at AES revision
`256bf6dd0e424b134d4f1c628f9aff30ea12566d`.

Follow the local reviewed profile, disposition ledger, and waiver process.
A result is source evidence; query completion does not establish standard
compliance. See `docs/engineering/AES-CodeQL.md` for limitations and the
required complementary verification.
