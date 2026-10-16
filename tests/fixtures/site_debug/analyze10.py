import re, urllib.request
from Crypto.Cipher import AES

html = open('cat.html', encoding='utf-8').read()
m = re.search(r'data-src="(https://pic\.wirqed\.cn[^"]+)"', html)
url = m.group(1)
req = urllib.request.Request(url, headers={'User-Agent':'Mozilla/5.0','Referer':'https://huangguoai.com/'})
raw = urllib.request.urlopen(req, timeout=30).read()
print('bytes:', len(raw), 'mod16:', len(raw)%16)

cands = [
    (b"f5d965df75336270", b"97b60394abc2fbe1", "utf8-16byte"),
    (bytes.fromhex("f5d965df75336270")+bytes(8), bytes.fromhex("97b60394abc2fbe1")+bytes(8), "hex8+pad"),
    (bytes.fromhex("f5d965df753362700000000000000000"), bytes.fromhex("97b60394abc2fbe10000000000000000"), "hex8+zeros16"),
]
for key, iv, name in cands:
    if len(key) not in (16,24,32):
        print(name, 'bad key len', len(key)); continue
    pt = AES.new(key, AES.MODE_CBC, iv).decrypt(raw)
    print(name, '->', pt[:8].hex(), 'jpeg' if pt[:2]==b'\xff\xd8' else ('png' if pt[:4]==b'\x89PNG' else 'unknown'))
