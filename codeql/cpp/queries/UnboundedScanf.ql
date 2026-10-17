/**
 * @name Unbounded scanf string conversion
 * @description Supplemental AES-SEC-001 source analysis; see the pinned control coverage catalog for limitations and required complementary evidence.
 * @kind problem
 * @problem.severity error
 * @precision high
 * @id aes/cpp/unbounded-scanf-string
 * @tags security
 *       aes-sec-001
 *       external/cwe/cwe-120
 */
import cpp
import semmle.code.cpp.commons.Scanf
import AesScope

from ScanfFormatLiteral format, int index
where
  isAesSource(format.getUse()) and
  format.getConversionChar(index).toLowerCase() = "s" and
  format.getMaxWidthOpt(index) = "" and
  not format.getUse().getScanfFunction().isSVariant()
select format.getUse(), "AES-SEC-001: this scanf-family string conversion has no field width. Bound input and verify the bound against the destination capacity."
