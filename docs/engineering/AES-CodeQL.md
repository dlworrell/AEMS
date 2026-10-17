# AES-SEC-001 and AES-SEC-002 CodeQL implementation

Status: Proposed implementation; reporting only  
Owner: AEMS  
Normative authority: AES at `256bf6dd0e424b134d4f1c628f9aff30ea12566d`

## Purpose and authority

These packs supplement the adopted AES standards with executable source checks.
They do not change either standard, approve waivers, or replace existing AEMS
adoption and review gates. Program-wide CodeQL adoption remains a Catylist
governance decision; this change prepares its implementation without changing
repository rulesets.

The exact sources and SHA-256 digests are in
[`config/aes-codeql-controls.json`](../../config/aes-codeql-controls.json).
Its 198 source locators cover normative paragraphs and list items, including
items inheriting a MUST/SHOULD introduction. Locators identify pinned source
lines, not newly adopted AES requirement IDs. Code fences containing illustrative
profiles are not additional normative clauses. The banned-interface and primitive
lists are implemented by the corresponding queries and traced to their governing
paragraphs. Every catalog entry remains partial or requires complementary evidence.

AES owns the obligations. AEMS owns the detector implementation, tests, reporting,
and proposed query-to-clause mappings. No zero-finding result establishes either
standard's satisfaction.

## Custom detectors

| Query ID suffix (`aes/cpp/` unless stated) | Result means | Required follow-up |
|---|---|---|
| `banned-interface` | Direct call or function reference to an AES-banned global/standard API | Replace or review the scope-specific exception |
| `unbounded-scanf-string` | A scanf-family string conversion has no width or separate secure-variant size contract | Bound input and check actual buffer capacity |
| `review-required-primitive` | A listed memory API, new/delete, or unsafe cast appears | Apply the existing review/disposition and waiver process |
| `discarded-snprintf-result` | Formatting status is discarded, including explicit void casts | Review correctness/security impact of truncation |
| `key-buffer-contract` | A name-identified pointer parameter is mutable or lacks a recognizable length parameter | Check whether it is secret input and verify the ABI contract |
| `borrowed-const-buffer-write` | A write destination locally flows from a const pointer parameter | Review mutation of borrowed storage; includes casts and aliases |
| `candidate-secret-memset` | Ordinary memset targets name-identified candidate secret storage | Distinguish initialization from optimization-resistant erasure |
| `native-thread-dispatch-review` | A known native thread/dispatch API is called | Review synchronous callback/thread-affinity contracts |
| `sqlite-disk-temp-storage` | A constant SQL string flowing to sqlite3_exec requests FILE/1 temporary storage | Determine connection confidentiality and verify both build and runtime storage policy |
| `aes/swift/unsafe-pointer-lifecycle` | An unsafe-pointer allocation, initialization, destruction, or rebinding operation appears | Review bridge isolation and the ownership/lifetime/cleanup contract |

Direct calls and function references have different C/C++ AST representations;
both are tested. Unrelated namespace methods, comments, string mentions,
bounded/suppressed scanf conversions, read-only sized key signatures, ordinary
non-secret initialization, and memory-backed SQLite temp storage are negative
fixtures. Discovery of a primitive is not a finding of undefined behavior.

### Interface matching and fortified builds

`isCInterface` (in `codeql/cpp/AesScope.qll`) matches the global or `std::`
interface by qualified name, never same-named class or namespace members. It
also accepts the checked and builtin forms a call can resolve to under
`_FORTIFY_SOURCE`: `__<name>_chk`, `__builtin___<name>_chk` and
`__builtin_<name>`. Results always report the canonical interface name.

With glibc and GCC, fortified calls still resolve to inline wrappers named after
the interface (in `string_fortified.h` and `stdio2.h`), and the `_chk` builtins
are called inside those system headers, which source selection excludes. Headers
that fortify with macros, such as Apple SDKs, rewrite the call site itself to
`__builtin___<name>_chk`; `policy/fortified.c` covers that form synthetically.

### Candidate secret names

`hasSensitiveName` is a name heuristic for `key-buffer-contract` and
`candidate-secret-memset`. A term (`key`, `secret`, `password`, `passwd`,
`passphrase`, optionally plural) must form its own word:

- snake_case, whole word or ALL_CAPS: `session_key`, `m_secret`, `KEY`, `secret_2`;
- camelCase, including after an acronym: `sessionKey`, `privateKeyBytes`, `APIKey`;
- a leading lowercase segment: `keyBytes`, `secretData`.

Word-bounded length, size, count, index and id companions are excluded
(`key_len`, `keyLen`, `keys_count`, `key_id`). Known limits:

- False negatives: names with no word boundary (`sessionkey`, `apikey`), secrets
  named without these terms (`token`, `nonce`, `seed`, `credential`, `pin`), and
  secrets reached through struct fields or aliases with neutral names.
