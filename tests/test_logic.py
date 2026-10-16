#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""测试：合成数据 + 真实抓取页面（site_debug/*.html）双重验证解析与解密。"""
import sys, os, json, base64, threading, time
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "windows"))
FIX = os.path.join(HERE, "fixtures", "site_debug")   # 真实抓取的页面样本
import huangguo_downloader as H
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad

ok = 0
fail = 0
def check(name, cond):
    global ok, fail
    if cond:
        ok += 1
        print(f"  [PASS] {name}")
    else:
        fail += 1
        print(f"  [FAIL] {name}")

# ============ A. 合成数据 ============
print("--- A1. 卡片解析（合成） ---")
card_html = '''
<body><div>
  <div class="hg-drama-card">
    <a href="/video/123456/"><img data-src="//cdn.example.com/cover1.jpg?auth_key=abc"></a>
    <div class="hg-drama-card__title"><a href="/video/123456/">测试剧一</a></div>
    <span class="hg-drama-card__episode">更新至12集</span>
    <span class="hg-drama-card__score">9.2分</span>
  </div>
  <div class="hg-drama-card">
    <a href="/video/789/"><img data-src="/cover2.jpg"></a>
    <div class="hg-drama-card__title"><a href="/video/789/">测试剧二</a></div>
  </div>
</div></body>
'''
cards = H.parse_grid_cards(card_html)
check("卡片数量=2", len(cards) == 2)
check("卡片1 id=123456", cards[0]["id"] == "123456")
check("卡片1 标题", cards[0]["name"] == "测试剧一")
check("卡片1 海报URL修正", cards[0]["pic"] == "https://cdn.example.com/cover1.jpg?auth_key=abc")
check("卡片1 备注", cards[0]["remarks"] == "更新至12集 · 9.2分")
check("卡片2 相对URL修正", cards[1]["pic"] == "https://huangguoai.com/cover2.jpg")

print("--- A2. 排行榜解析（合成） ---")
rank_html = '''
<div class="hg-rank-list">
  <div class="hg-rank-item">
    <a href="/video/555/"><img data-src="/r.jpg"></a>
    <h2 class="hg-rank-item__title">榜首剧</h2>
    <div class="hg-rank-item__tags">热门 · 新剧</div>
  </div>
</div>
'''
ranks = H.parse_ranks(rank_html)
check("排行榜数量=1", len(ranks) == 1)
check("排行榜标题", ranks[0]["name"] == "榜首剧")
check("排行榜备注", ranks[0]["remarks"] == "热门 · 新剧")

print("--- A3. 详情选集解析（合成，真实类名 hg-web-play__ep） ---")
detail_html = '''
<div class="hg-web-play__ep-grid" data-web-play-ep-grid>
  <a class="hg-web-play__ep is-active" href="/video/4808/" data-ep-id="1">01</a>
  <a class="hg-web-play__ep" href="/video/4808/ep-2/" data-ep-id="2">02</a>
  <a class="hg-web-play__ep" href="/video/4808/ep-3/" data-ep-id="3">03</a>
</div>
'''
eps = H.parse_detail_episodes(detail_html)
check("选集数量=3", len(eps) == 3)
check("选集2 url", eps[1]["url"] == "https://huangguoai.com/video/4808/ep-2/")
check("选集2 ep", eps[1]["ep"] == "2")
check("选集2 name 补零", eps[1]["name"] == "第02集")

print("--- A4. videoInitialData / 播放地址 ---")
play_json = json.dumps({"epPlaySrcs": {"1": "https://v.example.com/1/index.m3u8?t=1\\u0026k=2"},
                        "videoSrc": "https://v.example.com/main.m3u8"})
play_html = f'<script id="videoInitialData" type="application/json">{play_json}</script>'
m3u8, headers = H.parse_playinfo(play_html, "1", "https://huangguoai.com/video/4808/")
check("播放地址解析", m3u8 == "https://v.example.com/1/index.m3u8?t=1&k=2")
check("Referer 头", headers["Referer"] == "https://huangguoai.com/video/4808/")

print("--- A5. 海报 AES 解密 ---")
KEY = b"f5d965df75336270"
IV = b"97b60394abc2fbe1"
plain = b"\xff\xd8" + b"\x10\x20\x30\x40" * 5 + b"\xff\xd9"
ct = AES.new(KEY, AES.MODE_CBC, IV).encrypt(pad(plain, 16))
dec = H.decrypt_image(ct)
check("解密还原 JPEG", dec == plain)
check("guess_ext=jpg", H.guess_ext(dec) == "jpg")
raw2 = b"\xff\xd8abcdef"
check("非16倍数原样", H.decrypt_image(raw2) == raw2)

print("--- A6. 工具函数 ---")
check("safe_name 清洗", H.safe_name('a/b:c*?"><|d') == "a_b_c______d")

print("--- A7. 主播放列表码率选择 ---")
master = "#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=800000\nlow/index.m3u8\n#EXT-X-STREAM-INF:BANDWIDTH=2500000\nhigh/index.m3u8\n"
orig = H.http_get
H.http_get = lambda *a, **k: master
try:
    url, text = H._resolve_media_playlist("https://v.example.com/master.m3u8", {})
    check("挑选最高码率", url == "https://v.example.com/high/index.m3u8")
finally:
    H.http_get = orig

