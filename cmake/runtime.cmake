# Adds the prepared N64ModernRuntime copy. It vendors miniz with
# cmake_minimum_required(VERSION 3.5), which newer CMake reports as deprecated.
# Raise the policy floor for this third-party subtree only: the function scope
# ends the override on return, and the dependency copy stays untouched (it is
# hash-guarded by the patch tools).
function(sc64_add_runtime directory binary_dir)
    set(CMAKE_POLICY_VERSION_MINIMUM 3.10)
    add_subdirectory("${directory}" "${binary_dir}" ${ARGN})
endfunction()
