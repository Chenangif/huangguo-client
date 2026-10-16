package com.huangguo.app;

import org.json.JSONArray;
import org.json.JSONObject;

import java.net.URLEncoder;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/** 站点解析层：与 Windows 版 huangguo_downloader.py 的解析逻辑一一对应。 */
public class Site {

    public static final String SITE = "https://huangguoai.com";
    public static final String UA = Http.UA;

    public static final String[][] TABS = {
            {"首页", "home"},
            {"AI成人短剧", "ai-duanju"},
            {"AI成人漫剧", "ai-manju"},
            {"AI换脸", "ai-huanlian"},
            {"AI魔改", "ai-mogai"},
            {"排行榜", "ranks/hot"},
            {"收藏", "fav"},
            {"历史", "hist"},
    };

    public static class Card {
        public String id, name, pic, remarks;
        public Card(String id, String name, String pic, String remarks) {
            this.id = id; this.name = name; this.pic = pic; this.remarks = remarks;
        }
    }

    public static class Episode {
        public String ep, name, url;
        public Episode(String ep, String name, String url) {
            this.ep = ep; this.name = name; this.url = url;
        }
    }

    public static class Detail {
        public String title = "", desc = "", cover = "";
        public List<Episode> episodes = new ArrayList<>();
    }

    // ---------------- 列表 ----------------

    private static final Map<String, String> REF =
            Collections.singletonMap("Referer", SITE + "/");

    /** 取文本：OkHttp 直连优先，失败则用 WebView（Chromium）兜底。 */
    static String getText(String url) throws Exception {
        try {
            return Http.get(url, REF);
        } catch (Exception e) {
            String t = WebFetch.text(url, REF);
            if (t != null && !t.isEmpty()) return t;
            throw e;
        }
    }

    public static List<Card> fetchHome() throws Exception {
        String html = getText(SITE + "/");
        List<Card> out = parseCards(html);
        if (out.isEmpty()) out = parseCardsLoose(html);
        if (out.isEmpty()) out = fetchAnyCategory();      // HTML 解析不到 → 回退 JSON 接口
        return out;
    }

    public static List<Card> fetchRanks() throws Exception {
        String html = getText(SITE + "/ranks/hot/");
        List<Card> out = parseRanks(html);
        if (out.isEmpty()) out = parseCards(html);
        if (out.isEmpty()) out = fetchAnyCategory();
        return out;
    }

    /** 依次尝试各分类 JSON 接口，取第一个有数据的。 */
    public static List<Card> fetchAnyCategory() {
        String[] cats = {"ai-duanju", "ai-manju", "ai-huanlian", "ai-mogai"};
        for (String c : cats) {
            try {
                List<Card> r = fetchCategory(c, 1);
                if (!r.isEmpty()) return r;
            } catch (Exception ignored) {
            }
        }
        return new ArrayList<>();
    }

    /** 兜底：不依赖 hg-drama-card 类名，直接从 /video/{id}/ 链接抓标题与图。 */
    public static List<Card> parseCardsLoose(String html) {
        List<Card> out = new ArrayList<>();
        if (html == null || html.isEmpty()) return out;
        Set<String> seen = new HashSet<>();
        Matcher m = Pattern.compile(
                "<a\\s+[^>]*href=\"[^\"]*?/video/(\\d+)/[^\"]*\"[^>]*>([\\s\\S]{0,1200}?)</a>")
                .matcher(html);
        while (m.find()) {
            String id = m.group(1);
            if (!seen.add(id)) continue;
            String block = m.group(2);
            String pic = first(block, "data-src=\"([^\"]+)\"");
            if (pic == null) pic = first(block, "src=\"([^\"]+)\"");
            String title = first(block, "alt=\"([^\"]+)\"");
            if (title == null || title.isEmpty()) title = stripTags(block);
            if (title == null || title.isEmpty() || title.length() > 60) continue;
            out.add(new Card(id, title, fixUrl(pic), ""));
        }
        return out;
    }

    public static List<Card> search(String kw) throws Exception {
        String url = SITE + "/search/video/" + URLEncoder.encode(kw, "UTF-8") + "/";
        String html = getText(url);
        List<Card> out = parseCards(html);
        if (out.isEmpty()) out = parseCardsLoose(html);
        return out;
    }

