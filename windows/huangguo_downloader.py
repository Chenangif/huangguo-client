#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
黄果短剧 站点客户端 (Windows)
================================
把 huangguoai.com 搬进本地 exe：浏览分类 / 排行榜 / 搜索、看海报文、
点选集在线播放，并支持一键下载整理到本地文件夹。

功能：
  1. 浏览：首页 / AI成人短剧 / AI成人漫剧 / AI换脸 / AI魔改 / 排行榜 / 搜索。
     卡片墙显示海报缩略图 + 标题；点卡片进详情页看选集与简介。
  2. 播放：每集调用 ffplay（随 ffmpeg 一起就位）带请求头播放 HLS(.m3u8)；
     若无 ffplay 则先 ffmpeg 下到 mp4 再用默认播放器打开。
  3. 下载整理：详情页「下载整部」或主界面「批量下载」，按「剧名」建文件夹，
     海报存 poster.xxx，视频存 第XX集.mp4/.ts。
  4. 本地库：扫描保存目录，浏览已下载内容、直接打开播放。

站点技术细节：封面为 AES-128-CBC 加密字节（key/iv 取自 crypto-worker.js）；
播放页 <script id="videoInitialData"> 内嵌 JSON，epPlaySrcs[集数]/videoSrc 给出 m3u8。

合规：本工具解析站点公开页面，遵守来源站点与所在地法律法规，仅用于个人整理与
     备份你有权访问的内容。请尊重版权，勿二次分发。
"""

import os
import re
import sys
import json
import time
import base64
import queue
import threading
import subprocess
import urllib.request
import urllib.parse
import urllib.error
try:
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox, scrolledtext
    HAS_GUI = True
except Exception:
    tk = None
    ttk = None
    filedialog = None
    messagebox = None
    scrolledtext = None
    HAS_GUI = False
try:
    from PIL import Image, ImageTk
    HAS_PIL = True
except Exception:
    Image = None
    ImageTk = None
    HAS_PIL = False
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    from Crypto.Cipher import AES
    HAS_CRYPTO = True
except Exception:
    HAS_CRYPTO = False

# ----------------------------------------------------------------------------
# 常量
# ----------------------------------------------------------------------------
SITE = "https://huangguoai.com"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

# 站点封面图 AES-128-CBC 密钥（前端 crypto-worker.js）。
# 原始文档标注为「UTF-8 16 bytes」，即下方 16 字符字符串的 UTF-8 编码（16 字节）。
# 但社区文档里也出现过 Hex.parse 写法（会解码成 8 字节，对 AES-128 非法）。
# 为兼容两种可能，下面按候选顺序逐一尝试：优先 16 字节 UTF-8 字符串，其次 8 字节 hex。
IMG_KEY_CANDIDATES = [
    (b"f5d965df75336270", b"97b60394abc2fbe1"),                       # UTF-8 16 字节
    (bytes.fromhex("f5d965df75336270"), bytes.fromhex("97b60394abc2fbe1")),  # hex 解码 8 字节
]

# 左侧导航：分类标签 + 路由
TABS = [
    ("首页", "home"),
    ("AI成人短剧", "ai-duanju"),
    ("AI成人漫剧", "ai-manju"),
    ("AI换脸", "ai-huanlian"),
    ("AI魔改", "ai-mogai"),
    ("排行榜", "ranks/hot"),
]

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
FFMPEG_BIN_URL = ("https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/"
                  "ffmpeg-master-latest-win64-gpl.zip")


def app_base_dir():
    """程序基目录：打包成 exe 后指向 exe 所在目录，源码运行则指向脚本目录。"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


# ----------------------------------------------------------------------------
# HTTP 工具
# ----------------------------------------------------------------------------
def http_get(url, referer=None, binary=False, timeout=30, extra_headers=None):
    """发起 GET 请求，返回 bytes 或 str。失败抛异常。"""
    headers = {
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,"
                  "image/webp,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9",
    }
    if referer:
        headers["Referer"] = referer
    if extra_headers:
        headers.update(extra_headers)
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = resp.read()
    return data if binary else data.decode("utf-8", errors="replace")


def fix_url(u):
    if not u:
        return ""
    if u.startswith("//"):
        return "https:" + u
    if u.startswith("/"):
        return SITE + u
    return u


def strip_tags(s):
    return re.sub(r"<[^>]*>", "", str(s or "")).strip()


# ----------------------------------------------------------------------------
# 图片 AES 解密
# ----------------------------------------------------------------------------
def guess_ext(data):
    if data[:2] == b"\xff\xd8":
        return "jpg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    return "jpg"


