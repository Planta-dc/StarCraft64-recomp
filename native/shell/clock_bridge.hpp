#pragma once
#include <chrono>
// Enabled only in the separate Stage3 runtime build. Stage1 evidence and its
// private source tree remain reproducible without a desktop lifecycle dependency.
std::chrono::high_resolution_clock::time_point sc64_runtime_now();
void sc64_pause_point();
