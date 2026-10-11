#pragma once
#include <string>

// Engine log lines keep the historical "LEVEL:SC64: message" form. Evidence
// checkers treat any line starting with "ERROR:" as a failed run, and parse
// "SC64 {json}" style telemetry lines anywhere in a line.
namespace sc64::shell::log {
void info(const char* format, ...)
#if defined(__GNUC__)
    __attribute__((format(printf, 1, 2)))
#endif
    ;
void warning(const char* format, ...)
#if defined(__GNUC__)
    __attribute__((format(printf, 1, 2)))
#endif
    ;
void error(const char* format, ...)
#if defined(__GNUC__)
    __attribute__((format(printf, 1, 2)))
#endif
    ;
// Writes one already formatted line, used for structured telemetry.
void line(const std::string& text);
}
