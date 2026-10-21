#!/usr/bin/env python3
"""รวมไฟล์ทั้งหมดเป็นไฟล์เกมไฟล์เดียว

ใช้งาน:  python3 build.py
ผลลัพธ์: dist/DeejatBakery.html  (เปิดในมือถือได้ทันที ไม่ต้องมีโฟลเดอร์ css/js)
"""
import base64
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent
OUT = ROOT / "dist" / "DeejatBakery.html"

# ความปลอดภัยของไฟล์เดียว: ไม่โหลดอะไรจากภายนอกเลย (ทุกอย่างฝังอยู่ในไฟล์แล้ว)
# - ห้ามเชื่อมต่อเน็ต / ห้ามส่งฟอร์ม / ห้ามฝังปลั๊กอิน / ห้ามเปลี่ยน base URL
# - รูป/ฟอนต์ใช้ได้เฉพาะ data: และ blob: (รูปเชฟสร้างจาก blob ใน js/assets.js)
# ใส่เฉพาะใน dist (index.html แบบแยกไฟล์โหลด css/js จากโฟลเดอร์ ซึ่ง 'self' ใช้กับ file:// ไม่ได้แน่นอนทุกเบราว์เซอร์)
CSP = ("default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; "
       "img-src data: blob:; font-src data:; media-src data: blob:; connect-src 'none'; "
       "object-src 'none'; base-uri 'none'; form-action 'none'")
SECURITY_META = (f'<meta http-equiv="Content-Security-Policy" content="{CSP}">\n'
                 '<meta name="referrer" content="no-referrer">\n')


def src_path(rel: str) -> pathlib.Path:
    """ไฟล์ที่ index.html/assets.js อ้างถึง ต้องอยู่ในโฟลเดอร์โปรเจกต์เท่านั้น และต้องมีอยู่จริง"""
    path = (ROOT / rel).resolve()
    if ROOT not in path.parents:
        raise SystemExit(f"ไฟล์อยู่นอกโฟลเดอร์โปรเจกต์ ไม่ยอมฝัง: {rel}")
    if not path.is_file():
        raise SystemExit(f"หาไฟล์ไม่เจอ: {rel}")
    return path


def inline(html: str) -> str:
    def font_uri(m):
        # ฝังฟอนต์ใน assets/fonts/ เป็น data URI → ไฟล์เดียวเล่นได้แม้ไม่มีเน็ต
        path = src_path("assets/fonts/" + m.group(1))
        data = base64.b64encode(path.read_bytes()).decode("ascii")
        print(f"  embed font {path.name}  ({path.stat().st_size / 1024:.0f} KB)")
        return f"url(data:font/woff2;base64,{data})"

    def css(m):
        block = m.group(1)
        files = re.findall(r'href="([^"]+\.css)"', block)
        code = "\n".join(src_path(f).read_text(encoding="utf-8") for f in files)
        code = re.sub(r"url\(['\"]?\.\./assets/fonts/([^'\")]+)['\"]?\)", font_uri, code)
        if "../assets/" in code:
            raise SystemExit("CSS อ้างถึงไฟล์ใน assets/ ที่ฝังไม่ได้ — ไฟล์เดียวจะหาไฟล์นี้ไม่เจอ")
        if "</style" in code.lower():
            raise SystemExit("พบคำว่า </style ใน CSS จะทำให้ไฟล์เดียวพัง")
        return "<style>\n" + code + "\n</style>"

    def assets_script():
        # ฝังรูปใน assets/ (ตามรายการ ASSET_FILES ใน js/assets.js) เป็น base64
        src = (ROOT / "js" / "assets.js").read_text(encoding="utf-8")
        items = re.findall(r"(\w+): \{ path: '([^']+)'", src)
        parts = []
        for key, path in items:
            f = src_path(path)
            data = base64.b64encode(f.read_bytes()).decode("ascii")
            parts.append(f"{key}:'{data}'")
            print(f"  embed {path}  ({f.stat().st_size / 1024:.0f} KB)")
        return "<script>window.NJ_INLINE_ASSETS={" + ",".join(parts) + "};</script>\n"

    def js(m):
        block = m.group(1)
        files = re.findall(r'src="([^"]+\.js)"', block)
        # รวมเป็นสคริปต์เดียว ห่อไว้ใน block {} เพื่อไม่ให้ตัวแปรรั่วออกไป global
        code = "\n".join(src_path(f).read_text(encoding="utf-8").replace("'use strict';\n", "", 1) for f in files)
        low = code.lower()
        if "</script" in low:
            raise SystemExit("พบคำว่า </script ในโค้ด JS จะทำให้ไฟล์เดียวพัง — แก้เป็น <\\/script")
        if "<!--" in low and "<script" in low:
            raise SystemExit("พบ <!-- คู่กับ <script ในโค้ด JS เบราว์เซอร์อาจอ่านสคริปต์ผิด — แยกเป็น '<' + '!--'")
        return assets_script() + "<script>\n'use strict';\n{\n" + code + "\n}\n</script>"

    if "<!-- build:css -->" not in html or "<!-- build:js -->" not in html:
        raise SystemExit("index.html ไม่มีเครื่องหมาย build:css / build:js")
    html = re.sub(r"<!-- build:css -->(.*?)<!-- /build:css -->", css, html, flags=re.S)
    html = re.sub(r"<!-- build:js -->(.*?)<!-- /build:js -->", js, html, flags=re.S)
    html = html.replace("<!-- build:body -->\n", "").replace("<!-- /build:body -->\n", "")
    html = html.replace('<meta charset="utf-8">\n', '<meta charset="utf-8">\n' + SECURITY_META, 1)
    if SECURITY_META not in html:
        raise SystemExit('ใส่ Content-Security-Policy ไม่ได้ (index.html ต้องขึ้นต้นด้วย <meta charset="utf-8">)')
    return html


def main():
    html = inline((ROOT / "index.html").read_text(encoding="utf-8"))
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(html, encoding="utf-8", newline="\n")   # ได้ไฟล์เหมือนกันทุกเครื่อง (Windows/Mac)
    print(f"built {OUT.relative_to(ROOT)}  ({OUT.stat().st_size / 1024:.1f} KB)")


if __name__ == "__main__":
    main()
