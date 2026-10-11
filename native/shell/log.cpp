#include "log.hpp"
#include <cstdarg>
#include <cstdio>
#include <mutex>
#include <vector>
#if defined(__ANDROID__)
#include <android/log.h>
#endif

namespace sc64::shell::log {
namespace {
std::mutex mutex;
#if defined(__ANDROID__)
constexpr const char* tag = "SC64";
#endif
std::string format(const char* pattern, va_list arguments) {
    va_list copy;
    va_copy(copy, arguments);
    const int size = std::vsnprintf(nullptr, 0, pattern, copy);
    va_end(copy);
    if (size <= 0) return {};
    std::vector<char> buffer(std::size_t(size) + 1);
    std::vsnprintf(buffer.data(), buffer.size(), pattern, arguments);
    return {buffer.data(), std::size_t(size)};
}
void write(const char* level, [[maybe_unused]] int priority, const std::string& message) {
    std::lock_guard lock(mutex);
#if defined(__ANDROID__)
    __android_log_write(priority, tag, message.c_str());
#else
    std::fprintf(stdout, "%s:SC64: %s\n", level, message.c_str());
    std::fflush(stdout);
#endif
}
}

#if defined(__ANDROID__)
#define SC64_PRIORITY(name) ANDROID_LOG_##name
#else
#define SC64_PRIORITY(name) 0
#endif

void info(const char* pattern, ...) {
    va_list arguments;
    va_start(arguments, pattern);
    const auto message = format(pattern, arguments);
    va_end(arguments);
    write("INFO", SC64_PRIORITY(INFO), message);
}
void warning(const char* pattern, ...) {
    va_list arguments;
    va_start(arguments, pattern);
    const auto message = format(pattern, arguments);
    va_end(arguments);
    write("WARNING", SC64_PRIORITY(WARN), message);
}
void error(const char* pattern, ...) {
    va_list arguments;
    va_start(arguments, pattern);
    const auto message = format(pattern, arguments);
    va_end(arguments);
    write("ERROR", SC64_PRIORITY(ERROR), message);
}
void line(const std::string& text) { write("INFO", SC64_PRIORITY(INFO), text); }
}
