cmake_minimum_required(VERSION 3.20)
project(aes_fixture_app VERSION 1.0.0 LANGUAGES C)

include(CTest)
include(GNUInstallDirs)

option(AES_FIXTURE_WARNINGS_AS_ERRORS "Treat project warnings as errors" ON)
option(AES_FIXTURE_ENABLE_SANITIZERS "Enable AddressSanitizer and UBSan" OFF)

add_library(aes_fixture_app_core STATIC src/app.c)
target_compile_features(aes_fixture_app_core PUBLIC c_std_17)
target_include_directories(
  aes_fixture_app_core
  PUBLIC
    "${CMAKE_CURRENT_SOURCE_DIR}/include"
)
target_compile_options(
  aes_fixture_app_core
  PRIVATE
    -Wall
    -Wextra
    -Wpedantic
    -Wconversion
    -Wsign-conversion
    -Wshadow
)
if(AES_FIXTURE_WARNINGS_AS_ERRORS)
  target_compile_options(aes_fixture_app_core PRIVATE -Werror)
endif()
if(AES_FIXTURE_ENABLE_SANITIZERS)
  target_compile_options(
    aes_fixture_app_core
    PRIVATE
      -fsanitize=address,undefined
      -fno-omit-frame-pointer
  )
  target_link_options(
    aes_fixture_app_core
    PRIVATE
      -fsanitize=address,undefined
  )
endif()

add_executable(aes_fixture_app src/main.c)
target_link_libraries(aes_fixture_app PRIVATE aes_fixture_app_core)
target_compile_features(aes_fixture_app PRIVATE c_std_17)
target_compile_options(
  aes_fixture_app
  PRIVATE
    -Wall
    -Wextra
    -Wpedantic
    -Wconversion
    -Wsign-conversion
    -Wshadow
)
if(AES_FIXTURE_WARNINGS_AS_ERRORS)
  target_compile_options(aes_fixture_app PRIVATE -Werror)
endif()
if(AES_FIXTURE_ENABLE_SANITIZERS)
  target_compile_options(
    aes_fixture_app
    PRIVATE
      -fsanitize=address,undefined
      -fno-omit-frame-pointer
  )
  target_link_options(
    aes_fixture_app
    PRIVATE
      -fsanitize=address,undefined
  )
endif()

if(BUILD_TESTING)
  add_executable(aes_fixture_app_test tests/test_app.c)
  target_link_libraries(
    aes_fixture_app_test
    PRIVATE
      aes_fixture_app_core
  )
  target_compile_features(aes_fixture_app_test PRIVATE c_std_17)
  target_compile_options(
    aes_fixture_app_test
    PRIVATE
      -Wall
      -Wextra
      -Wpedantic
      -Wconversion
      -Wsign-conversion
      -Wshadow
  )
  if(AES_FIXTURE_WARNINGS_AS_ERRORS)
    target_compile_options(aes_fixture_app_test PRIVATE -Werror)
  endif()
  if(AES_FIXTURE_ENABLE_SANITIZERS)
    target_compile_options(
      aes_fixture_app_test
      PRIVATE
        -fsanitize=address,undefined
        -fno-omit-frame-pointer
    )
    target_link_options(
      aes_fixture_app_test
      PRIVATE
        -fsanitize=address,undefined
    )
  endif()
  add_test(NAME aes_fixture_app_test COMMAND aes_fixture_app_test)
endif()

install(
  TARGETS aes_fixture_app
  RUNTIME DESTINATION "${CMAKE_INSTALL_BINDIR}"
)
