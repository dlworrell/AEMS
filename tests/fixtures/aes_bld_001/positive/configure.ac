AC_PREREQ([2.69])
AC_INIT([aes-fixture], [1.0.0], [https://github.com/dlworrell/AEMS/issues])
AC_CONFIG_SRCDIR([src/fixture.c])
AC_CONFIG_AUX_DIR([build-aux])
AC_CONFIG_MACRO_DIRS([m4])
AM_INIT_AUTOMAKE([foreign subdir-objects parallel-tests color-tests])
AC_PROG_CC
AM_PROG_AR
LT_INIT([disable-shared])

AC_ARG_ENABLE(
  [warnings-as-errors],
  [AS_HELP_STRING(
    [--disable-warnings-as-errors],
    [do not promote project warnings to errors]
  )],
  [],
  [enable_warnings_as_errors=yes]
)
AM_CONDITIONAL(
  [WARNINGS_AS_ERRORS],
  [test "x$enable_warnings_as_errors" = "xyes"]
)

AC_CONFIG_FILES([Makefile aes-fixture.pc])
AC_OUTPUT
