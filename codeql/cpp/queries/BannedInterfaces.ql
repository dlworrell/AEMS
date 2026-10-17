/**
 * @name Use of an AES-banned C interface
 * @description Supplemental AES-SEC-001 source analysis; see the pinned control coverage catalog for limitations and required complementary evidence.
 * @kind problem
 * @problem.severity error
 * @precision high
 * @id aes/cpp/banned-interface
 * @tags security
 *       aes-sec-001
 *       external/cwe/cwe-676
 */
import cpp
import AesScope

from Expr access, Function target, string name
where
  (target = access.(FunctionCall).getTarget() or target = access.(FunctionAccess).getTarget()) and
  name = ["gets", "strcpy", "strcat", "sprintf", "vsprintf", "atoi", "atol", "atoll", "tmpnam", "mktemp", "system", "popen"] and
  isCInterface(target, name) and isAesSource(access)
select access, "AES-SEC-001: " + name + " is banned outside an explicitly approved exception. Replace it or record the required scope-specific waiver. Function-pointer references also require review."
