# Optimization profile for the software renderer (gfx_core and its replay/test
# tools): -O3 plus link-time optimization in optimized configurations. Measured
# offline against -O2 without LTO (docs/performance.md): rasterization about 1.3-1.5x
# faster, GBI interpretation about 1.15x faster, with byte-identical output.
# LTO is skipped silently when the toolchain does not support it.
include(CheckIPOSupported)
check_ipo_supported(RESULT SC64_IPO_SUPPORTED LANGUAGES CXX)

function(sc64_optimize_gfx_targets)
    foreach(target IN LISTS ARGN)
        target_compile_options(${target} PRIVATE "$<$<CONFIG:RelWithDebInfo,Release>:-O3>")
        if(SC64_IPO_SUPPORTED)
            set_property(TARGET ${target} PROPERTY INTERPROCEDURAL_OPTIMIZATION_RELWITHDEBINFO ON)
            set_property(TARGET ${target} PROPERTY INTERPROCEDURAL_OPTIMIZATION_RELEASE ON)
        endif()
    endforeach()
endfunction()
