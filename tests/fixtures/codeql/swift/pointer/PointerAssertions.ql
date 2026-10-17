import swift
import AesPointer

from ApplyExpr call, string operation
where aesUnsafePointerOperation(call, operation)
select call.getLocation().getStartLine(), operation
