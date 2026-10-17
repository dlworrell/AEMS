/**
 * @name Review memset on candidate secret storage
 * @description Supplemental AES-SEC-002 source analysis; see the pinned control coverage catalog for limitations and required complementary evidence.
 * @kind problem
 * @problem.severity warning
 * @precision medium
 * @id aes/cpp/candidate-secret-memset
 * @tags security
 *       aes-sec-002
 *       external/cwe/cwe-14
 */
import cpp
import semmle.code.cpp.dataflow.new.DataFlow
import AesScope

from VariableAccess access, FunctionCall call
where
  hasSensitiveName(access.getTarget().getName()) and
  isCInterface(call.getTarget(), "memset") and isAesSource(call) and
  DataFlow::localFlow(DataFlow::exprNode(access), DataFlow::exprNode(call.getArgument(0)))
select call, "AES-SEC-002: review memset on name-identified candidate secret storage. Ordinary initialization is allowed; erasure needs an admitted optimization-resistant primitive. This does not prove storage is secret or that clearing is absent."
