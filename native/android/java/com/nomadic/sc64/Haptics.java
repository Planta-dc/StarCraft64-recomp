package com.nomadic.sc64;

import android.app.Activity;
import android.content.Context;
import android.os.VibrationEffect;
import android.os.Vibrator;

/** Short touch confirmations and original Rumble Pak motor output. */
public final class Haptics {
    private Haptics() {}

    /** Vibrate for milliseconds at amplitude 1..255; milliseconds <= 0 stops. */
    public static void vibrate(Activity activity, int milliseconds, int amplitude) {
        try {
            Vibrator vibrator = (Vibrator) activity.getSystemService(Context.VIBRATOR_SERVICE);
            if (vibrator == null || !vibrator.hasVibrator()) return;
            if (milliseconds <= 0) { vibrator.cancel(); return; }
            int strength = vibrator.hasAmplitudeControl()
                ? Math.max(1, Math.min(255, amplitude)) : VibrationEffect.DEFAULT_AMPLITUDE;
            vibrator.vibrate(VibrationEffect.createOneShot(milliseconds, strength));
        } catch (SecurityException ignored) {
            // A manifest without VIBRATE disables haptics rather than input.
        }
    }
}
