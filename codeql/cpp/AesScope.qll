/** Project-owned source selection. Paths do not approve unsafe operations or waive findings. */
import cpp

predicate isAesSource(Locatable element) {
  element.getFile().getRelativePath() != "" and
  not element.getFile().getRelativePath().regexpMatch(
    "(^|.*/)(vendor|third_party|third-party|node_modules|build|dist)/.*"
  ) and
  not element.getFile().getRelativePath().regexpMatch(
    "(^|.*/)(tests|examples)/fixtures/.*"
  )
}

/** Match the global/standard API, not unrelated same-named class/namespace methods. */
bindingset[name]
predicate isCInterface(Function function, string name) {
  function.getQualifiedName() = [name, "std::" + name]
}

/**
 * Name-based candidates only; this is not a classification of every secret.
 * A sensitive term (optionally plural) must form its own word: bounded by the
 * start or end of the name, '_' or a digit, or a camelCase boundary. Length,
 * size, count, index and id companions are metadata and are excluded.
 */
bindingset[name]
predicate hasSensitiveName(string name) {
  exists(string term |
    term = ["key", "secret", "password", "passwd", "passphrase"]
  |
    // snake_case, whole word or ALL_CAPS: session_key, m_secret, KEY, secret_2
    name.toLowerCase().regexpMatch("(.*[_0-9])?" + term + "s?([_0-9].*)?")
    or
    // camelCase segment, including after an acronym: sessionKey, APIKey, privateKeyBytes
    name.regexpMatch("(.*[a-zA-Z0-9])?" + term.charAt(0).toUpperCase() + term.suffix(1) +
        "s?([A-Z0-9_].*)?")
    or
    // leading lowercase segment followed by camelCase: keyBytes, secretData
    name.regexpMatch(term + "s?[A-Z0-9].*")
  ) and
  not name.toLowerCase().regexpMatch(".*_(len|length|size|count|cnt|idx|index|id)") and
  not name.regexpMatch(".*(Len|Length|Size|Count|Cnt|Idx|Index|Id)")
}
