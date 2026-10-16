import re
for f in ['search.html','rank.html']:
    try:
        html = open(f, encoding='utf-8').read()
    except Exception as e:
        print(f, 'missing', e); continue
    body = html[html.find('<body'):]
    cards = len(re.findall(r'hg-drama-card"', body))
    vids = re.findall(r'href="(/video/\d+/)"', body)
    # rank 页可能是列表行
    rows = len(re.findall(r'hg-rank', body))
    print(f, 'cards:', cards, 'video links:', len(vids), vids[:5], 'rank rows:', rows)