def cover_resize(img, w, h):
    """居中裁剪到 w:h 比例后缩放到 (w, h)，避免直接 resize 造成的拉伸变形。
    竖版海报裁剪时略偏上（人脸通常在上部）。"""
    sw, sh = img.size
    target, src = w / h, sw / sh
    if src > target:  # 源图太宽 → 裁两侧
        nw = int(sh * target)
        x = (sw - nw) // 2
        img = img.crop((x, 0, x + nw, sh))
    elif src < target:  # 源图太高 → 裁上下，偏上取景
        nh = int(sw / target)
        y = min((sh - nh) // 3, max(0, sh - nh))
        img = img.crop((0, y, sw, y + nh))
    return img.resize((w, h), Image.LANCZOS)


def decrypt_image(raw):
    """站点封面为 AES-128-CBC 加密字节；解密后剥离 PKCS7 padding 并截断到图像结尾。
       若源图未加密或长度非 16 倍数，则原样返回。会依次尝试多个密钥候选。"""
    if not HAS_CRYPTO:
        return raw
    if not raw or len(raw) % 16 != 0:
        return raw
    for key, iv in IMG_KEY_CANDIDATES:
        if len(key) not in (16, 24, 32) or len(iv) != 16:
            continue
        try:
            pt = AES.new(key, AES.MODE_CBC, iv).decrypt(raw)
        except Exception:
            continue
        # 开头不是图像签名 → 这个密钥不对，或无加密，跳到下一候选
        if not (pt[:2] == b"\xff\xd8"
                or pt[:8] == b"\x89PNG\r\n\x1a\n"
                or (pt[:4] == b"RIFF" and pt[8:12] == b"WEBP")
                or pt[:6] in (b"GIF87a", b"GIF89a")):
            continue
        # 剥离 PKCS7 padding
        pad = pt[-1]
        if 1 <= pad <= 16 and pt[-pad:] == bytes([pad]) * pad:
            pt = pt[:-pad]
        # 收尾截断：JPEG 留到最后一个 \xff\xd9；PNG 留到 IEND+CRC
        i = pt.rfind(b"\xff\xd9")
        if i != -1:
            pt = pt[:i + 2]
        else:
            i = pt.rfind(b"IEND")
            if i != -1:
                pt = pt[:i + 8]
        return pt
    return raw


# ----------------------------------------------------------------------------
# HTML 解析
# ----------------------------------------------------------------------------
def _card_blocks(slice_html):
    starts = [m.end() for m in
              re.finditer(r'<div\s+class="[^"]*\bhg-drama-card\b[^"]*"[^>]*>', slice_html)]
    out = []
    for idx, s in enumerate(starts):
        e = starts[idx + 1] if idx + 1 < len(starts) else len(slice_html)
        out.append(slice_html[s:e])
    return out


def _video_id_from(block):
    m = re.search(r'href="[^"]*?/video/(\d+)/[^"]*"', block)
    return m.group(1) if m else None


def _parse_card(block):
    vid = _video_id_from(block)
    if not vid:
        return None
    img_m = (re.search(r'data-src="(https?://[^"]+)"', block)
             or re.search(r'src="(https?://[^"]+)"', block)
             or re.search(r'data-src="([^"]+)"', block))
    title_m = re.search(r'hg-drama-card__title[^>]*>([\s\S]*?)</a>', block)
    title = strip_tags(title_m.group(1)) if title_m else ""
    if not title:
        alt_m = re.search(r'<img[^>]*\balt="([^"]+)"', block)
        if alt_m and alt_m.group(1).strip():
            title = alt_m.group(1).strip()
    if not title:
        tt = re.search(r'<a[^>]+href="[^"]*/video/\d+/?"[^>]*>([\s\S]*?)</a>', block)
        if tt:
            title = strip_tags(tt.group(1))
    if not title:
        return None
    ep_m = re.search(r'hg-drama-card__episode[^>]*>([\s\S]*?)</span>', block)
    score_m = re.search(r'hg-drama-card__score[^>]*>([\s\S]*?)</span>', block)
    rem = strip_tags(ep_m.group(1)) if ep_m else ""
    sc = strip_tags(score_m.group(1)) if score_m else ""
    remarks = (rem + " · " + sc) if (rem and sc) else (rem or sc)
    return {
        "id": vid,
        "name": title,
        "pic": fix_url(img_m.group(1)) if img_m else "",
        "remarks": remarks,
    }


def parse_grid_cards(html, all_grids=True):
    """解析页面中的所有 hg-drama-card 卡片（不依赖外层 grid 容器）。"""
    if not html:
        return []
    body = html[html.find("<body"):] if "<body" in html else html
    starts = [m.start() for m in
              re.finditer(r'<div\s+class="hg-drama-card"', body)]
    if not starts:
        # 兜底：匹配带其它 class 组合的卡片
        starts = [m.start() for m in
                  re.finditer(r'<div\s+class="[^"]*\bhg-drama-card\b[^"]*"', body)]
    list_out = []
    seen = set()
    for idx, s in enumerate(starts):
        e = starts[idx + 1] if idx + 1 < len(starts) else len(body)
        block = body[s:e]
        try:
            item = _parse_card(block)
            if not item or item["id"] in seen:
                continue
            seen.add(item["id"])
            list_out.append(item)
        except Exception:
            pass
    return list_out


def parse_ranks(html):
    if not html:
        return []
    m = re.search(r'<div\s+class="[^"]*\bhg-rank-list\b[^"]*"[^>]*>', html)
    from_pos = m.end() if m else 0
    slice_html = html[from_pos:]
    starts = [mm.start() for mm in
              re.finditer(r'<div\s+class="hg-rank-item"', slice_html)]
    if not starts:
        starts = [mm.start() for mm in
                  re.finditer(r'<div\s+class="[^"]*\bhg-rank-item\b[^"]*"', slice_html)]
    out = []
    seen = set()
    for i, s in enumerate(starts):
        e = starts[i + 1] if i + 1 < len(starts) else len(slice_html)
        block = slice_html[s:e]
        try:
            vid = _video_id_from(block)
            if not vid or vid in seen:
                continue
            seen.add(vid)
            img_m = (re.search(r'data-src="(https?://[^"]+)"', block)
                     or re.search(r'data-src="([^"]+)"', block))
            title = ""
            t = re.search(r'hg-rank-item__title[^>]*>([\s\S]*?)</h2>', block)
            if t:
                title = strip_tags(t.group(1))
            if not title:
                alt_m = re.search(r'<img[^>]*\balt="([^"]+)"', block)
                if alt_m and alt_m.group(1).strip():
                    title = alt_m.group(1).strip()
            if not title:
                tt = re.search(r'<a[^>]+href="[^"]*/video/\d+/?"[^>]*>([\s\S]*?)</a>', block)
                if tt:
                    title = strip_tags(tt.group(1))
            if not title:
                continue
            tags_m = re.search(r'hg-rank-item__tags[^>]*>([\s\S]*?)</div>', block)
            out.append({
                "id": vid,
                "name": title,
                "pic": fix_url(img_m.group(1)) if img_m else "",
                "remarks": strip_tags(tags_m.group(1)) if tags_m else "",
            })
        except Exception:
            pass
    return out


def parse_detail_episodes(html):
    """从详情/播放页解析选集：.hg-web-play__ep-grid 内的 <a> 给出播放页链接与 data-ep-id。"""
    episodes = []
    grid_m = re.search(
        r'<div\s+class="[^"]*\bhg-web-play__ep-grid\b[^"]*"[^>]*>([\s\S]*?)</div>', html)
    if not grid_m:
        grid_m = re.search(
            r'<div\s+class="[^"]*\bhg-web-detail__ep-grid\b[^"]*"[^>]*>([\s\S]*?)</div>', html)
    if grid_m:
        for tag in re.finditer(r'<a\b[^>]*hg-web-play__ep[^>]*>[\s\S]*?</a>', grid_m.group(1)):
            t = tag.group(0)
            href_m = re.search(r'href="([^"]+)"', t)
            if not href_m:
                continue
            href = fix_url(href_m.group(1))
            ep_m = re.search(r'data-ep-id="([^"]*)"', t)
            ep = ep_m.group(1) if ep_m else ""
            name = ("第" + ep.zfill(2) + "集") if ep else strip_tags(t)
            episodes.append({"ep": ep or str(len(episodes) + 1), "url": href, "name": name})
    if not episodes:
        # 兜底：直接找 /video/{id}/ep-{n}/ 链接
        seen = set()
        for m in re.finditer(r'href="(/video/\d+/ep-\d+/)"[^>]*data-ep-id="(\d+)"', html):
            if m.group(2) in seen:
                continue
            seen.add(m.group(2))
            episodes.append({"ep": m.group(2), "url": fix_url(m.group(1)),
                             "name": "第" + m.group(2).zfill(2) + "集"})
    return episodes


def fetch_category_api(category, page, size=21, referer=None):
    """用站点 JSON API 拉分类列表。返回 (items, pagination)；失败抛异常。"""
    url = (SITE + "/api/videos/category/" + urllib.parse.quote(category)
           + "?page=" + str(page) + "&size=" + str(size))
    text = http_get(url, referer=referer or SITE + "/", timeout=30)
    data = json.loads(text)
    items = []
    for it in (data.get("data") or {}).get("items") or []:
        vid = str(it.get("id") or "")
        title = (it.get("title") or "").strip()
        if not vid or not title:
            continue
        rem = []
        if it.get("episode_count"):
            rem.append("更新至%d集" % it["episode_count"])
        if it.get("score"):
            rem.append("%s分" % it["score"])
        items.append({
            "id": vid,
            "name": title,
            "pic": it.get("cover") or "",
            "remarks": " · ".join(rem),
        })
    return items, (data.get("data") or {}).get("pagination") or {}


def parse_detail_data(html):
    """解析详情页 videoInitialData JSON，返回 dict（title/description/coverSrc/...）。"""
    m = re.search(r'id="videoInitialData"[^>]*>([\s\S]*?)</script>', html)
    if not m:
        return None
    text = m.group(1).strip()
    try:
        return json.loads(text)
    except Exception:
        return None


def parse_detail_meta(html):
    """从 videoInitialData 抽取简介（兜底用正则找详情文本）。"""
    data = parse_detail_data(html)
    if data and data.get("description"):
        return str(data["description"])[:400]
    m = re.search(r'itemprop="description"[^>]*>([\s\S]*?)</', html)
    if m:
        return strip_tags(m.group(1))
    m = re.search(r'hg-web-detail__intro[^>]*>([\s\S]*?)</div>', html)
    if m:
        return strip_tags(m.group(1))[:300]
    return ""


def parse_playinfo(html, ep, referer):
    """从播放页 <script id="videoInitialData"> 解析 m3u8 地址与请求头。"""
    m = re.search(r'id="videoInitialData"[^>]*>([\s\S]*?)</script>', html)
    if not m:
        return None, None
    text = m.group(1).strip().replace("&quot;", '"').replace("&#34;", '"')
    try:
        data = json.loads(text)
    except Exception:
        return None, None
    srcs = data.get("epPlaySrcs") or {}
    play = srcs.get(ep) or data.get("videoSrc") or ""
    if not play:
        play = data.get("previewSrc") or data.get("contentUrl") or ""
    play = play.replace("\\u0026", "&").replace("&amp;", "&").strip()
    if play and not play.startswith("http"):
        mm = re.search(r'(https?://[^\s"\']+)', play)
        if mm:
            play = mm.group(1)
    if not play:
        return None, None
    headers = {
        "User-Agent": UA,
        "Referer": referer or SITE + "/",
        "Accept": "application/vnd.apple.mpegurl,application/x-mpegURL,*/*;q=0.8",
    }
    return play, headers


# ----------------------------------------------------------------------------
# HLS 下载
# ----------------------------------------------------------------------------
def _resolve_media_playlist(m3u8_url, headers):
    """若为主播放列表（含多个码率），挑选最高码率对应的媒体播放列表。"""
    text = http_get(m3u8_url, extra_headers=headers, timeout=30)
    if "#EXT-X-STREAM-INF" not in text:
        return m3u8_url, text
    best = None
    best_bw = -1
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.startswith("#EXT-X-STREAM-INF"):
            bw_m = re.search(r"BANDWIDTH=(\d+)", line)
            bw = int(bw_m.group(1)) if bw_m else 0
            if i + 1 < len(lines):
                uri = lines[i + 1].strip()
                if uri and not uri.startswith("#"):
                    if bw > best_bw:
                        best_bw = bw
                        best = uri
    if best:
        return urllib.parse.urljoin(m3u8_url, best), None
    return m3u8_url, text


def download_hls_ffmpeg(m3u8_url, headers, out_path, ffmpeg_path):
    hdr = "\r\n".join(f"{k}: {v}" for k, v in headers.items())
    cmd = [ffmpeg_path, "-y", "-headers", hdr, "-i", m3u8_url,
           "-c", "copy", "-bsf:a", "aac_adtstoasc", out_path]
    try:
        subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                       timeout=1800, check=True)
    except subprocess.CalledProcessError:
        cmd2 = [ffmpeg_path, "-y", "-headers", hdr, "-i", m3u8_url, "-c", "copy", out_path]
        subprocess.run(cmd2, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                       timeout=1800, check=True)
    return out_path


def download_hls_manual(m3u8_url, headers, out_path):
    """无 ffmpeg 时的回退：逐段下载并合并为 .ts（支持 HLS-AES-128 解密）。"""
    media_url, text = _resolve_media_playlist(m3u8_url, headers)
    if text is None:
        text = http_get(media_url, extra_headers=headers, timeout=30)
    base = media_url.rsplit("/", 1)[0] + "/"

    key = None
    base_iv = None
    seg_lines = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("#EXT-X-KEY"):
            uri_m = re.search(r'URI="([^"]+)"', line)
            iv_m = re.search(r'IV=0x([0-9A-Fa-f]+)', line)
            if uri_m:
                key_url = urllib.parse.urljoin(base, uri_m.group(1))
                key = http_get(key_url, binary=True, extra_headers=headers, timeout=30)
            if iv_m:
                base_iv = bytes.fromhex(iv_m.group(1))
        elif line.startswith("#"):
            continue
        else:
            seg_lines.append(line)

    with open(out_path, "wb") as fout:
        for idx, seg in enumerate(seg_lines):
            seg_url = urllib.parse.urljoin(base, seg)
            raw = http_get(seg_url, binary=True, extra_headers=headers, timeout=60)
            if key:
                iv = base_iv if base_iv else idx.to_bytes(16, "big")
                raw = AES.new(key, AES.MODE_CBC, iv).decrypt(raw)
            fout.write(raw)
    return out_path


def download_hls(m3u8_url, headers, out_path, ffmpeg_path):
    if ffmpeg_path and os.path.isfile(ffmpeg_path):
        try:
            return download_hls_ffmpeg(m3u8_url, headers, out_path, ffmpeg_path)
        except Exception:
            ts_path = os.path.splitext(out_path)[0] + ".ts"
            return download_hls_manual(m3u8_url, headers, ts_path)
    else:
        return download_hls_manual(m3u8_url, headers, out_path)


# ----------------------------------------------------------------------------
# 文件 / 目录工具
# ----------------------------------------------------------------------------
def safe_name(name):
    name = re.sub(r'[\\/:*?"<>|]', "_", name or "未命名")
    name = name.strip().strip(".")
    return name[:80] or "未命名"


def find_ffmpeg(explicit):
    if explicit and os.path.isfile(explicit):
        return explicit
    local = os.path.join(app_base_dir(), "bin", "ffmpeg.exe")
    if os.path.isfile(local):
        return local
    for p in os.environ.get("PATH", "").split(os.pathsep):
        cand = os.path.join(p, "ffmpeg.exe")
        if os.path.isfile(cand):
            return cand
    return None


