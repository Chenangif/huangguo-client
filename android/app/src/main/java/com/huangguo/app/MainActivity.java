package com.huangguo.app;

import android.content.ClipData;
import android.content.ClipboardManager;
import android.content.Context;
import android.content.Intent;
import android.net.ConnectivityManager;
import android.net.NetworkInfo;
import android.os.Build;
import android.os.Bundle;
import android.text.TextUtils;
import android.view.View;
import android.widget.Button;
import android.widget.EditText;
import android.widget.ProgressBar;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;

import androidx.appcompat.app.AlertDialog;
import androidx.appcompat.app.AppCompatActivity;
import androidx.recyclerview.widget.GridLayoutManager;
import androidx.recyclerview.widget.RecyclerView;

import com.google.android.material.tabs.TabLayout;

import java.util.ArrayList;
import java.util.List;

public class MainActivity extends AppCompatActivity {

    private RecyclerView rv;
    private ProgressBar pb;
    private TextView tvEmpty;
    private final List<Site.Card> cards = new ArrayList<>();
    private CardAdapter adapter;

    private String currentTab = "home";
    private String searchKw = null;
    private int page = 1;
    private boolean loading = false;
    private boolean hasMore = false;

    @Override
    protected void onCreate(Bundle b) {
        super.onCreate(b);
        setContentView(R.layout.activity_main);

        rv = findViewById(R.id.rv);
        pb = findViewById(R.id.pb);
        tvEmpty = findViewById(R.id.tvEmpty);
        EditText et = findViewById(R.id.etSearch);

        GridLayoutManager lm = new GridLayoutManager(this, 3);
        rv.setLayoutManager(lm);
        adapter = new CardAdapter(cards, this::openCard, this::onCardLong);
        rv.setAdapter(adapter);

        TabLayout tabs = findViewById(R.id.tabs);
        for (String[] t : Site.TABS) {
            tabs.addTab(tabs.newTab().setText(t[0]));
        }
        tabs.addOnTabSelectedListener(new TabLayout.OnTabSelectedListener() {
            @Override
            public void onTabSelected(TabLayout.Tab tab) {
                int p = tab.getPosition();
                if (p < 0 || p >= Site.TABS.length) return;
                currentTab = Site.TABS[p][1];
                searchKw = null;
                load(true, 0);
            }

            @Override public void onTabUnselected(TabLayout.Tab tab) { }
            @Override public void onTabReselected(TabLayout.Tab tab) {
                if ("fav".equals(currentTab) || "hist".equals(currentTab)) load(true, 0);
            }
        });

        et.setOnEditorActionListener((v, actionId, event) -> {
            if (actionId == android.view.inputmethod.EditorInfo.IME_ACTION_SEARCH) {
                doSearch(et.getText().toString().trim());
                return true;
            }
            return false;
        });
        Button btnSearch = findViewById(R.id.btnSearch);
        btnSearch.setOnClickListener(v -> doSearch(et.getText().toString().trim()));
        Button btnDiag = findViewById(R.id.btnDiag);
        btnDiag.setOnClickListener(v -> runDiagnostics());
        Button btnDl = findViewById(R.id.btnDl);
        btnDl.setOnClickListener(v -> startActivity(new Intent(this, DownloadsActivity.class)));

        rv.addOnScrollListener(new RecyclerView.OnScrollListener() {
            @Override
            public void onScrolled(@androidx.annotation.NonNull RecyclerView r, int dx, int dy) {
                GridLayoutManager g = (GridLayoutManager) r.getLayoutManager();
                if (g == null || loading || !hasMore) return;
                int last = g.findLastVisibleItemPosition();
                if (last >= g.getItemCount() - 6) {
                    load(false, 0);
                }
            }
        });

        load(true, 0);
    }

    private void openCard(Site.Card c) {
        Intent i = new Intent(this, DetailActivity.class);
        i.putExtra("id", c.id);
        i.putExtra("name", c.name);
        i.putExtra("pic", c.pic);
        i.putExtra("remarks", c.remarks);
        if ("hist".equals(currentTab)) {
            Store.Item h = Store.historyOf(c.id);
            if (h != null) i.putExtra("playEp", h.ep);   // 历史记录点击直接续播
        }
        startActivity(i);
    }

