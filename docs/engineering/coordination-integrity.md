# Coordination record integrity (pilot)

`scripts/coordination_integrity.py` builds and checks an offline sha256
manifest for a directory of coordination records, such as the Dropbox overlay
that Em coordinates. Em and Claude Code proposed this pilot on 30–31 October
2026, and the owner approved it on 31 October. It runs only on local files: it
needs no network access, no credentials and no model.

## Commands

```sh
# First manifest of a records directory (written outside it). Prints its digest.
python3 scripts/coordination_integrity.py build RECORDS --output m1.json

# Next manifest, chained to the previous one.
python3 scripts/coordination_integrity.py build RECORDS --predecessor m1.json --output m2.json

# Check the records against a manifest.
python3 scripts/coordination_integrity.py verify RECORDS --manifest m2.json \
  --expected-predecessor <digest of m1.json, or genesis> --anchor <trusted digest of m2.json>
```

`verify` exits with 0 for `verified`, 1 for `unverified`, 3 for `rejected` and
2 for unusable input (a missing or symlinked records directory, or an
unreadable manifest). `--format markdown` prints a short report instead of JSON.

## What it checks

- **Files:** every regular file under the directory is listed with its path,
  sha256, size, and the file's own `id` when it is a JSON object with one.
  Paths are sorted, so a manifest of unchanged records is byte-identical.
- **Rejected:**
  - a changed, missing or extra file;
  - a duplicate path or duplicate record id;
  - an absolute path or a path containing `..` or a backslash;
  - a symlink or other non-regular file;
  - a predecessor that differs from the expected previous manifest;
  - a manifest digest that differs from the trusted anchor.
- **Also rejected:** a malformed manifest field (sha256, size or record id), and
  a listed record id that differs from the `id` in the file itself, and a file
  whose `id` is an empty string (refused by `build` too).
- **Unverified:** everything matches, but no trusted anchor was given, or no
  expected predecessor was given so the chain was not checked. The report's
  `anchor_checked` and `chain_checked` fields say which.
- **Verified:** everything matches, the manifest's digest equals an anchor read
  from somewhere the records' writers cannot change, and its predecessor equals
  the expected previous manifest.

The records directory itself must not be a symlink, for `build` and `verify`
alike. Directories above it may be symlinks, as system paths often are.

## What it does not show

A matching anchor shows the records equal that manifest, not that the manifest
is the latest one. Record identity is the file's own top-level `id` only;
other fields such as `event_id` are not read until the coordinator's record
schema is agreed. Matching hashes do not show who wrote a record, that anyone authorized it, or
that the work it describes happened. An integrity result is not task status,
engineering closure or owner approval. Where anchors are kept, and the record
schema itself, are decided separately. The schema belongs to the coordinator;
this tool only checks the files.
