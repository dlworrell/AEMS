# AES-SEC-001 Make control preset.
#
# Include explicitly from a repository-owned Makefile and apply these variables
# only to project-owned code and supported host tests.

AES_SEC_001_WARNINGS := -Wall -Wextra -Wpedantic -Werror=return-type
AES_SEC_001_C_WARNINGS := \
	-Werror=implicit-function-declaration \
	-Werror=incompatible-pointer-types
AES_SEC_001_SANITIZERS := \
	-fsanitize=address,undefined \
	-fno-omit-frame-pointer

.PHONY: aes-sec-001-help
aes-sec-001-help:
	@printf '%s\n' \
		"AES_SEC_001_WARNINGS=$(AES_SEC_001_WARNINGS)" \
		"AES_SEC_001_C_WARNINGS=$(AES_SEC_001_C_WARNINGS)" \
		"AES_SEC_001_SANITIZERS=$(AES_SEC_001_SANITIZERS)"
