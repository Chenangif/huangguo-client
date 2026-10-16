"""端到端：启动 HlsProxy，用真实 m3u8 验证 /player、/m3u8 重写、/seg 转发。"""
import sys, os, json, re, urllib.request, threading, time
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "windows"))
FIX = os.path.join(HERE, "fixtures", "site_debug")
import huangguo_downloader as H

html = open(os.path.join(FIX, "detail.html"), encoding="utf-8").read()
data = H.parse_detail_data(html)
m3u8_url = data["videoSrc"].replace("\\u0026", "&")
print("upstream m3u8:", m3u8_url[:100])

proxy = H.HlsProxy({"User-Agent": H.UA})
proxy.start()
print("proxy port:", proxy.port)

# 1) /player 页面
pu = proxy.player_url(m3u8_url, "测试标题", 12.5, "4808:1", "x.json")
print("player url:", pu[:110])
r = urllib.request.urlopen(pu, timeout=10)
page = r.read().decode()
print("player page:", r.status, "len", len(page), "| has hls.js:", "Hls.isSupported" in page)

# 2) /m3u8 重写
import base64, urllib.parse
qs = urllib.parse.urlencode({"src": proxy._p(m3u8_url, "/m3u8")})
# player_url 的 src 已带 u 参数；直接请求 /m3u8?u=
r2 = urllib.request.urlopen(proxy._p(m3u8_url, "/m3u8"), timeout=30)
pl = r2.read().decode()
print("m3u8:", r2.status, "len", len(pl))
print(pl[:300])
assert "#EXTM3U" in pl
assert "127.0.0.1" in pl and "/seg?u=" in pl

# 3) /seg 转发：取第一个分片 URL
seg_line = [l for l in pl.splitlines() if "/seg?u=" in l][0]
r3 = urllib.request.urlopen(seg_line, timeout=60)
seg = r3.read()
print("seg:", r3.status, "bytes", len(seg), "head", seg[:4].hex())
assert len(seg) > 1000

# 4) /key 转发
key_line = re.search(r'URI="(http://127\.0\.0\.1:\d+/key\?u=[^"]+)"', pl)
if key_line:
    r4 = urllib.request.urlopen(key_line.group(1), timeout=30)
    k = r4.read()
    print("key:", r4.status, "bytes", len(k), "hex", k.hex()[:32])
    assert len(k) == 16

proxy.stop()
print("\nE2E OK")
