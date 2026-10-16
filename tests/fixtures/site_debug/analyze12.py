import re
html = open('rank.html', encoding='utf-8').read()
body = html[html.find('<body'):]
# 找榜单条目区
i = body.find('hg-rank-list')
print('hg-rank-list at', i)
j = body.find('TOP 1')
if j == -1:
    j = body.find('top1')
print(body[i if i!=-1 else 0: (i if i!=-1 else 0)+2500][:2500])