def find_ffplay(explicit_ffmpeg=None):
    ff = explicit_ffmpeg or find_ffmpeg("")
    if ff:
        d = os.path.dirname(ff)
        cand = os.path.join(d, "ffplay.exe")
        if os.path.isfile(cand):
            return cand
    local = os.path.join(app_base_dir(), "bin", "ffplay.exe")
    if os.path.isfile(local):
        return local
    for p in os.environ.get("PATH", "").split(os.pathsep):
        cand = os.path.join(p, "ffplay.exe")
        if os.path.isfile(cand):
            return cand
    return None


def cache_dir():
    d = os.path.join(app_base_dir(), "cache")
    os.makedirs(d, exist_ok=True)
    return d


def local_library(save_dir):
    """扫描保存目录，返回 [(name, folder, poster_path, episode_count, episodes_files)]"""
    items = []
    if not os.path.isdir(save_dir):
        return items
    for name in sorted(os.listdir(save_dir)):
        folder = os.path.join(save_dir, name)
        if not os.path.isdir(folder):
            continue
        poster = None
        for ext in ("jpg", "png", "webp", "gif"):
            p = os.path.join(folder, "poster." + ext)
            if os.path.isfile(p):
                poster = p
                break
        eps = []
        for fn in os.listdir(folder):
            if re.match(r"第\d+集\.(mp4|ts)$", fn):
                eps.append(os.path.join(folder, fn))
        if poster or eps:
            items.append({
                "name": name, "folder": folder, "poster": poster,
                "count": len(eps), "episodes": sorted(eps),
            })
    return items


# ----------------------------------------------------------------------------
# 收藏 / 历史 / 播放进度（data.json）
# ----------------------------------------------------------------------------
DATA_PATH = os.path.join(app_base_dir(), "data.json")


def load_data():
    try:
        with open(DATA_PATH, "r", encoding="utf-8") as f:
            d = json.load(f)
        if isinstance(d, dict):
            d.setdefault("favorites", [])
            d.setdefault("history", [])
            d.setdefault("progress", {})
            return d
    except Exception:
        pass
    return {"favorites": [], "history": [], "progress": {}}


def save_data(d):
    try:
        with open(DATA_PATH, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=1)
    except Exception:
        pass


def ep_key(drama_id, ep):
    return f"{drama_id}:{ep}"


def record_history(drama_id, name, pic, ep):
    d = load_data()
    d["history"] = [h for h in d["history"] if h.get("id") != str(drama_id)]
    d["history"].insert(0, {"id": str(drama_id), "name": name, "pic": pic,
                            "ep": str(ep), "time": time.strftime("%Y-%m-%d %H:%M")})
    d["history"] = d["history"][:100]
    save_data(d)


def toggle_favorite(drama_id, name, pic, remarks=""):
    d = load_data()
    did = str(drama_id)
    for f in d["favorites"]:
        if f.get("id") == did:
            d["favorites"].remove(f)
            save_data(d)
            return False
    d["favorites"].insert(0, {"id": did, "name": name, "pic": pic,
                              "remarks": remarks, "time": time.strftime("%Y-%m-%d %H:%M")})
    save_data(d)
    return True


def is_favorite(drama_id):
    did = str(drama_id)
    return any(f.get("id") == did for f in load_data().get("favorites", []))


def get_progress(drama_id, ep):
    return load_data().get("progress", {}).get(ep_key(drama_id, ep), 0.0)


def set_progress(drama_id, ep, seconds):
    d = load_data()
    d.setdefault("progress", {})[ep_key(drama_id, ep)] = float(seconds)
    save_data(d)


# ----------------------------------------------------------------------------
# HLS 本地代理（供内嵌 hls.js 播放器使用：浏览器无法带 Referer 等请求头）
# ----------------------------------------------------------------------------
class HlsProxy:
    """127.0.0.1 本地 HTTP 服务：
       /m3u8?u=<b64url>  → 取上游播放列表并重写内部 URI 指回代理
       /seg?u=<b64url>   → 转发分片/key 二进制
       所有响应都带 CORS 头，hls.js 可直接加载。"""

    def __init__(self, headers):
        self.headers = dict(headers)
        self.port = 0
        self.httpd = None
        self.thread = None

    def start(self):
        import http.server
        from socketserver import ThreadingMixIn
        proxy = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _respond(self, data, ctype):
                self.send_response(200)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                try:
                    self.wfile.write(data)
                except Exception:
                    pass

            def do_GET(self):
                parsed = urllib.parse.urlparse(self.path)
                if parsed.path == "/player":
                    qs0 = urllib.parse.parse_qs(parsed.query)
                    ttl = (qs0.get("title") or ["播放"])[0]
                    html = (build_player_html()
                            .replace("__TITLE__", ttl.replace("<", "&lt;")))
                    self._respond(html.encode("utf-8"), "text/html; charset=utf-8")
                    return
                qs = urllib.parse.parse_qs(parsed.query)
                u = (qs.get("u") or [""])[0]
                if not u:
                    self.send_response(400)
                    self.end_headers()
                    return
                url = base64.urlsafe_b64decode(u.encode()).decode("utf-8", "replace")
                try:
                    req = urllib.request.Request(url, headers=proxy.headers)
                    with urllib.request.urlopen(req, timeout=60) as resp:
                        raw = resp.read()
                except Exception:
                    self.send_response(502)
                    self.end_headers()
                    return
                if parsed.path == "/m3u8":
                    base = url.rsplit("/", 1)[0] + "/"
                    out_lines = []
                    for line in raw.decode("utf-8", "replace").splitlines():
                        s = line.strip()
                        if not s:
                            continue
                        if s.startswith("#"):
                            m = re.search(r'URI="([^"]+)"', s)
                            if m:
                                absu = urllib.parse.urljoin(base, m.group(1))
                                s = s.replace(m.group(1), proxy._p(absu, "/key"))
                            out_lines.append(s)
                        else:
                            absu = urllib.parse.urljoin(base, s)
                            out_lines.append(proxy._p(absu, "/seg"))
                    body = ("\n".join(out_lines) + "\n").encode("utf-8")
                    self._respond(body, "application/vnd.apple.mpegurl")
                else:
                    self._respond(raw, "application/octet-stream")

        class Server(ThreadingMixIn, http.server.HTTPServer):
            daemon_threads = True

        self.httpd = Server(("127.0.0.1", 0), Handler)
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    @staticmethod
    def _b64(u):
        return base64.urlsafe_b64encode(u.encode()).decode()

    def _p(self, url, path):
        return f"http://127.0.0.1:{self.port}{path}?u=" + self._b64(url)

    def player_url(self, m3u8_url, title="", start_at=0.0, progress_id="", progress_file=""):
        q = urllib.parse.urlencode({
            "src": self._p(m3u8_url, "/m3u8"),
            "title": title or "",
            "start": start_at or 0,
            "pid": progress_id or "",
            "pfile": progress_file or "",
        })
        return f"http://127.0.0.1:{self.port}/player?{q}"

    def stop(self):
        if self.httpd:
            try:
                self.httpd.shutdown()
            except Exception:
                pass
            self.httpd = None


def hls_js_path():
    """打包内嵌的 hls.min.js（PyInstaller --add-data），否则尝试 CDN。"""
    if getattr(sys, "frozen", False):
        cand = os.path.join(sys._MEIPASS, "hls.min.js")
        if os.path.isfile(cand):
            return cand
    local = os.path.join(app_base_dir(), "hls.min.js")
    if os.path.isfile(local):
        return local
    return None


def build_player_html():
    """生成播放器 HTML（hls.js 本地内联；缺省时退回 CDN）。"""
    local = hls_js_path()
    if local:
        try:
            with open(local, "r", encoding="utf-8") as f:
                hls_src = f.read()
            hls_tag = "<script>" + hls_src + "</script>"
        except Exception:
            hls_tag = '<script src="https://cdn.jsdelivr.net/npm/hls.js@1/dist/hls.min.js"></script>'
    else:
        hls_tag = '<script src="https://cdn.jsdelivr.net/npm/hls.js@1/dist/hls.min.js"></script>'
    return """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>__TITLE__</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
  html,body{margin:0;height:100%;background:#000;overflow:hidden}
  video{width:100%;height:100%;outline:none}
  #tip{position:fixed;left:12px;top:10px;color:#fff;font:14px sans-serif;
       text-shadow:0 1px 2px #000;z-index:9;opacity:.9}
</style>
""" + hls_tag + """
</head><body>
<video id="v" controls autoplay></video>
<div id="tip">__TITLE__</div>
<script>
const qs = new URLSearchParams(location.search);
const src = qs.get("src") || "";
const startAt = parseFloat(qs.get("start") || "0") || 0;
const pid = qs.get("pid") || "";
const pfile = qs.get("pfile") || "";
const video = document.getElementById("v");
let lastReport = 0;

function report(force) {
  if (!pid || !pfile) return;
  const now = Date.now();
  if (!force && now - lastReport < 5000) return;
  lastReport = now;
  try {
    if (window.pywebview && window.pywebview.api) {
      window.pywebview.api.report_progress(pid, pfile, video.currentTime, video.duration || 0);
    }
  } catch (e) {}
}

if (Hls.isSupported()) {
  const hls = new Hls({maxBufferLength: 60});
  hls.loadSource(src);
  hls.attachMedia(video);
  hls.on(Hls.Events.MANIFEST_PARSED, function(){ video.play().catch(()=>{}); });
  hls.on(Hls.Events.ERROR, function(_, data){
    if (data.fatal) { document.getElementById("tip").textContent = "播放出错: " + data.type; }
  });
} else if (video.canPlayType("application/vnd.apple.mpegurl")) {
  video.src = src;
  video.play().catch(()=>{});
} else {
  document.getElementById("tip").textContent = "当前环境不支持 HLS 播放";
}

if (startAt > 0) {
  video.addEventListener("loadedmetadata", function once(){
    if (video.duration && startAt < video.duration - 5) video.currentTime = startAt;
    video.removeEventListener("loadedmetadata", once);
  });
}
video.addEventListener("timeupdate", () => report(false));
video.addEventListener("pause", () => report(true));
setInterval(() => report(false), 5000);
</script>
</body></html>"""


