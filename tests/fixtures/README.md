# 测试样本（fixtures）

`tests/test_logic.py` 的 B 组用例需要真实页面样本才能完整运行。

## 准备样本

在 Windows PowerShell 里执行（带 UA 头，否则站点会拒绝）：

```powershell
$ua = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
$h  = @{ 'User-Agent' = $ua; 'Referer' = 'https://huangguoai.com/' }
$d  = 'tests\fixtures\site_debug'
New-Item -ItemType Directory -Force -Path $d | Out-Null

Invoke-WebRequest -Uri 'https://huangguoai.com/'          -Headers $h -OutFile "$d\home.html"
Invoke-WebRequest -Uri 'https://huangguoai.com/video/{id}/' -Headers $h -OutFile "$d\detail.html"
Invoke-WebRequest -Uri 'https://huangguoai.com/ranks/hot/'   -Headers $h -OutFile "$d\rank.html"
Invoke-WebRequest -Uri 'https://huangguoai.com/api/videos/category/ai-duanju?page=1&size=21' `
                  -Headers $h -OutFile "$d\cat.json"
```

`{id}` 换成任意剧集 id（从首页卡片链接里取）。

## 说明

- 样本页面是第三方站点内容，**已通过 .gitignore 排除，不入库**；
- 未放样本时，B 组用例会自动跳过，A 组（合成数据）仍完整运行。

`site_debug/*.py` 是结构分析脚本，用于站点改版后重新确认解析规则。
