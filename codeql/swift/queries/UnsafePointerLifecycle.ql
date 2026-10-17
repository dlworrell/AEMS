/**
 * @name Review Swift unsafe-pointer lifecycle operations
 * @description Pointer allocation, destruction, and rebinding require a reviewed bridge and explicit ownership.
 * @kind problem
 * @problem.severity warning
 * @precision medium
 * @id aes/swift/unsafe-pointer-lifecycle
 * @tags security
 *       aes-sec-002
 *       external/cwe/cwe-664
 */
import swift
import AesPointer

from ApplyExpr call
where aesUnsafePointerOperation(call, _)
select call,
  "AES-SEC-002: review this unsafe-pointer operation for bridge isolation, ownership, lifetime, and paired cleanup. This finding does not establish a lifecycle violation."
