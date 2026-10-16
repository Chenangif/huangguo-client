import re, json, urllib.request
html = open('detail.html', encoding='utf-8').read()
m = re.search(r'<script[^>]*id="videoInitialData"[^>]*>(.*?)</script>', html, re.S)
data = json.loads(m.group(1).strip())
url = data['videoSrc']
for name, headers in [('no-headers', {'User-Agent':'Mozilla/5.0'}),
                      ('with-referer', {'User-Agent':'Mozilla/5.0','Referer':'https://huangguoai.com/'})]:
    try:
        req = urllib.request.Request(url, headers=headers)
        txt = urllib.request.urlopen(req, timeout=30).read(600).decode('utf-8', 'replace')
        print('==', name, 'OK')
        print(txt[:400])
        break
    except Exception as e:
        print('==', name, 'FAIL:', e)
