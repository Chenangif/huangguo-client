import re, json
html = open('detail.html', encoding='utf-8').read()

# videoInitialData 内容
m = re.search(r'<script[^>]*id="videoInitialData"[^>]*>(.*?)</script>', html, re.S)
if m:
    txt = m.group(1).strip()
    print("=== videoInitialData (first 1500) ===")
    print(txt[:1500])
    try:
        data = json.loads(txt)
        print("\n=== keys ===", list(data.keys()) if isinstance(data, dict) else type(data))
    except Exception as e:
        print("json fail:", e)

# 标题
t = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.S)
print("\n=== h1 ===", t.group(1).strip()[:100] if t else None)

# 集数网格
i = html.find('hg-web-detail__ep-grid')
print("\n=== ep-grid context ===")
print(html[i-100:i+1200] if i != -1 else "NOT FOUND")
