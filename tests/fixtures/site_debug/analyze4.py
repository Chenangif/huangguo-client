import re
html = open('cat.html', encoding='utf-8').read()
body = html[html.find('<body'):]
# 找分页/加载更多相关标记
for pat in [r'data-page="[^"]*"', r'href="[^"]*page[^"]*"', r'api[^"\']{0,80}', r'data-(?:total|next|more)[^ >]*', r'/ai-duanju/[^"]*']:
    found = re.findall(pat, body)
    print(pat, '->', list(dict.fromkeys(found))[:12])
