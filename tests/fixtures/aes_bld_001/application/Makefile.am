ACLOCAL_AMFLAGS = -I m4

AM_CPPFLAGS = -I$(top_srcdir)/include
AM_CFLAGS = -std=c17 -Wall -Wextra -Wpedantic -Wconversion \
	-Wsign-conversion -Wshadow
if WARNINGS_AS_ERRORS
AM_CFLAGS += -Werror
endif

bin_PROGRAMS = aes_fixture_app
aes_fixture_app_SOURCES = src/main.c src/app.c

check_PROGRAMS = tests/aes_fixture_app_test
tests_aes_fixture_app_test_SOURCES = tests/test_app.c src/app.c
TESTS = $(check_PROGRAMS)

EXTRA_DIST = \
	.aems/aes-bld-001.json \
	.aems/aes-bld-001-waivers.json \
	.clang-tidy \
	.github/workflows/aes-bld-001.yml \
	CMakeLists.txt \
	CMakePresets.json \
	build-aux/.gitkeep \
	docs/engineering/AES-BLD-001-toolchain-profile.md \
	include/aes_fixture_app/app.h \
	m4/.gitkeep
