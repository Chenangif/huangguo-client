import re
for f in ['cat.html','detail.html','home.html']:
    html = open(f, encoding='utf-8').read()
    apis = set(re.findall(r'api/?(?:videos)?/[a-zA-Z0-9_/\\\-]{2,60}', html))
    apis = set(a.replace('\\/','/') for a in apis)
    print('==', f)
    for a in sorted(apis)[:25]:
        print('  ', a)
    # 也找 js 文件
    print('  scripts:', set(re.findall(r'src="(/static/web/js/[^"]+)"', html)))
