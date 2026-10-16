# 黄果短剧 站点客户端

一个把 huangguoai.com「搬进本地」的客户端项目，包含两个端：

| 端 | 技术栈 | 产物 |
|---|---|---|
| **Windows 桌面端** | Python 3 + tkinter + pywebview | 单文件 `HuangguoDownloader.exe` |
| **Android 手机端** | Java + Gradle + Android SDK + ExoPlayer(media3) | `黄果短剧-安卓版.apk` |

两端共用同一套站点解析规则：浏览分类 / 排行榜 / 搜索、解密显示海报、解析选集、取 m3u8 播放地址、后台下载。

---

## 目录结构

```
.
├── windows/                  # Windows 桌面端（Python）
│   ├── huangguo_downloader.py    # 主程序：GUI + CLI + 内嵌播放器 + 下载
│   ├── build_exe.bat             # 一键打包成单文件 exe
│   ├── requirements.txt          # 运行/打包依赖
│   ├── hls.min.js                # 内嵌播放器内核（离线内置）
│   ├── app_icon.ico / .png       # 程序图标
├── android/                  # Android 手机端（Gradle 工程）
│   ├── settings.gradle / build.gradle / gradle.properties
│   └── app/
│       ├── build.gradle
│       └── src/main/
│           ├── AndroidManifest.xml
│           ├── java/com/huangguo/app/     # 17 个类
│           │   ├── Site.java              # 站点解析层（与桌面端同一套规则）
│           │   ├── Http.java / WebFetch.java  # OkHttp + WebView 兜底
│           │   ├── CryptoUtil.java        # 封面 AES-128-CBC 解密
│           │   ├── MainActivity.java      # 分类 Tabs + 搜索 + 收藏/历史
│           │   ├── DetailActivity.java    # 详情 + 选集
│           │   ├── PlayerActivity.java    # 播放器：全屏/长按2x/旋转/选集
│           │   ├── Downloads.java / DownloadService.java / DownloadsActivity.java
│           │   └── Store.java / CoverLoader.java / CardAdapter.java / EpisodeAdapter.java / App.java
│           └── res/                        # 布局、图标、主题
├── tests/                    # 解析层与代理的单元/端到端测试（43 项）
│   ├── test_logic.py
│   ├── test_proxy_e2e.py
│   └── fixtures/            # 抓取脚本；页面样本需自行放置（不入库）
├── docs/                     # 构建与站点结构文档
│   ├── SITE_STRUCTURE.md
│   ├── BUILD_WINDOWS.md
│   └── BUILD_ANDROID.md
└── LICENSE
```

---

## 功能

### 浏览
- 首页 / AI成人短剧 / AI成人漫剧 / AI换脸 / AI魔改 / 排行榜 六个栏目；
- 关键词搜索；
- 分类列表走站点 JSON 接口（分页准确），卡片墙显示解密后的海报 + 标题，下滑自动翻页。

### 播放
- **桌面端**：程序内嵌播放窗口（WebView2 + 离线内置 hls.js），视频流经本地代理转发（自动带站点请求头、处理 HLS AES-128 密钥）；无 WebView2 时回退系统浏览器。
- **手机端**：ExoPlayer(media3) 播 HLS，带 UA/Referer 头。
  - **全屏**：横屏 + 沉浸隐藏状态栏/导航栏，**全屏时零 UI，点一下屏幕才出现控制条和按钮**，3 秒不动自动隐藏；
  - **长按画面 2 倍速**，松手恢复 1 倍（无任何提示浮层）；
  - **旋转**按钮：横屏 / 竖屏一键切换；
  - **选集**：播放页底部横滑集数条，点一下直接换集；
  - **不息屏**：播放中 / 全屏中保持屏幕常亮，暂停或退出后恢复自动息屏。

### 收藏 / 历史
- 收藏：详情页「★ 收藏」按钮，或**长按任意海报**；收藏页长按可取消。
- 历史：播放自动记录（看了第几集、播到第几秒），详情页出现「▶ 续播 第NN集」，历史页点击直接续播；长按可删记录。

### 下载
- **桌面端**：单集下载 / 整部下载 / 按分类批量抓取；按「剧名」建文件夹，含 `poster` 与各集视频。有 ffmpeg 存 mp4，无 ffmpeg 走内置 TS 合并。
- **手机端**：长按集数加入队列 → 「下载」页看实时进度，支持**暂停 / 继续 / 取消 / 失败重试 / 播放 / 删除**；文件存到手机 `下载/黄果短剧/剧名_第NN集.ts`。

---

## 快速开始

### Windows 桌面端

**方式一：直接用打包好的 exe**
双击 `HuangguoDownloader.exe` 即可，无需安装任何东西。
- 播放不需要 ffmpeg（内置播放器内核）；
- 下载成 mp4 需要 ffmpeg：右上角「配置 ffmpeg」→「自动下载 ffmpeg」；
- 没有 ffmpeg 也能下载，会走内置 TS 合并（存 `.ts`）。

**方式二：运行源码**
```bat
pip install -r windows/requirements.txt
python windows/huangguo_downloader.py
```

**命令行批量模式**
```bat
python windows/huangguo_downloader.py --cli --category ai-duanju --pages 3 --save-dir "D:\黄果短剧"
```

**打包 exe**
双击 `windows/build_exe.bat`，产物在 `dist\HuangguoDownloader.exe`。
> 详见 [docs/BUILD_WINDOWS.md](docs/BUILD_WINDOWS.md)（含「打出来双击没反应」的排查）。

### Android 手机端

- 最低支持 **Android 7.0（API 24）**，目标 API 34；
- 传到手机安装时允许「未知来源」即可（debug 签名，未上架商店）；
- 首次点下载会要**通知权限**（Android 13+），允许后再点一次下载。

**从源码构建** 见 [docs/BUILD_ANDROID.md](docs/BUILD_ANDROID.md)（Windows 原生 Gradle，不需要 WSL）。

---

## 运行/构建环境

- Python 3.13（安装时勾选 `Add python.exe to PATH` 与 `tcl/tk and IDLE`）
- JDK 17 + Android SDK（platform 34 / build-tools 34.0.0）+ Gradle 8.7
- 可选：`ffmpeg.exe` / `ffplay.exe` 放到 exe 同目录的 `bin\`

---

## 测试

```bat
python tests/test_logic.py        # 43 项：合成数据 + 真实样本页面
python tests/test_proxy_e2e.py    # 端到端：本地代理的 m3u8 重写与分片转发
```

`test_logic.py` 会读取 `tests/fixtures/site_debug/*.html`；样本页面未放置时会自动跳过真实页面部分（仅验证合成数据）。

---

## 合规说明

本项目仅解析目标站点的公开页面，用于**个人整理与备份你有权访问的内容**。请遵守来源站点的服务条款与所在地区的法律法规，**不要二次分发**抓取到的视频资源。本项目不托管、不分发任何受版权保护的内容。
