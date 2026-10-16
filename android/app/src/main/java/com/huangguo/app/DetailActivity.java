package com.huangguo.app;

import android.Manifest;
import android.content.Intent;
import android.os.Build;
import android.os.Bundle;
import android.view.View;
import android.widget.Button;
import android.widget.ImageView;
import android.widget.TextView;
import android.widget.Toast;

import androidx.appcompat.app.AppCompatActivity;
import androidx.core.content.ContextCompat;
import androidx.recyclerview.widget.GridLayoutManager;
import androidx.recyclerview.widget.RecyclerView;

import java.util.ArrayList;
import java.util.List;

public class DetailActivity extends AppCompatActivity {

    private String id, name, pic, remarks, playEp;
    private final List<Site.Episode> eps = new ArrayList<>();
    private EpisodeAdapter adapter;
    private Button btnFav, btnResume;
    private boolean autoPlayed = false;

    @Override
    protected void onCreate(Bundle b) {
        super.onCreate(b);
        setContentView(R.layout.activity_detail);

        id = getIntent().getStringExtra("id");
        name = getIntent().getStringExtra("name");
        pic = getIntent().getStringExtra("pic");
        remarks = getIntent().getStringExtra("remarks");
        playEp = getIntent().getStringExtra("playEp");
        if (id == null) {
            finish();
            return;
        }

        ImageView cover = findViewById(R.id.ivCover);
        TextView tvTitle = findViewById(R.id.tvTitle);
        TextView tvMeta = findViewById(R.id.tvMeta);
        TextView tvDesc = findViewById(R.id.tvDesc);
        RecyclerView rvEp = findViewById(R.id.rvEp);
        btnFav = findViewById(R.id.btnFav);
        btnResume = findViewById(R.id.btnResume);

        tvTitle.setText(name == null ? "" : name);
        tvMeta.setText(remarks == null ? "" : remarks);
        CoverLoader.load(this, pic, cover);

        refreshFavBtn();
        refreshResumeBtn();
        btnFav.setOnClickListener(v -> {
            boolean fav = Store.toggleFav(new Site.Card(id,
                    name == null ? "" : name, pic == null ? "" : pic,
                    remarks == null ? "" : remarks));
            refreshFavBtn();
            Toast.makeText(this, fav ? "已收藏" : "已取消收藏", Toast.LENGTH_SHORT).show();
        });
        btnResume.setOnClickListener(v -> {
            Store.Item h = Store.historyOf(id);
            if (h == null) return;
            int idx = indexOfEp(h.ep);
            openPlayer(idx >= 0 ? idx : 0, h.pos);
        });

        rvEp.setLayoutManager(new GridLayoutManager(this, 4));
        rvEp.setNestedScrollingEnabled(false);
        adapter = new EpisodeAdapter(eps, new EpisodeAdapter.Callback() {
            @Override
            public void onPlay(int pos) {
                openPlayer(pos, 0);
            }

            @Override
            public void onDownload(int pos) {
                startDownload(pos);
            }
        });
        rvEp.setAdapter(adapter);

        new Thread(() -> {
            try {
                Site.Detail d = Site.fetchDetail(id);
                runOnUiThread(() -> {
                    if (d.title != null && !d.title.isEmpty()) tvTitle.setText(d.title);
                    tvMeta.setText((remarks == null || remarks.isEmpty() ? "" : remarks + " · ")
                            + d.episodes.size() + " 集");
                    tvDesc.setText(d.desc == null ? "" : d.desc);
                    eps.clear();
                    eps.addAll(d.episodes);
                    adapter.notifyDataSetChanged();
                    if (!d.cover.isEmpty()) {
                        CoverLoader.load(DetailActivity.this, d.cover, cover);
                    }
                    refreshResumeBtn();
                    tryAutoPlay();
                });
            } catch (Exception e) {
                runOnUiThread(() -> Toast.makeText(this, "详情加载失败：" + e, Toast.LENGTH_SHORT).show());
            }
        }).start();
    }

    private int indexOfEp(String ep) {
        if (ep == null) return -1;
        for (int i = 0; i < eps.size(); i++) {
            if (ep.equals(eps.get(i).ep)) return i;
        }
        try {
            int n = Integer.parseInt(ep);
            for (int i = 0; i < eps.size(); i++) {
                try {
                    if (Integer.parseInt(eps.get(i).ep) == n) return i;
                } catch (NumberFormatException ignored) {
                }
            }
        } catch (NumberFormatException ignored) {
        }
        return -1;
    }

    /** 从「历史」页点进来时自动续播。 */
    private void tryAutoPlay() {
        if (autoPlayed || playEp == null || eps.isEmpty()) return;
        autoPlayed = true;
        int idx = indexOfEp(playEp);
        Store.Item h = Store.historyOf(id);
        long pos = (h != null && playEp.equals(h.ep)) ? h.pos : 0L;
        openPlayer(idx >= 0 ? idx : 0, pos);
    }

    private void refreshFavBtn() {
        boolean fav = Store.isFav(id);
        btnFav.setText(fav ? "★ 已收藏" : "☆ 收藏");
    }

    private void refreshResumeBtn() {
        Store.Item h = Store.historyOf(id);
        if (h != null && !eps.isEmpty()) {
            btnResume.setVisibility(View.VISIBLE);
            btnResume.setText("▶ 续播 第" + Site.pad2(h.ep) + "集");
        } else if (h != null) {
            btnResume.setVisibility(View.VISIBLE);
            btnResume.setText("▶ 续播");
        } else {
            btnResume.setVisibility(View.GONE);
        }
    }

    private void openPlayer(int pos, long startPos) {
        if (pos < 0 || pos >= eps.size()) return;
        ArrayList<String> list = new ArrayList<>();
        for (Site.Episode e : eps) list.add(e.ep);
        Intent i = new Intent(this, PlayerActivity.class);
        i.putExtra("id", id);
        i.putExtra("name", name);
        i.putExtra("pic", pic == null ? "" : pic);
        i.putStringArrayListExtra("eps", list);
        i.putExtra("index", pos);
        i.putExtra("startPos", startPos);
        startActivity(i);
    }

    private void startDownload(int pos) {
        if (pos < 0 || pos >= eps.size()) return;
        if (Build.VERSION.SDK_INT >= 33 && ContextCompat.checkSelfPermission(this,
                Manifest.permission.POST_NOTIFICATIONS) != android.content.pm.PackageManager.PERMISSION_GRANTED) {
            requestPermissions(new String[]{Manifest.permission.POST_NOTIFICATIONS}, 77);
            Toast.makeText(this, "请先允许通知，再点一次下载", Toast.LENGTH_SHORT).show();
            return;
        }
        if (Build.VERSION.SDK_INT <= 28 && ContextCompat.checkSelfPermission(this,
                Manifest.permission.WRITE_EXTERNAL_STORAGE) != android.content.pm.PackageManager.PERMISSION_GRANTED) {
            requestPermissions(new String[]{Manifest.permission.WRITE_EXTERNAL_STORAGE}, 78);
            Toast.makeText(this, "请先允许存储权限，再点一次下载", Toast.LENGTH_SHORT).show();
            return;
        }
        Site.Episode e = eps.get(pos);
        String title = name == null ? ("视频" + id) : name;
        Downloads.enqueue(id, e.ep, title);
        Intent svc = new Intent(this, DownloadService.class);
        ContextCompat.startForegroundService(this, svc);
        Toast.makeText(this, "已加入下载队列：" + e.name + "\n（可在右上角「下载」查看进度）",
                Toast.LENGTH_SHORT).show();
    }
}