print("--- A8. HLS 代理重写 ---")
proxy = H.HlsProxy({"User-Agent": "UA-TEST"})
m3u8_upstream = ('#EXTM3U\n#EXT-X-KEY:METHOD=AES-128,URI="https://k.example.com/crypt.key",'
                 'IV=0x00fe520246d13938bf909c3685b19dcf\n'
                 'https://s.example.com/seg0.ts?auth_key=1\nseg-relative.ts\n')
H.http_get = lambda *a, **k: m3u8_upstream
proxy.port = 18099
b64u = proxy._b64("https://u.example.com/list.m3u8")
# 直接构造重写逻辑验证：模拟 do_GET 里的重写段
base = "https://u.example.com/"
lines_out = []
for line in m3u8_upstream.splitlines():
    s = line.strip()
    if not s:
        continue
    if s.startswith("#"):
        import re as _re
        m = _re.search(r'URI="([^"]+)"', s)
        if m:
            absu = __import__("urllib.parse", fromlist=["urljoin"]).urljoin(base, m.group(1))
            s = s.replace(m.group(1), proxy._p(absu, "/key"))
        lines_out.append(s)
    else:
        absu = __import__("urllib.parse", fromlist=["urljoin"]).urljoin(base, s)
        lines_out.append(proxy._p(absu, "/seg"))
joined = "\n".join(lines_out)
check("key URI 重写到代理", "/key?u=" in joined and "127.0.0.1:18099" in joined)
check("分片 URI 重写到代理", "/seg?u=" in joined)
key_dec = base64.urlsafe_b64decode(joined.split('/key?u=')[1].split('"')[0].split(",")[0].encode()).decode()
check("key URL 可逆", key_dec == "https://k.example.com/crypt.key")

# ============ B. 真实页面（site_debug） ============
print("--- B1. 真实首页 ---")
if os.path.isfile(os.path.join(FIX, "home.html")):
    html = open(os.path.join(FIX, "home.html"), encoding="utf-8").read()
    cards = H.parse_grid_cards(html)
    check(f"首页卡片 >= 12（实际 {len(cards)}）", len(cards) >= 12)
    check("卡片 id 纯数字", all(c["id"].isdigit() for c in cards))
    check("卡片有标题", all(c["name"] for c in cards))
    check("封面是 CDN http 链接", all(c["pic"].startswith("http") for c in cards))
else:
    print("  (skip: 无 home.html)")

print("--- B2. 真实分类页 ---")
if os.path.isfile(os.path.join(FIX, "cat.html")):
    html = open(os.path.join(FIX, "cat.html"), encoding="utf-8").read()
    cards = H.parse_grid_cards(html)
    check(f"分类页卡片 >= 50（实际 {len(cards)}）", len(cards) >= 50)
else:
    print("  (skip)")

print("--- B3. 真实排行榜 ---")
if os.path.isfile(os.path.join(FIX, "rank.html")):
    html = open(os.path.join(FIX, "rank.html"), encoding="utf-8").read()
    ranks = H.parse_ranks(html)
    check(f"排行榜条目 >= 15（实际 {len(ranks)}）", len(ranks) >= 15)
    check("榜首有标题", ranks and ranks[0]["name"])
else:
    print("  (skip)")

print("--- B4. 真实详情页 ---")
if os.path.isfile(os.path.join(FIX, "detail.html")):
    html = open(os.path.join(FIX, "detail.html"), encoding="utf-8").read()
    eps = H.parse_detail_episodes(html)
    check(f"选集 = 14（实际 {len(eps)}）", len(eps) == 14)
    check("末集 url 含 ep-14", eps and eps[-1]["url"].endswith("/ep-14/"))
    data = H.parse_detail_data(html)
    check("videoInitialData 有 title", bool(data and data.get("title")))
    check("videoInitialData 有 description", bool(data and data.get("description")))
    check("videoSrc 是 m3u8", bool(data and str(data.get("videoSrc", "")).endswith((".m3u8", "")) and ".m3u8" in str(data.get("videoSrc", ""))))
    meta = H.parse_detail_meta(html)
    check("简介非空", bool(meta))
else:
    print("  (skip)")

# ============ C. 收藏/历史/进度 ============
print("--- C1. 收藏/历史/进度 ---")
import tempfile
tmpdir = tempfile.mkdtemp()
orig_data = H.DATA_PATH
H.DATA_PATH = os.path.join(tmpdir, "data.json")
try:
    check("toggle 收藏→True", H.toggle_favorite("12", "剧名", "pic") is True)
    check("is_favorite", H.is_favorite("12") is True)
    check("toggle 取消→False", H.toggle_favorite("12", "剧名", "pic") is False)
    H.record_history("12", "剧名", "pic", "3")
    d = H.load_data()
    check("历史记录 1 条", len(d["history"]) == 1 and d["history"][0]["ep"] == "3")
    H.record_history("12", "剧名", "pic", "5")
    d = H.load_data()
    check("同一剧历史去重置顶", len(d["history"]) == 1 and d["history"][0]["ep"] == "5")
    H.set_progress("12", "5", 123.4)
    check("进度读写", abs(H.get_progress("12", "5") - 123.4) < 0.01)
    check("ep_key", H.ep_key("12", "3") == "12:3")
finally:
    H.DATA_PATH = orig_data

print(f"\n结果：通过 {ok} 项，失败 {fail} 项")
sys.exit(1 if fail else 0)
