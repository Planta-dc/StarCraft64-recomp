#pragma once
#include <exception>
#include <mutex>
#include <string>

namespace sc64::runtime {
// Runs host work on a guest thread. Cooperative shutdown unwinds guest threads
// with Terminated (ultramodern::thread_terminated derives std::exception); it
// must reach the runtime thread wrapper instead of being reported as a failure.
template<class Terminated, class Work, class Report>
void report_host_failure(Work&& work, Report&& report) {
    try { work(); }
    catch (const Terminated&) { throw; }
    catch (const std::exception& error) { report(error.what()); }
}

// The first failure is the root cause; later failures usually come from the
// shutdown it started and must not replace it.
class FirstError {
public:
    bool record(const std::string& message) {
        std::lock_guard lock(mutex_);
        if (recorded_) return false;
        recorded_ = true;
        message_ = message.empty() ? "Runtime failure without a message" : message;
        return true;
    }
    std::string get() const { std::lock_guard lock(mutex_); return message_; }
private:
    mutable std::mutex mutex_;
    std::string message_;
    bool recorded_ = false;
};
}
