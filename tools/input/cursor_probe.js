// Original-emulator observations only; no guest RAM modification.
const output=ares.args[1];
ares.setHomebrew(false);
ares.setRenderer("angrylion");
ares.loadRom(ares.args[0]);
if(ares.args[2]!=="none") ares.researchLoadState(ares.args[2]);
else ares.researchLoadFlash(ares.args[3]);
ares.researchStart(output);
ares.resume();
const pad=ares.controller(1);
if(ares.args[2]==="none") {
    ares.researchPak(1,"Controller Pak");
    const route=[[null,960],["Start",6],[null,60],["Start",6],[null,180],
        ["A",6],[null,180],["Right",6],[null,30],["Right",6],[null,30],["A",6],[null,900]];
    for(const [button,fields] of route) {
        if(button) pad.hold(button);
        ares.waitFrames(fields);
        if(button) pad.release(button);
    }
    for(let i=0;i<6;++i) {
        pad.hold("A"); ares.waitFrames(6); pad.release("A"); ares.waitFrames(60);
        ares.screenshot().save(output+"/advisor-"+i+".png");
    }
}
const steps=[
    ["neutral",0,0,15], ["right6",1,0,6], ["right12",1,0,6],
    ["stationary",0,0,6], ["left12",-1,0,12],
    ["positive_y6",0,1,6], ["negative_y12",0,-1,12], ["rest",0,0,6],
    ["settled",0,0,18], ["dpad_right",0,0,24,"Right"], ["dpad_left",0,0,24,"Left"],
    ["z_right",.5,0,24,"Z"], ["z_rest",0,0,18], ["z_left",-.5,0,24,"Z"],
    ["z_positive_y",0,.5,12,"Z"], ["z_negative_y",0,-.5,12,"Z"]
];
for (const [label,x,y,fields,button] of steps) {
    pad.stick(x,y);
    if(button) pad.hold(button);
    ares.waitFrames(fields);
    if(button) pad.release(button);
    ares.researchSnapshot(label);
    const frame=ares.screenshot();
    frame.save(output+"/"+label+".png");
    console.log(label,ares.frameCount(),frame.width,frame.height,frame.sha256);
}
pad.stick(0,0);
ares.researchStop();
