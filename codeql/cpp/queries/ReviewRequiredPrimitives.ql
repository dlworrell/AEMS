/**
 * @name Review an unsafe native primitive
 * @description Supplemental AES-SEC-001 source analysis; see the pinned control coverage catalog for limitations and required complementary evidence.
 * @kind problem
 * @problem.severity warning
 * @precision high
 * @id aes/cpp/review-required-primitive
 * @tags security
 *       aes-sec-001
 *       external/cwe/cwe-664
 */
import cpp
import AesScope

from Expr operation, string name
where
  isAesSource(operation) and
  (
    exists(Function target |
      (operation.(FunctionAccess).getTarget() = target or operation.(FunctionCall).getTarget() = target) and
      name = ["memcpy", "memmove", "strncpy", "snprintf", "malloc", "calloc", "realloc", "free"] and
      isCInterface(target, name)
    )
    or operation instanceof NewOrNewArrayExpr and name = "new"
    or operation instanceof DeleteOrDeleteArrayExpr and name = "delete"
    or operation instanceof ReinterpretCast and name = "reinterpret_cast"
    or operation instanceof ConstCast and name = "const_cast"
  )
select operation, "AES-SEC-001: " + name + " requires a reviewed invariant and approved wrapper or scope-specific disposition/waiver. A directory name alone does not approve this operation."
