/**
 * @name Review SQLite disk-backed temporary storage
 * @description Supplemental AES-SEC-002 source analysis; see the pinned control coverage catalog for limitations and required complementary evidence.
 * @kind problem
 * @problem.severity warning
 * @precision high
 * @id aes/cpp/sqlite-disk-temp-storage
 * @tags security
 *       aes-sec-002
 *       external/cwe/cwe-312
 */
import cpp
import semmle.code.cpp.dataflow.new.DataFlow
import AesScope

from FunctionCall call, StringLiteral sql
where
  isCInterface(call.getTarget(), "sqlite3_exec") and isAesSource(call) and
  DataFlow::localFlow(DataFlow::exprNode(sql), DataFlow::exprNode(call.getArgument(1))) and
  sql.getValue().regexpMatch("(?is)\\s*pragma\\s+(?:[a-zA-Z_][a-zA-Z_0-9]*\\.)?temp_store\\s*(?:=\\s*|\\(\\s*)(?:file|1)\\s*(?:[;)]|$).*" )
select call, "AES-SEC-002: this SQLite command requests file-backed temporary storage. For confidential connections, enforce encrypted or in-memory temporary state after keying and before protected access; review the dependency build too."
