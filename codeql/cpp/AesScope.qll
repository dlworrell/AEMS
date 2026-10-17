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

/** Name-based candidates only; this is not a classification of every secret. */
bindingset[name]
predicate hasSensitiveName(string name) {
  name.regexpMatch(
    "(?i)(key|key_bytes|secret|secret_bytes|password|recovery_key|derived_key|private_key)(_[0-9]+)?"
  )
}
