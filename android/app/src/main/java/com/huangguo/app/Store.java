package com.huangguo.app;

import android.content.Context;
import android.content.SharedPreferences;

import org.json.JSONArray;
import org.json.JSONObject;

import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.List;

/** 收藏与播放历史：SharedPreferences + JSON，无需数据库。 */
public class Store {

    public static class Item {
        public String id = "", name = "", pic = "", remarks = "", ep = "1";
        public long pos = 0L, ts = 0L;
    }

    private static final String PREF = "huangguo";
    private static final String K_FAV = "fav";
    private static final String K_HIS = "his";
    private static final int MAX_HIS = 200;

    private static SharedPreferences prefs() {
        return App.CTX.getSharedPreferences(PREF, Context.MODE_PRIVATE);
    }

    private static List<Item> read(String key) {
        List<Item> out = new ArrayList<>();
        try {
            JSONArray a = new JSONArray(prefs().getString(key, "[]"));
            for (int i = 0; i < a.length(); i++) {
                JSONObject o = a.optJSONObject(i);
                if (o == null) continue;
                Item it = new Item();
                it.id = o.optString("id", "");
                it.name = o.optString("name", "");
                it.pic = o.optString("pic", "");
                it.remarks = o.optString("remarks", "");
                it.ep = o.optString("ep", "1");
                it.pos = o.optLong("pos", 0L);
                it.ts = o.optLong("ts", 0L);
                if (!it.id.isEmpty()) out.add(it);
            }
        } catch (Exception ignored) {
        }
        return out;
    }

    private static void write(String key, List<Item> list) {
        try {
            JSONArray a = new JSONArray();
            for (Item it : list) {
                JSONObject o = new JSONObject();
                o.put("id", it.id);
                o.put("name", it.name);
                o.put("pic", it.pic);
                o.put("remarks", it.remarks);
                o.put("ep", it.ep);
                o.put("pos", it.pos);
                o.put("ts", it.ts);
                a.put(o);
            }
            prefs().edit().putString(key, a.toString()).apply();
        } catch (Exception ignored) {
        }
    }

    // ---------------- 收藏 ----------------

    public static boolean isFav(String id) {
        if (id == null) return false;
        for (Item it : read(K_FAV)) {
            if (id.equals(it.id)) return true;
        }
        return false;
    }

    /** 返回切换后的状态：true=已收藏。 */
    public static boolean toggleFav(Site.Card c) {
        if (c == null || c.id == null) return false;
        List<Item> list = read(K_FAV);
        for (int i = 0; i < list.size(); i++) {
            if (c.id.equals(list.get(i).id)) {
                list.remove(i);
                write(K_FAV, list);
                return false;
            }
        }
        Item it = new Item();
        it.id = c.id;
        it.name = c.name == null ? "" : c.name;
        it.pic = c.pic == null ? "" : c.pic;
        it.remarks = c.remarks == null ? "" : c.remarks;
        it.ts = System.currentTimeMillis();
        list.add(0, it);
        write(K_FAV, list);
        return true;
    }

    public static void removeFav(String id) {
        List<Item> list = read(K_FAV);
        for (int i = 0; i < list.size(); i++) {
            if (id != null && id.equals(list.get(i).id)) {
                list.remove(i);
                break;
            }
        }
        write(K_FAV, list);
    }

    public static List<Site.Card> favoriteCards() {
        List<Site.Card> out = new ArrayList<>();
        for (Item it : read(K_FAV)) {
            out.add(new Site.Card(it.id, it.name, it.pic, "已收藏"));
        }
        return out;
    }

    // ---------------- 历史 ----------------

    public static void addHistory(String id, String name, String pic, String remarks,
                                  String ep, long pos) {
        if (id == null) return;
        List<Item> list = read(K_HIS);
        for (int i = 0; i < list.size(); i++) {
            if (id.equals(list.get(i).id)) {
                Item it = list.remove(i);
                it.ep = ep;
                it.pos = pos;
                it.ts = System.currentTimeMillis();
                if (name != null && !name.isEmpty()) it.name = name;
                if (pic != null && !pic.isEmpty()) it.pic = pic;
                list.add(0, it);
                write(K_HIS, list);
                return;
            }
        }
        Item it = new Item();
        it.id = id;
        it.name = name == null ? "" : name;
        it.pic = pic == null ? "" : pic;
        it.remarks = remarks == null ? "" : remarks;
        it.ep = ep == null ? "1" : ep;
        it.pos = pos;
        it.ts = System.currentTimeMillis();
        list.add(0, it);
        while (list.size() > MAX_HIS) list.remove(list.size() - 1);
        write(K_HIS, list);
    }

    public static Item historyOf(String id) {
        if (id == null) return null;
        for (Item it : read(K_HIS)) {
            if (id.equals(it.id)) return it;
        }
        return null;
    }

    public static void removeHistory(String id) {
        List<Item> list = read(K_HIS);
        for (int i = 0; i < list.size(); i++) {
            if (id != null && id.equals(list.get(i).id)) {
                list.remove(i);
                break;
            }
        }
        write(K_HIS, list);
    }

    public static List<Item> historyItems() {
        List<Item> list = read(K_HIS);
        Collections.sort(list, new Comparator<Item>() {
            @Override
            public int compare(Item a, Item b) {
                return Long.compare(b.ts, a.ts);
            }
        });
        return list;
    }

    public static List<Site.Card> historyCards() {
        List<Site.Card> out = new ArrayList<>();
        for (Item it : historyItems()) {
            out.add(new Site.Card(it.id, it.name, it.pic, "看到第" + Site.pad2(it.ep) + "集 · 续播"));
        }
        return out;
    }
}