    private boolean onCardLong(Site.Card c) {
        if ("fav".equals(currentTab)) {
            Store.removeFav(c.id);
            Toast.makeText(this, "已取消收藏", Toast.LENGTH_SHORT).show();
            load(true, 0);
            return true;
        }
        if ("hist".equals(currentTab)) {
            Store.removeHistory(c.id);
            Toast.makeText(this, "已删除该条历史", Toast.LENGTH_SHORT).show();
            load(true, 0);
            return true;
        }
        boolean fav = Store.toggleFav(c);
        Toast.makeText(this, fav ? "已收藏（可在「收藏」页查看）" : "已取消收藏", Toast.LENGTH_SHORT).show();
        return true;
    }

    private void doSearch(String kw) {
        searchKw = kw.isEmpty() ? null : kw;
        load(true, 0);
    }

    private void load(final boolean reset, final int attempt) {
        if (loading) return;
        loading = true;
        if (reset) {
            page = 1;
            hasMore = false;
        }
        final int wantPage = page;
        final String tab = currentTab;
        final String kw = searchKw;
        pb.setVisibility(View.VISIBLE);
        tvEmpty.setVisibility(View.GONE);

        new Thread(() -> {
            List<Site.Card> res = new ArrayList<>();
            String err = null;
            try {
                if (kw != null) {
                    res = Site.search(kw);
                } else if ("home".equals(tab)) {
                    res = Site.fetchHome();
                } else if (tab.startsWith("ranks")) {
                    res = Site.fetchRanks();
                } else if ("fav".equals(tab)) {
                    res = Store.favoriteCards();
                } else if ("hist".equals(tab)) {
                    res = Store.historyCards();
                } else {
                    res = Site.fetchCategory(tab, wantPage);
                }
            } catch (Exception e) {
                err = e.getClass().getSimpleName()
                        + (e.getMessage() == null ? "" : ": " + e.getMessage());
            }
            final List<Site.Card> out = res;
            final String error = err;
            runOnUiThread(() -> {
                loading = false;
                pb.setVisibility(View.GONE);

                if (error != null) {
                    if (attempt < 1) {
                        tvEmpty.setText("加载中（重试）…");
                        tvEmpty.setVisibility(View.VISIBLE);
                        new android.os.Handler().postDelayed(() -> load(reset, attempt + 1), 800);
                        return;
                    }
                    tvEmpty.setText("加载失败：\n" + error + "\n\n点右上角「诊断」查看网络详情");
                    tvEmpty.setVisibility(View.VISIBLE);
                    Toast.makeText(this, "加载失败：" + error, Toast.LENGTH_LONG).show();
                    return;
                }

                if (reset) {
                    cards.clear();
                    rv.scrollToPosition(0);
                }
                cards.addAll(out);
                boolean paged = (kw == null) && !"home".equals(tab) && !tab.startsWith("ranks")
                        && !"fav".equals(tab) && !"hist".equals(tab);
                hasMore = paged && !out.isEmpty();
                adapter.notifyDataSetChanged();
                if (hasMore) page = wantPage + 1;

                if (cards.isEmpty()) {
                    if ("fav".equals(tab)) {
                        tvEmpty.setText("还没有收藏\n长按任意海报即可收藏");
                    } else if ("hist".equals(tab)) {
                        tvEmpty.setText("还没有播放记录");
                    } else {
                        tvEmpty.setText("暂无内容\n（站点可能不可达，点「诊断」查看详情）");
                    }
                    tvEmpty.setVisibility(View.VISIBLE);
                } else {
                    tvEmpty.setVisibility(View.GONE);
                }
            });
        }).start();
    }

    // ---------------- 诊断 ----------------

