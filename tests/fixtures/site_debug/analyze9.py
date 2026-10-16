import re, urllib.request
html = open('cat.html', encoding='utf-8').read()
m = re.search(r'data-src="(https://pic\.wirqed\.cn[^"]+)"', html)
url = m.group(1)
print('URL:', url)
req = urllib.request.Request(url, headers={'User-Agent':'Mozilla/5.0','Referer':'https://huangguoai.com/'})
raw = urllib.request.urlopen(req, timeout=30).read()
print('bytes:', len(raw), 'magic:', raw[:12].hex())
print('is jpeg:', raw[:2]==b'\xff\xd8', 'is png:', raw[:4]==b'\x89PNG')
