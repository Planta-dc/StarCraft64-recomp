#pragma once

// Content-view coordinates normalized to [0,1], with a bottom-left origin.
// Platform cursor operations run exclusively on the shell's main thread.
struct Sc64CursorRegion {
    double x0 = 0, y0 = 0, x1 = 0, y1 = 0;
    bool contains(double x, double y) const { return x>=x0 && x<x1 && y>=y0 && y<y1; }
};
inline Sc64CursorRegion sc64_project_cursor_region(const Sc64CursorRegion& image,
        double x0, double y0, double x1, double y1, double width, double height) {
    const double sx=(image.x1-image.x0)/width, sy=(image.y1-image.y0)/height;
    return {image.x0+x0*sx,image.y1-y1*sy,image.x0+x1*sx,image.y1-y0*sy};
}
bool sc64_update_mouse_cursor(bool requested, const Sc64CursorRegion& region,
                              const Sc64CursorRegion* visible_region = nullptr,
                              const Sc64CursorRegion* minimap_region = nullptr);
void sc64_restore_mouse_cursor();