    private void runDiagnostics() {
        final AlertDialog wait = new AlertDialog.Builder(this)
                .setTitle("网络诊断")
                .setMessage("正在检测…")
                .setCancelable(false)
                .show();

        new Thread(() -> {
            StringBuilder sb = new StringBuilder();
            sb.append("设备：").append(Build.MANUFACTURER).append(' ')
                    .append(Build.MODEL).append(" / Android ")
                    .append(Build.VERSION.RELEASE).append(" (API ")
                    .append(Build.VERSION.SDK_INT).append(")\n");
            sb.append("网络：").append(networkInfo()).append('\n');
            sb.append("DNS：").append(Http.dnsProbe("huangguoai.com")).append('\n');
            sb.append("CDN DNS：").append(Http.dnsProbe("pic.wirqed.cn")).append('\n');
            sb.append('\n');

            sb.append("[1] 首页 HTML\n  ").append(Http.probe(Site.SITE + "/")).append('\n');
            String html = null;
            try {
                html = Http.get(Site.SITE + "/");
                sb.append("  解析卡片：").append(Site.parseCards(html).size()).append(" 张\n");
            } catch (Exception e) {
                sb.append("  解析异常：").append(e).append('\n');
            }

            String api = Site.SITE + "/api/videos/category/ai-duanju?page=1&size=21";
            sb.append("\n[2] 分类接口\n  ").append(Http.probe(api)).append('\n');
            try {
                sb.append("  解析条目：").append(Site.fetchCategory("ai-duanju", 1).size())
                        .append(" 条\n");
            } catch (Exception e) {
                sb.append("  解析异常：").append(e).append('\n');
            }

            sb.append("\n[3] 封面下载 + AES 解密\n");
            try {
                List<Site.Card> cs = (html != null) ? Site.parseCards(html) : new ArrayList<>();
                if (cs.isEmpty()) cs = Site.fetchAnyCategory();
                if (cs.isEmpty()) {
                    sb.append("  跳过（拿不到卡片）\n");
                } else {
                    Site.Card c = cs.get(0);
                    sb.append("  URL：").append(TextUtils.isEmpty(c.pic) ? "(空)" : c.pic).append('\n');
                    if (!TextUtils.isEmpty(c.pic)) {
                        byte[] raw = Http.getBytes(c.pic, java.util.Collections
                                .singletonMap("Referer", Site.SITE + "/"));
                        sb.append("  原始：").append(raw.length).append(" bytes\n");
                        byte[] dec = CryptoUtil.decryptCover(raw);
                        sb.append("  解密后：").append(dec == null ? 0 : dec.length).append(" bytes, ")
                                .append(CryptoUtil.looksLikeImage(dec) ? "是图片 ✓" : "不像图片 ✗")
                                .append('\n');
                        android.graphics.BitmapFactory.Options o =
                                new android.graphics.BitmapFactory.Options();
                        o.inJustDecodeBounds = true;
                        android.graphics.BitmapFactory.decodeByteArray(dec, 0, dec.length, o);
                        sb.append("  尺寸：").append(o.outWidth).append('x').append(o.outHeight)
                                .append('\n');
                    }
                }
            } catch (Exception e) {
                sb.append("  异常：").append(e).append('\n');
            }

            sb.append("\n[4] WebView 兜底取页（等同手机浏览器）\n");
            try {
                String t = WebFetch.text(Site.SITE + "/",
                        java.util.Collections.singletonMap("Referer", Site.SITE + "/"));
                if (t == null || t.isEmpty()) {
                    sb.append("  FAIL: 返回空\n");
                } else {
                    sb.append("  OK ").append(t.length()).append(" 字符，解析卡片 ")
                            .append(Site.parseCards(t).size()).append(" 张\n");
                }
            } catch (Exception e) {
                sb.append("  异常：").append(e).append('\n');
            }

            final String text = sb.toString();
            runOnUiThread(() -> {
                try { wait.dismiss(); } catch (Exception ignored) { }
                showDiagResult(text);
            });
        }).start();
    }

    private void showDiagResult(String text) {
        TextView tv = new TextView(this);
        tv.setText(text);
        tv.setTextIsSelectable(true);
        tv.setTextSize(12f);
        tv.setPadding(32, 24, 32, 24);
        ScrollView sv = new ScrollView(this);
        sv.addView(tv);

        new AlertDialog.Builder(this)
                .setTitle("网络诊断结果")
                .setView(sv)
                .setPositiveButton("复制", (d, w) -> {
                    ClipboardManager cm =
                            (ClipboardManager) getSystemService(Context.CLIPBOARD_SERVICE);
                    if (cm != null) cm.setPrimaryClip(ClipData.newPlainText("diag", text));
                    Toast.makeText(this, "已复制", Toast.LENGTH_SHORT).show();
                })
                .setNegativeButton("关闭", null)
                .show();
    }

    private String networkInfo() {
        try {
            ConnectivityManager cm =
                    (ConnectivityManager) getSystemService(Context.CONNECTIVITY_SERVICE);
            if (cm == null) return "未知";
            NetworkInfo ni = cm.getActiveNetworkInfo();
            if (ni == null) return "无网络连接";
            return ni.getTypeName() + " / " + ni.getSubtypeName() + " / connected="
                    + ni.isConnected();
        } catch (Exception e) {
            return "未知 (" + e.getClass().getSimpleName() + ")";
        }
    }
}
