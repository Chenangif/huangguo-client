import re
html = open('home.html', encoding='utf-8').read()
body = html[html.find('<body'):]
m = re.search(r'<(article|div|li)[^>]*class="[^"]*\bhg-drama-card\b[^"]*"[^>]*>', body)
if m:
    print(body[m.start():m.start()+2600])
