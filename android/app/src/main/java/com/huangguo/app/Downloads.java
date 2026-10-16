package com.huangguo.app;

import android.content.Context;
import android.content.SharedPreferences;

import org.json.JSONArray;
import org.json.JSONObject;

import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

/** 下载任务管理：活动任务（内存中）+ 已完成任务（持久化）。 */
public class Downloads {

    public static final int QUEUED = 0;
    public static final int RUNNING = 1;
    public static final int PAUSED = 2;
    public static final int DONE = 3;
    public static final int ERROR = 4;

    public static class Task {
        public String id = "", ep = "1", title = "";
        public int state = QUEUED;
        public int done = 0, total = 0;
        public String err = "";
        public String uri = "";
        public long size = 0L, bytes = 0L, ts = 0L;
        public volatile boolean paused = false;
        public volatile boolean cancel = false;

        public String label() {
            return (title == null || title.isEmpty() ? ("视频" + id) : title)
                    + " · 第" + Site.pad2(ep) + "集";
        }
    }

    public static final List<Task> ACTIVE = new CopyOnWriteArrayList<>();
    private static final List<Task> FINISHED = new CopyOnWriteArrayList<>();
    private static boolean loaded = false;

    public static synchronized void ensureLoaded() {
        if (loaded) return;
        loaded = true;
        try {
            SharedPreferences p = App.CTX.getSharedPreferences("huangguo", Context.MODE_PRIVATE);
            JSONArray a = new JSONArray(p.getString("dl_done", "[]"));
            for (int i = 0; i < a.length(); i++) {
                JSONObject o = a.optJSONObject(i);
                if (o == null) continue;
                Task t = new Task();
                t.id = o.optString("id", "");
                t.ep = o.optString("ep", "1");
                t.title = o.optString("title", "");
                t.uri = o.optString("uri", "");
                t.size = o.optLong("size", 0L);
                t.ts = o.optLong("ts", 0L);
                t.state = DONE;
                FINISHED.add(t);
            }
        } catch (Exception ignored) {
        }
        sortFinished();
    }

    private static void sortFinished() {
        List<Task> l = new ArrayList<>(FINISHED);
        Collections.sort(l, new Comparator<Task>() {
            @Override
            public int compare(Task a, Task b) {
                return Long.compare(b.ts, a.ts);
            }
        });
        FINISHED.clear();
        FINISHED.addAll(l);
    }

    private static void save() {
        try {
            JSONArray a = new JSONArray();
            for (Task t : FINISHED) {
                JSONObject o = new JSONObject();
                o.put("id", t.id);
                o.put("ep", t.ep);
                o.put("title", t.title);
                o.put("uri", t.uri);
                o.put("size", t.size);
                o.put("ts", t.ts);
                a.put(o);
            }
            SharedPreferences p = App.CTX.getSharedPreferences("huangguo", Context.MODE_PRIVATE);
            p.edit().putString("dl_done", a.toString()).apply();
        } catch (Exception ignored) {
        }
    }

    /** 入队（同剧同集不重复）。 */
    public static synchronized Task enqueue(String id, String ep, String title) {
        ensureLoaded();
        for (Task t : ACTIVE) {
            if (t.id.equals(id) && t.ep.equals(ep)) return t;
        }
        Task t = new Task();
        t.id = id;
        t.ep = ep;
        t.title = title == null ? "" : title;
        t.state = QUEUED;
        t.ts = System.currentTimeMillis();
        ACTIVE.add(t);
        return t;
    }

    /** 取出下一个待执行任务。 */
    public static synchronized Task next() {
        for (Task t : ACTIVE) {
            if (t.state == QUEUED) {
                t.state = RUNNING;
                t.err = "";
                t.paused = false;
                t.cancel = false;
                return t;
            }
        }
        return null;
    }

    public static synchronized boolean hasQueued() {
        for (Task t : ACTIVE) {
            if (t.state == QUEUED || t.state == RUNNING) return true;
        }
        return false;
    }

    public static synchronized void finish(Task t, String uri, long size) {
        t.state = DONE;
        t.uri = uri == null ? "" : uri;
        t.size = size;
        t.ts = System.currentTimeMillis();
        t.done = Math.max(t.done, t.total);
        ACTIVE.remove(t);
        FINISHED.add(0, t);
        save();
    }

    public static synchronized void fail(Task t, String err) {
        t.state = ERROR;
        t.err = err == null ? "" : err;
    }

    public static synchronized void retry(Task t) {
        if (t.state == ERROR || t.state == PAUSED) {
            t.state = QUEUED;
            t.err = "";
            t.done = 0;
        }
    }

    public static synchronized void remove(Task t) {
        t.cancel = true;
        ACTIVE.remove(t);
        FINISHED.remove(t);
        save();
    }

    public static synchronized void clearFinished() {
        FINISHED.clear();
        save();
    }

    /** 活动任务在前，已完成任务在后。 */
    public static synchronized List<Task> all() {
        ensureLoaded();
        List<Task> out = new ArrayList<>();
        out.addAll(ACTIVE);
        out.addAll(FINISHED);
        return out;
    }

    public static synchronized int activeCount() {
        return ACTIVE.size();
    }
}
