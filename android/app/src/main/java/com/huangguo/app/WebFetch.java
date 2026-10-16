package com.huangguo.app;

import android.os.Handler;
import android.os.Looper;
import android.webkit.WebView;
import android.webkit.WebViewClient;

import java.util.HashMap;
import java.util.Map;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

/**
 * 兜底取页：用系统 WebView（Chromium，等同于手机浏览器）加载页面再取源码。
 * 仅当 OkHttp 直连失败时调用，用于绕过 WAF/TLS 指纹一类只拦原生客户端的情况。
 */
public class WebFetch {

    public static String text(String url, Map<String, String> headers) {
        if (App.CTX == null || url == null) return null;

        final String[] out = new String[1];
        final WebView[] ref = new WebView[1];
        final CountDownLatch latch = new CountDownLatch(1);

        new Handler(Looper.getMainLooper()).post(() -> {
            try {
                WebView wv = new WebView(App.CTX);
                ref[0] = wv;
                wv.getSettings().setJavaScriptEnabled(true);
                wv.getSettings().setLoadsImagesAutomatically(false);
                wv.getSettings().setUserAgentString(Http.UA);
                wv.getSettings().setDomStorageEnabled(true);
                final boolean[] done = {false};
                wv.setWebViewClient(new WebViewClient() {
                    @Override
                    public void onPageFinished(WebView v, String u) {
                        if (done[0]) return;
                        done[0] = true;
                        v.evaluateJavascript(
                                "(function(){return document.documentElement.outerHTML||'';})()",
                                value -> {
                                    out[0] = decode(value);
                                    latch.countDown();
                                });
                    }

                    @Override
                    public void onReceivedError(WebView v, int code, String desc, String failing) {
                        if (!done[0]) {
                            done[0] = true;
                            latch.countDown();
                        }
                    }
                });
                Map<String, String> h = new HashMap<>();
                if (headers != null) h.putAll(headers);
                wv.loadUrl(url, h);
            } catch (Throwable t) {
                latch.countDown();
            }
        });

        try {
            latch.await(25, TimeUnit.SECONDS);
        } catch (InterruptedException ignored) {
        }

        if (ref[0] != null) {
            final WebView wv = ref[0];
            new Handler(Looper.getMainLooper()).post(wv::destroy);
        }
        return out[0];
    }

    /** evaluateJavascript 返回的是 JSON 字符串字面量（< 等被 \u003C 转义）。 */
    private static String decode(String js) {
        if (js == null) return null;
        if (js.equals("null")) return null;
        try {
            return new org.json.JSONArray("[" + js + "]").optString(0, null);
        } catch (Exception e) {
            return js;
        }
    }
}
