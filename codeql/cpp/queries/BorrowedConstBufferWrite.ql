/**
 * @name Write through a borrowed const pointer
 * @description Supplemental AES-SEC-002 source analysis; see the pinned control coverage catalog for limitations and required complementary evidence.
 * @kind problem
 * @problem.severity warning
 * @precision high
 * @id aes/cpp/borrowed-const-buffer-write
 * @tags security
 *       aes-sec-002
 *       external/cwe/cwe-758
 */
import cpp
import semmle.code.cpp.dataflow.new.DataFlow
import AesScope

from Parameter parameter, PointerType pointer, VariableAccess access, FunctionCall call, string name
where
  pointer = parameter.getType().getUnderlyingType() and pointer.getBaseType().isConst() and
  access.getTarget() = parameter and
  name = ["memset", "memset_s", "explicit_bzero", "bzero", "memcpy", "memmove", "strcpy", "strncpy"] and
  isCInterface(call.getTarget(), name) and isAesSource(call) and
  DataFlow::localFlow(DataFlow::exprNode(access), DataFlow::exprNode(call.getArgument(0)))
select call, "AES-SEC-002: this write destination flows from a borrowed const pointer. Do not erase or mutate caller-owned const storage. Review ownership and use project-owned mutable storage."
