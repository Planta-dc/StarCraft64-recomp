// Original controller-only UI experiment. Canonical snapshots remain private.
const output=ares.args[1];
ares.setHomebrew(false);
ares.setRenderer("angrylion");
ares.loadRom(ares.args[0]);
ares.researchLoadFlash(ares.args[2]);
ares.researchStart(output);
ares.resume();
ares.researchPak(1,"Controller Pak");
const pad=ares.controller(1);
function checkpoint(label) {
    ares.researchSnapshot(label);
    const frame=ares.screenshot();
    frame.save(output+"/"+label+".png");
    console.log(label,ares.frameCount(),frame.width,frame.height,frame.sha256);
}
function press(button,wait=60,fields=6) {
    pad.hold(button); ares.waitFrames(fields); pad.release(button); ares.waitFrames(wait);
}
ares.waitFrames(960); checkpoint("boot");
press("Start"); checkpoint("title");
press("Start",180); checkpoint("main");
press("Down"); checkpoint("main-down");
press("Up"); checkpoint("main-up");
if (ares.args[3]==="campaign") {
    function turn(x) { pad.stick(x,0); ares.waitFrames(12); pad.stick(0,0); ares.waitFrames(90); }
    turn(-.95); checkpoint("campaign-left-1");
    turn(-.95); checkpoint("campaign-left-2");
    press("A",90,24); checkpoint("campaign-warning");
    press("B",90,24); checkpoint("campaign-warning-back");
    press("A",90,24); checkpoint("campaign-warning-again");
    press("Start",180,24); checkpoint("campaign-continued");
    press("B",180,24); checkpoint("campaign-main-return");
    turn(.95); checkpoint("campaign-right");
} else {
press("A",180); checkpoint("single");
if (ares.args[3]==="mission") {
    press("Down"); press("Down"); checkpoint("mission-row");
    press("A",900); checkpoint("briefing");
    press("Start",900); checkpoint("advisor");
} else {
    press("Right",30); checkpoint("single-right");
    press("Right",30); checkpoint("single-load-saved");
    press("A",900); checkpoint("advisor");
}
for(let i=0;i<6;++i) { press("A"); checkpoint("advisor-"+i); }
press("Start"); checkpoint("pause");
press("Down"); checkpoint("pause-down");
press("B"); checkpoint("pause-back");
pad.hold("Z"); press("R"); pad.release("Z");
ares.waitFrames(30); checkpoint("build");
press("Down"); checkpoint("build-down");
press("B"); checkpoint("build-back");
if (ares.args[3]==="hud") {
    // Move from the saved game's initial centre to the visible unit cluster.
    // These are controller movements, not guest-coordinate writes.
    pad.stick(-.8,0); ares.waitFrames(28); pad.stick(0,0); ares.waitFrames(18);
    pad.stick(0,-.8); ares.waitFrames(18); pad.stick(0,0); ares.waitFrames(18);
    checkpoint("unit-point"); press("A"); checkpoint("unit-selected");
    pad.hold("Z"); press("R"); pad.release("Z");
    ares.waitFrames(30); checkpoint("unit-build"); press("B");
    // A rectangle over the starting units tests the multiple-selection HUD.
    pad.hold("A"); pad.stick(.8,.8); ares.waitFrames(18);
    pad.stick(0,0); ares.waitFrames(18); pad.release("A"); ares.waitFrames(60);
    checkpoint("group-selected");
    press("C-Left"); checkpoint("group-hold");
    press("C-Right"); checkpoint("group-move"); press("B");
    pad.stick(-.8,0); ares.waitFrames(10); pad.stick(0,0); ares.waitFrames(18);
    pad.stick(0,-.8); ares.waitFrames(8); pad.stick(0,0); ares.waitFrames(18);
    checkpoint("single-point"); press("A"); checkpoint("single-selected");
}
}
ares.researchStop();
