// Run a reproducible controller sequence and keep all retail-derived evidence local.
const output = ares.args[1].replace(/^out=/, "");
const state = ares.args[2].replace(/^state=/, "");
const actions = JSON.parse(ares.args[3]);
ares.setHomebrew(false);
if (ares.args[4] === "4mb") ares.researchExpansion(false);
if(ares.args[4] === "interpreter") ares.setRecompiler(false);
ares.setRenderer("angrylion");
ares.loadRom(ares.args[0]);
if (state !== "none") ares.researchLoadState(state);
if (ares.args[5]) ares.researchLoadFlash(ares.args[5].replace(/^flash=/, ""));
ares.researchStart(output);
ares.startAudio();
ares.resume();
const pads = [ares.controller(1), ares.controller(2)];
for (let i = 0; i < actions.length; ++i) {
    const action = actions[i];
    const pad = pads[(action.player || 1) - 1];
    if (action.pak) ares.researchPak(action.player || 1, action.pak);
    if (action.window) ares.researchWindow(action.window, action.fields || 6);
    if (action.hold) pad.hold(action.hold);
    if (action.stick) pad.stick(action.stick[0], action.stick[1]);
    if (action.screens) {
        for (let field = 0; field < (action.fields || 1); ++field) {
            ares.waitFrames(1);
            ares.screenshot().save(output + "/step-" + i + "-field-" + field + ".png");
        }
    } else ares.waitFrames(action.fields || 1);
    if (action.hold) pad.release(action.hold);
    if (action.stick) pad.stick(0, 0);
    const frame = ares.screenshot();
    frame.save(output + "/step-" + i + ".png");
    console.log(i, ares.frameCount(), frame.width, frame.height, frame.sha256);
    if (action.save) ares.researchSaveState(output + "/" + action.save + ".state");
}
ares.researchSnapshot("end");
ares.researchSaveState(output + "/end.state");
ares.researchStop();
ares.stopAudio().save(output + "/audio.wav");
ares.writeFile(output + "/input.json", JSON.stringify(actions, null, 2));
