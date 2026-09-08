cmake_minimum_required(VERSION 3.16)
project(vcc_biasing_stt
        VERSION 0.2.0
        DESCRIPTION "On-device STT with contextual biasing for non-native English"
        LANGUAGES CXX)

# ---------------------------------------------------------------------------
# Options
# ---------------------------------------------------------------------------
option(VCC_BUILD_TESTS      "Build the unit tests"                  ON)
option(VCC_BUILD_ENGINE     "Build the HTTP engine the PyQt5 dashboard drives" ON)
option(VCC_WARNINGS_AS_ERRORS "Treat compiler warnings as errors"   OFF)

# Where the prebuilt sherpa-onnx lives. Layout expected:
#   <dir>/include/sherpa-onnx/c-api/c-api.h
#   <dir>/lib/{sherpa-onnx-c-api.lib|libsherpa-onnx-c-api.so, onnxruntime.*}
set(SHERPA_ONNX_DIR "${CMAKE_SOURCE_DIR}/third_party/sherpa-onnx"
    CACHE PATH "Prebuilt sherpa-onnx root (see scripts/fetch_sherpa_onnx.sh)")

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

if(NOT CMAKE_BUILD_TYPE AND NOT CMAKE_CONFIGURATION_TYPES)
  set(CMAKE_BUILD_TYPE Release CACHE STRING "" FORCE)
endif()

