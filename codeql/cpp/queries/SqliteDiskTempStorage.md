# Review SQLite disk-backed temporary storage

AES-SEC-002: this SQLite command requests file-backed temporary storage. For confidential connections, enforce encrypted or in-memory temporary state after keying and before protected access; review the dependency build too.

This query supports AES-SEC-002 at AES revision
`256bf6dd0e424b134d4f1c628f9aff30ea12566d`.

Follow the local reviewed profile, disposition ledger, and waiver process.
A result is source evidence; query completion does not establish standard
compliance. See `docs/engineering/AES-CodeQL.md` for limitations and the
required complementary verification.
