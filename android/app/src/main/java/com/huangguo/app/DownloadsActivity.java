package com.huangguo.app;

import android.content.Intent;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.view.LayoutInflater;
import android.view.View;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.ProgressBar;
import android.widget.TextView;
import android.widget.Toast;

import androidx.annotation.NonNull;
import androidx.appcompat.app.AppCompatActivity;
import androidx.core.content.FileProvider;
import androidx.recyclerview.widget.LinearLayoutManager;
import androidx.recyclerview.widget.RecyclerView;

import java.io.File;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

/** 下载管理：进度/暂停/继续/取消/重试/播放/删除。 */
public class DownloadsActivity extends AppCompatActivity {

    private final Handler handler = new Handler(Looper.getMainLooper());
    private final List<Downloads.Task> data = new ArrayList<>();
    private Adapter adapter;
    private TextView tvEmpty;
    private RecyclerView rv;
    private final Runnable tick = new Runnable() {
        @Override
        public void run() {
            refresh();
            handler.postDelayed(this, 600);
        }
    };

    @Override
    protected void onCreate(Bundle b) {
        super.onCreate(b);
        setContentView(R.layout.activity_downloads);
        setTitle("下载管理");

        tvEmpty = findViewById(R.id.tvEmpty);
        rv = findViewById(R.id.rv);
        rv.setLayoutManager(new LinearLayoutManager(this));
        adapter = new Adapter();
        rv.setAdapter(adapter);
        refresh();
    }

    @Override
    protected void onResume() {
        super.onResume();
        handler.post(tick);
    }

    @Override
    protected void onPause() {
        super.onPause();
        handler.removeCallbacks(tick);
    }

    private void refresh() {
        data.clear();
        data.addAll(Downloads.all());
        adapter.notifyDataSetChanged();
        tvEmpty.setVisibility(data.isEmpty() ? View.VISIBLE : View.GONE);
    }

    /** 启动/唤醒下载服务。 */
    private void kick() {
        Intent svc = new Intent(this, DownloadService.class);
        androidx.core.content.ContextCompat.startForegroundService(this, svc);
    }

    private void play(Downloads.Task t) {
        try {
            Intent i = new Intent(Intent.ACTION_VIEW);
            Uri u;
            if (t.uri.startsWith("/")) {
                File f = new File(t.uri);
                if (!f.exists()) {
                    Toast.makeText(this, "文件已不存在", Toast.LENGTH_SHORT).show();
                    return;
                }
                u = FileProvider.getUriForFile(this, getPackageName() + ".fileprovider", f);
                i.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
            } else {
                u = Uri.parse(t.uri);
                i.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
            }
            i.setDataAndType(u, "video/*");
            startActivity(Intent.createChooser(i, "播放"));
        } catch (Exception e) {
            Toast.makeText(this, "无法播放：" + e.getMessage(), Toast.LENGTH_SHORT).show();
        }
    }

    private void deleteFile(Downloads.Task t) {
        try {
            if (t.uri.startsWith("/")) {
                File f = new File(t.uri);
                if (f.exists()) f.delete();
            } else if (Build.VERSION.SDK_INT >= 29) {
                try {
                    getContentResolver().delete(Uri.parse(t.uri), null, null);
                } catch (Exception ignored) {
                }
            }
        } catch (Exception ignored) {
        }
        Downloads.remove(t);
        refresh();
        Toast.makeText(this, "已删除", Toast.LENGTH_SHORT).show();
    }

    private static String size(long b) {
        if (b <= 0) return "";
        if (b < 1024 * 1024) return String.format(Locale.getDefault(), "%.0fKB", b / 1024.0);
        return String.format(Locale.getDefault(), "%.1fMB", b / 1024.0 / 1024.0);
    }

    private class Adapter extends RecyclerView.Adapter<Adapter.VH> {

        @NonNull
        @Override
        public VH onCreateViewHolder(@NonNull ViewGroup parent, int viewType) {
            View v = LayoutInflater.from(parent.getContext()).inflate(R.layout.item_download, parent, false);
            return new VH(v);
        }

        @Override
        public void onBindViewHolder(@NonNull VH h, int pos) {
            Downloads.Task t = data.get(pos);
            h.tvTitle.setText(t.label());

            int pct = (t.total > 0) ? (int) (t.done * 100L / t.total) : 0;

            switch (t.state) {
                case Downloads.DONE:
                    h.tvStatus.setText("已完成 · " + size(t.size));
                    h.pb.setProgress(100);
                    h.btn1.setText("播放");
                    h.btn1.setVisibility(View.VISIBLE);
                    h.btn1.setOnClickListener(v -> play(t));
                    h.btn2.setText("删除");
                    h.btn2.setVisibility(View.VISIBLE);
                    h.btn2.setOnClickListener(v -> deleteFile(t));
                    break;

                case Downloads.ERROR:
                    h.tvStatus.setText("失败：" + t.err);
                    h.pb.setProgress(pct);
                    h.btn1.setText("重试");
                    h.btn1.setVisibility(View.VISIBLE);
                    h.btn1.setOnClickListener(v -> {
                        Downloads.retry(t);
                        kick();
                        refresh();
                    });
                    h.btn2.setText("移除");
                    h.btn2.setVisibility(View.VISIBLE);
                    h.btn2.setOnClickListener(v -> {
                        Downloads.remove(t);
                        refresh();
                    });
                    break;

                case Downloads.PAUSED:
                    h.tvStatus.setText("已暂停 " + t.done + "/" + t.total);
                    h.pb.setProgress(pct);
                    h.btn1.setText("继续");
                    h.btn1.setVisibility(View.VISIBLE);
                    h.btn1.setOnClickListener(v -> {
                        t.paused = false;
                        t.state = Downloads.RUNNING;
                        refresh();
                    });
                    h.btn2.setText("取消");
                    h.btn2.setVisibility(View.VISIBLE);
                    h.btn2.setOnClickListener(v -> {
                        Downloads.remove(t);
                        refresh();
                    });
                    break;

                case Downloads.RUNNING:
                    h.tvStatus.setText("下载中 " + t.done + "/" + t.total
                            + (t.bytes > 0 ? " · " + size(t.bytes) : ""));
                    h.pb.setProgress(pct);
                    h.btn1.setText("暂停");
                    h.btn1.setVisibility(View.VISIBLE);
                    h.btn1.setOnClickListener(v -> {
                        t.paused = true;
                        t.state = Downloads.PAUSED;
                        refresh();
                    });
                    h.btn2.setText("取消");
                    h.btn2.setVisibility(View.VISIBLE);
                    h.btn2.setOnClickListener(v -> {
                        Downloads.remove(t);
                        refresh();
                    });
                    break;

                default: // QUEUED
                    h.tvStatus.setText("排队中…");
                    h.pb.setProgress(0);
                    h.btn1.setText("取消");
                    h.btn1.setVisibility(View.VISIBLE);
                    h.btn1.setOnClickListener(v -> {
                        Downloads.remove(t);
                        refresh();
                    });
                    h.btn2.setVisibility(View.GONE);
                    break;
            }
        }

        @Override
        public int getItemCount() {
            return data.size();
        }

        class VH extends RecyclerView.ViewHolder {
            TextView tvTitle, tvStatus;
            ProgressBar pb;
            Button btn1, btn2;

            VH(View v) {
                super(v);
                tvTitle = v.findViewById(R.id.tvTitle);
                tvStatus = v.findViewById(R.id.tvStatus);
                pb = v.findViewById(R.id.pb);
                btn1 = v.findViewById(R.id.btn1);
                btn2 = v.findViewById(R.id.btn2);
            }
        }
    }
}
