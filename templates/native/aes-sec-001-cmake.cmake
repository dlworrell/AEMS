# AES-SEC-001 CMake control preset.
#
# Include this file from a repository-owned CMakeLists.txt after declaring the
# project. The repository remains responsible for attaching
# aes_sec_001_warnings and aes_sec_001_sanitizers to appropriate targets.

add_library(aes_sec_001_warnings INTERFACE)
target_compile_options(
  aes_sec_001_warnings
  INTERFACE
    $<$<C_COMPILER_ID:GNU,Clang>:-Wall;-Wextra;-Wpedantic;-Werror=return-type>
    $<$<CXX_COMPILER_ID:GNU,Clang>:-Wall;-Wextra;-Wpedantic;-Werror=return-type;-Wnon-virtual-dtor>
    $<$<CXX_COMPILER_ID:MSVC>:/W4;/permissive->
)

option(AES_SEC_001_ENABLE_SANITIZERS "Enable supported AES-SEC-001 test sanitizers" OFF)
add_library(aes_sec_001_sanitizers INTERFACE)
if(AES_SEC_001_ENABLE_SANITIZERS AND CMAKE_C_COMPILER_ID MATCHES "GNU|Clang")
  target_compile_options(
    aes_sec_001_sanitizers
    INTERFACE -fsanitize=address,undefined -fno-omit-frame-pointer
  )
  target_link_options(
    aes_sec_001_sanitizers
    INTERFACE -fsanitize=address,undefined
  )
endif()
