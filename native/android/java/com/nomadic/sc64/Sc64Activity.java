package com.nomadic.sc64;

import android.content.Intent;
import org.libsdl.app.SDLActivity;

/** SDL activity for the statically linked shell library (libmain.so). */
public final class Sc64Activity extends SDLActivity {
    /** Optional string-array extra with `--config=sc64.key=value` arguments. */
    public static final String EXTRA_ARGUMENTS = "com.nomadic.sc64.ARGUMENTS";

    @Override
    protected String[] getLibraries() {
        // SDL is linked into libmain.so; there is no separate libSDL3.so.
        return new String[] {"main"};
    }

    @Override
    protected String[] getArguments() {
        Intent intent = getIntent();
        String[] arguments = intent == null ? null : intent.getStringArrayExtra(EXTRA_ARGUMENTS);
        return arguments == null ? new String[0] : arguments;
    }
}
