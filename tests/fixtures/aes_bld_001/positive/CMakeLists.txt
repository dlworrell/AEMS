cmake_minimum_required(VERSION 3.20)
project(aes_fixture VERSION 1.0.0 LANGUAGES C)

include(CTest)
include(GNUInstallDirs)

option(AES_FIXTURE_WARNINGS_AS_ERRORS "Treat project warnings as errors" ON)
option(AES_FIXTURE_ENABLE_SANITIZERS "Enable AddressSanitizer and UBSan" OFF)

add_library(aes_fixture STATIC src/fixture.c)
add_library(aes_fixture::aes_fixture ALIAS aes_fixture)
target_compile_features(aes_fixture PUBLIC c_std_17)
target_include_directories(
  aes_fixture
  PUBLIC
    "$<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>"
    "$<INSTALL_INTERFACE:${CMAKE_INSTALL_INCLUDEDIR}>"
)
target_compile_options(
  aes_fixture
  PRIVATE
    -Wall
    -Wextra
    -Wpedantic
    -Wconversion
    -Wsign-conversion
    -Wshadow
)
if(AES_FIXTURE_WARNINGS_AS_ERRORS)
  target_compile_options(aes_fixture PRIVATE -Werror)
endif()
if(AES_FIXTURE_ENABLE_SANITIZERS)
  target_compile_options(
    aes_fixture
    PRIVATE
      -fsanitize=address,undefined
      -fno-omit-frame-pointer
  )
  target_link_options(aes_fixture PRIVATE -fsanitize=address,undefined)
endif()

if(BUILD_TESTING)
  add_executable(aes_fixture_test tests/test_fixture.c)
  target_link_libraries(aes_fixture_test PRIVATE aes_fixture)
  target_compile_options(
    aes_fixture_test
    PRIVATE
      -Wall
      -Wextra
      -Wpedantic
      -Wconversion
      -Wsign-conversion
      -Wshadow
  )
  if(AES_FIXTURE_WARNINGS_AS_ERRORS)
    target_compile_options(aes_fixture_test PRIVATE -Werror)
  endif()
  if(AES_FIXTURE_ENABLE_SANITIZERS)
    target_compile_options(
      aes_fixture_test
      PRIVATE
        -fsanitize=address,undefined
        -fno-omit-frame-pointer
    )
    target_link_options(
      aes_fixture_test
      PRIVATE
        -fsanitize=address,undefined
    )
  endif()
  add_test(NAME aes_fixture_test COMMAND aes_fixture_test)
endif()

set(prefix "${CMAKE_INSTALL_PREFIX}")
set(exec_prefix "\${prefix}")
set(libdir "\${exec_prefix}/${CMAKE_INSTALL_LIBDIR}")
set(includedir "\${prefix}/${CMAKE_INSTALL_INCLUDEDIR}")
set(PACKAGE_VERSION "${PROJECT_VERSION}")
configure_file(
  aes-fixture.pc.in
  "${CMAKE_CURRENT_BINARY_DIR}/aes-fixture.pc"
  @ONLY
)

install(
  TARGETS aes_fixture
  EXPORT aes_fixture_targets
  ARCHIVE DESTINATION "${CMAKE_INSTALL_LIBDIR}"
)
install(
  FILES include/aes_fixture/fixture.h
  DESTINATION "${CMAKE_INSTALL_INCLUDEDIR}/aes_fixture"
)
install(
  FILES "${CMAKE_CURRENT_BINARY_DIR}/aes-fixture.pc"
  DESTINATION "${CMAKE_INSTALL_LIBDIR}/pkgconfig"
)
