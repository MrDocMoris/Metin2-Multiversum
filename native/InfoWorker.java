package de.mrdocmoris.metin2;

import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.os.Build;

import androidx.annotation.NonNull;
import androidx.core.app.NotificationCompat;
import androidx.core.app.NotificationManagerCompat;
import androidx.work.Worker;
import androidx.work.WorkerParameters;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

/**
 * Prüft im Hintergrund (alle 2 Stunden und beim App-Start) die Forum-Daten
 * und meldet Neues per Benachrichtigung: Event-Änderungen für den eigenen Server,
 * angekündigte Wartungen, neue große Events und Neuigkeiten (Updates).
 */
public class InfoWorker extends Worker {
    static final String URL_INFO = "https://raw.githubusercontent.com/MrDocMoris/Metin2-Multiversum/main/daten/events.json";
    static final String CHANNEL = "m2_info";

    public InfoWorker(@NonNull Context ctx, @NonNull WorkerParameters params) { super(ctx, params); }

    private static class Item {
        final String key, kind, title, text;
        Item(String key, String kind, String title, String text) { this.key = key; this.kind = kind; this.title = title; this.text = text; }
    }

    @NonNull
    @Override
    public Result doWork() {
        Context ctx = getApplicationContext();
        try {
            // Einstellungen aus der App (Capacitor Preferences)
            SharedPreferences cap = ctx.getSharedPreferences("CapacitorStorage", Context.MODE_PRIVATE);
            JSONObject cfg = new JSONObject(cap.getString("m2_bg", "{\"plan\":true,\"news\":true,\"wartung\":true,\"events\":true}"));

            HttpURLConnection c = (HttpURLConnection) new URL(URL_INFO + "?t=" + System.currentTimeMillis()).openConnection();
            c.setConnectTimeout(15000);
            c.setReadTimeout(20000);
            c.setUseCaches(false);
            if (c.getResponseCode() != 200) return Result.success();
            StringBuilder sb = new StringBuilder();
            try (BufferedReader r = new BufferedReader(new InputStreamReader(c.getInputStream(), StandardCharsets.UTF_8))) {
                String line;
                while ((line = r.readLine()) != null) sb.append(line).append('\n');
            }
            JSONObject d = new JSONObject(sb.toString());

            List<Item> items = new ArrayList<>();
            JSONArray hin = d.optJSONArray("hinweise");
            if (hin != null) for (int i = 0; i < hin.length(); i++) {
                JSONObject h = hin.getJSONObject(i);
                items.add(new Item("h:" + h.optString("datum"), "plan", "⚠️ Event-Plan geändert", h.optString("text")));
            }
            JSONObject w = d.optJSONObject("wartung");
            if (w != null && !w.isNull("naechste")) {
                String st = w.optString("naechste");
                items.add(new Item("w:" + st, "wartung", "🛠️ Wartung angekündigt", fmt(st) + " – die Server sind dann eine Zeit lang offline."));
            }
            JSONArray news = d.optJSONArray("news");
            if (news != null) for (int i = 0; i < news.length(); i++) {
                JSONObject n = news.getJSONObject(i);
                String st = n.optString("start", "");
                items.add(new Item("e:" + n.optString("name") + st, "events", "🎉 Neues Event: " + n.optString("name"), st.isEmpty() ? "Bis " + fmt(n.optString("ende")) : "Ab " + fmt(st) + (n.has("ende") ? " bis " + fmt(n.optString("ende")) : "")));
            }
            JSONArray gn = d.optJSONArray("neuigkeiten");
            if (gn != null) for (int i = 0; i < gn.length(); i++) {
                JSONObject n = gn.getJSONObject(i);
                items.add(new Item("n:" + n.optString("url"), "news", "📰 Metin2-News", n.optString("titel")));
            }

            SharedPreferences sp = ctx.getSharedPreferences("m2bg", Context.MODE_PRIVATE);
            boolean first = !sp.getBoolean("init", false);
            Set<String> seen = new HashSet<>(sp.getStringSet("seen", new HashSet<>()));
            Set<String> now = new HashSet<>();
            int id = 7000;
            for (Item it : items) {
                now.add(it.key);
                if (!first && !seen.contains(it.key) && cfg.optBoolean(it.kind, true)) post(ctx, it.title, it.text, id + (it.key.hashCode() & 0x3ff));
            }
            // gesehene Einträge behalten (auch alte), damit nichts doppelt kommt
            seen.addAll(now);
            if (seen.size() > 300) seen = now;
            sp.edit().putBoolean("init", true).putStringSet("seen", seen).apply();
        } catch (Exception e) {
            return Result.retry();
        }
        return Result.success();
    }

    /** "2026-11-25T09:00" -> "25.11. um 09:00 Uhr" */
    static String fmt(String iso) {
        if (iso == null || iso.length() < 10) return "";
        String s = iso.substring(8, 10) + "." + iso.substring(5, 7) + ".";
        if (iso.length() >= 16) s += " um " + iso.substring(11, 16) + " Uhr";
        return s;
    }

    static void post(Context ctx, String title, String text, int id) {
        NotificationManager nm = (NotificationManager) ctx.getSystemService(Context.NOTIFICATION_SERVICE);
        if (Build.VERSION.SDK_INT >= 26 && nm.getNotificationChannel(CHANNEL) == null)
            nm.createNotificationChannel(new NotificationChannel(CHANNEL, "Neues aus dem Forum", NotificationManager.IMPORTANCE_DEFAULT));
        Intent open = ctx.getPackageManager().getLaunchIntentForPackage(ctx.getPackageName());
        PendingIntent pi = open == null ? null : PendingIntent.getActivity(ctx, id, open, PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
        NotificationCompat.Builder b = new NotificationCompat.Builder(ctx, CHANNEL)
                .setSmallIcon(R.drawable.ic_stat_m2)
                .setContentTitle(title)
                .setContentText(text)
                .setStyle(new NotificationCompat.BigTextStyle().bigText(text))
                .setAutoCancel(true);
        if (pi != null) b.setContentIntent(pi);
        try { NotificationManagerCompat.from(ctx).notify(id, b.build()); } catch (SecurityException ignored) {}
    }
}
