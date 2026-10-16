package com.huangguo.app;

import android.content.pm.ActivityInfo;
import android.net.Uri;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.view.GestureDetector;
import android.view.LayoutInflater;
import android.view.MotionEvent;
import android.view.View;
import android.view.ViewGroup;
import android.view.WindowManager;
import android.widget.Button;
import android.widget.TextView;
import android.widget.Toast;

import androidx.annotation.NonNull;
import androidx.appcompat.app.AppCompatActivity;
import androidx.media3.common.MediaItem;
import androidx.media3.common.Player;
import androidx.media3.datasource.DefaultHttpDataSource;
import androidx.media3.exoplayer.ExoPlayer;
import androidx.media3.exoplayer.hls.HlsMediaSource;
import androidx.media3.ui.PlayerView;
import androidx.recyclerview.widget.LinearLayoutManager;
import androidx.recyclerview.widget.RecyclerView;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.Map;

public class PlayerActivity extends AppCompatActivity {

    private PlayerView playerView;
    private ExoPlayer player;
    private RecyclerView rvEps;
    private View topBar;

    private String id, name, pic;
    private ArrayList<String> eps = new ArrayList<>();
    private int index = 0;
    private long startPos = 0;

    private boolean fullscreen = false;
    private boolean landscape = false;
    private boolean fast = false;

    @Override
    protected void onCreate(Bundle b) {
        super.onCreate(b);
        setContentView(R.layout.activity_player);

        id = getIntent().getStringExtra("id");
        name = getIntent().getStringExtra("name");
        pic = getIntent().getStringExtra("pic");
        ArrayList<String> list = getIntent().getStringArrayListExtra("eps");
        if (list != null && !list.isEmpty()) eps = list;
        index = getIntent().getIntExtra("index", 0);
        if (index < 0 || index >= eps.size()) index = 0;
        startPos = getIntent().getLongExtra("startPos", 0L);

        playerView = findViewById(R.id.playerView);
        rvEps = findViewById(R.id.rvEps);
        topBar = findViewById(R.id.topBar);
        Button btnFull = findViewById(R.id.btnFull);
        Button btnEps = findViewById(R.id.btnEps);
        Button btnRotate = findViewById(R.id.btnRotate);

        playerView.setControllerShowTimeoutMs(3000);

        rvEps.setLayoutManager(new LinearLayoutManager(this, LinearLayoutManager.HORIZONTAL, false));
        rvEps.setAdapter(new ChipAdapter());

        // 自定义按钮跟随播放器控制条的显隐：全屏时点一下屏幕才会出现
        playerView.setControllerVisibilityListener(new PlayerView.ControllerVisibilityListener() {
            @Override
            public void onVisibilityChanged(int visibility) {
                if (fullscreen) {
                    topBar.setVisibility(visibility);
                    if (visibility != View.VISIBLE) rvEps.setVisibility(View.GONE);
                }
            }
        });

        btnFull.setOnClickListener(v -> {
            if (fullscreen) exitFullscreen();
            else enterFullscreen();
        });
        btnRotate.setOnClickListener(v -> {
            landscape = !landscape;
            setRequestedOrientation(landscape
                    ? ActivityInfo.SCREEN_ORIENTATION_SENSOR_LANDSCAPE
                    : ActivityInfo.SCREEN_ORIENTATION_SENSOR_PORTRAIT);
            if (landscape && !fullscreen) {
                // 转横屏时顺便进入沉浸，保持画面干净
                fullscreen = true;
                applyImmersive();
                updateScreenOn();
                playerView.hideController();
                topBar.setVisibility(View.GONE);
                rvEps.setVisibility(View.GONE);
            } else if (!landscape && fullscreen) {
                exitFullscreen();
            }
        });
        btnEps.setOnClickListener(v ->
                rvEps.setVisibility(rvEps.getVisibility() == View.VISIBLE ? View.GONE : View.VISIBLE));

        // 长按画面 2 倍速，松手恢复（无任何提示）
        GestureDetector gd = new GestureDetector(this, new GestureDetector.SimpleOnGestureListener() {
            @Override
            public void onLongPress(MotionEvent e) {
                if (player != null) {
                    fast = true;
                    player.setPlaybackSpeed(2.0f);
                }
            }
        });
        playerView.setOnTouchListener((v, event) -> {
            gd.onTouchEvent(event);
            int a = event.getAction();
            if ((a == MotionEvent.ACTION_UP || a == MotionEvent.ACTION_CANCEL) && fast) {
                fast = false;
                if (player != null) player.setPlaybackSpeed(1.0f);
            }
            return false;
        });

        loadEp(index);
    }

    private void enterFullscreen() {
        fullscreen = true;
        landscape = true;
        setRequestedOrientation(ActivityInfo.SCREEN_ORIENTATION_SENSOR_LANDSCAPE);
        applyImmersive();
        updateScreenOn();
        playerView.hideController();
        topBar.setVisibility(View.GONE);
        rvEps.setVisibility(View.GONE);
    }

    private void exitFullscreen() {
        fullscreen = false;
        landscape = false;
        setRequestedOrientation(ActivityInfo.SCREEN_ORIENTATION_SENSOR_PORTRAIT);
        applyNormal();
        updateScreenOn();
        playerView.showController();
        topBar.setVisibility(View.VISIBLE);
    }

