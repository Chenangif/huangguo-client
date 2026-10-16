import re, json
html = open('detail.html', encoding='utf-8').read()
m = re.search(r'<script[^>]*id="videoInitialData"[^>]*>(.*?)</script>', html, re.S)
data = json.loads(m.group(1).strip())
for k in ['title','ep','videoSrc','videoType','videoApi','videoKey','videoIv','posterSrc','previewSrc','views','time','tags']:
    v = data.get(k)
    print(k, '=', (str(v)[:160] if v is not None else None))
print('epPlaySrcs eps =', sorted(data['epPlaySrcs'].keys(), key=lambda x:int(x))[:30], '... total', len(data['epPlaySrcs']))

# 页面上集数按钮怎么渲染
for pat in ['hg-web-detail', 'ep-item', 'ep-list', 'playlist', 'hg-ep']:
    idxs = [mm.start() for mm in re.finditer(pat, html)]
    print(pat, '->', len(idxs))
body = html[html.find('<body'):]
i = body.find('选集')
print('=== 选集 context ===')
print(body[i-200:i+1500] if i!=-1 else 'not found')