# Binaries land in build/bin next to the DLLs they need, so they run without
# anyone having to fix up PATH.
set(CMAKE_RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/bin")
foreach(cfg Debug Release RelWithDebInfo MinSizeRel)
  string(TOUPPER "${cfg}" CFG)
  set(CMAKE_RUNTIME_OUTPUT_DIRECTORY_${CFG} "${CMAKE_BINARY_DIR}/bin")
endforeach()

# ---------------------------------------------------------------------------
# sherpa-onnx
# ---------------------------------------------------------------------------
set(SHERPA_INCLUDE_DIR "${SHERPA_ONNX_DIR}/include")
set(SHERPA_LIB_DIR "${SHERPA_ONNX_DIR}/lib")

if(NOT EXISTS "${SHERPA_INCLUDE_DIR}/sherpa-onnx/c-api/c-api.h")
  message(FATAL_ERROR
    "sherpa-onnx headers not found under ${SHERPA_INCLUDE_DIR}.\n"
    "Run:  bash scripts/fetch_sherpa_onnx.sh\n"
    "or point -DSHERPA_ONNX_DIR=<path> at an existing install.")
endif()

find_library(SHERPA_C_API_LIB
  NAMES sherpa-onnx-c-api libsherpa-onnx-c-api
  PATHS "${SHERPA_LIB_DIR}"
  NO_DEFAULT_PATH)
if(NOT SHERPA_C_API_LIB)
  message(FATAL_ERROR
    "sherpa-onnx-c-api library not found in ${SHERPA_LIB_DIR}.\n"
    "Run:  bash scripts/fetch_sherpa_onnx.sh")
endif()

add_library(sherpa_onnx_c INTERFACE)
target_include_directories(sherpa_onnx_c INTERFACE "${SHERPA_INCLUDE_DIR}")
target_link_libraries(sherpa_onnx_c INTERFACE "${SHERPA_C_API_LIB}")

# A static sherpa build needs onnxruntime (and the C++ runtime bits) spelled
# out; a shared build already carries them. Link it when it is there either way.
find_library(SHERPA_ONNXRUNTIME_LIB
  NAMES onnxruntime libonnxruntime
  PATHS "${SHERPA_LIB_DIR}"
  NO_DEFAULT_PATH)
if(SHERPA_ONNXRUNTIME_LIB)
  target_link_libraries(sherpa_onnx_c INTERFACE "${SHERPA_ONNXRUNTIME_LIB}")
endif()

# ---------------------------------------------------------------------------
# Core library
# ---------------------------------------------------------------------------
add_library(vcc_core STATIC
  src/core.cpp
  src/log.cpp
  src/config.cpp
  src/text.cpp

  src/diff.cpp
  src/hotwords.cpp
  src/wav.cpp
  src/models.cpp
  src/asr.cpp
  src/json.cpp
  src/audio_wasapi.cpp
  src/audio_null.cpp
)

target_include_directories(vcc_core PUBLIC "${CMAKE_SOURCE_DIR}/include")
target_link_libraries(vcc_core PUBLIC sherpa_onnx_c)

if(MSVC)
  target_compile_options(vcc_core PUBLIC /W4 /permissive- /utf-8 /Zc:__cplusplus)
  # The Win32 audio headers are noisy about deprecated CRT calls we do not make.
  target_compile_definitions(vcc_core PUBLIC _CRT_SECURE_NO_WARNINGS NOMINMAX WIN32_LEAN_AND_MEAN)
  if(VCC_WARNINGS_AS_ERRORS)
    target_compile_options(vcc_core PUBLIC /WX)
  endif()
else()
  target_compile_options(vcc_core PUBLIC -Wall -Wextra -Wno-unused-parameter)
  if(VCC_WARNINGS_AS_ERRORS)
    target_compile_options(vcc_core PUBLIC -Werror)
  endif()
endif()

if(WIN32)
  # ole32/oleaut32: COM for the WASAPI device enumerator.
  # winmm: not used directly, but mmdeviceapi pulls in its import lib on some SDKs.
  target_link_libraries(vcc_core PUBLIC ole32 oleaut32 propsys ws2_32)
else()
  find_package(Threads REQUIRED)
  target_link_libraries(vcc_core PUBLIC Threads::Threads)
endif()

# ---------------------------------------------------------------------------
# Applications
# ---------------------------------------------------------------------------
add_executable(vcc_cli src/apps/vcc_cli.cpp src/pipeline.cpp)
target_link_libraries(vcc_cli PRIVATE vcc_core)

add_executable(vcc_listen src/apps/vcc_listen.cpp src/pipeline.cpp)
target_link_libraries(vcc_listen PRIVATE vcc_core)

if(VCC_BUILD_ENGINE)
  # The API server the PyQt5 dashboard launches and talks to. Not for the
  # device image: it binds localhost and has no authentication.
  add_executable(vcc_engine src/apps/vcc_engine.cpp src/pipeline.cpp src/http.cpp)
  target_link_libraries(vcc_engine PRIVATE vcc_core)
endif()

# ---------------------------------------------------------------------------
# Runtime dependencies next to the binaries
# ---------------------------------------------------------------------------
file(GLOB SHERPA_RUNTIME_LIBS
  "${SHERPA_LIB_DIR}/*.dll"
  "${SHERPA_LIB_DIR}/*.so"
  "${SHERPA_LIB_DIR}/*.so.*"
  "${SHERPA_LIB_DIR}/*.dylib")

if(SHERPA_RUNTIME_LIBS)
  add_custom_target(vcc_copy_runtime ALL
    COMMAND ${CMAKE_COMMAND} -E make_directory "${CMAKE_BINARY_DIR}/bin"
    COMMAND ${CMAKE_COMMAND} -E copy_if_different ${SHERPA_RUNTIME_LIBS} "${CMAKE_BINARY_DIR}/bin"
    COMMENT "Copying sherpa-onnx runtime libraries next to the executables")
  add_dependencies(vcc_cli vcc_copy_runtime)
endif()

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
if(VCC_BUILD_TESTS)
  enable_testing()

  # These exercise pure logic (normalisation, distances, matching, WAV codec)
  # and need no model, so they stay fast enough to run on every build.
  add_executable(vcc_tests
    tests/test_main.cpp
    tests/test_text.cpp

    tests/test_diff.cpp
    tests/test_hotwords.cpp
    tests/test_wav.cpp
    tests/test_config.cpp
    tests/test_json.cpp
    tests/test_models.cpp
  )
  target_link_libraries(vcc_tests PRIVATE vcc_core)
  target_include_directories(vcc_tests PRIVATE "${CMAKE_SOURCE_DIR}/tests")
  add_test(NAME unit COMMAND vcc_tests)
  set_tests_properties(unit PROPERTIES WORKING_DIRECTORY "${CMAKE_SOURCE_DIR}")
endif()

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
message(STATUS "")
message(STATUS "vcc_biasing_stt ${PROJECT_VERSION}")
message(STATUS "  build type   : ${CMAKE_BUILD_TYPE}")
message(STATUS "  compiler     : ${CMAKE_CXX_COMPILER_ID} ${CMAKE_CXX_COMPILER_VERSION}")
message(STATUS "  sherpa-onnx  : ${SHERPA_C_API_LIB}")
message(STATUS "  engine       : ${VCC_BUILD_ENGINE}")
message(STATUS "  tests        : ${VCC_BUILD_TESTS}")
message(STATUS "  binaries     : ${CMAKE_BINARY_DIR}/bin")
message(STATUS "")