- False positives: non-secret uses of the words, such as `HotKey`, `public_key`,
  `key_type` or `sort_keys`, and `secret_valid`-style flags.

The fixtures assert 18 names that must match and 8 that must not
(`keyboard`, `monkey`, `hotkey`, `secretary_note` and the companions above).
Treat results as review candidates, never as a secret inventory.

## Upstream analysis and limitations

The default `aes-security.qls` suites import exact upstream query-pack versions:

| Language | Library pack | Upstream query pack |
|---|---|---|
| C/C++ | `codeql/cpp-all@12.2.0` | `codeql/cpp-queries@1.9.1`, security-extended |
| Swift | `codeql/swift-all@6.8.5` | `codeql/swift-queries@1.3.12`, security-extended |

These versions match CodeQL CLI 2.27.2. The `aes-custom.qls` suites contain only
the additions above and are useful for focused validation. Library dependencies
are pinned in the pack manifests and dependency locks. Query-pack imports also
have exact version constraints. Update these together through reviewed changes.

Upstream analysis supplies additional memory, integer, lifetime, injection,
cryptographic, and sensitive-data checks. It still cannot prove every relevant
path safe or discharge a complete AES standard.

The custom source selection excludes conventional vendor/build directories and
`tests/fixtures`/`examples/fixtures`. Review that selection against actual ownership.
Directory names never approve unsafe wrappers or suppress waiver obligations.
The upstream queries have their own source models and may report additional files.
The authoritative governed-scope manifest, repository-wide adoption evidence, and
existing gates remain applicable. This implementation does not resolve governed
scope ownership or reconcile findings automatically with disposition ledgers.

Secret naming is heuristic. Dynamic SQL, arbitrary indirect calls, cross-language
flows, and whole-program lifetimes are incomplete. Swift extraction and query
tests require macOS; CI runs them on a GitHub-hosted macOS runner.
Objective-C/Objective-C++, assembly, target-only 65C816 code, and unsupported CUDA
surfaces require explicit complementary coverage; a C++ database does not attest
to them.

## Install and test

Install the official CodeQL CLI 2.27.2. The CI workflow verifies its downloaded
archive against an explicit platform SHA-256. GitHub's CodeQL licensing applies.

From the AEMS repository root:

```sh
codeql pack install codeql/cpp
codeql pack install tests/fixtures/codeql/cpp --additional-packs=codeql
codeql pack download codeql/cpp-queries@1.9.1
codeql query compile --check-only codeql/cpp/queries
codeql test run --threads=1 --additional-packs=codeql tests/fixtures/codeql/cpp
python3 -m unittest discover -s tests -p 'test_aes_codeql.py' -v
```

On macOS, additionally run:

```sh
codeql pack install codeql/swift
codeql pack install tests/fixtures/codeql/swift --additional-packs=codeql
codeql pack download codeql/swift-queries@1.3.12
codeql query compile --check-only codeql/swift/queries
codeql test run --threads=1 --additional-packs=codeql tests/fixtures/codeql/swift
```

### What CI checks

`.github/workflows/aes-codeql-tests.yml` runs a C/C++ job on Linux and a Swift
job on a GitHub-hosted macOS runner. Each job:

1. runs the unit tests for evidence, coverage and suite handling;
2. installs the checksum-verified CLI and the locked pack dependencies;
3. reads the upstream pack pin from `codeql/<language>/aes-security.qls` (the
   only place it is recorded), downloads it, and runs
   `scripts/resolve_aes_codeql_suite.py verify`, which fails unless every AES
   custom query and at least one upstream query appear in the resolved suite;
4. compiles the whole resolved default suite with `--check-only`;
5. runs the fixture query tests.

The C/C++ job also checks the source-pinned coverage catalog and runs the
real-header end-to-end test. `tests/fixtures/codeql/cpp-real-headers/real.c`
includes the system headers and is extracted twice, plain (`gcc -O0`) and
fortified (`gcc -O2 -D_FORTIFY_SOURCE=2`). `scripts/aes_codeql.py --custom-only`
runs on both databases, and `scripts/check_real_header_evidence.py` requires
`banned-interface` results for `strcpy`, `strcat`, `sprintf`, `vsprintf`,
`system`, `popen` and `atoi` (matched by exact interface name), plus
`candidate-secret-memset` and `discarded-snprintf-result`, in both. Both evidence
files are uploaded as the `aes-codeql-real-header-evidence` artifact. The
fixture's `--source-root` must stay at its own folder, because source selection
excludes `tests/fixtures/`.

To run the real-header test locally:

