import swift

/** Inventory candidates; approval requires the repository's reviewed bridge contract. */
predicate aesUnsafePointerOperation(ApplyExpr call, string operation) {
  exists(Callable target |
    target = call.getStaticTarget() and
    operation = target.getName().regexpCapture("^([^(:]+).*", 1) and
    operation = ["allocate", "deallocate", "initialize", "deinitialize", "move", "bindMemory", "withMemoryRebound"] and
    target.(Decl).getEnclosingDecl().asNominalTypeDecl().getFullName().matches("%Unsafe%Pointer%")
  ) and
  call.getFile().getRelativePath() != "" and
  not call.getFile().getRelativePath().regexpMatch(
    "(^|.*/)(vendor|third_party|third-party|build|dist)/.*"
  ) and
  not call.getFile().getRelativePath().regexpMatch("(^|.*/)(tests|examples)/fixtures/.*")
}
