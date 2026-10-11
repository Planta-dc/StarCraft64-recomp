#pragma once
struct SDL_Window;
// Parent window for the ROM dialog and the cursor policy; null detaches.
void sc64_platform_attach_window(SDL_Window* window);
