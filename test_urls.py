
import re

user_input = """[Prathvi_Singh.pdf - Google Drive](https://drive.google.com/file/d/1ilFzXa_zvtEWzL271ptnlEkZB8C_Z_aK/view) 
[Jay_Dalsaniya_Resume 2.pdf](https://drive.google.com/file/d/1HOCK-xlf3PQMMKNnVAbhZL8nNyyJSWYB/view?usp=sharing)
[Yeshwanth_Sai_Barri.pdf](https://drive.google.com/file/d/11dWQyJy2Fc2GjCNa8TKzQPkuDPeg2lir/view?usp=sharing)"""

raw_lines = user_input.strip().splitlines()
urls = []
for line in raw_lines:
    line = line.strip()
    if not line:
        continue
    md_match = re.search(r'\[.*?\]\((https?://[^\s)]+)\)', line)
    if md_match:
        urls.append(md_match.group(1))
    else:
        url_match = re.search(r'(https?://[^\s<>"\'\)]+)', line)
        if url_match:
            urls.append(url_match.group(1))
        else:
            urls.append(line)

print("Extracted URLs:")
for u in urls:
    print(u)
