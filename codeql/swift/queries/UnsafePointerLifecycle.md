# Review Swift unsafe-pointer lifecycle operations

AES-SEC-002 requires reviewed bridge isolation, ownership, lifetime, and cleanup
contracts. This query inventories allocation, initialization, destruction, and
rebinding operations on Swift unsafe-pointer types. An ordinary same-named
method on another type is not a finding.

Every result requires review against the local boundary profile. A call is not
automatically an ownership violation, and a zero-result scan does not establish
that raw-pointer escapes, C callbacks, or unchecked concurrency are safe.

Run Swift 6 complete-concurrency compilation, lifecycle/failure tests, relevant
sanitizers, and the existing AES-SEC-002 boundary scanner as complementary checks.
