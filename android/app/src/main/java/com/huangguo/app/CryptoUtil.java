package com.huangguo.app;

import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import javax.crypto.Cipher;
import javax.crypto.spec.IvParameterSpec;
import javax.crypto.spec.SecretKeySpec;

/** 站点封面为 AES-128-CBC 加密字节（密钥取自前端 crypto-worker.js）。 */
public class CryptoUtil {

    private static final byte[] KEY = "f5d965df75336270".getBytes(StandardCharsets.UTF_8);
    private static final byte[] IV = "97b60394abc2fbe1".getBytes(StandardCharsets.UTF_8);

    public static byte[] decryptCover(byte[] raw) {
        if (raw == null || raw.length == 0 || raw.length % 16 != 0) {
            return raw;
        }
        try {
            Cipher c = Cipher.getInstance("AES/CBC/NoPadding");
            c.init(Cipher.DECRYPT_MODE, new SecretKeySpec(KEY, "AES"), new IvParameterSpec(IV));
            byte[] pt = c.doFinal(raw);
            if (!looksLikeImage(pt)) {
                return raw;             // 密钥不对或未加密 → 原样返回
            }
            int pad = pt[pt.length - 1] & 0xFF;
            if (pad >= 1 && pad <= 16) {
                boolean ok = true;
                for (int i = pt.length - pad; i < pt.length; i++) {
                    if ((pt[i] & 0xFF) != pad) { ok = false; break; }
                }
                if (ok) {
                    pt = Arrays.copyOf(pt, pt.length - pad);
                }
            }
            int eoi = -1;
            for (int i = pt.length - 2; i >= 0; i--) {
                if ((pt[i] & 0xFF) == 0xFF && (pt[i + 1] & 0xFF) == 0xD9) { eoi = i + 2; break; }
            }
            if (eoi > 0) {
                pt = Arrays.copyOf(pt, eoi);
            }
            return pt;
        } catch (Exception e) {
            return raw;
        }
    }

    /** HLS 分片解密（EXT-X-KEY, AES-128）。 */
    public static byte[] decryptSegment(byte[] data, byte[] key, byte[] iv) throws Exception {
        Cipher c = Cipher.getInstance("AES/CBC/PKCS7Padding");
        c.init(Cipher.DECRYPT_MODE, new SecretKeySpec(key, "AES"), new IvParameterSpec(iv));
        return c.doFinal(data);
    }

    static boolean looksLikeImage(byte[] b) {
        if (b == null || b.length < 8) return false;
        if ((b[0] & 0xFF) == 0xFF && (b[1] & 0xFF) == 0xD8) return true;
        if ((b[0] & 0xFF) == 0x89 && b[1] == 'P' && b[2] == 'N' && b[3] == 'G') return true;
        if (b[0] == 'R' && b[1] == 'I' && b[2] == 'F' && b[3] == 'F') return true;
        if (b[0] == 'G' && b[1] == 'I' && b[2] == 'F') return true;
        return false;
    }
}
