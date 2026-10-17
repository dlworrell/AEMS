/**
 * @name Review a candidate key-buffer contract
 * @description Supplemental AES-SEC-002 source analysis; see the pinned control coverage catalog for limitations and required complementary evidence.
 * @kind problem
 * @problem.severity warning
 * @precision medium
 * @id aes/cpp/key-buffer-contract
 * @tags security
 *       aes-sec-002
 *       external/cwe/cwe-20
 */
import cpp
import AesScope

from Parameter parameter, PointerType pointer
where
  pointer = parameter.getType().getUnderlyingType() and
  hasSensitiveName(parameter.getName()) and isAesSource(parameter) and
  (
    not pointer.getBaseType().isConst()
    or not exists(Parameter length |
      length = parameter.getFunction().getAParameter() and
      length.getName().regexpMatch("(?i)(.*_)?(len|length|size)") and
      length.getType().getUnspecifiedType() instanceof IntegralType
    )
  )
select parameter, "AES-SEC-002: review this name-identified candidate secret input for read-only bytes and an explicit byte length. Internal owned mutable storage can be legitimate; parameter names are not a complete secret inventory."
