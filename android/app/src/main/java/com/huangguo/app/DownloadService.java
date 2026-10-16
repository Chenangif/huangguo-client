package com.huangguo.app;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.Service;
import android.content.ContentValues;
import android.content.Intent;
import android.net.Uri;
import android.os.Build;
import android.os.Environment;
import android.os.IBinder;
import android.provider.MediaStore;

import androidx.annotation.Nullable;
import androidx.core.app.NotificationCompat;

import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.URL;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/** 下载队列服务：解析 m3u8（含 AES-128 分片解密）合并为 .ts，保存到「下载/黄果短剧」。 */
public class DownloadService extends Service {

    private static final int NID = 1001;
    private static final String CH = "huangguo_dl";
    private static volatile boolean looping = false;
    private NotificationManager nm;

    @Override
    public void onCreate() {
        super.onCreate();
        nm = (NotificationManager) getSystemService(NOTIFICATION_SERVICE);
        if (Build.VERSION.SDK_INT >= 26 && nm.getNotificationChannel(CH) == null) {
            NotificationChannel c = new NotificationChannel(CH, "下载", NotificationManager.IMPORTANCE_LOW);
            nm.createNotificationChannel(c);
        }
        startForeground(NID, build("准备下载…", 0));
    }

    @Nullable
    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        if (!looping) {
            looping = true;
            new Thread(() -> {
                try {
                    Downloads.ensureLoaded();
                    Downloads.Task t;
                    while ((t = Downloads.next()) != null) {
                        runTask(t);
                    }
                } catch (Throwable ignored) {
                }
                looping = false;
                stopForeground(true);
                stopSelf();
            }).start();
        }
        return START_NOT_STICKY;
    }

    private void runTask(Downloads.Task task) {
        File tmp = null;
        try {
            notif(task.label() + " · 解析中", 0);
            String m3u8 = Site.fetchPlayUrl(task.id, task.ep);
            if (m3u8 == null || m3u8.isEmpty()) throw new Exception("取不到播放地址");

            Map<String, String> headers = new HashMap<>();
            headers.put("User-Agent", Site.UA);
            headers.put("Referer", Site.SITE + "/");

            String mediaUrl = m3u8;
            String text = Http.get(m3u8, headers);
            if (text.contains("#EXT-X-STREAM-INF")) {
                mediaUrl = pickVariant(m3u8, text);
                text = Http.get(mediaUrl, headers);
            }

            Playlist pl = parseMedia(text);
            if (pl.segs.isEmpty()) throw new Exception("m3u8 无分片");
            task.total = pl.segs.size();
            task.done = 0;

            byte[] key = null;
            if (pl.keyUri != null) key = Http.getBytes(absolute(mediaUrl, pl.keyUri), headers);

            File dir = new File(getCacheDir(), "dl");
            if (!dir.exists()) dir.mkdirs();
            tmp = new File(dir, task.id + "_" + task.ep + ".ts");
            FileOutputStream out = new FileOutputStream(tmp);

            for (int i = 0; i < pl.segs.size(); i++) {
                while (task.paused && !task.cancel) {
                    Thread.sleep(300);
                    notif(task.label() + " · 已暂停", pct(task));
                }
                if (task.cancel) throw new InterruptedException("已取消");

                byte[] data = Http.getBytes(absolute(mediaUrl, pl.segs.get(i)), headers);
                if (key != null) {
                    byte[] iv = (pl.keyIv != null) ? pl.keyIv : seqIv(pl.mediaSequence + i);
                    data = CryptoUtil.decryptSegment(data, key, iv);
                }
                out.write(data);
                task.done = i + 1;
                task.bytes += data.length;
                notif(task.label() + " · " + (i + 1) + "/" + pl.segs.size(), pct(task));
            }
            out.close();

            String fname = safeName(task.title) + "_第" + Site.pad2(task.ep) + "集.ts";
            String where = savePublic(tmp, fname);
            Downloads.finish(task, where, tmp.length());
            nm.notify(NID + 1, new NotificationCompat.Builder(this, CH)
                    .setSmallIcon(android.R.drawable.stat_sys_download_done)
                    .setContentTitle("下载完成")
                    .setContentText(fname)
                    .setAutoCancel(true)
                    .build());
        } catch (InterruptedException ie) {
            Downloads.remove(task);
        } catch (Exception e) {
            Downloads.fail(task, String.valueOf(e.getMessage()));
            nm.notify(NID + 2, new NotificationCompat.Builder(this, CH)
                    .setSmallIcon(android.R.drawable.stat_notify_error)
                    .setContentTitle("下载失败")
                    .setContentText(task.label() + " " + e.getMessage())
                    .build());
        }
        if (tmp != null && tmp.exists()) {
            try {
                tmp.delete();
            } catch (Exception ignored) {
            }
        }
    }

    private static int pct(Downloads.Task t) {
        if (t.total <= 0) return 0;
        return (int) (t.done * 100L / t.total);
    }

    // ---------------- m3u8 解析 ----------------

    private static class Playlist {
        List<String> segs = new ArrayList<>();
        String keyUri = null;
        byte[] keyIv = null;
        int mediaSequence = 0;
    }

    private static Playlist parseMedia(String text) {
        Playlist p = new Playlist();
        for (String raw : text.split("\n")) {
            String l = raw.trim();
            if (l.isEmpty()) continue;
            if (l.startsWith("#EXT-X-MEDIA-SEQUENCE:")) {
                try {
                    p.mediaSequence = Integer.parseInt(l.substring(l.indexOf(':') + 1).trim());
                } catch (Exception ignored) {
                }
            } else if (l.startsWith("#EXT-X-KEY")) {
                String method = attr(l, "METHOD");
                if (method != null && !"NONE".equalsIgnoreCase(method)) {
                    String uri = attr(l, "URI");
                    if (uri != null) p.keyUri = uri;
                    String iv = attr(l, "IV");
                    if (iv != null && iv.toLowerCase().startsWith("0x")) {
                        p.keyIv = hex(iv.substring(2));
                    }
                }
            } else if (!l.startsWith("#")) {
                p.segs.add(l);
            }
        }
        return p;
    }

    private static String pickVariant(String base, String text) throws Exception {
        String[] lines = text.split("\n");
        String best = null;
        long bwBest = -1;
        for (int i = 0; i < lines.length; i++) {
            String l = lines[i].trim();
            if (l.startsWith("#EXT-X-STREAM-INF")) {
                Matcher m = Pattern.compile("BANDWIDTH=(\\d+)").matcher(l);
                long bw = m.find() ? Long.parseLong(m.group(1)) : 0;
                String uri = null;
                for (int j = i + 1; j < lines.length; j++) {
                    String u = lines[j].trim();
                    if (!u.isEmpty() && !u.startsWith("#")) {
                        uri = u;
                        break;
                    }
                }
                if (uri != null && bw >= bwBest) {
                    bwBest = bw;
                    best = uri;
                }
            }
        }
        if (best == null) throw new Exception("无法选择清晰度");
        return absolute(base, best);
    }

    static String absolute(String base, String u) throws Exception {
        if (u == null) return "";
        u = u.trim().replace("\"", "");
        if (u.startsWith("http")) return u;
        URL b = new URL(base);
        if (u.startsWith("/")) return b.getProtocol() + "://" + b.getHost() + u;
        String path = b.getPath();
        int idx = path.lastIndexOf('/');
        return b.getProtocol() + "://" + b.getHost() + (idx >= 0 ? path.substring(0, idx + 1) : "/") + u;
    }

    static byte[] seqIv(int seq) {
        byte[] iv = new byte[16];
        for (int i = 0; i < 8; i++) {
            iv[15 - i] = (byte) ((seq >>> (8 * i)) & 0xFF);
        }
        return iv;
    }

    private static byte[] hex(String s) {
        int n = s.length() / 2;
        byte[] out = new byte[Math.max(16, n)];
        for (int i = 0; i < n; i++) {
            out[i] = (byte) Integer.parseInt(s.substring(i * 2, i * 2 + 2), 16);
        }
        return out;
    }

    private static String attr(String line, String name) {
        Matcher m = Pattern.compile(name + "=([^,]+)").matcher(line);
        if (!m.find()) return null;
        return m.group(1).trim().replace("\"", "");
    }

    // ---------------- 保存到手机 ----------------

    /** 返回 content:// 字符串（Android 10+）或绝对路径（旧系统）。 */
    private String savePublic(File tmp, String name) throws Exception {
        if (Build.VERSION.SDK_INT >= 29) {
            ContentValues cv = new ContentValues();
            cv.put(MediaStore.Downloads.DISPLAY_NAME, name);
            cv.put(MediaStore.Downloads.MIME_TYPE, "video/mp2ts");
            cv.put(MediaStore.Downloads.RELATIVE_PATH, Environment.DIRECTORY_DOWNLOADS + "/黄果短剧");
            cv.put(MediaStore.Downloads.IS_PENDING, 1);
            Uri uri = getContentResolver().insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, cv);
            if (uri == null) throw new Exception("无法创建文件");
            OutputStream os = getContentResolver().openOutputStream(uri);
            if (os == null) throw new Exception("无法写入文件");
            copy(tmp, os);
            os.close();
            cv.clear();
            cv.put(MediaStore.Downloads.IS_PENDING, 0);
            getContentResolver().update(uri, cv, null, null);
            return uri.toString();
        } else {
            File dir = new File(Environment.getExternalStoragePublicDirectory(
                    Environment.DIRECTORY_DOWNLOADS), "黄果短剧");
            if (!dir.exists()) dir.mkdirs();
            File dst = new File(dir, name);
            OutputStream os = new FileOutputStream(dst);
            copy(tmp, os);
            os.close();
            return dst.getAbsolutePath();
        }
    }

    private static void copy(File src, OutputStream os) throws Exception {
        InputStream is = new FileInputStream(src);
        byte[] buf = new byte[65536];
        int n;
        while ((n = is.read(buf)) > 0) os.write(buf, 0, n);
        is.close();
    }

    private static String safeName(String s) {
        if (s == null) return "视频";
        return s.replaceAll("[\\\\/:*?\"<>|]", "_").trim();
    }

    private void notif(String text, int progress) {
        nm.notify(NID, build(text, progress));
    }

    private Notification build(String text, int progress) {
        return new NotificationCompat.Builder(this, CH)
                .setSmallIcon(android.R.drawable.stat_sys_download)
                .setContentTitle("黄果短剧下载")
                .setContentText(text)
                .setProgress(100, progress, progress <= 0)
                .setOngoing(true)
                .build();
    }
}