def serve_player_page(proxy, m3u8_url, title, start_at, progress_id, progress_file):
    """（已内置于 HlsProxy 的 /player 路由，保留占位以兼容旧调用。）"""
    return None


# ----------------------------------------------------------------------------
# 内嵌播放窗口（独立子进程跑 pywebview/WebView2；不可用时回退系统浏览器）
# ----------------------------------------------------------------------------
LIVE_PROGRESS_PATH = os.path.join(app_base_dir(), "progress_live.json")


class PlayerApi:
    """pywebview js_api：播放器页面每几秒回调，把进度写入 progress_live.json。"""

    def __init__(self, pfile):
        self.pfile = pfile

    def report_progress(self, pid, pfile, t, dur):
        try:
            data = {}
            if os.path.isfile(self.pfile):
                with open(self.pfile, "r", encoding="utf-8") as f:
                    data = json.load(f)
            if isinstance(data, dict):
                data[str(pid)] = {"t": float(t or 0), "dur": float(dur or 0),
                                  "time": time.time()}
                tmp = self.pfile + ".tmp"
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False)
                os.replace(tmp, self.pfile)
        except Exception:
            pass


def _playwin_main(m3u8_url, title, start_at, pid, pfile):
    """播放子进程入口：起本地代理 → 内嵌 WebView2(hls.js) 播放。"""
    proxy = HlsProxy({"User-Agent": UA})
    proxy.start()
    url = proxy.player_url(m3u8_url, title, start_at, pid, pfile)
    played_kind = "browser"
    try:
        import webview  # pywebview
        webview.create_window(title or "播放", url, width=1000, height=640,
                              js_api=PlayerApi(pfile))
        played_kind = "webview"
        webview.start()
    except Exception:
        import webbrowser
        webbrowser.open(url)
        # 浏览器模式下无进度回报，等窗口自然关闭前保持代理存活
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
    finally:
        proxy.stop()


def spawn_player(m3u8_url, title, start_at=0.0, pid="", pfile=None):
    """从主程序启动播放子进程。返回 ('webview'|'browser')。"""
    if pfile is None:
        pfile = LIVE_PROGRESS_PATH
    if getattr(sys, "frozen", False):
        cmd = [sys.executable, "--__playwin", m3u8_url, title or "",
               str(start_at), str(pid), pfile]
    else:
        cmd = [sys.executable, os.path.abspath(__file__), "--cli", "--__playwin",
               m3u8_url, title or "", str(start_at), str(pid), pfile]
    subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     close_fds=True)
    return True


def merge_live_progress():
    """把子进程写入的 progress_live.json 合并进 data.json 的 progress。"""
    try:
        if not os.path.isfile(LIVE_PROGRESS_PATH):
            return
        with open(LIVE_PROGRESS_PATH, "r", encoding="utf-8") as f:
            live = json.load(f)
        if not isinstance(live, dict) or not live:
            return
        d = load_data()
        prog = d.setdefault("progress", {})
        now = time.time()
        for k, v in live.items():
            try:
                if now - float(v.get("time", 0)) < 86400:
                    prog[k] = float(v.get("t", 0))
            except Exception:
                continue
        save_data(d)
    except Exception:
        pass
def play_m3u8(play_url, headers, title=""):
    """用 ffplay 在线播放（带请求头）；无 ffplay 则返回 ('download', None) 让调用方用
       ffmpeg 下到 mp4 再开默认播放器。"""
    ffplay = find_ffplay()
    if ffplay:
        hdr = "\r\n".join(f"{k}: {v}" for k, v in headers.items())
        cmd = [ffplay, "-headers", hdr, "-i", play_url, "-window_title", title or "播放"]
        try:
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return ("ffplay", None)
        except Exception:
            return ("download", None)
    return ("download", None)


def play_local(path):
    try:
        os.startfile(path)
        return True
    except Exception:
        return False


# ----------------------------------------------------------------------------
# 爬虫主逻辑（后台线程运行；用于批量下载）
# ----------------------------------------------------------------------------
class Crawler:
    def __init__(self, sink=None):
        self.sink = sink
        self.stop_event = threading.Event()
        self.executor = None

    def _emit(self, kind, payload):
        if self.sink is not None:
            self.sink.q.put((kind, payload))
        else:
            if kind == "log":
                print(payload)
            elif kind == "status":
                print("[状态]", payload)
            elif kind == "progress":
                print(f"[进度] {payload[0]}/{payload[1]}")
            elif kind == "done":
                print("=== 抓取结束 ===")

    def log(self, msg):
        self._emit("log", msg)

    def set_progress(self, done, total):
        self._emit("progress", (done, total))

    def set_status(self, msg):
        self._emit("status", msg)

    def stop(self):
        self.stop_event.set()
        self.log("⚠ 已请求停止，正在结束当前任务……")

    def run(self, cfg):
        try:
            self._run(cfg)
        except Exception as e:
            self.log(f"❌ 发生错误：{e}")
        finally:
            self._emit("done", None)
            if self.executor:
                self.executor.shutdown(wait=False)

    def _run(self, cfg):
        save_dir = cfg["save_dir"]
        category = cfg["category"]
        keyword = cfg["keyword"].strip()
        mode = cfg["mode"]
        max_pages = max(1, int(cfg.get("max_pages", 1)))
        workers = max(1, int(cfg.get("workers", 4)))
        do_posters = cfg.get("do_posters", True)
        do_videos = cfg.get("do_videos", True)
        ffmpeg_path = find_ffmpeg(cfg.get("ffmpeg_path"))

        os.makedirs(save_dir, exist_ok=True)
        self.executor = ThreadPoolExecutor(max_workers=workers)

        self.set_status("正在获取短剧列表……")
        dramas = []
        if mode == "search" and keyword:
            self.log(f"🔍 搜索关键词：{keyword}")
            html = http_get(SITE + "/search/video/" + urllib.parse.quote(keyword) + "/")
            dramas = parse_grid_cards(html)
        else:
            if category == "home":
                html = http_get(SITE + "/")
                dramas = parse_grid_cards(html)
            elif category.startswith("ranks"):
                html = http_get(SITE + "/" + category + "/")
                dramas = parse_ranks(html)
            else:
                for page in range(1, max_pages + 1):
                    if self.stop_event.is_set():
                        break
                    self.log(f"📄 抓取分类：{category} 第 {page} 页（JSON API）")
                    try:
                        items, pagination = fetch_category_api(category, page)
                    except Exception as e_api:
                        self.log(f"  ⚠ API 失败（{e_api}），改用 HTML 解析……")
                        try:
                            url = SITE + "/" + category + "/" + (str(page) + "/" if page > 1 else "")
                            html = http_get(url)
                            items = parse_grid_cards(html)
                        except Exception as e:
                            self.log(f"  ⚠ 该页获取失败：{e}")
                            break
                    if not items:
                        self.log("  （该页无内容，停止翻页）")
                        break
                    dramas.extend(items)
                    pages_total = pagination.get("pages") or 0
                    if pages_total and page >= pages_total:
                        break

        if not dramas:
            self.log("❌ 未解析到任何短剧，请检查网络或站点结构是否变化。")
            return
        self.log(f"✅ 共发现 {len(dramas)} 部短剧。")

        self.set_status("正在解析详情与选集……")
        detail_futures = {}
        for d in dramas:
            if self.stop_event.is_set():
                break
            fut = self.executor.submit(self._fetch_detail, d)
            detail_futures[fut] = d

        drama_episodes = {}
        for fut in as_completed(detail_futures):
            if self.stop_event.is_set():
                continue
            d = detail_futures[fut]
            try:
                eps = fut.result()
                drama_episodes[d["id"]] = eps
                if eps:
                    self.log(f"  🎬《{d['name']}》{len(eps)} 集")
                else:
                    self.log(f"  ⚠《{d['name']}》未解析到选集")
            except Exception as e:
                drama_episodes[d["id"]] = []
                self.log(f"  ⚠《{d['name']}》详情获取失败：{e}")

        tasks = []
        for d in dramas:
            folder = os.path.join(save_dir, safe_name(d["name"]))
            if do_posters and d.get("pic"):
                tasks.append(("poster", d, folder))
            if do_videos:
                for ep in drama_episodes.get(d["id"], []):
                    tasks.append(("video", d, (folder, ep)))

        total = len(tasks)
        if total == 0:
            self.log("❌ 没有可下载的任务（海报文或视频均未就绪）。")
            return
        self.log(f"🚀 开始下载，共 {total} 个任务，并发 {workers}。")
        done = 0
        self.set_progress(0, total)

        futures = {}
        for t in tasks:
            if self.stop_event.is_set():
                break
            fut = self.executor.submit(self._do_task, t, ffmpeg_path)
            futures[fut] = t

        for fut in as_completed(futures):
            t = futures[fut]
            try:
                ok, msg = fut.result()
                self.log(("  ✅ " if ok else "  ❌ ") + msg)
            except Exception as e:
                self.log(f"  ❌ 任务异常：{e}")
            done += 1
            self.set_progress(done, total)

        self.set_status(f"完成！成功归档至：{save_dir}")
        self.log(f"🏁 全部结束，成功目录：{save_dir}")

    def _fetch_detail(self, d):
        html = http_get(SITE + "/video/" + d["id"] + "/")
        return parse_detail_episodes(html)

    def _do_task(self, t, ffmpeg_path):
        kind, d, payload = t
        folder = payload if kind == "poster" else payload[0]
        os.makedirs(folder, exist_ok=True)
        if kind == "poster":
            return self._download_poster(d, folder)
        else:
            ep = payload[1]
            return self._download_video(d, ep, folder, ffmpeg_path)

    def _download_poster(self, d, folder):
        pic = d.get("pic")
        if not pic:
            return False, f"《{d['name']}》无海报地址"
        try:
            raw = http_get(pic, binary=True, timeout=40,
                           extra_headers={"Referer": SITE + "/"})
            dec = decrypt_image(raw)
            ext = guess_ext(dec)
            if ext == "jpg" and dec[:2] != b"\xff\xd8" and dec[:8] != b"\x89PNG":
                dec = raw
                ext = guess_ext(raw)
            path = os.path.join(folder, "poster." + ext)
            with open(path, "wb") as f:
                f.write(dec)
            return True, f"海报《{d['name']}》→ {os.path.basename(path)}"
        except Exception as e:
            return False, f"海报《{d['name']}》失败：{e}"

    def _download_video(self, d, ep, folder, ffmpeg_path):
        try:
            html = http_get(ep["url"], referer=SITE + "/")
            m3u8, headers = parse_playinfo(html, ep["ep"], ep["url"])
            if not m3u8:
                return False, f"《{d['name']}》{ep['name']} 未找到视频地址"
            epno = ep["ep"] if ep["ep"] else re.sub(r"\D", "", ep["name"]) or "1"
            out_base = os.path.join(folder, "第" + str(epno) + "集")
            out_mp4 = out_base + ".mp4"
            out_ts = out_base + ".ts"
            if os.path.isfile(out_mp4) or os.path.isfile(out_ts):
                return True, f"《{d['name']}》{ep['name']} 已存在，跳过"
            out = out_mp4 if (ffmpeg_path and os.path.isfile(ffmpeg_path)) else out_ts
            download_hls(m3u8, headers, out, ffmpeg_path)
            if os.path.isfile(out) and os.path.getsize(out) > 0:
                return True, f"视频《{d['name']}》{ep['name']} → {os.path.basename(out)}"
            return False, f"《{d['name']}》{ep['name']} 下载为空"
        except Exception as e:
            return False, f"视频《{d['name']}》{ep['name']} 失败：{e}"


