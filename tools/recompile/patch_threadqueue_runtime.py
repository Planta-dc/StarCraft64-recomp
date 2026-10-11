#!/usr/bin/env python3
"""Pure, pinned source transformations for guest queue removal and timer exit.

The host patch owns application order and writes. These transformations do not
modify a dependency checkout themselves.
"""
from __future__ import annotations

THREADQUEUE_SHA256 = "b9bb55edeb9cb99a153d00d80a13c5a09140113403499af7656fd9489d38f305"
TIMER_SHA256 = "5320da1c67d44425f4f13b58d0d3e7afae3029c8142557f9e734083a2f75617f"


def replace(text: str, before: str, after: str) -> str:
    if text.count(before) != 1:
        raise ValueError(f"Guest scheduler source drift at {before[:100]!r}")
    return text.replace(before, after, 1)


def patch_threadqueue(text: str) -> str:
    return replace(text, """    PTR(PTR(OSThread)) cur = queue_;
    while (cur != NULLPTR) {
        PTR(OSThread)* cur_ptr = queue_to_ptr(PASS_RDRAM queue_);
        if (*cur_ptr == t_) {
            *cur_ptr = TO_PTR(OSThread, *cur_ptr)->next;
            return true;
        }
        cur = TO_PTR(OSThread, *cur_ptr)->next;
    }""", """    PTR(OSThread)* current_link = queue_to_ptr(PASS_RDRAM queue_);
    while (*current_link != NULLPTR) {
        OSThread* current_thread = TO_PTR(OSThread, *current_link);
        if (*current_link == t_) {
            *current_link = current_thread->next;
            return true;
        }
        // Follow the link's storage address, not the queue head or next value.
        current_link = &current_thread->next;
    }""")


def patch_timers(text: str) -> str:
    text = replace(text, '#include <thread>', '#include <thread>\n#include <atomic>')
    text = replace(text, 'using Action = std::variant<AddTimerAction, RemoveTimerAction>;', '''struct StopTimerAction {};
using Action = std::variant<AddTimerAction, RemoveTimerAction, StopTimerAction>;
static std::atomic_bool sc64_timers_stopping = false;''')
    text = replace(text, '    while (true) {\n        // Empty the action queue', '    while (!sc64_timers_stopping.load()) {\n        // Empty the action queue')
    text = replace(text, '''        while (timer_context.action_queue.try_dequeue(cur_action)) {
            process_timer_action(cur_action);
        }''', '''        while (timer_context.action_queue.try_dequeue(cur_action)) {
            if (sc64_timers_stopping.load()) return;
            process_timer_action(cur_action);
        }''')
    text = replace(text, '''            timer_context.action_queue.wait_dequeue(cur_action);
            process_timer_action(cur_action);''', '''            timer_context.action_queue.wait_dequeue(cur_action);
            if (sc64_timers_stopping.load()) return;
            process_timer_action(cur_action);''')
    text = replace(text, '''        // Get the timer that's closest to running out
        PTR(OSTimer) cur_timer_''', '''        if (sc64_timers_stopping.load()) return;
        // Get the timer that's closest to running out
        PTR(OSTimer) cur_timer_''')
    text = replace(text, '''            // Timer was interrupted by a new action 
            // Add the current timer back''', '''            if (sc64_timers_stopping.load()) return;
            // Timer was interrupted by a new action 
            // Add the current timer back''')
    text = replace(text, '''        else {
            // Waiting for the timer completed''', '''        else {
            if (sc64_timers_stopping.load()) return;
            // Waiting for the timer completed''')
    text = replace(text, '''    timer_context.thread = std::thread{ timer_thread, PASS_RDRAM1 };
    timer_context.thread.detach();''', '''    if (timer_context.thread.joinable()) throw std::logic_error("Timer thread already running");
    sc64_timers_stopping.store(false);
    timer_context.thread = std::thread{ timer_thread, PASS_RDRAM1 };''')
    text += '''
// Guest producers must finish before this call. The flag makes stop independent
// of cross-producer queue ordering; the action wakes idle or long timer waits.
// RDRAM must remain mapped until this join has completed.
extern "C" void sc64_join_timers() {
    if (!timer_context.thread.joinable()) return;
    sc64_timers_stopping.store(true);
    timer_context.action_queue.enqueue(StopTimerAction{});
    timer_context.thread.join();
}
'''
    return text
