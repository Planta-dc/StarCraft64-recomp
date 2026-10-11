// Included inside js-host.cpp's anonymous namespace; research API only.
auto js_researchStart(JSContext* c, JSValueConst, int argc, JSValueConst* argv) -> JSValue {
  if(argc != 1) return throwError(c, "researchStart(directory)");
  try { ares::Nintendo64::Stage0::start(jsStr(c, argv[0])); }
  catch(const std::exception& e) { return throwError(c, e.what()); }
  return JS_UNDEFINED;
}
auto js_researchStop(JSContext*, JSValueConst, int, JSValueConst*) -> JSValue {
  ares::Nintendo64::Stage0::stop(); return JS_UNDEFINED;
}
auto js_researchWindow(JSContext* c, JSValueConst, int argc, JSValueConst* argv) -> JSValue {
  uint32_t fields = 0;
  if(argc != 2 || JS_ToUint32(c, &fields, argv[1]) || fields > 120)
    return throwError(c, "researchWindow(label, fields <= 120)");
  try { ares::Nintendo64::Stage0::window(jsStr(c, argv[0]), fields); }
  catch(const std::exception& e) { return throwError(c, e.what()); }
  return JS_UNDEFINED;
}
auto js_researchSnapshot(JSContext* c, JSValueConst, int argc, JSValueConst* argv) -> JSValue {
  if(argc != 1) return throwError(c, "researchSnapshot(label)");
  try { ares::Nintendo64::Stage0::snapshot(jsStr(c, argv[0])); }
  catch(const std::exception& e) { return throwError(c, e.what()); }
  return JS_UNDEFINED;
}
auto js_researchSaveState(JSContext* c, JSValueConst, int argc, JSValueConst* argv) -> JSValue {
  if(argc != 1) return throwError(c, "researchSaveState(path)");
  try { ares::Nintendo64::Stage0::saveState(jsStr(c, argv[0])); }
  catch(const std::exception& e) { return throwError(c, e.what()); }
  return JS_UNDEFINED;
}
auto js_researchLoadState(JSContext* c, JSValueConst, int argc, JSValueConst* argv) -> JSValue {
  if(argc != 1) return throwError(c, "researchLoadState(path)");
  try { ares::Nintendo64::Stage0::loadState(jsStr(c, argv[0])); }
  catch(const std::exception& e) { return throwError(c, e.what()); }
  return JS_UNDEFINED;
}
auto js_researchLoadFlash(JSContext* c, JSValueConst, int argc, JSValueConst* argv) -> JSValue {
  if(argc != 1) return throwError(c, "researchLoadFlash(path)");
  try { ares::Nintendo64::Stage0::loadFlash(jsStr(c, argv[0])); }
  catch(const std::exception& e) { return throwError(c, e.what()); }
  return JS_UNDEFINED;
}
auto js_researchExpansion(JSContext* c, JSValueConst, int argc, JSValueConst* argv) -> JSValue {
  if(emulatorRunner.loaded()) return throwError(c, "researchExpansion before loadRom only");
  ares::Nintendo64::Stage0::expansion = argc > 0 && JS_ToBool(c, argv[0]);
  return JS_UNDEFINED;
}
auto js_researchPak(JSContext* c, JSValueConst, int argc, JSValueConst* argv) -> JSValue {
  using namespace ares::Nintendo64;
  int32_t id = 0;
  if(argc != 2 || JS_ToInt32(c, &id, argv[0]) || id < 1 || id > 4)
    return throwError(c, "researchPak(port 1..4, type)");
  auto type = jsStr(c, argv[1]);
  if(type != "Rumble Pak" && type != "Controller Pak" && type != "none")
    return throwError(c, "unsupported research Pak");
  ControllerPort* ports[] = {&controllerPort1, &controllerPort2, &controllerPort3, &controllerPort4};
  auto* pad = dynamic_cast<Gamepad*>(ports[id - 1]->device.get());
  if(!pad) return throwError(c, "port has no Gamepad");
  pad->port->disconnect();
  if(type != "none") { pad->port->allocate(type); pad->port->connect(); }
  return JS_UNDEFINED;
}
