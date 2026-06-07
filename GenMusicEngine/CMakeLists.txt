cmake_minimum_required(VERSION 3.27)

project(GenMusicEngine LANGUAGES C CXX OBJCXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
set(CMAKE_OBJCXX_STANDARD 20)
set(CMAKE_POLICY_VERSION_MINIMUM 3.5)

if(NOT APPLE)
    message(FATAL_ERROR "GenMusicEngine uses magentart::core/MLX/AVAudioEngine and currently requires macOS.")
endif()

get_filename_component(DEFAULT_MAGENTART_ROOT
    "${CMAKE_CURRENT_LIST_DIR}/../magenta-realtime"
    ABSOLUTE
)
set(MAGENTART_ROOT "${DEFAULT_MAGENTART_ROOT}" CACHE PATH
    "Path to the official magenta-realtime C++ source checkout.")
if(NOT EXISTS "${MAGENTART_ROOT}/core/CMakeLists.txt")
    message(FATAL_ERROR
        "MAGENTART_ROOT must point to the official magenta-realtime checkout. "
        "Expected ${MAGENTART_ROOT}/core/CMakeLists.txt")
endif()

include(FetchContent)

FetchContent_Declare(
    mlx
    GIT_REPOSITORY https://github.com/ml-explore/mlx.git
    GIT_TAG        v0.31.1
    GIT_SHALLOW    ON
)
set(MLX_BUILD_TESTS OFF CACHE BOOL "" FORCE)
set(MLX_BUILD_EXAMPLES OFF CACHE BOOL "" FORCE)
set(MLX_BUILD_BENCHMARKS OFF CACHE BOOL "" FORCE)
set(MLX_BUILD_PYTHON_BINDINGS OFF CACHE BOOL "" FORCE)
set(MLX_BUILD_PYTHON_STUBS OFF CACHE BOOL "" FORCE)
set(MLX_BUILD_GGUF OFF CACHE BOOL "" FORCE)
set(MLX_BUILD_CUDA OFF CACHE BOOL "" FORCE)
FetchContent_MakeAvailable(mlx)

FetchContent_Declare(
    sentencepiece
    GIT_REPOSITORY https://github.com/google/sentencepiece.git
    GIT_TAG        v0.2.0
    GIT_SHALLOW    ON
)
set(SPM_ENABLE_SHARED OFF CACHE BOOL "" FORCE)
FetchContent_MakeAvailable(sentencepiece)

FetchContent_Declare(
    tensorflow-lite
    GIT_REPOSITORY https://github.com/tensorflow/tensorflow.git
    GIT_TAG        v2.21.0
    SOURCE_SUBDIR  tensorflow/lite
    GIT_SHALLOW    ON
)
set(TFLITE_ENABLE_XNNPACK OFF CACHE BOOL "" FORCE)
set(TFLITE_ENABLE_GPU OFF CACHE BOOL "" FORCE)
set(TFLITE_BUILD_TESTS OFF CACHE BOOL "" FORCE)
set(FETCHCONTENT_SOURCE_DIR_TENSORFLOW "${CMAKE_BINARY_DIR}/_deps/tensorflow-lite-src" CACHE PATH
    "Point TF Lite's internal TF fetch at our already-cloned v2.21.0 source" FORCE)
FetchContent_MakeAvailable(tensorflow-lite)

add_subdirectory("${MAGENTART_ROOT}/core" "${CMAKE_BINARY_DIR}/magentart_core")

add_executable(gen_music_engine
    src/main.mm
)

target_compile_options(gen_music_engine PRIVATE
    $<$<CXX_COMPILER_ID:AppleClang,Clang,GNU>:-Wall -Wextra -Wpedantic>
)

target_compile_options(gen_music_engine PRIVATE -fobjc-arc)

target_link_libraries(gen_music_engine PRIVATE
    magentart::core
    "-framework AVFoundation"
    "-framework AudioToolbox"
    "-framework CoreAudio"
    "-framework Foundation"
)