    /** JSON API：/api/videos/category/{cat}?page=N&size=21 */
    public static List<Card> fetchCategory(String cat, int page) throws Exception {
        String url = SITE + "/api/videos/category/" + URLEncoder.encode(cat, "UTF-8")
                + "?page=" + page + "&size=21";
        String text = getText(url);
        int p0 = text.indexOf('{');
        int p1 = text.lastIndexOf('}');
        if (p0 > 0 && p1 > p0) text = text.substring(p0, p1 + 1);
        List<Card> out = new ArrayList<>();
        JSONObject root = new JSONObject(text);
        JSONObject data = root.optJSONObject("data");
        if (data == null) return out;
        JSONArray items = data.optJSONArray("items");
        if (items == null) return out;
        for (int i = 0; i < items.length(); i++) {
            JSONObject it = items.optJSONObject(i);
            if (it == null) continue;
            String id = it.optString("id", "");
            String title = it.optString("title", "").trim();
            if (id.isEmpty() || title.isEmpty() || "null".equals(id)) continue;
            StringBuilder rem = new StringBuilder();
            int ec = it.optInt("episode_count", 0);
            if (ec > 0) rem.append("更新至").append(ec).append("集");
            String score = it.optString("score", "");
            if (!score.isEmpty() && !"null".equals(score)) {
                if (rem.length() > 0) rem.append(" · ");
                rem.append(score).append("分");
            }
            out.add(new Card(id, title, fixUrl(it.optString("cover", "")), rem.toString()));
        }
        return out;
    }

    // ---------------- HTML 卡片 ----------------

    public static List<Card> parseCards(String html) {
        List<Card> out = new ArrayList<>();
        if (html == null || html.isEmpty()) return out;
        int b = html.indexOf("<body");
        String body = (b >= 0) ? html.substring(b) : html;
        Matcher m = Pattern.compile("<div\\s+class=\"[^\"]*\\bhg-drama-card\\b[^\"]*\"[^>]*>").matcher(body);
        List<Integer> starts = new ArrayList<>();
        while (m.find()) starts.add(m.end());
        Set<String> seen = new HashSet<>();
        for (int i = 0; i < starts.size(); i++) {
            int s = starts.get(i);
            int e = (i + 1 < starts.size()) ? starts.get(i + 1) : body.length();
            Card c = parseCard(body.substring(s, Math.min(e, body.length())));
            if (c != null && seen.add(c.id)) out.add(c);
        }
        return out;
    }

    private static Card parseCard(String block) {
        String vid = first(block, "href=\"[^\"]*?/video/(\\d+)/[^\"]*\"");
        if (vid == null) return null;
        String pic = first(block, "data-src=\"(https?://[^\"]+)\"");
        if (pic == null) pic = first(block, "src=\"(https?://[^\"]+)\"");
        if (pic == null) pic = first(block, "data-src=\"([^\"]+)\"");

        String title = first(block, "hg-drama-card__title[^>]*>([\\s\\S]*?)</a>");
        if (title != null) title = stripTags(title);
        if (title == null || title.isEmpty()) {
            String alt = first(block, "<img[^>]*\\balt=\"([^\"]+)\"");
            if (alt != null && !alt.trim().isEmpty()) title = alt.trim();
        }
        if (title == null || title.isEmpty()) {
            String tt = first(block, "<a[^>]+href=\"[^\"]*/video/\\d+/\"?\"[^>]*>([\\s\\S]*?)</a>");
            if (tt != null) title = stripTags(tt);
        }
        if (title == null || title.isEmpty()) return null;

        String ep = first(block, "hg-drama-card__episode[^>]*>([\\s\\S]*?)</span>");
        String sc = first(block, "hg-drama-card__score[^>]*>([\\s\\S]*?)</span>");
        String rem = (ep != null) ? stripTags(ep) : "";
        String score = (sc != null) ? stripTags(sc) : "";
        String remarks = (!rem.isEmpty() && !score.isEmpty()) ? (rem + " · " + score)
                : (!rem.isEmpty() ? rem : score);
        return new Card(vid, title, fixUrl(pic), remarks);
    }

    public static List<Card> parseRanks(String html) {
        List<Card> out = new ArrayList<>();
        if (html == null || html.isEmpty()) return out;
        Matcher lm = Pattern.compile("<div\\s+class=\"[^\"]*\\bhg-rank-list\\b[^\"]*\"[^>]*>").matcher(html);
        String slice = lm.find() ? html.substring(lm.end()) : html;
        Matcher m = Pattern.compile("<div\\s+class=\"hg-rank-item\"").matcher(slice);
        List<Integer> starts = new ArrayList<>();
        while (m.find()) starts.add(m.start());
        Set<String> seen = new HashSet<>();
        for (int i = 0; i < starts.size(); i++) {
            int s = starts.get(i);
            int e = (i + 1 < starts.size()) ? starts.get(i + 1) : slice.length();
            String block = slice.substring(s, Math.min(e, slice.length()));
            String vid = first(block, "href=\"[^\"]*?/video/(\\d+)/[^\"]*\"");
            if (vid == null || !seen.add(vid)) continue;
            String pic = first(block, "data-src=\"(https?://[^\"]+)\"");
            if (pic == null) pic = first(block, "data-src=\"([^\"]+)\"");
            String title = first(block, "hg-rank-item__title[^>]*>([\\s\\S]*?)</h2>");
            if (title != null) title = stripTags(title);
            if (title == null || title.isEmpty()) {
                String alt = first(block, "<img[^>]*\\balt=\"([^\"]+)\"");
                if (alt != null) title = alt.trim();
            }
            if (title == null || title.isEmpty()) continue;
            String tags = first(block, "hg-rank-item__tags[^>]*>([\\s\\S]*?)</div>");
            out.add(new Card(vid, title, fixUrl(pic), tags != null ? stripTags(tags) : ""));
        }
        return out;
    }

