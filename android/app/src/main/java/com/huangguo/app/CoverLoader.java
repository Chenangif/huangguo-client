package com.huangguo.app;

import android.content.Context;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.os.Handler;
import android.os.Looper;
import android.util.LruCache;
import android.widget.ImageView;

import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.util.Collections;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/** 异步加载并解密封面（AES-128-CBC），带内存缓存 + 磁盘缓存。 */
public class CoverLoader {

    private static final LruCache<String, Bitmap> MEM = new LruCache<String, Bitmap>(24 * 1024 * 1024) {
        @Override
        protected int sizeOf(String key, Bitmap value) {
            return value.getByteCount();
        }
    };
    private static final ExecutorService POOL = Executors.newFixedThreadPool(4);
    private static final Handler MAIN = new Handler(Looper.getMainLooper());

    public static void load(Context ctx, String url, ImageView iv) {
        if (url == null || url.isEmpty()) {
            iv.setImageDrawable(null);
            iv.setBackgroundColor(0xFFDDDDDD);
            return;
        }
        Bitmap cached = MEM.get(url);
        if (cached != null) {
            iv.setImageBitmap(cached);
            return;
        }
        iv.setTag(url);
        iv.setImageDrawable(null);
        iv.setBackgroundColor(0xFFDDDDDD);
        POOL.submit(() -> {
            try {
                File dir = new File(ctx.getCacheDir(), "covers");
                if (!dir.exists()) dir.mkdirs();
                File f = new File(dir, Integer.toString(Math.abs(url.hashCode())) + ".img");
                byte[] data;
                if (f.exists() && f.length() > 0) {
                    data = readAll(f);
                } else {
                    byte[] raw = Http.getBytes(url, Collections.singletonMap("Referer", Site.SITE + "/"));
                    data = CryptoUtil.decryptCover(raw);
                    writeAll(f, data);
                }
                Bitmap bm = decodeSampled(data, 400);
                if (bm == null) return;
                MEM.put(url, bm);
                MAIN.post(() -> {
                    if (url.equals(iv.getTag())) iv.setImageBitmap(bm);
                });
            } catch (Exception ignored) {
            }
        });
    }

    private static Bitmap decodeSampled(byte[] data, int maxW) {
        BitmapFactory.Options o = new BitmapFactory.Options();
        o.inJustDecodeBounds = true;
        BitmapFactory.decodeByteArray(data, 0, data.length, o);
        int sample = 1;
        if (o.outWidth > maxW) {
            sample = Math.round((float) o.outWidth / (float) maxW);
            if (sample < 1) sample = 1;
        }
        o.inJustDecodeBounds = false;
        o.inSampleSize = sample;
        return BitmapFactory.decodeByteArray(data, 0, data.length, o);
    }

    private static byte[] readAll(File f) throws Exception {
        byte[] b = new byte[(int) f.length()];
        InputStream is = new java.io.FileInputStream(f);
        int off = 0;
        while (off < b.length) {
            int n = is.read(b, off, b.length - off);
            if (n < 0) break;
            off += n;
        }
        is.close();
        return b;
    }

    private static void writeAll(File f, byte[] data) throws Exception {
        OutputStream os = new FileOutputStream(f);
        os.write(data);
        os.close();
    }
}
