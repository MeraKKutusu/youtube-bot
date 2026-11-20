#!/usr/bin/env python3
"""PreToolUse hook'u: gizli dosyalara yazmayı ve dosyalara anahtar yazılmasını engeller.

Engellenenler:
  - .env, .env.* (yalnızca .env.example serbest), *secret*, client_secret*.json,
    *token*.json, *.pem, *.key, credentials*.json dosyalarına Edit/Write
  - Herhangi bir dosyaya anahtar gibi görünen bir değer yazılması
    (ör. PEXELS_API_KEY=abc123...)
  - Bash ile bu dosyalara yazma, kopyalama ya da git add (>, >>, tee, cp, mv, sed -i)

Engellenince 2 koduyla çıkar; Claude Code işlemi durdurur ve
stderr'deki açıklamayı Claude'a iletir.
"""
import json
import re
import sys

GIZLI_DOSYA = re.compile(
    r"(^|[\\/])("
    r"\.env(\.(?!example$)[^\\/]+)?"
    r"|[^\\/]*secret[^\\/]*"
    r"|[^\\/]*token[^\\/]*\.json"
    r"|credentials[^\\/]*\.json"
    r"|[^\\/]+\.(pem|key|p12|pfx)"
    r")$",
    re.IGNORECASE,
)

# ANAHTAR_ADI = "uzun-değer" biçimindeki atamalar. ${{ secrets.X }} ve
# os.environ[...] gibi değerler $ ya da harf dışı karakterle başladığı için takılmaz.
ANAHTAR_DEGERI = re.compile(
    r"(api[_-]?key|secret|token|password|parola|sifre|şifre)[A-Za-z0-9_]*"
    r"[\"']?\s*[:=]\s*[\"']?[A-Za-z0-9_\-]{20,}",
    re.IGNORECASE,
)

# Bash'te yazma/kopyalama/commit'leme işlemleri
BASH_YAZMA = re.compile(r">|\btee\b|\bcp\b|\bmv\b|\bsed\s+-i|\bgit\s+add\b")
BASH_PARCA = re.compile(r"[^\s|;&<>()]+")


def engelle(mesaj):
    print(f"Gizli bilgi koruması: {mesaj}. API anahtarları yalnızca GitHub Secrets'ta durmalı.",
          file=sys.stderr)
    sys.exit(2)


def gizli_mi(yol):
    return bool(yol) and bool(GIZLI_DOSYA.search(yol.strip().strip("'\"")))


def main():
    try:
        olay = json.load(sys.stdin)
    except json.JSONDecodeError:
        return
    arac = olay.get("tool_name", "")
    girdi = olay.get("tool_input", {}) or {}

    if arac == "Bash":
        komut = girdi.get("command", "")
        if BASH_YAZMA.search(komut):
            for parca in BASH_PARCA.findall(komut):
                if gizli_mi(parca):
                    engelle(f"'{parca}' gizli bir dosya; Bash ile yazılamaz, kopyalanamaz ya da commit'lenemez")
        if ANAHTAR_DEGERI.search(komut):
            engelle("komutta açık bir anahtar değeri var")
        return

    yol = girdi.get("file_path") or girdi.get("notebook_path") or ""
    if gizli_mi(yol):
        engelle(f"'{yol}' gizli bir dosya; düzenlenemez")

    metinler = [girdi.get("content"), girdi.get("new_string"), girdi.get("new_source")]
    for d in girdi.get("edits", []) or []:
        metinler.append(d.get("new_string"))
    for metin in metinler:
        if metin and ANAHTAR_DEGERI.search(metin):
            engelle(f"'{yol}' dosyasına açık bir anahtar değeri yazılmak isteniyor")


if __name__ == "__main__":
    main()
