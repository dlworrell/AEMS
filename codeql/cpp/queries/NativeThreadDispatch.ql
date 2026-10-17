/**
 * @name Review native asynchronous dispatch at callback boundaries
 * @description Supplemental AES-SEC-002 source analysis; see the pinned control coverage catalog for limitations and required complementary evidence.
 * @kind problem
 * @problem.severity warning
 * @precision high
 * @id aes/cpp/native-thread-dispatch-review
 * @tags security
 *       aes-sec-002
 *       external/cwe/cwe-362
 */
import cpp
import AesScope

from FunctionCall call, string name
where
  name = ["pthread_create", "thrd_create", "CreateThread", "_beginthread", "_beginthreadex", "dispatch_async", "dispatch_async_f"] and
  isCInterface(call.getTarget(), name) and isAesSource(call)
select call, "AES-SEC-002: review this native thread/dispatch entry against callback synchrony, thread-affinity, executor, and lifetime contracts. Asynchronous work is not inherently prohibited."
