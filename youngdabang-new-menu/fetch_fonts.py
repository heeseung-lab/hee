# Download Google Fonts (OFL) subset to exactly the characters used in content.js → fonts/ + fonts.css
import re, urllib.parse, urllib.request
src = open('content.js', encoding='utf-8').read()
chars = ''.join(sorted(set(''.join(re.findall(r"'([^']*)'", src))) | set('0123456789NEW ?,·')))
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"}
css_out = []
for fam, w, key in [("Noto Serif KR", "700", "serif"), ("Nanum Pen Script", "400", "pen"), ("IBM Plex Mono", "500", "mono")]:
    q = urllib.parse.urlencode({"family": f"{fam}:wght@{w}", "text": chars})
    css = urllib.request.urlopen(urllib.request.Request("https://fonts.googleapis.com/css2?" + q, headers=UA)).read().decode()
    url = re.search(r"url\((https://[^)]+)\)", css).group(1)
    open(f"fonts/{key}.woff2", "wb").write(urllib.request.urlopen(urllib.request.Request(url, headers=UA)).read())
    css_out.append(f"@font-face{{font-family:'{fam}';font-weight:{w};src:url('fonts/{key}.woff2') format('woff2');}}")
open("fonts.css", "w").write("\n".join(css_out) + "\n")
print("fonts:", len(chars), "characters")
