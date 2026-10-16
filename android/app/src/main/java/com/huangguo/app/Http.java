package com.huangguo.app;

import java.io.IOException;
import java.net.InetAddress;
import java.nio.charset.StandardCharsets;
import java.security.SecureRandom;
import java.security.cert.X509Certificate;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.TimeUnit;

import javax.net.ssl.SSLContext;
import javax.net.ssl.SSLSocketFactory;
import javax.net.ssl.TrustManager;
import javax.net.ssl.X509TrustManager;

import okhttp3.ConnectionSpec;
import okhttp3.Cookie;
import okhttp3.CookieJar;
import okhttp3.HttpUrl;
import okhttp3.OkHttpClient;
import okhttp3.Request;
import okhttp3.Response;
import okhttp3.ResponseBody;

/** 网络层：OkHttp + 浏览器风格请求头 + 重试 + 证书宽松兜底。 */
public class Http {

    public static final String UA =
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
          + "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36";

    public static final String UA_MOBILE =
            "Mozilla/5.0 (Linux; Android 12; SM-G991B) AppleWebKit/537.36 "
          + "(KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36";

    private static final Map<String, List<Cookie>> JAR = new HashMap<>();

    private static final CookieJar COOKIE_JAR = new CookieJar() {
        @Override
        public void saveFromResponse(HttpUrl url, List<Cookie> cookies) {
            if (cookies != null && !cookies.isEmpty()) JAR.put(url.host(), cookies);
        }

        @Override
        public List<Cookie> loadForRequest(HttpUrl url) {
            List<Cookie> c = JAR.get(url.host());
            return c != null ? c : new ArrayList<>();
        }
    };

    private static OkHttpClient normal;
    private static OkHttpClient loose;

    private static synchronized OkHttpClient normal() {
        if (normal == null) {
            normal = new OkHttpClient.Builder()
                    .connectTimeout(15, TimeUnit.SECONDS)
                    .readTimeout(30, TimeUnit.SECONDS)
                    .writeTimeout(30, TimeUnit.SECONDS)
                    .followRedirects(true)
                    .followSslRedirects(true)
                    .retryOnConnectionFailure(true)
                    .cookieJar(COOKIE_JAR)
                    .connectionSpecs(Arrays.asList(
                            ConnectionSpec.MODERN_TLS,
                            ConnectionSpec.COMPATIBLE_TLS,
                            ConnectionSpec.CLEARTEXT))
                    .build();
        }
        return normal;
    }

    /** 证书校验宽松的兜底客户端（仅在主客户端 TLS 握手失败时使用）。 */
    private static synchronized OkHttpClient loose() {
        if (loose == null) {
            try {
                final X509TrustManager tm = new X509TrustManager() {
                    @Override public void checkClientTrusted(X509Certificate[] c, String a) { }
                    @Override public void checkServerTrusted(X509Certificate[] c, String a) { }
                    @Override public X509Certificate[] getAcceptedIssuers() { return new X509Certificate[0]; }
                };
                SSLContext ctx = SSLContext.getInstance("TLS");
                ctx.init(null, new TrustManager[]{tm}, new SecureRandom());
                final SSLSocketFactory sf = ctx.getSocketFactory();
                loose = new OkHttpClient.Builder()
                        .connectTimeout(15, TimeUnit.SECONDS)
                        .readTimeout(30, TimeUnit.SECONDS)
                        .followRedirects(true)
                        .followSslRedirects(true)
                        .retryOnConnectionFailure(true)
                        .cookieJar(COOKIE_JAR)
                        .sslSocketFactory(sf, tm)
                        .hostnameVerifier((hostname, session) -> true)
                        .connectionSpecs(Arrays.asList(
                                ConnectionSpec.MODERN_TLS,
                                ConnectionSpec.COMPATIBLE_TLS,
                                ConnectionSpec.CLEARTEXT))
                        .build();
            } catch (Exception e) {
                loose = normal();
            }
        }
        return loose;
    }

    public static String get(String url) throws Exception {
        return get(url, null);
    }

