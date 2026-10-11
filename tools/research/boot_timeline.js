// Record a per-field original-screen timeline for the boot sequence. Each
// field logs the scanout size, SHA-256 and mean RGB; PNGs and canonical RAM
// snapshots are saved at requested fields. All retail-derived output stays in
// the private directory passed as out=.
// Arguments: rom out=<dir> actions=<json> [png_every=N]
// Action keys: fields (required), hold (button), pak, snap (RAM label).
const output = ares.args[1].replace(/^out=/, "");
const actions = JSON.parse(ares.args[2].replace(/^actions=/, ""));
const pngEvery = ares.args[3] ? Number(ares.args[3].replace(/^png_every=/, "")) : 0;
ares.setHomebrew(false);
ares.setRenderer("angrylion");
ares.loadRom(ares.args[0]);
ares.researchStart(output);
ares.resume();
const pad = ares.controller(1);
const lines = [];
let field = 0;
function sample() {
    let frame;
    try { frame = ares.screenshot(); }
    catch (error) { lines.push(JSON.stringify({field: ares.frameCount(), step: field, blank: true})); return; }
    const px = new Uint8Array(frame.data);
    let r = 0, g = 0, b = 0, n = 0;
    for (let i = 0; i < px.length; i += 4 * 7) { r += px[i]; g += px[i + 1]; b += px[i + 2]; ++n; }
    lines.push(JSON.stringify({field: ares.frameCount(), step: field, width: frame.width,
        height: frame.height, sha256: frame.sha256,
        mean: [r / n, g / n, b / n].map(v => Math.round(v * 100) / 100)}));
    if (pngEvery && field % pngEvery === 0) frame.save(output + "/field-" + field + ".png");
}
for (const action of actions) {
    if (action.pak) ares.researchPak(1, action.pak);
    if (action.snap) ares.researchSnapshot(action.snap);
    if (action.hold) pad.hold(action.hold);
    for (let i = 0; i < (action.fields || 0); ++i) {
        ares.waitFrames(1); ++field; sample();
    }
    if (action.hold) pad.release(action.hold);
}
ares.researchStop();
ares.writeFile(output + "/timeline.jsonl", lines.join("\n") + "\n");
ares.writeFile(output + "/input.json", JSON.stringify(actions, null, 2));