```sh
fixture=tests/fixtures/codeql/cpp-real-headers
for variant in plain fortify; do
  flags=-O0; [ "$variant" = fortify ] && flags='-O2 -D_FORTIFY_SOURCE=2'
  codeql database create "/tmp/db-$variant" --language=cpp --overwrite \
    --source-root "$fixture" --command="gcc $flags -c real.c -o /dev/null"
  python3 scripts/aes_codeql.py --database "/tmp/db-$variant" --language cpp \
    --repository dlworrell/AEMS --commit-sha "$(git rev-parse HEAD)" \
    --output-dir "/tmp/evidence-$variant" --custom-only
done
python3 scripts/check_real_header_evidence.py \
  plain="$(ls /tmp/evidence-plain/*.json)" fortify="$(ls /tmp/evidence-fortify/*.json)"
```

For offline/library-source validation, use the official `github/codeql` source
commit `a7057b836bf29767461026718b14d20790b9085f` (CLI v2.27.2), including the
language libraries, query sources, `shared`, and `misc/suite-helpers`. Add that
checkout to `--additional-packs`, alongside `codeql`. Record its revision and
dirty state with the validation evidence. Registry-based dependency locks are
the normal distribution mechanism; source overrides must be recorded explicitly.

## Analyze a governed repository

Create the database from a clean checkout of the exact implementation commit,
using the actual target toolchain and build options. Database construction is
repository-owned: it can execute build code and belongs on a suitably isolated
runner. For example, after configuring a repository's supported host build:

```sh
codeql database create build/codeql/cpp --language=cpp --source-root=. \
  --command='cmake --build build/host --clean-first'
```

Then use the AEMS runner, supplying the commit used during extraction:

```sh
python3 /path/to/AEMS/scripts/aes_codeql.py \
  --database build/codeql/cpp --language cpp \
  --repository owner/repository --commit-sha FULL_EXTRACTION_COMMIT_SHA \
  --output-dir build/aes-codeql-evidence
```

Use `--language swift` with an independently extracted Swift database on macOS.
Use `--custom-only` only when deliberately omitting upstream analysis; the evidence
records that narrower profile. `--additional-packs` supports a recorded local
official library checkout.

The runner preserves fresh SARIF and JSON for each attempt, records CodeQL version,
scanner revision/dirty state, standard/source digests, and query/pack-source hashes.
The subject commit is explicitly caller-asserted: an existing database does not
independently prove that it came from the supplied Git revision. Keep extraction
logs and checkout provenance with the report. Source overrides and platform
toolchain identity belong in the same evidence bundle.

Completion is `completed-no-findings` or `completed-with-findings`. Missing tools,
timeouts, malformed/partial SARIF, missing custom-query metadata, or unsuccessful
invocations return an operational error and `failed` evidence. Suppressed and
baselined findings remain visible. Every report records
`standards_compliance: NOT_ESTABLISHED` and complementary evidence as unevaluated.
Exit zero means analysis completed; it is not a security acceptance gate.

## Complementary obligations

Continue existing AES-SEC-001/002 adoption, boundary, disposition, and waiver checks.
Supply applicable warning-clean builds, ASan/UBSan/TSan results, parser fuzzing,
Swift 6 complete-concurrency compilation, thread-identity and lifecycle tests,
wrong-key/integrity/failure/restore tests, dependency and provenance review,
tracked-file/private-data checks, release artifact inspection, and threat-model
review. Secret erasure and key-store properties require target-specific evidence.
History-migration authorization remains a separate governance obligation.

The workflow added here validates the query implementation and its synthetic
fixtures on Linux/macOS. It does not enroll downstream repositories, upload
production findings, change merge protection, or grant scanner administration.

## Maintain coverage

To regenerate the source-pinned catalog from a local AES Git checkout:

```sh
python3 scripts/update_aes_codeql_coverage.py --aes-repository /path/to/AES
python3 scripts/update_aes_codeql_coverage.py --aes-repository /path/to/AES --check
```

To adopt another AES revision, pass its full SHA with `--aes-revision`, review all
changed clauses and query mappings, and update tests and validation evidence in
the same change. Stable normative IDs should originate in AES; source locators
remain implementation traceability until such IDs are adopted.

## References

- [AES-SEC-001](https://github.com/dlworrell/AES/blob/256bf6dd0e424b134d4f1c628f9aff30ea12566d/standards/AES-SEC-001-secure-c-cpp-coding-rules.md)
- [AES-SEC-002](https://github.com/dlworrell/AES/blob/256bf6dd0e424b134d4f1c628f9aff30ea12566d/standards/AES-SEC-002-cross-language-secret-storage-boundaries.md)
- [CodeQL query suites](https://docs.github.com/en/code-security/tutorials/customize-code-scanning/create-query-suites)
- [Testing custom queries](https://docs.github.com/en/code-security/how-tos/find-and-fix-code-vulnerabilities/scan-from-the-command-line/test-custom-queries)
- [Supported languages and frameworks](https://codeql.github.com/docs/codeql-overview/supported-languages-and-frameworks/)