    // ---------------- 详情 ----------------

    public static Detail fetchDetail(String id) throws Exception {
        String html = getText(SITE + "/video/" + id + "/");
        Detail d = new Detail();
        JSONObject data = initialData(html);
        if (data != null) {
            d.title = data.optString("title", "");
            d.desc = data.optString("description", "");
            d.cover = fixUrl(data.optString("coverSrc", ""));
        }
        if (d.title == null || d.title.isEmpty()) {
            String t = first(html, "<title>([\\s\\S]*?)</title>");
            d.title = (t != null) ? stripTags(t) : "";
        }
        d.episodes = parseEpisodes(html, id);
        return d;
    }

    private static JSONObject initialData(String html) {
        if (html == null) return null;
        Matcher m = Pattern.compile("id=\"videoInitialData\"[^>]*>([\\s\\S]*?)</script>").matcher(html);
        if (!m.find()) return null;
        try {
            return new JSONObject(m.group(1).trim());
        } catch (Exception e) {
            return null;
        }
    }

    public static List<Episode> parseEpisodes(String html, String id) {
        List<Episode> out = new ArrayList<>();
        Set<String> seen = new HashSet<>();
        Matcher m = Pattern.compile("href=\"(/video/\\d+/ep-(\\d+)/)\"[^>]*data-ep-id=\"(\\d+)\"").matcher(html);
        while (m.find()) {
            String ep = m.group(3);
            if (!seen.add(ep)) continue;
            out.add(new Episode(ep, "第" + pad2(ep) + "集", fixUrl(m.group(1))));
        }
        if (out.isEmpty()) {
            Matcher m2 = Pattern.compile("href=\"(/video/(\\d+)/ep-(\\d+)/)\"").matcher(html);
            while (m2.find()) {
                String ep = m2.group(3);
                if (!seen.add(ep)) continue;
                out.add(new Episode(ep, "第" + pad2(ep) + "集", fixUrl(m2.group(1))));
            }
        }
        if (out.isEmpty()) {
            out.add(new Episode("1", "第01集", SITE + "/video/" + id + "/"));
        }
        return out;
    }

    /** 取某集的 m3u8 地址。 */
    public static String fetchPlayUrl(String id, String ep) throws Exception {
        String page = SITE + "/video/" + id + "/ep-" + ep + "/";
        String html = getText(page);
        String play = null;
        JSONObject data = initialData(html);
        if (data != null) {
            JSONObject srcs = data.optJSONObject("epPlaySrcs");
            if (srcs != null) {
                play = srcs.optString(ep, "");
                if (play.isEmpty()) {
                    // 有些页面用 1-based 下标或补零键名
                    play = srcs.optString(pad2(ep), "");
                }
            }
            if (play == null || play.isEmpty()) play = data.optString("videoSrc", "");
            if (play == null || play.isEmpty()) play = data.optString("previewSrc", "");
            if (play == null || play.isEmpty()) play = data.optString("contentUrl", "");
        }
        if (play == null || play.isEmpty()) {
            Matcher m = Pattern.compile("(https?://[^\"'\\s]+\\.m3u8[^\"'\\s]*)").matcher(html);
            if (m.find()) play = m.group(1);
        }
        return play;
    }

    // ---------------- 工具 ----------------

    public static String stripTags(String s) {
        if (s == null) return "";
        return s.replaceAll("<[^>]*>", "")
                .replace("&nbsp;", " ")
                .replace("&amp;", "&")
                .replace("&quot;", "\"")
                .trim();
    }

    public static String fixUrl(String u) {
        if (u == null || u.isEmpty()) return "";
        if (u.startsWith("//")) return "https:" + u;
        if (u.startsWith("/")) return SITE + u;
        return u;
    }

    public static String pad2(String s) {
        if (s == null) return "01";
        StringBuilder t = new StringBuilder(s);
        while (t.length() < 2) t.insert(0, "0");
        return t.toString();
    }

    private static String first(String s, String regex) {
        Matcher m = Pattern.compile(regex).matcher(s);
        return m.find() ? m.group(1) : null;
    }
}
