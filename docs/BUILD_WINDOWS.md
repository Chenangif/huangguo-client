# 打包 Windows exe

## 一键打包

双击 `windows/build_exe.bat`，产物在 `windows\dist\HuangguoDownloader.exe`。

脚本做了三件事：检查 `python` 可用 → 检查 tkinter 可用 → `pip install` 依赖并 PyInstaller 打包。

打包命令（脚本内实际执行）：

```bat
python -m PyInstaller --onefile --windowed --name HuangguoDownloader ^
  --icon app_icon.ico ^
  --add-data "hls.min.js;." --add-data "app_icon.ico;." ^
  --hidden-import Crypto.Cipher.AES --hidden-import PIL --hidden-import PIL.Image --hidden-import PIL.ImageTk ^
  --collect-all webview --collect-all clr_loader --hidden-import clr ^
  huangguo_downloader.py
```

## ⚠️ 最常见的坑：打包成功但 exe 双击无反应

**原因**：打包用的 Python 解释器**没有可用的 tcl/tk**（例如嵌入式或某些托管版 Python）。
PyInstaller 依然会报 `Build complete`，但产物缺少 tkinter → 启动时 `import tkinter` 失败；又因为 `--windowed` 没有控制台，错误被吞掉，表现就是「双击什么都没有」。

**排查**：在打包用的那个解释器上执行

```bat
python -c "import tkinter; tkinter.Tk()"
```

报错就换解释器。

**解决**：用从 python.org 安装的 Python，安装时勾选
`Add python.exe to PATH` 与 `tcl/tk and IDLE`，并确保它在 PATH 中排第一。

`build_exe.bat` 开头已内置这个守卫，检测到无 tkinter 会直接报错停止，避免打出「哑炮」。

## 依赖

运行时（打进 exe）：`pycryptodome`（封面解密）、`Pillow`（图片缩放）、`pywebview`（内嵌播放窗口）。
仅打包时需要：`pyinstaller`。
可选：`ffmpeg.exe` / `ffplay.exe` 放 exe 同目录 `bin\`，用于 mp4 下载与 ffplay 播放。

## 运行期生成的文件（在 exe 同目录）

| 文件 | 说明 |
|---|---|
| `config.json` | 保存目录、ffmpeg 路径等设置 |
| `data.json` | 收藏、观看历史、每集播放进度 |
| `progress_live.json` | 播放窗口实时进度（自动合并进 data.json） |
| `cache\` | 海报缓存，可随时删除 |