    private void applyImmersive() {
        getWindow().getDecorView().setSystemUiVisibility(
                View.SYSTEM_UI_FLAG_FULLSCREEN
                        | View.SYSTEM_UI_FLAG_HIDE_NAVIGATION
                        | View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY
                        | View.SYSTEM_UI_FLAG_LAYOUT_STABLE
                        | View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN
                        | View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION);
    }

    private void applyNormal() {
        getWindow().getDecorView().setSystemUiVisibility(View.SYSTEM_UI_FLAG_VISIBLE);
    }

    /** 播放中 / 全屏中保持屏幕常亮（FLAG_KEEP_SCREEN_ON，随窗口可见性自动失效，无需权限） */
    private void keepScreenOn(boolean on) {
        if (on) {
            getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        } else {
            getWindow().clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        }
    }

    /** 全屏或正在播放时都保持常亮 */
    private void updateScreenOn() {
        boolean playing = player != null && player.isPlaying();
        keepScreenOn(fullscreen || playing);
    }

    private void loadEp(int i) {
        if (i < 0 || i >= eps.size()) return;
        index = i;
        String ep = eps.get(i);
        setTitle((name == null ? "播放" : name) + " · 第" + Site.pad2(ep) + "集");
        startPos = 0;
        Store.Item h = Store.historyOf(id);
        if (h != null && ep.equals(h.ep) && h.pos > 1500) {
            startPos = h.pos;    // 续播：同一集才恢复进度
        }
        new Thread(() -> {
            String url = null;
            String err = null;
            try {
                url = Site.fetchPlayUrl(id, ep);
            } catch (Exception e) {
                err = e.toString();
            }
            final String u = url;
            final String e2 = err;
            runOnUiThread(() -> {
                if (u == null || u.isEmpty()) {
                    Toast.makeText(this, "取不到播放地址：" + e2, Toast.LENGTH_SHORT).show();
                    return;
                }
                startPlay(u);
            });
        }).start();
    }

    private void startPlay(String m3u8) {
        if (player == null) {
            player = new ExoPlayer.Builder(this).build();
            playerView.setPlayer(player);
            // 播放开始/暂停时同步常亮状态（退出或暂停后允许息屏省电）
            player.addListener(new Player.Listener() {
                @Override
                public void onIsPlayingChanged(boolean isPlaying) {
                    updateScreenOn();
                }
            });
        }
        Map<String, String> headers = new HashMap<>();
        headers.put("User-Agent", Site.UA);
        headers.put("Referer", Site.SITE + "/");
        headers.put("Accept", "application/vnd.apple.mpegurl,application/x-mpegURL,*/*;q=0.8");

        DefaultHttpDataSource.Factory dsf = new DefaultHttpDataSource.Factory()
                .setUserAgent(Site.UA)
                .setDefaultRequestProperties(headers)
                .setAllowCrossProtocolRedirects(true);
        HlsMediaSource.Factory hls = new HlsMediaSource.Factory(dsf);
        player.setMediaSource(hls.createMediaSource(MediaItem.fromUri(Uri.parse(m3u8))));
        player.prepare();
        if (startPos > 0) player.seekTo(startPos);
        player.play();
        keepScreenOn(true);   // 一旦开始播放就常亮
        recordHistory();
    }

    private void recordHistory() {
        if (index < 0 || index >= eps.size()) return;
        Store.addHistory(id, name, pic, "", eps.get(index),
                player != null ? player.getCurrentPosition() : 0L);
    }

    @Override
    protected void onResume() {
        super.onResume();
        updateScreenOn();     // 回到前台时恢复常亮
    }

    @Override
    protected void onPause() {
        super.onPause();
        if (player != null) recordHistory();
        keepScreenOn(false);  // 离开播放页就允许息屏
    }

    @Override
    protected void onDestroy() {
        super.onDestroy();
        keepScreenOn(false);
        if (player != null) {
            recordHistory();
            player.release();
            player = null;
        }
    }

    private class ChipAdapter extends RecyclerView.Adapter<ChipAdapter.VH> {
        @NonNull
        @Override
        public VH onCreateViewHolder(@NonNull ViewGroup parent, int viewType) {
            View v = LayoutInflater.from(parent.getContext()).inflate(R.layout.item_ep_chip, parent, false);
            return new VH(v);
        }

        @Override
        public void onBindViewHolder(@NonNull VH h, int pos) {
            TextView t = h.itemView.findViewById(R.id.tvChip);
            t.setText("第" + Site.pad2(eps.get(pos)) + "集");
            t.setBackgroundColor(pos == index ? 0xFFFFB300 : 0x00000000);
            t.setTextColor(pos == index ? 0xFF000000 : 0xFFFFFFFF);
            t.setOnClickListener(v -> {
                loadEp(pos);
                notifyDataSetChanged();
                rvEps.setVisibility(View.GONE);
            });
        }

        @Override
        public int getItemCount() {
            return eps.size();
        }

        class VH extends RecyclerView.ViewHolder {
            VH(View v) {
                super(v);
            }
        }
    }
}
