ACLOCAL_AMFLAGS = -I m4

AM_CPPFLAGS = -I$(top_srcdir)/include
AM_CFLAGS = -std=c17 -Wall -Wextra -Wpedantic -Wconversion \
	-Wsign-conversion -Wshadow
if WARNINGS_AS_ERRORS
AM_CFLAGS += -Werror
endif

lib_LTLIBRARIES = libaes_fixture.la
libaes_fixture_la_SOURCES = src/fixture.c
libaes_fixture_la_LDFLAGS = -version-info 1:0:0 -no-undefined

aesfixtureincludedir = $(includedir)/aes_fixture
aesfixtureinclude_HEADERS = include/aes_fixture/fixture.h

check_PROGRAMS = tests/aes_fixture_test
tests_aes_fixture_test_SOURCES = tests/test_fixture.c
tests_aes_fixture_test_LDADD = libaes_fixture.la
TESTS = $(check_PROGRAMS)

pkgconfigdir = $(libdir)/pkgconfig
pkgconfig_DATA = aes-fixture.pc

EXTRA_DIST = \
	.aems/aes-bld-001.json \
	.aems/aes-bld-001-waivers.json \
	.clang-tidy \
	.github/workflows/aes-bld-001.yml \
	CMakeLists.txt \
	CMakePresets.json \
	aes-fixture.pc.in \
	build-aux/.gitkeep \
	consumer/consumer.c \
	docs/engineering/AES-BLD-001-toolchain-profile.md \
	m4/.gitkeep