# ----------------------------------------------------------------------------
# GUI —— 站点客户端
# ----------------------------------------------------------------------------
class App:
    def __init__(self, root):
        self.root = root
        self.root.title("黄果短剧 站点客户端")
        self.root.geometry("1080x720")
        self.root.resizable(True, True)
        # 窗口图标：优先用打包时内嵌的 app_icon.ico，其次源码目录
        try:
            icon = os.path.join(sys._MEIPASS, "app_icon.ico") \
                if getattr(sys, "_MEIPASS", None) else os.path.join(
                    os.path.dirname(os.path.abspath(__file__)), "app_icon.ico")
            if os.path.isfile(icon):
                self.root.iconbitmap(icon)
        except Exception:
            pass

        self.q = queue.Queue()
        self.cfg = self.load_config()
        self.crawler = None
        self.crawler_thread = None
        self.thumb_pool = ThreadPoolExecutor(max_workers=6)
        self.thumb_cache = {}      # url -> (path, mtime)
        self.current_cards = []    # 当前浏览列表
        self.detail_windows = []
        self.busy = False

        self.build_ui()
        self.poll_queue()

    # ---- 配置 ----
    def load_config(self):
        default = {
            "save_dir": os.path.join(os.path.expanduser("~"), "Desktop", "黄果短剧"),
            "max_pages": 3,
            "workers": 4,
            "ffmpeg_path": "",
        }
        try:
            with open(os.path.join(app_base_dir(), "config.json"), "r", encoding="utf-8") as f:
                saved = json.load(f)
            default.update(saved)
        except Exception:
            pass
        return default

    def save_config(self):
        try:
            with open(os.path.join(app_base_dir(), "config.json"), "w", encoding="utf-8") as f:
                json.dump(self.cfg, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    # ---- UI 布局 ----
    def build_ui(self):
        # 顶部工具栏
        top = ttk.Frame(self.root)
        top.pack(fill="x", padx=8, pady=6)
        ttk.Label(top, text="🏠 黄果短剧客户端", font=("Microsoft YaHei", 13, "bold")
                  ).pack(side="left")
        self.search_var = tk.StringVar()
        self.search_entry = ttk.Entry(top, textvariable=self.search_var, width=26)
        self.search_entry.pack(side="left", padx=6)
        self.search_entry.bind("<Return>", lambda e: self.do_search())
        ttk.Button(top, text="搜索", command=self.do_search).pack(side="left")
        self.ff_status = ttk.Label(top, text="")
        self.ff_status.pack(side="left", padx=10)
        ttk.Button(top, text="配置 ffmpeg", command=self.open_settings).pack(side="right")

        # 主体：左导航 + 右内容
        body = ttk.PanedWindow(self.root, orient="horizontal")
        body.pack(fill="both", expand=True, padx=6, pady=4)

        # 左侧导航
        left = ttk.Frame(body, width=160)
        body.add(left, weight=0)
        ttk.Label(left, text="浏览", font=("Microsoft YaHei", 11, "bold")).pack(anchor="w", padx=8, pady=4)
        self.nav_var = tk.StringVar(value="home")
        for label, key in TABS:
            ttk.Radiobutton(left, text=label, variable=self.nav_var, value=key,
                            command=self.on_nav).pack(anchor="w", padx=10, pady=2)
        ttk.Separator(left).pack(fill="x", padx=8, pady=6)
        ttk.Radiobutton(left, text="⭐ 收藏", variable=self.nav_var, value="__fav__",
                        command=self.on_nav).pack(anchor="w", padx=10, pady=2)
        ttk.Radiobutton(left, text="🕐 历史", variable=self.nav_var, value="__hist__",
                        command=self.on_nav).pack(anchor="w", padx=10, pady=2)
        ttk.Radiobutton(left, text="📁 本地库", variable=self.nav_var, value="__local__",
                        command=self.on_nav).pack(anchor="w", padx=10, pady=2)
        ttk.Radiobutton(left, text="⬇ 批量下载", variable=self.nav_var, value="__batch__",
                        command=self.on_nav).pack(anchor="w", padx=10, pady=2)
        self.refresh_ff_status()

        # 右侧内容
        right = ttk.Frame(body)
        body.add(right, weight=1)

        # 内容标题栏
        bar = ttk.Frame(right)
        bar.pack(fill="x", pady=2)
        self.title_var = tk.StringVar(value="首页")
        ttk.Label(bar, textvariable=self.title_var, font=("Microsoft YaHei", 12, "bold")
                  ).pack(side="left", padx=4)
        self.count_var = tk.StringVar(value="")
        ttk.Label(bar, textvariable=self.count_var).pack(side="left", padx=6)
        self.more_btn = ttk.Button(bar, text="加载更多", command=self.load_more)
        self.more_btn.pack(side="right", padx=4)
        self.refresh_btn = ttk.Button(bar, text="刷新", command=self.reload_current)
        self.refresh_btn.pack(side="right", padx=4)

        # 卡片画布（可滚动）
        self.canvas = tk.Canvas(right, bg="#f4f4f4")
        self.scroll = ttk.Scrollbar(right, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.scroll.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scroll.pack(side="right", fill="y")
        self.card_frame = ttk.Frame(self.canvas)
        self.canvas.create_window((0, 0), window=self.card_frame, anchor="nw")
        self.card_frame.bind("<Configure>", self._on_frame_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)

        # 状态栏
        self.status_var = tk.StringVar(value="就绪")
        ttk.Label(self.root, textvariable=self.status_var, relief="sunken",
                  anchor="w").pack(fill="x", side="bottom")

        self.on_nav()

    def _on_frame_configure(self, e):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas_configure(self, e):
        self.canvas.itemconfig(self.canvas.find_withtag("all"), width=e.width)
        self.reflow_cards()

    def _on_mousewheel(self, e):
        if e.widget == self.canvas or str(e.widget).startswith(str(self.card_frame)):
            self.canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")

    def reflow_cards(self):
        """按当前宽度重排卡片列数。"""
        if not self.current_cards:
            return
        cw = self.canvas.winfo_width()
        cols = max(2, min(6, cw // 200))
        for i, w in enumerate(self._card_widgets):
            r, c = divmod(i, cols)
            w.grid(row=r, column=c, padx=8, pady=8, sticky="nsew")

    # ---- 导航 ----
    def on_nav(self):
        key = self.nav_var.get()
        for label, k in TABS:
            if k == key:
                self.title_var.set(label)
                break
        else:
            self.title_var.set({"__local__": "本地库",
                                "__batch__": "批量下载",
                                "__fav__": "⭐ 收藏",
                                "__hist__": "🕐 观看历史"}.get(key, key))
        self.clear_cards()
        if key == "__local__":
            self.more_btn.pack_forget()
            self.show_local_library()
        elif key == "__batch__":
            self.more_btn.pack_forget()
            self.show_batch_panel()
        elif key == "__fav__":
            self.more_btn.pack_forget()
            self.show_favorites()
        elif key == "__hist__":
            self.more_btn.pack_forget()
            self.show_history()
        else:
            self.more_btn.pack(side="right", padx=4)
            self.load_page(1)

    def do_search(self):
        kw = self.search_var.get().strip()
        if not kw:
            messagebox.showinfo("提示", "请输入搜索关键词")
            return
        self.nav_var.set("__search__")
        self.title_var.set("搜索：" + kw)
        self._search_kw = kw
        self.more_btn.pack_forget()
        self.clear_cards()
        self.load_search()

    def clear_cards(self):
        for w in getattr(self, "_card_widgets", []):
            w.destroy()
        self._card_widgets = []
        self.current_cards = []
        self.count_var.set("")

    def load_page(self, page):
        if self.busy:
            return
        self.busy = True
        self.set_status(f"正在加载…（第 {page} 页）")
        threading.Thread(target=self._fetch_page, args=(page,), daemon=True).start()

    def _fetch_page(self, page):
        key = self.nav_var.get()
        try:
            items, pagination = [], {}
            if key == "home":
                html = http_get(SITE + "/")
                items = parse_grid_cards(html)
            elif key.startswith("ranks"):
                html = http_get(SITE + "/" + key + "/")
                items = parse_ranks(html)
            else:
                try:
                    items, pagination = fetch_category_api(key, page)
                except Exception:
                    url = SITE + "/" + key + "/" + (str(page) + "/" if page > 1 else "")
                    html = http_get(url)
                    items = parse_grid_cards(html)
            self.q.put(("cards", (items, page, pagination)))
        except Exception as e:
            self.q.put(("error", f"加载失败：{e}"))
        finally:
            self.busy = False

    def load_search(self):
        if self.busy:
            return
        self.busy = True
        threading.Thread(target=self._fetch_search, daemon=True).start()

    def _fetch_search(self):
        try:
            kw = getattr(self, "_search_kw", "")
            html = http_get(SITE + "/search/video/" + urllib.parse.quote(kw) + "/")
            items = parse_grid_cards(html)
            self.q.put(("cards", (items, 1, {})))
        except Exception as e:
            self.q.put(("error", f"搜索失败：{e}"))
        finally:
            self.busy = False

    def load_more(self):
        key = self.nav_var.get()
        if key.startswith("ranks") or key == "home":
            self.q.put(("log", "该栏目为单页"))
            return
        self._page = getattr(self, "_page", 1) + 1
        pages_total = getattr(self, "_pages_total", 0)
        if pages_total and self._page > pages_total:
            self.q.put(("log", f"已是最后一页（共 {pages_total} 页）"))
            self._page = pages_total
            return
        self.load_page(self._page)

    def reload_current(self):
        key = self.nav_var.get()
        if key in ("__local__", "__batch__"):
            return
        if key == "__search__":
            self.load_search()
        else:
            self._page = 1
            self.clear_cards()
            self.load_page(1)

    def show_local_library(self):
        items = local_library(self.cfg["save_dir"])
        self.count_var.set(f"共 {len(items)} 部")
        if not items:
            self.q.put(("error", f"本地库为空：{self.cfg['save_dir']}"))
            return
        self.current_cards = [{"id": "local", "name": it["name"], "pic": it["poster"] or "",
                               "remarks": f"{it['count']} 集", "_local": it} for it in items]
        self.q.put(("render_local", items))

    def show_favorites(self):
        merge_live_progress()
        d = load_data()
        favs = d.get("favorites", [])
        self.count_var.set(f"共 {len(favs)} 部")
        self.set_status("就绪" if favs else "还没有收藏。打开任意剧集点「★ 收藏」即可。")
        for f in favs:
            c = {"id": f["id"], "name": f.get("name", ""), "pic": f.get("pic", ""),
                 "remarks": f.get("remarks", "")}
            self.current_cards.append(c)
            self.add_card(c)
        self.reflow_cards()

    def show_history(self):
        merge_live_progress()
        d = load_data()
        hist = d.get("history", [])
        self.count_var.set(f"共 {len(hist)} 条")
        self.set_status("就绪" if hist else "暂无观看记录。")
        for h in hist:
            prog = d.get("progress", {}).get(ep_key(h["id"], h.get("ep", "1")), 0.0)
            rm = f"上次看到 {h.get('ep','1').zfill(2)} 集"
            if prog > 5:
                rm += f"（{int(prog // 60)} 分 {int(prog % 60)} 秒）"
            c = {"id": h["id"], "name": h.get("name", ""), "pic": h.get("pic", ""),
                 "remarks": rm + " · " + h.get("time", "")}
            self.current_cards.append(c)
            self.add_card(c)
        self.reflow_cards()

    # ---- 卡片渲染 ----
    def add_card(self, card):
        w = ttk.Frame(self.card_frame, relief="ridge", borderwidth=1)
        poster = tk.Label(w, bg="#ddd", width=20, height=11, cursor="hand2")
        poster.pack(fill="x")
        ttk.Label(w, text=card.get("name", "")[:20], font=("Microsoft YaHei", 9, "bold"),
                  wraplength=170).pack(fill="x", padx=4, pady=2)
        rm = card.get("remarks", "")
        if rm:
            ttk.Label(w, text=rm[:24], foreground="#666",
                      wraplength=170).pack(fill="x", padx=4)
        w.bind("<Button-1>", lambda e, c=card: self.open_detail(c))
        poster.bind("<Button-1>", lambda e, c=card: self.open_detail(c))
        self._card_widgets.append(w)
        # 缩略图
        if card.get("pic"):
            self.load_thumb(poster, card["pic"])
        else:
            poster.config(text="(无海报)")
        return w

    def load_thumb(self, label, url, size=(170, 230)):
        cdir = cache_dir()
        h = str(abs(hash(url)))
        cached = os.path.join(cdir, h + ".jpg")
        if os.path.isfile(cached):
            self.root.after(0, lambda: self._set_thumb(label, cached, *size))
            return
        def work():
            try:
                raw = http_get(url, binary=True, timeout=30,
                               extra_headers={"Referer": SITE + "/"})
                dec = decrypt_image(raw)
                ext = guess_ext(dec)
                if ext == "jpg" and dec[:2] != b"\xff\xd8" and dec[:8] != b"\x89PNG":
                    dec = raw
                    ext = guess_ext(raw)
                path = os.path.join(cdir, h + "." + ext)
                with open(path, "wb") as f:
                    f.write(dec)
                self.root.after(0, lambda: self._set_thumb(label, path, *size))
            except Exception:
                pass
        self.thumb_pool.submit(work)

    def _set_thumb(self, label, path, w=170, h=230):
        try:
            img = Image.open(path)
            img = img.convert("RGB")
            img = cover_resize(img, w, h)
            ph = ImageTk.PhotoImage(img)
            label.image = ph
            # 关键修复：Label 设置 image 后 width/height 的单位会从"文本单位"
            # 变成"像素"。占位时的 width=20/height=11 若不同步覆盖，
            # label 会被钉在约 170x11 像素，把整张海报竖着裁成一条横条。
            label.config(image=ph, text="", width=w, height=h,
                         compound="top", anchor="center")
        except Exception:
            pass

    # ---- 详情页 ----
    def open_detail(self, card):
        if card.get("id") == "local":
            self.open_local_detail(card["_local"])
            return
        win = tk.Toplevel(self.root)
        win.title("详情：" + card.get("name", ""))
        win.geometry("720x560")
        self.detail_windows.append(win)
        win.bind("<Destroy>", lambda e: self._clean_detail(win))
        DetailView(self, win, card)

    def open_local_detail(self, local):
        win = tk.Toplevel(self.root)
        win.title("本地：" + local["name"])
        win.geometry("720x560")
        self.detail_windows.append(win)
        LocalDetailView(self, win, local)

    def _clean_detail(self, win):
        if win in self.detail_windows:
            self.detail_windows.remove(win)

    # ---- 批量下载面板 ----
    def show_batch_panel(self):
        f = ttk.Frame(self.card_frame)
        self._card_widgets.append(f)
        f.grid(row=0, column=0, columnspan=6, padx=10, pady=10, sticky="nsew")
        ttk.Label(f, text="批量下载（按分类或搜索）",
                  font=("Microsoft YaHei", 12, "bold")).grid(row=0, column=0, sticky="w", pady=6)

        self.batch_mode = tk.StringVar(value="category")
        ttk.Radiobutton(f, text="按分类", variable=self.batch_mode, value="category"
                        ).grid(row=1, column=0, sticky="w")
        ttk.Radiobutton(f, text="按搜索", variable=self.batch_mode, value="search"
                        ).grid(row=1, column=1, sticky="w")

        ttk.Label(f, text="分类:").grid(row=2, column=0, sticky="w", pady=4)
        self.batch_cat = tk.StringVar(value="ai-duanju")
        cb = ttk.Combobox(f, textvariable=self.batch_cat,
                          values=[t[1] for t in TABS], state="readonly", width=18)
        cb.grid(row=2, column=1, sticky="w")
        self._batch_cat_combo = cb

        ttk.Label(f, text="关键词:").grid(row=3, column=0, sticky="w", pady=4)
        self.batch_kw = tk.StringVar()
        ttk.Entry(f, textvariable=self.batch_kw, width=22).grid(row=3, column=1, sticky="w")

        ttk.Label(f, text="翻页数:").grid(row=4, column=0, sticky="w", pady=4)
        self.batch_pages = tk.StringVar(value=str(self.cfg.get("max_pages", 3)))
        ttk.Spinbox(f, from_=1, to=50, textvariable=self.batch_pages, width=6
                    ).grid(row=4, column=1, sticky="w")
        ttk.Label(f, text="并发数:").grid(row=5, column=0, sticky="w", pady=4)
        self.batch_workers = tk.StringVar(value=str(self.cfg.get("workers", 4)))
        ttk.Spinbox(f, from_=1, to=16, textvariable=self.batch_workers, width=6
                    ).grid(row=5, column=1, sticky="w")
        self.batch_poster = tk.BooleanVar(value=True)
        self.batch_video = tk.BooleanVar(value=True)
        ttk.Checkbutton(f, text="下载海报", variable=self.batch_poster).grid(row=6, column=0, sticky="w")
        ttk.Checkbutton(f, text="下载视频", variable=self.batch_video).grid(row=6, column=1, sticky="w")

        ttk.Label(f, text="保存目录:").grid(row=7, column=0, sticky="w", pady=4)
        self.batch_dir = tk.StringVar(value=self.cfg["save_dir"])
        ttk.Entry(f, textvariable=self.batch_dir, width=40).grid(row=7, column=1, columnspan=2, sticky="w")
        ttk.Button(f, text="浏览...", command=lambda: self._pick(self.batch_dir)
                   ).grid(row=7, column=3, sticky="w", padx=4)

        ttk.Button(f, text="开始批量下载", command=self.start_batch
                   ).grid(row=8, column=0, pady=8, sticky="w")

        # 日志框
        self.batch_log = scrolledtext.ScrolledText(f, height=14, width=80)
        self.batch_log.grid(row=9, column=0, columnspan=4, pady=6, sticky="nsew")
        self.batch_log.config(state="disabled")

    def _pick(self, var):
        d = filedialog.askdirectory(initialdir=var.get())
        if d:
            var.set(d)

    def start_batch(self):
        cfg = {
            "save_dir": self.batch_dir.get(),
            "mode": self.batch_mode.get(),
            "category": self.batch_cat.get(),
            "keyword": self.batch_kw.get(),
            "max_pages": int(self.batch_pages.get() or 3),
            "workers": int(self.batch_workers.get() or 4),
            "do_posters": self.batch_poster.get(),
            "do_videos": self.batch_video.get(),
            "ffmpeg_path": self.cfg.get("ffmpeg_path", ""),
        }
        self.cfg["save_dir"] = cfg["save_dir"]
        self.cfg["max_pages"] = cfg["max_pages"]
        self.cfg["workers"] = cfg["workers"]
        self.save_config()
        if not cfg["do_posters"] and not cfg["do_videos"]:
            messagebox.showwarning("提示", "请至少勾选一项")
            return
        self.batch_start_btn_state(False)
        self.crawler = Crawler(self)
        self.crawler_thread = threading.Thread(
            target=self.crawler.run, args=(dict(cfg),), daemon=True)
        self.crawler_thread.start()

    def batch_start_btn_state(self, enabled):
        # 找到开始批量下载按钮
        for w in getattr(self, "_card_widgets", []):
            for child in w.winfo_children():
                if isinstance(child, ttk.Button) and child.cget("text") == "开始批量下载":
                    child.config(state="normal" if enabled else "disabled")

    # ---- 播放 / 下载（供详情页调用） ----
    def play_episode(self, card, ep):
        self.set_status(f"正在获取播放地址：《{card['name']}》{ep['name']} …")
        threading.Thread(target=self._play_worker, args=(card, ep), daemon=True).start()

    def _play_worker(self, card, ep):
        try:
            html = http_get(ep["url"], referer=SITE + "/")
            m3u8, headers = parse_playinfo(html, ep["ep"], ep["url"])
            if not m3u8:
                self.q.put(("error", "未找到播放地址"))
                return
            # 记录历史
            record_history(card["id"], card["name"], card.get("pic", ""), ep["ep"])
            merge_live_progress()
            start_at = get_progress(card["id"], ep["ep"])
            pid = ep_key(card["id"], ep["ep"])
            title = f"{card['name']} {ep['name']}"
            spawn_player(m3u8_url=m3u8, title=title, start_at=start_at,
                         pid=pid, pfile=LIVE_PROGRESS_PATH)
            resume = f"，从 {int(start_at//60)} 分 {int(start_at%60)} 秒续播" if start_at > 5 else ""
            self.q.put(("log", f"▶ 已打开播放窗口：《{card['name']}》{ep['name']}{resume}"))
            self.set_status(f"正在播放：《{card['name']}》{ep['name']}{resume}")
        except Exception as e:
            self.q.put(("error", f"播放失败：{e}"))

    def download_single(self, card, log_fn):
        """详情页「下载整部」：下载海报 + 全部选集到本地。"""
        threading.Thread(target=self._download_single_worker, args=(card, log_fn),
                         daemon=True).start()

    def _download_single_worker(self, card, log_fn):
        ffmpeg_path = find_ffmpeg(self.cfg.get("ffmpeg_path", ""))
        folder = os.path.join(self.cfg["save_dir"], safe_name(card["name"]))
        os.makedirs(folder, exist_ok=True)
        # 海报
        if card.get("pic"):
            try:
                raw = http_get(card["pic"], binary=True, timeout=40,
                               extra_headers={"Referer": SITE + "/"})
                dec = decrypt_image(raw)
                ext = guess_ext(dec)
                if ext == "jpg" and dec[:2] != b"\xff\xd8" and dec[:8] != b"\x89PNG":
                    dec = raw
                    ext = guess_ext(raw)
                with open(os.path.join(folder, "poster." + ext), "wb") as f:
                    f.write(dec)
                log_fn("✅ 海报已存")
            except Exception as e:
                log_fn(f"❌ 海报失败：{e}")
        # 选集
        try:
            html = http_get(SITE + "/video/" + card["id"] + "/")
            eps = parse_detail_episodes(html)
        except Exception as e:
            log_fn(f"❌ 详情获取失败：{e}")
            return
        if not eps:
            log_fn("⚠ 未解析到选集")
            return
        for ep in eps:
            try:
                ph = http_get(ep["url"], referer=SITE + "/")
                m3u8, headers = parse_playinfo(ph, ep["ep"], ep["url"])
                if not m3u8:
                    log_fn(f"⚠ {ep['name']} 无地址")
                    continue
                epno = ep["ep"] if ep["ep"] else re.sub(r"\D", "", ep["name"]) or "1"
                out = os.path.join(folder, "第" + str(epno) + "集.mp4")
                if os.path.isfile(out):
                    log_fn(f"· {ep['name']} 已存在")
                    continue
                download_hls(m3u8, headers, out, ffmpeg_path)
                log_fn(f"✅ {ep['name']}")
            except Exception as e:
                log_fn(f"❌ {ep['name']} 失败：{e}")
        log_fn("🏁 本部下完成")

    # ---- 设置 ----
    def open_settings(self):
        win = tk.Toplevel(self.root)
        win.title("设置")
        win.geometry("460x220")
        ttk.Label(win, text="保存目录:").grid(row=0, column=0, sticky="w", padx=8, pady=6)
        self.set_dir = tk.StringVar(value=self.cfg["save_dir"])
        ttk.Entry(win, textvariable=self.set_dir, width=40).grid(row=0, column=1, padx=4)
        ttk.Button(win, text="浏览...", command=lambda: self._pick(self.set_dir)
                   ).grid(row=0, column=2, padx=4)
        ttk.Label(win, text="ffmpeg.exe:").grid(row=1, column=0, sticky="w", padx=8, pady=6)
        self.set_ff = tk.StringVar(value=self.cfg.get("ffmpeg_path", ""))
        ttk.Entry(win, textvariable=self.set_ff, width=40).grid(row=1, column=1, padx=4)
        ttk.Button(win, text="浏览...", command=lambda: self._pick(self.set_ff)
                   ).grid(row=1, column=2, padx=4)
        ttk.Button(win, text="自动下载 ffmpeg", command=lambda: self.auto_download_ffmpeg(win)
                   ).grid(row=2, column=1, pady=6, sticky="w")
        ttk.Button(win, text="保存", command=lambda: self.save_settings(win)
                   ).grid(row=3, column=1, pady=6, sticky="e")

    def save_settings(self, win):
        self.cfg["save_dir"] = self.set_dir.get()
        self.cfg["ffmpeg_path"] = self.set_ff.get()
        self.save_config()
        self.refresh_ff_status()
        win.destroy()
        messagebox.showinfo("已保存", "设置已保存")

    def refresh_ff_status(self):
        ff = find_ffmpeg(self.cfg.get("ffmpeg_path", ""))
        if ff:
            self.ff_status.config(text="✅ ffmpeg 就绪", foreground="green")
        elif getattr(self, "ff_status", None):
            self.ff_status.config(text="⚠ 未配置 ffmpeg", foreground="red")

    def auto_download_ffmpeg(self, win=None):
        self.set_status("正在下载 ffmpeg（约 40MB）……")
        threading.Thread(target=self._auto_ff_worker, args=(win,), daemon=True).start()

    def _auto_ff_worker(self, win):
        try:
            import zipfile, tempfile
            bin_dir = os.path.join(app_base_dir(), "bin")
            os.makedirs(bin_dir, exist_ok=True)
            tmp = os.path.join(tempfile.gettempdir(), "ffmpeg.zip")
            data = http_get(FFMPEG_BIN_URL, binary=True, timeout=180)
            with open(tmp, "wb") as f:
                f.write(data)
            with zipfile.ZipFile(tmp) as z:
                for name in z.namelist():
                    if name.endswith("ffmpeg.exe"):
                        z.extract(name, bin_dir)
                        src = os.path.join(bin_dir, name)
                        dst = os.path.join(bin_dir, "ffmpeg.exe")
                        if src != dst:
                            if os.path.isfile(dst):
                                os.remove(dst)
                            os.replace(src, dst)
                        break
                # ffplay 同包
                for name in z.namelist():
                    if name.endswith("ffplay.exe"):
                        z.extract(name, bin_dir)
                        src = os.path.join(bin_dir, name)
                        dst = os.path.join(bin_dir, "ffplay.exe")
                        if src != dst:
                            if os.path.isfile(dst):
                                os.remove(dst)
                            os.replace(src, dst)
                        break
            os.remove(tmp)
            self.cfg["ffmpeg_path"] = os.path.join(bin_dir, "ffmpeg.exe")
            self.save_config()
            self.q.put(("ffready", "✅ ffmpeg 已下载到 bin/（含 ffplay）"))
        except Exception as e:
            self.q.put(("error", f"ffmpeg 下载失败：{e}（可手动下载放到 bin/ 或 PATH）"))

    # ---- 状态 / 队列 ----
    def set_status(self, msg):
        try:
            self.status_var.set(msg)
        except Exception:
            pass

    def poll_queue(self):
        try:
            while True:
                kind, payload = self.q.get_nowait()
                if kind == "cards":
                    items, page, pagination = payload
                    self._page = page
                    self._pages_total = (pagination or {}).get("pages") or 0
                    if page == 1:
                        self.clear_cards()
                    for c in items:
                        self.current_cards.append(c)
                        self.add_card(c)
                    self.count_var.set(f"共 {len(self.current_cards)} 部")
                    self.reflow_cards()
                    if not items:
                        self.set_status("该栏目暂无内容")
                    else:
                        self.set_status("就绪")
                elif kind == "render_local":
                    items = payload
                    for it in items:
                        c = {"id": "local", "name": it["name"], "pic": it["poster"] or "",
                             "remarks": f"{it['count']} 集", "_local": it}
                        self.current_cards.append(c)
                        self.add_card(c)
                    self.reflow_cards()
                elif kind == "log":
                    self.append_batch_log(payload)
                elif kind == "error":
                    self.set_status(str(payload))
                    messagebox.showerror("错误", str(payload)) if HAS_GUI else None
                elif kind == "ffready":
                    self.refresh_ff_status()
                    self.set_status(payload)
                    self.append_batch_log(payload)
                elif kind == "progress":
                    pass  # 批量下载进度合并在日志里
                elif kind == "status":
                    self.set_status(str(payload))
                elif kind == "done":
                    self.batch_start_btn_state(True)
                    self.set_status("批量下载完成")
        except queue.Empty:
            pass
        # 每 ~20 秒合并一次播放子进程写入的进度
        self._poll_count = getattr(self, "_poll_count", 0) + 1
        if self._poll_count % 128 == 0:
            try:
                merge_live_progress()
            except Exception:
                pass
        self.root.after(150, self.poll_queue)

    def append_batch_log(self, msg):
        if hasattr(self, "batch_log"):
            self.batch_log.config(state="normal")
            self.batch_log.insert("end", msg + "\n")
            self.batch_log.see("end")
            self.batch_log.config(state="disabled")

    def append_detail_log(self, win, msg):
        # 详情页日志（若有）
        attr = getattr(win, "_log", None)
        if attr:
            attr.config(state="normal")
            attr.insert("end", msg + "\n")
            attr.see("end")
            attr.config(state="disabled")


# ----------------------------------------------------------------------------
# 详情视图
# ----------------------------------------------------------------------------
class DetailView:
    def __init__(self, app, win, card):
        self.app = app
        self.win = win
        self.card = card
        self.episodes = []
        self.poster_label = tk.Label(win, bg="#ddd", width=26, height=20)
        self.poster_label.pack(side="left", padx=10, pady=10, fill="y")

        right = ttk.Frame(win)
        right.pack(side="left", fill="both", expand=True, padx=8, pady=8)
        ttk.Label(right, text=card.get("name", ""), font=("Microsoft YaHei", 14, "bold")
                  ).pack(anchor="w")
        self.meta_var = tk.StringVar(value=card.get("remarks", ""))
        ttk.Label(right, textvariable=self.meta_var, foreground="#666").pack(anchor="w", pady=2)
        self.intro_var = tk.StringVar(value="")
        ttk.Label(right, textvariable=self.intro_var, wraplength=420,
                  foreground="#444").pack(anchor="w", pady=4, fill="x")

        bf = ttk.Frame(right)
        bf.pack(anchor="w", pady=6)
        ttk.Button(bf, text="⬇ 下载整部", command=self.download_all).pack(side="left", padx=4)
        self.fav_btn = ttk.Button(bf, text="★ 收藏", command=self.toggle_fav)
        self.fav_btn.pack(side="left", padx=4)
        ttk.Button(bf, text="🌐 浏览器打开",
                   command=lambda: os.startfile(SITE + "/video/" + card["id"] + "/")
                   if os.name == "nt" else None).pack(side="left", padx=4)
        self._update_fav_btn()

        ttk.Label(right, text="选集", font=("Microsoft YaHei", 11, "bold")
                  ).pack(anchor="w", pady=4)
        ep_frame = ttk.Frame(right)
        ep_frame.pack(fill="both", expand=True)
        self.ep_canvas = tk.Canvas(ep_frame)
        self.ep_scroll = ttk.Scrollbar(ep_frame, orient="vertical",
                                       command=self.ep_canvas.yview)
        self.ep_inner = ttk.Frame(self.ep_canvas)
        self.ep_canvas.create_window((0, 0), window=self.ep_inner, anchor="nw")
        self.ep_canvas.configure(yscrollcommand=self.ep_scroll.set)
        self.ep_canvas.pack(side="left", fill="both", expand=True)
        self.ep_scroll.pack(side="right", fill="y")
        self.ep_inner.bind("<Configure>",
                            lambda e: self.ep_canvas.configure(
                                scrollregion=self.ep_canvas.bbox("all")))

        win._log = scrolledtext.ScrolledText(right, height=6)
        win._log.pack(fill="x", pady=6)
        win._log.config(state="disabled")

        # 加载海报 + 选集
        if card.get("pic"):
            app.load_thumb(self.poster_label, card["pic"], size=(220, 300))
        threading.Thread(target=self._load, daemon=True).start()

    def _load(self):
        try:
            html = http_get(SITE + "/video/" + self.card["id"] + "/", referer=SITE + "/")
            self.episodes = parse_detail_episodes(html)
            intro = parse_detail_meta(html)
            self.app.root.after(0, lambda: self.meta_var.set(
                (self.card.get("remarks", "") + " · " + str(len(self.episodes)) + " 集").strip(" · ")))
            if intro:
                self.app.root.after(0, lambda: self.intro_var.set(intro[:300]))
            self.app.root.after(0, self.render_episodes)
        except Exception as e:
            self.app.append_detail_log(self.win, f"详情加载失败：{e}")

    def render_episodes(self):
        for w in self.ep_inner.winfo_children():
            w.destroy()
        for ep in self.episodes:
            row = ttk.Frame(self.ep_inner)
            row.pack(fill="x", pady=2)
            ttk.Label(row, text=ep["name"], width=12).pack(side="left", padx=4)
            ttk.Button(row, text="▶ 播放", command=lambda e=ep: self.app.play_episode(self.card, e)
                       ).pack(side="left", padx=4)
            ttk.Button(row, text="⬇ 下载", command=lambda e=ep: self.download_one(e)
                       ).pack(side="left", padx=4)

    def _update_fav_btn(self):
        try:
            if is_favorite(self.card["id"]):
                self.fav_btn.config(text="✚ 已收藏（点取消）")
            else:
                self.fav_btn.config(text="★ 收藏")
        except Exception:
            pass

    def toggle_fav(self):
        on = toggle_favorite(self.card["id"], self.card.get("name", ""),
                             self.card.get("pic", ""), self.card.get("remarks", ""))
        self._update_fav_btn()
        self.app.set_status("已收藏" if on else "已取消收藏")

    def download_one(self, ep):
        def log(msg):
            self.app.append_detail_log(self.win, msg)
        log(f"开始 {ep['name']} …")
        threading.Thread(target=self._dl_one, args=(ep, log), daemon=True).start()

    def _dl_one(self, ep, log):
        ff = find_ffmpeg(self.app.cfg.get("ffmpeg_path", ""))
        try:
            ph = http_get(ep["url"], referer=SITE + "/")
            m3u8, headers = parse_playinfo(ph, ep["ep"], ep["url"])
            if not m3u8:
                log(f"⚠ {ep['name']} 无地址")
                return
            folder = os.path.join(self.app.cfg["save_dir"], safe_name(self.card["name"]))
            os.makedirs(folder, exist_ok=True)
            epno = ep["ep"] if ep["ep"] else re.sub(r"\D", "", ep["name"]) or "1"
            out = os.path.join(folder, "第" + str(epno) + "集.mp4")
            if os.path.isfile(out):
                log(f"· 已存在")
                return
            download_hls(m3u8, headers, out, ff)
            log(f"✅ {ep['name']}")
        except Exception as e:
            log(f"❌ {ep['name']} 失败：{e}")

    def download_all(self):
        def log(msg):
            self.app.append_detail_log(self.win, msg)
        self.app.download_single(self.card, log)


class LocalDetailView:
    def __init__(self, app, win, local):
        self.app = app
        self.win = win
        self.local = local
        poster = tk.Label(win, bg="#ddd", width=26, height=20)
        poster.pack(side="left", padx=10, pady=10, fill="y")
        if local.get("poster") and os.path.isfile(local["poster"]):
            try:
                img = Image.open(local["poster"]).convert("RGB")
                img = cover_resize(img, 200, 270)
                ph = ImageTk.PhotoImage(img)
                poster.image = ph
                # 同样要覆盖占位的文本单位 width/height（图片模式下单位是像素）
                poster.config(image=ph, width=200, height=270)
            except Exception:
                pass

        right = ttk.Frame(win)
        right.pack(side="left", fill="both", expand=True, padx=8, pady=8)
        ttk.Label(right, text=local["name"], font=("Microsoft YaHei", 14, "bold")
                  ).pack(anchor="w")
        ttk.Label(right, text=f"已下载 {local['count']} 集").pack(anchor="w", pady=2)
        ttk.Button(right, text="📂 打开文件夹",
                   command=lambda: os.startfile(local["folder"]) if os.name == "nt" else None
                   ).pack(anchor="w", pady=6)

        ttk.Label(right, text="本地文件", font=("Microsoft YaHei", 11, "bold")
                  ).pack(anchor="w", pady=4)
        ep_frame = ttk.Frame(right)
        ep_frame.pack(fill="both", expand=True)
        canvas = tk.Canvas(ep_frame)
        scroll = ttk.Scrollbar(ep_frame, orient="vertical", command=canvas.yview)
        inner = ttk.Frame(canvas)
        canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=scroll.set)
        canvas.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        for p in local["episodes"]:
            row = ttk.Frame(inner)
            row.pack(fill="x", pady=2)
            ttk.Label(row, text=os.path.basename(p), width=20).pack(side="left", padx=4)
            ttk.Button(row, text="▶ 播放",
                       command=lambda pp=p: play_local(pp)).pack(side="left", padx=4)


# ----------------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------------
def run_cli(args):
    import argparse
    p = argparse.ArgumentParser(description="黄果短剧 站点客户端（命令行模式）")
    p.add_argument("--category", default="ai-duanju")
    p.add_argument("--search", default="", help="搜索关键词（与 --category 二选一）")
    p.add_argument("--pages", type=int, default=3)
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--save-dir", required=True)
    p.add_argument("--ffmpeg", default="")
    p.add_argument("--no-posters", action="store_true")
    p.add_argument("--no-videos", action="store_true")
    a = p.parse_args(args)

    cfg = {
        "save_dir": a.save_dir,
        "mode": "search" if a.search else "category",
        "category": a.category,
        "keyword": a.search,
        "max_pages": a.pages,
        "workers": a.workers,
        "do_posters": not a.no_posters,
        "do_videos": not a.no_videos,
        "ffmpeg_path": a.ffmpeg,
    }
    crawler = Crawler(None)
    crawler.run(cfg)


def main():
    argv = sys.argv[1:]
    # 播放子进程模式：exe --__playwin <m3u8> <title> <start> <pid> <pfile>
    if "--__playwin" in argv:
        i = argv.index("--__playwin")
        rest = argv[i + 1:]
        if len(rest) >= 5:
            try:
                start_at = float(rest[2])
            except Exception:
                start_at = 0.0
            _playwin_main(rest[0], rest[1], start_at, rest[3], rest[4])
        return
    if not HAS_CRYPTO:
        print("⚠ 未安装 pycryptodome，海报解密将不可用。请运行：pip install pycryptodome")
    if "--cli" in argv or not HAS_GUI:
        cli_args = [x for x in argv if x != "--cli"]
        if not cli_args and not HAS_GUI:
            print("当前环境缺少 tkinter（GUI 不可用）。请用命令行模式运行，例如：")
            print('  python huangguo_downloader.py --cli --category ai-duanju '
                  '--save-dir "D:\\黄果短剧"')
            return
        run_cli(cli_args)
        return
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
