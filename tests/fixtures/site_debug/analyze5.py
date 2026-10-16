import json
d = json.load(open('api_cat.json', encoding='utf-8'))
data = d['data']
print('data keys:', list(data.keys()))
items = data['items']
print('items:', len(items), 'item keys:', list(items[0].keys()))
it = items[0]
for k in ['id','title','cover','episode_count','score','hot','is_finished','duration']:
    print(' ', k, '=', str(it.get(k))[:80])
