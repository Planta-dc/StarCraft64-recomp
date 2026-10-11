package com.nomadic.sc64;

import android.content.Intent;
import android.util.Log;
import java.util.ArrayList;
import java.util.List;
import org.libsdl.app.SDLActivity;

/** SDL activity for the statically linked shell library (libmain.so). */
public final class Sc64Activity extends SDLActivity {
    /** Optional string-array extra with `--config=sc64.key=value` arguments. */
    public static final String EXTRA_ARGUMENTS = "com.nomadic.sc64.ARGUMENTS";
    /**
     * The activity is exported, so any installed app can send these extras. Only
     * the renderer choice used by tools/android/run.py is honored; storage, ROM,
     * recipe and trace settings stay under the packaged config.ini.
     */
    private static final String ALLOWED_ARGUMENT = "--config=sc64.render_driver=";

    @Override
    protected String[] getLibraries() {
        // SDL is linked into libmain.so; there is no separate libSDL3.so.
        return new String[] {"main"};
    }

    @Override
    protected String[] getArguments() {
        Intent intent = getIntent();
        String[] requested = intent == null ? null : intent.getStringArrayExtra(EXTRA_ARGUMENTS);
        if (requested == null) return new String[0];
        List<String> accepted = new ArrayList<>();
        for (String argument : requested) {
            if (argument != null && argument.startsWith(ALLOWED_ARGUMENT)) {
                accepted.add(argument);
            } else {
                Log.w("SC64", "Ignoring unsupported launch argument");
            }
        }
        return accepted.toArray(new String[0]);
    }
}
