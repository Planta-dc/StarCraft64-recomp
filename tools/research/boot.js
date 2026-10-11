// Research only: original ROM, default hardware paths, software RDP reference.
const output = ares.args[1].replace(/^out=/, "");
ares.setHomebrew(false);
ares.setRenderer("angrylion");
ares.loadRom(ares.args[0]);
ares.researchStart(output);
ares.startAudio();
ares.resume();
for (let i = 0; i < 8; i++) {
    ares.wait(2);
    const frame = ares.screenshot();
    frame.save(output + "/boot-" + i + ".png");
    console.log(i, ares.frameCount(), frame.width, frame.height, frame.sha256);
}
ares.researchSnapshot("boot-end");
ares.researchSaveState(output + "/boot-end.state");
ares.researchStop();
ares.stopAudio().save(output + "/boot.wav");
