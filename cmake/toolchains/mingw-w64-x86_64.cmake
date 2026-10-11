# Cross-compile the Windows x86_64 shell on the macOS host with Homebrew
# mingw-w64 (GCC). The executable is linked statically, so it needs no MinGW
# runtime DLLs on the target machine.
set(CMAKE_SYSTEM_NAME Windows)
set(CMAKE_SYSTEM_PROCESSOR x86_64)
set(SC64_MINGW_PREFIX "x86_64-w64-mingw32" CACHE STRING "mingw-w64 tool prefix")
set(CMAKE_C_COMPILER ${SC64_MINGW_PREFIX}-gcc)
set(CMAKE_CXX_COMPILER ${SC64_MINGW_PREFIX}-g++)
set(CMAKE_RC_COMPILER ${SC64_MINGW_PREFIX}-windres)
set(CMAKE_FIND_ROOT_PATH_MODE_PROGRAM NEVER)
set(CMAKE_FIND_ROOT_PATH_MODE_LIBRARY ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_INCLUDE ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_PACKAGE ONLY)
set(CMAKE_EXE_LINKER_FLAGS_INIT "-static -static-libgcc -static-libstdc++")