    public static String get(String url, Map<String, String> headers) throws Exception {
        return new String(getBytes(url, headers), StandardCharsets.UTF_8);
    }

    public static byte[] getBytes(String url, Map<String, String> headers) throws Exception {
        Exception last = null;
        for (int attempt = 0; attempt < 2; attempt++) {
            OkHttpClient c = (attempt == 0) ? normal() : loose();
            try {
                return once(c, url, headers);
            } catch (Exception e) {
                last = e;
                if (isSsl(e) && attempt == 0) continue;   // TLS 问题 → 换宽松客户端再试
                if (attempt == 0) {
                    try { Thread.sleep(600); } catch (InterruptedException ignored) { }
                }
            }
        }
        throw (last != null) ? last : new IOException("unknown error for " + url);
    }

    private static byte[] once(OkHttpClient client, String url, Map<String, String> headers)
            throws Exception {
        Request.Builder rb = new Request.Builder().url(url)
                .header("User-Agent", UA)
                .header("Accept", acceptFor(url))
                .header("Accept-Language", "zh-CN,zh;q=0.9")
                .header("Upgrade-Insecure-Requests", "1")
                .header("Sec-Fetch-Mode", "navigate")
                .header("Sec-Fetch-Site", "none")
                .header("Connection", "keep-alive");
        if (headers != null) {
            for (Map.Entry<String, String> e : headers.entrySet()) {
                rb.header(e.getKey(), e.getValue());
            }
        }
        Response resp = client.newCall(rb.build()).execute();
        try {
            int code = resp.code();
            if (code >= 400) {
                throw new IOException("HTTP " + code + " " + resp.message() + " -> " + url);
            }
            ResponseBody body = resp.body();
            if (body == null) throw new IOException("empty body -> " + url);
            return body.bytes();
        } finally {
            resp.close();
        }
    }

    private static String acceptFor(String url) {
        String u = url.toLowerCase();
        if (u.contains(".m3u8")) {
            return "application/vnd.apple.mpegurl,application/x-mpegURL,*/*;q=0.8";
        }
        if (u.contains("pic.wirqed.cn") || u.endsWith(".jpg") || u.endsWith(".png")
                || u.endsWith(".webp") || u.endsWith(".jpeg")) {
            return "image/avif,image/webp,image/apng,image/*,*/*;q=0.8";
        }
        return "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,"
             + "image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7";
    }

    private static boolean isSsl(Exception e) {
        String n = e.getClass().getName();
        if (n.contains("SSL") || n.contains("Cert") || n.contains("Trust")) return true;
        Throwable c = e.getCause();
        return c != null && (c.getClass().getName().contains("SSL")
                || c.getClass().getName().contains("Cert"));
    }

    // ---------------- 诊断 ----------------

    /** 返回 "HTTP 200 | 124176 bytes | 312ms" 或 "FAIL: 异常详情"。 */
    public static String probe(String url) {
        long t0 = System.currentTimeMillis();
        try {
            byte[] b = getBytes(url, null);
            return "HTTP 200 | " + b.length + " bytes | "
                    + (System.currentTimeMillis() - t0) + "ms";
        } catch (Exception e) {
            StringBuilder sb = new StringBuilder("FAIL: ");
            sb.append(e.getClass().getSimpleName());
            if (e.getMessage() != null) sb.append(" / ").append(e.getMessage());
            Throwable c = e.getCause();
            int depth = 0;
            while (c != null && depth++ < 3) {
                sb.append("\n   cause: ").append(c.getClass().getSimpleName());
                if (c.getMessage() != null) sb.append(" / ").append(c.getMessage());
                c = c.getCause();
            }
            sb.append(" | ").append(System.currentTimeMillis() - t0).append("ms");
            return sb.toString();
        }
    }

    public static String dnsProbe(String host) {
        try {
            long t0 = System.currentTimeMillis();
            InetAddress a = InetAddress.getByName(host);
            return a.getHostAddress() + " (" + (System.currentTimeMillis() - t0) + "ms)";
        } catch (Exception e) {
            return "FAIL: " + e.toString();
        }
    }
}
