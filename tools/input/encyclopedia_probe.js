// Original controller-only Encyclopedia experiment: main menu item 3, article
// links (selection, follow, wrap), Start on a link and Back. Canonical
// snapshots stay private. Route "links" walks link-heavy building articles.
const output=ares.args[1];
const route=ares.args[3]||"basic";
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
ares.waitFrames(960);
press("Start"); press("Start",180); checkpoint("main");
press("Down"); press("Down"); press("Down"); checkpoint("main-encyclopedia");
press("A",180); checkpoint("scv");
if (route==="basic") {
    press("Down"); checkpoint("scv-down");
    press("Up"); checkpoint("scv-up");
    press("Right"); checkpoint("marine");
    press("Down"); checkpoint("marine-down-1");
    press("Down"); checkpoint("marine-down-2");
    press("Down"); checkpoint("marine-down-3");
    press("Up"); checkpoint("marine-up-3");
    press("Up"); press("Up"); checkpoint("marine-up-1");
    press("Down"); press("A",90); checkpoint("follow-command-center");
    press("Down"); checkpoint("command-center-down");
    press("Right",90); checkpoint("command-center-right");
    press("Right",90); press("Right",90); press("Right",90); checkpoint("right-x4");
    press("B",180); checkpoint("back");
} else {
    // Marine -> Barracks (its second Needs link), then walk Barracks' links.
    press("Right"); checkpoint("marine");
    press("Down"); press("Down"); press("A",90); checkpoint("barracks");
    for (let i=1;i<=6;++i) { press("Down"); checkpoint("barracks-down-"+i); }
    // Start on a highlighted link (Enter): does it follow the link or leave?
    press("Start",120); checkpoint("barracks-start");
}
ares.researchStop();
