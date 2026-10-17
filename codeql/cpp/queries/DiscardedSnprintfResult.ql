/**
 * @name Review unchecked bounded-formatting truncation
 * @description Supplemental AES-SEC-001 source analysis; see the pinned control coverage catalog for limitations and required complementary evidence.
 * @kind problem
 * @problem.severity warning
 * @precision high
 * @id aes/cpp/discarded-snprintf-result
 * @tags security
 *       aes-sec-001
 *       external/cwe/cwe-252
 */
import cpp
import AesScope

from FunctionCall call, ExprStmt statement, string name
where
  name = ["snprintf", "vsnprintf"] and isCInterface(call.getTarget(), name) and
  statement.getExpr() = call.getParentWithConversions*() and isAesSource(call)
select call, "AES-SEC-001: the formatting return value is discarded. Check for errors/truncation when they affect correctness or security; document intentional bounded initialization."
