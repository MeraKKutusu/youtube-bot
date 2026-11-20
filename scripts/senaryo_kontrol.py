#!/usr/bin/env python3
"""Senaryo JSON dosyalarını kanal kurallarına göre denetler.

Kullanım:
  python3 scripts/senaryo_kontrol.py senaryolar/001-octopus.json [...]
Hata varsa 1 koduyla çıkar. Uyarılar videoyu durdurmaz.
"""
import json
import re
import sys
import unicodedata
from pathlib import Path

MOODLAR = ("tense", "mysterious", "fun", "epic")
DILLER = ("en", "tr")
KAPANIS_TR = "Takip et, yarın daha şaşırtıcısı var."
EN_FAZLA_BASLIK = 70
KELIME_ARALIGI = (45, 80)      # dışı hata
HEDEF_KELIME = (52, 70)        # dışı uyarı (gerçek ölçüm: 73 kelime ≈ 40 sn konuşma)


def _sade(yazi):
    yazi = unicodedata.normalize("NFC", str(yazi)).strip().lower()
    return re.sub(r"[^\w]+", " ", yazi).strip()


def kelime_sayisi(veri):
    return sum(len(str(c.get("tr", "")).split())
               for b in veri.get("bolumler", []) for c in b.get("cumleler", []))


def yeni_bicim_mi(veri):
    return "yayin" in veri or "mood" in veri


def kontrol(veri, dosya_adi=""):
    """(hatalar, uyarilar) döndürür. Eski biçimdeki senaryolar yalnızca
    temel yapı açısından denetlenir."""
    hatalar, uyarilar = [], []
    bolumler = veri.get("bolumler")
    if not isinstance(bolumler, list) or not bolumler:
        return ["'bolumler' boş ya da yok"], []
    for i, b in enumerate(bolumler, 1):
        if not str(b.get("arama", "")).strip():
            hatalar.append(f"{i}. bölümde 'arama' boş")
        cumleler = b.get("cumleler")
        if cumleler is None and str(b.get("metin", "")).strip():
            continue  # eski biçim
        if not isinstance(cumleler, list) or not cumleler:
            hatalar.append(f"{i}. bölümde 'cumleler' boş")
            continue
        for j, c in enumerate(cumleler, 1):
            for dil in DILLER:
                if not str((c or {}).get(dil, "")).strip():
                    hatalar.append(f"{i}. bölüm {j}. cümlede '{dil}' boş")

    if not yeni_bicim_mi(veri):
        uyarilar.append("eski senaryo biçimi (mood/yayin yok); efektler varsayılanla üretilir")
        return hatalar, uyarilar

    no = veri.get("seri_no")
    if not isinstance(no, int) or no < 0:
        hatalar.append("'seri_no' 0 ya da daha büyük bir tam sayı olmalı")
    if veri.get("mood") not in MOODLAR:
        hatalar.append(f"'mood' şunlardan biri olmalı: {', '.join(MOODLAR)}")
    if not str(veri.get("konu", "")).strip():
        hatalar.append("'konu' boş")

    for alan in ("kanca_yazisi", "sabit_yorum"):
        deger = veri.get(alan)
        if not isinstance(deger, dict):
            hatalar.append(f"'{alan}' en ve tr içeren bir nesne olmalı")
            continue
        for dil in DILLER:
            yazi = str(deger.get(dil, "")).strip()
            if not yazi:
                hatalar.append(f"'{alan}.{dil}' boş")
            elif alan == "kanca_yazisi" and not 3 <= len(yazi.split()) <= 5:
                hatalar.append(f"'kanca_yazisi.{dil}' 3-5 kelime olmalı: {yazi!r}")
            elif alan == "sabit_yorum" and "?" not in yazi:
                hatalar.append(f"'sabit_yorum.{dil}' izleyiciye bir soru olmalı")

    yayin = veri.get("yayin")
    if not isinstance(yayin, dict):
        hatalar.append("'yayin' en ve tr içeren bir nesne olmalı")
    else:
        for dil in DILLER:
            y = yayin.get(dil) or {}
            baslik = str(y.get("baslik", "")).strip()
            if not baslik:
                hatalar.append(f"'yayin.{dil}.baslik' boş")
            elif len(baslik) > EN_FAZLA_BASLIK:
                hatalar.append(f"'yayin.{dil}.baslik' {len(baslik)} karakter; en fazla {EN_FAZLA_BASLIK}")
            if not str(y.get("aciklama", "")).strip():
                hatalar.append(f"'yayin.{dil}.aciklama' boş")
            etiketler = y.get("hashtagler")
            if not isinstance(etiketler, list) or not 3 <= len(etiketler) <= 5:
                hatalar.append(f"'yayin.{dil}.hashtagler' 3-5 hashtag olmalı")
            else:
                for h in etiketler:
                    if not re.fullmatch(r"#[^\s#]+", str(h)):
                        hatalar.append(f"geçersiz hashtag: {h!r}")

    if not veri.get("kaynaklar"):
        uyarilar.append("'kaynaklar' boş: bilgileri doğrulayan kaynak linkleri ekleyin")

    # Kapanış: izleyiciye soru + takip çağrısı
    tum = [c for b in bolumler for c in (b.get("cumleler") or [])]
    if tum:
        if _sade(tum[-1].get("tr", "")) != _sade(KAPANIS_TR):
            hatalar.append(f"son cümle tam olarak \"{KAPANIS_TR}\" olmalı")
        if not any("?" in str(c.get("tr", "")) for c in tum[-3:-1]):
            hatalar.append("kapanışta (son cümleden hemen önce) izleyiciye bir soru olmalı")

    sayi = kelime_sayisi(veri)
    if not KELIME_ARALIGI[0] <= sayi <= KELIME_ARALIGI[1]:
        hatalar.append(f"Türkçe metin {sayi} kelime; 30-40 sn için {HEDEF_KELIME[0]}-{HEDEF_KELIME[1]} kelime olmalı")
    elif not HEDEF_KELIME[0] <= sayi <= HEDEF_KELIME[1]:
        uyarilar.append(f"Türkçe metin {sayi} kelime; hedef {HEDEF_KELIME[0]}-{HEDEF_KELIME[1]}")

    if dosya_adi and Path(dosya_adi).name != "ornek.json":
        if not re.fullmatch(r"\d{3}-[a-z0-9-]+\.json", Path(dosya_adi).name):
            uyarilar.append("dosya adı 001-kucuk-harf-konu.json biçiminde olmalı")
    return hatalar, uyarilar


def main(yollar):
    if not yollar:
        print(__doc__)
        return 1
    kotu = False
    for yol in yollar:
        try:
            veri = json.loads(Path(yol).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            print(f"✗ {yol}: okunamadı: {e}")
            kotu = True
            continue
        hatalar, uyarilar = kontrol(veri, yol)
        durum = "✗" if hatalar else "✓"
        print(f"{durum} {yol} ({kelime_sayisi(veri)} Türkçe kelime)")
        for h in hatalar:
            print(f"   HATA: {h}")
        for u in uyarilar:
            print(f"   uyarı: {u}")
        kotu = kotu or bool(hatalar)
    return 1 if kotu else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
