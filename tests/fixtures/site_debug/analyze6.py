import json
d = json.load(open('api_cat.json', encoding='utf-8'))
print('pagination =', json.dumps(d['data']['pagination'], ensure_ascii=False))
