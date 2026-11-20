#!/usr/bin/env python3
"""Senaryo JSON dosyasından 1080x1920 Türkçe YouTube Shorts videosu üretir.

Adımlar:
  1. edge-tts ile Türkçe seslendirme + kelime zamanlamaları
  2. Her bölüm için görüntü, bu sırayla denenir:
       a. Pixabay video (dikey olanlar önce), yoksa Pixabay dikey fotoğraf
       b. Pexels video/fotoğraf (isteğe bağlı; yalnızca anahtar varsa)
       c. Hiçbiri olmazsa ffmpeg ile renkli, hareketli arka plan
     Anahtar olmaması ya da sonuç bulunamaması videoyu durdurmaz.
  3. Ekranın ortasında büyük, kalın, siyah kenarlıklı beyaz altyazı
  4. ffmpeg ile 1080x1920, 30 fps MP4

API anahtarları yalnızca ortam değişkenlerinden okunur (PIXABAY_API_KEY,
PEXELS_API_KEY); GitHub Actions'ta Secret'lardan gelir. Kodda ya da repoda
tutulmaz ve loglara yazılmaz.

Kullanım:
  python scripts/uret.py --senaryo senaryolar/ornek.json --ses Emel \
      --cikti cikti --calisma calisma
"""
import argparse
import asyncio
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

GENISLIK, YUKSEKLIK, FPS = 1080, 1920, 30
SESLER = {"Emel": "tr-TR-EmelNeural", "Ahmet": "tr-TR-AhmetNeural"}

# Altyazı ayarları
FONT_DIZINI = "/usr/share/fonts/truetype/dejavu"
FONT_ADI = "DejaVu Sans"   # Türkçe karakterlerin hepsini içerir
FONT_BOYUTU = 96
KENARLIK = 7               # siyah kenarlık kalınlığı (piksel)
YAN_BOSLUK = 130           # sağdaki Shorts butonlarından uzak dursun
EN_FAZLA_KELIME = 3        # ekranda aynı anda en fazla kaç kelime
EN_FAZLA_HARF = 18         # bir altyazı parçasının en fazla uzunluğu

PIXABAY_VIDEO = "https://pixabay.com/api/videos/"
PIXABAY_FOTO = "https://pixabay.com/api/"
PEXELS_VIDEO = "https://api.pexels.com/v1/videos/search"
PEXELS_FOTO = "https://api.pexels.com/v1/search"
EN_BUYUK_VIDEO = 80 * 1024 * 1024   # bundan büyük video dosyalarını indirme

# Görüntü bulunamazsa kullanılacak hareketli arka plan renkleri
RENK_PALETLERI = [
    ("0x1e3a8a", "0x7c3aed", "0x06b6d4"),
    ("0x0f766e", "0x22c55e", "0xfacc15"),
    ("0x9d174d", "0xf97316", "0xfde047"),
    ("0x312e81", "0xdb2777", "0xf472b6"),
    ("0x14532d", "0x0ea5e9", "0x6366f1"),
    ("0x7f1d1d", "0xea580c", "0xa855f7"),
]


class KomutHatasi(RuntimeError):
    pass


def hata(mesaj):
    print(f"HATA: {mesaj}", file=sys.stderr)
    sys.exit(1)


def uyari(mesaj):
    # GitHub Actions bu biçimi sarı uyarı olarak gösterir
    print(f"::warning::{mesaj}")


def calistir(komut):
    sonuc = subprocess.run(komut, capture_output=True, text=True)
    if sonuc.returncode != 0:
        print(sonuc.stderr[-3000:], file=sys.stderr)
        raise KomutHatasi(f"komut başarısız oldu: {komut[0]}")
    return sonuc.stdout


# ---------------------------------------------------------------- senaryo

def senaryo_oku(yol):
    try:
        veri = json.loads(Path(yol).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        hata(f"senaryo okunamadı ({yol}): {e}")
    for alan in ("baslik", "aciklama", "etiketler", "bolumler"):
        if alan not in veri:
            hata(f"senaryoda '{alan}' alanı eksik")
    if not veri["bolumler"]:
        hata("senaryoda hiç bölüm yok")
    for i, b in enumerate(veri["bolumler"], 1):
        if not str(b.get("metin", "")).strip() or not str(b.get("arama", "")).strip():
            hata(f"{i}. bölümde 'metin' ya da 'arama' boş")
    return veri


def tam_metin_ve_bolum_konumlari(bolumler):
    """Bölüm metinlerini birleştirir; her bölümün metindeki başlangıç konumunu döndürür."""
    parcalar, konumlar, konum = [], [], 0
    for b in bolumler:
        metin = " ".join(str(b["metin"]).split())
        konumlar.append(konum)
        parcalar.append(metin)
        konum += len(metin) + 1
    return " ".join(parcalar), konumlar


# ---------------------------------------------------------------- seslendirme

async def _seslendir(metin, ses, mp3_yolu):
    import edge_tts

    try:
        iletisim = edge_tts.Communicate(metin, ses, boundary="WordBoundary")
    except TypeError:  # eski sürümler kelime sınırlarını zaten varsayılan verir
        iletisim = edge_tts.Communicate(metin, ses)
    sinirlar = []
    with open(mp3_yolu, "wb") as f:
        async for parca in iletisim.stream():
            if parca["type"] == "audio":
                f.write(parca["data"])
            elif parca["type"] in ("WordBoundary", "SentenceBoundary"):
                sinirlar.append((parca["type"], parca["offset"] / 1e7,
                                 parca["duration"] / 1e7, parca["text"]))
    return sinirlar


def seslendir(metin, ses, mp3_yolu):
    """Sesi mp3 olarak yazar; (tür, başlangıç_sn, süre_sn, yazı) listesi döndürür."""
    for deneme in range(1, 4):
        try:
            sinirlar = asyncio.run(_seslendir(metin, ses, mp3_yolu))
            if sinirlar and Path(mp3_yolu).stat().st_size > 0:
                return sinirlar
            print(f"Seslendirme boş döndü (deneme {deneme})", file=sys.stderr)
        except Exception as e:  # ağ hataları vb.
            print(f"Seslendirme hatası (deneme {deneme}): {e}", file=sys.stderr)
        time.sleep(5 * deneme)
    hata("edge-tts seslendirmesi 3 denemede de başarısız oldu; workflow'u yeniden çalıştırın")


def kelimeleri_cikar(metin, sinirlar):
    """Her kelime için [başlangıç_sn, bitiş_sn, metindeki_konum] listesi."""
    kelimeler, imlec = [], 0
    for tur, bas, sure, yazi in sinirlar:
        yazi = yazi.strip()
        if not yazi:
            continue
        konum = metin.find(yazi, imlec)
        if konum < 0:
            continue
        if tur == "WordBoundary":
            kelimeler.append([bas, bas + sure, konum])
        else:
            # Yalnızca cümle zamanları geldiyse süreyi harf sayısına göre dağıt
            parcalar = [(m.start(), m.end()) for m in re.finditer(r"\S+", yazi)]
            toplam = sum(e - s for s, e in parcalar) or 1
            t = bas
            for s, e in parcalar:
                d = sure * (e - s) / toplam
                kelimeler.append([t, t + d, konum + s])
                t += d
        imlec = konum + len(yazi)
    if not kelimeler:
        hata("seslendirmeden kelime zamanlamaları alınamadı")
    return kelimeler


# ---------------------------------------------------------------- altyazı

def _ass_zaman(sn):
    sn = max(0.0, sn)
    s = int(sn // 3600)
    d = int(sn % 3600 // 60)
    return f"{s}:{d:02d}:{sn % 60:05.2f}"


def _ass_kacis(yazi):
    return yazi.replace("\\", "").replace("{", "(").replace("}", ")")


def altyazi_yaz(metin, kelimeler, ses_suresi, ass_yolu):
    # Kelimeleri kısa gruplara ayır; cümle sonunda grubu kapat
    gruplar, grup = [], []
    for i, k in enumerate(kelimeler):
        grup.append(i)
        bas = kelimeler[grup[0]][2]
        son = kelimeler[i + 1][2] if i + 1 < len(kelimeler) else len(metin)
        yazi = metin[bas:son].strip()
        sonraki_uzun = False
        if i + 1 < len(kelimeler):
            son2 = kelimeler[i + 2][2] if i + 2 < len(kelimeler) else len(metin)
            sonraki_uzun = len(metin[bas:son2].strip()) > EN_FAZLA_HARF
        if (len(grup) >= EN_FAZLA_KELIME or yazi[-1:] in ".!?…:;"
                or sonraki_uzun or i + 1 == len(kelimeler)):
            gruplar.append(grup)
            grup = []

    satirlar = []
    for j, g in enumerate(gruplar):
        bas_konum = kelimeler[g[0]][2]
        son_index = g[-1] + 1
        son_konum = kelimeler[son_index][2] if son_index < len(kelimeler) else len(metin)
        yazi = _ass_kacis(metin[bas_konum:son_konum].strip())
        baslangic = kelimeler[g[0]][0]
        if j + 1 < len(gruplar):
            bitis = kelimeler[gruplar[j + 1][0]][0]
        else:
            bitis = min(ses_suresi, kelimeler[g[-1]][1] + 0.5)
        if bitis <= baslangic:
            bitis = baslangic + 0.3
        satirlar.append(f"Dialogue: 0,{_ass_zaman(baslangic)},{_ass_zaman(bitis)},Ana,,0,0,0,,{yazi}")

    # Alignment 5 = tam orta. Bold -1 = kalın. BorderStyle 1 + Outline = kenarlık.
    baslik = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {GENISLIK}
PlayResY: {YUKSEKLIK}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Ana,{FONT_ADI},{FONT_BOYUTU},&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,{KENARLIK},2,5,{YAN_BOSLUK},{YAN_BOSLUK},0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    Path(ass_yolu).write_text(baslik + "\n".join(satirlar) + "\n", encoding="utf-8")


# ---------------------------------------------------------------- görüntü kaynakları

class KaynakKapali(Exception):
    """Anahtar geçersiz: bu kaynak bu çalıştırmada bir daha denenmez."""


def _gizle(yazi, anahtarlar):
    """Hata mesajlarındaki anahtarları siler (Pixabay anahtarı URL'de gider)."""
    yazi = str(yazi)
    for a in anahtarlar:
        if a:
            yazi = yazi.replace(a, "***")
    return re.sub(r"key=[^&\s]+", "key=***", yazi)


def _api_get(url, params, headers, anahtar):
    import requests

    for deneme in range(1, 4):
        try:
            r = requests.get(url, params=params, headers=headers, timeout=30)
            if r.status_code in (400, 401, 403) and deneme == 1:
                ilk = r.text[:200]
                if "key" in ilk.lower() or r.status_code in (401, 403):
                    raise KaynakKapali(_gizle(f"HTTP {r.status_code}: {ilk}", [anahtar]))
            if r.status_code == 429:
                time.sleep(10 * deneme)
                continue
            r.raise_for_status()
            return r.json()
        except KaynakKapali:
            raise
        except Exception as e:
            print(f"İstek başarısız (deneme {deneme}): {_gizle(e, [anahtar])}", file=sys.stderr)
            time.sleep(3 * deneme)
    return {}


def _indir(url, hedef):
    import requests

    with requests.get(url, stream=True, timeout=120) as r:
        r.raise_for_status()
        with open(hedef, "wb") as f:
            for blok in r.iter_content(1 << 20):
                f.write(blok)
    if Path(hedef).stat().st_size == 0:
        raise ValueError("boş dosya indi")


def _sorgular(sorgu):
    sorgu = sorgu.strip()[:100]  # Pixabay en fazla 100 karakter kabul ediyor
    liste = [sorgu]
    kelimeler = sorgu.split()
    if len(kelimeler) > 2:
        liste.append(" ".join(kelimeler[:2]))
    if len(kelimeler) > 1:
        liste.append(kelimeler[0])
    return liste


def pixabay_adaylar(anahtar, sorgu):
    """Sırayla denenecek (tür, url, kimlik) adayları üretir: önce video, sonra foto."""
    for s in _sorgular(sorgu):
        veri = _api_get(PIXABAY_VIDEO, {"key": anahtar, "q": s, "per_page": 20,
                                        "safesearch": "true"}, None, anahtar)
        dikey, yatay = [], []
        for v in veri.get("hits", []):
            boyutlar = [b for b in (v.get("videos") or {}).values()
                        if b.get("url") and b.get("width") and b.get("height")
                        and (b.get("size") or 0) <= EN_BUYUK_VIDEO]
            if not boyutlar:
                continue
            # Kısa kenarı 1080'e en yakın boyut: ne bulanık ne gereksiz büyük
            boyutlar.sort(key=lambda b: abs(min(b["width"], b["height"]) - GENISLIK))
            b = boyutlar[0]
            (dikey if b["height"] > b["width"] else yatay).append(
                ("video", b["url"], ("pixabay-v", v.get("id"))))
        yield from dikey
        yield from yatay  # yatay videolar ortadan 9:16 kırpılır

    for s in _sorgular(sorgu):
        veri = _api_get(PIXABAY_FOTO, {"key": anahtar, "q": s, "image_type": "photo",
                                       "orientation": "vertical", "per_page": 20,
                                       "safesearch": "true"}, None, anahtar)
        for p in veri.get("hits", []):
            url = p.get("largeImageURL") or p.get("webformatURL")
            if url:
                yield ("foto", url, ("pixabay-f", p.get("id")))


def pexels_adaylar(anahtar, sorgu):
    basliklar = {"Authorization": anahtar}
    for s in _sorgular(sorgu):
        veri = _api_get(PEXELS_VIDEO, {"query": s, "orientation": "portrait", "per_page": 15},
                        basliklar, anahtar)
        for v in veri.get("videos", []):
            dosyalar = [f for f in v.get("video_files", [])
                        if f.get("file_type") == "video/mp4" and f.get("width") and f.get("height")
                        and f["height"] > f["width"] and f["width"] >= 540]
            if dosyalar:
                dosyalar.sort(key=lambda f: abs(f["width"] - GENISLIK))
                yield ("video", dosyalar[0]["link"], ("pexels-v", v.get("id")))
    for s in _sorgular(sorgu):
        veri = _api_get(PEXELS_FOTO, {"query": s, "orientation": "portrait", "per_page": 15},
                        basliklar, anahtar)
        for p in veri.get("photos", []):
            url = (p.get("src") or {}).get("large2x") or (p.get("src") or {}).get("portrait")
            if url:
                yield ("foto", url, ("pexels-f", p.get("id")))


def kaynaklari_hazirla():
    """Anahtarı olan kaynakları öncelik sırasıyla döndürür: [(ad, anahtar, aday_fonk)]."""
    kaynaklar = []
    pixabay = os.environ.get("PIXABAY_API_KEY", "").strip()
    pexels = os.environ.get("PEXELS_API_KEY", "").strip()
    if pixabay:
        kaynaklar.append(["Pixabay", pixabay, pixabay_adaylar])
    if pexels:
        kaynaklar.append(["Pexels", pexels, pexels_adaylar])
    if not kaynaklar:
        uyari("PIXABAY_API_KEY yok; tüm bölümlerde renkli hareketli arka plan kullanılacak")
    return kaynaklar


def medya_bul_indir(kaynaklar, sorgu, klasor, sira, kullanilan):
    """(tür, yol, kaynak_adı) döndürür. Hiçbir şey bulunamazsa ("arka_plan", None, None)."""
    for kaynak in list(kaynaklar):
        ad, anahtar, adaylar = kaynak
        try:
            for tur, url, kimlik in adaylar(anahtar, sorgu):
                if kimlik in kullanilan:
                    continue
                uzanti = "mp4" if tur == "video" else "jpg"
                yol = Path(klasor) / f"medya_{sira:02d}.{uzanti}"
                try:
                    _indir(url, yol)
                except Exception as e:
                    print(f"{ad} indirmesi başarısız: {_gizle(e, [anahtar])}", file=sys.stderr)
                    continue
                kullanilan.add(kimlik)
                return tur, yol, ad
        except KaynakKapali as e:
            uyari(f"{ad} anahtarı reddedildi ({e}); bu kaynak atlanıyor")
            kaynaklar.remove(kaynak)
        except Exception as e:
            uyari(f"{ad} araması başarısız: {_gizle(e, [anahtar])}")
    if kaynaklar:
        uyari(f"'{sorgu}' için görüntü bulunamadı; hareketli arka plan kullanılıyor")
    return "arka_plan", None, None


# ---------------------------------------------------------------- video

def sure_olc(yol):
    return float(calistir(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                           "-of", "default=nw=1:nk=1", str(yol)]).strip())


def _kodla(giris, filtre, sure, hedef):
    calistir(["ffmpeg", "-y", "-loglevel", "error", *giris, "-t", f"{sure:.3f}",
              "-vf", filtre, "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
              "-pix_fmt", "yuv420p", str(hedef)])


def arka_plan_olustur(sira, sure, hedef):
    """Renkli, yavaşça dönen gradyan arka plan üretir."""
    r1, r2, r3 = RENK_PALETLERI[sira % len(RENK_PALETLERI)]
    boyut = f"{GENISLIK}x{YUKSEKLIK}"
    try:
        _kodla(["-f", "lavfi", "-i",
                f"gradients=s={boyut}:r={FPS}:c0={r1}:c1={r2}:c2={r3}:n=3:speed=0.015:type=radial"],
               "format=yuv420p,setsar=1", sure, hedef)
    except KomutHatasi:
        # Eski ffmpeg'de gradients yoksa: rengi zamanla dönen düz arka plan
        _kodla(["-f", "lavfi", "-i", f"color=c={r1}:s={boyut}:r={FPS}"],
               "format=yuv420p,hue=h=t*25:s=1.4,setsar=1", sure, hedef)


def parca_olustur(tur, kaynak, sure, hedef, sira):
    if tur == "arka_plan":
        arka_plan_olustur(sira, sure, hedef)
        return
    olcek = (f"scale={GENISLIK}:{YUKSEKLIK}:force_original_aspect_ratio=increase,"
             f"crop={GENISLIK}:{YUKSEKLIK},setsar=1,fps={FPS}")
    if tur == "video":
        _kodla(["-stream_loop", "-1", "-i", str(kaynak)], olcek, sure, hedef)
    else:
        # Fotoğrafta hafif yakınlaşma efekti
        kare = max(1, round(sure * FPS))
        filtre = (f"scale={GENISLIK * 2}:{YUKSEKLIK * 2}:force_original_aspect_ratio=increase,"
                  f"crop={GENISLIK * 2}:{YUKSEKLIK * 2},"
                  f"zoompan=z='1+0.10*on/{kare}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
                  f":d=1:s={GENISLIK}x{YUKSEKLIK}:fps={FPS},setsar=1")
        _kodla(["-loop", "1", "-i", str(kaynak)], filtre, sure, hedef)


def youtube_bilgileri_yaz(veri, kaynak_adlari, yol):
    etiketler = veri["etiketler"]
    if isinstance(etiketler, list):
        etiketler = ", ".join(str(e).strip() for e in etiketler)
    aciklama = veri["aciklama"].strip()
    if kaynak_adlari:
        aciklama += f"\n\nGörüntüler: {', '.join(kaynak_adlari)}"
    Path(yol).write_text(
        f"BAŞLIK\n{veri['baslik'].strip()}\n\n"
        f"AÇIKLAMA\n{aciklama}\n\n"
        f"ETİKETLER\n{etiketler}\n",
        encoding="utf-8")


def uret(args):
    veri = senaryo_oku(args.senaryo)
    cikti, calisma = Path(args.cikti), Path(args.calisma)
    cikti.mkdir(parents=True, exist_ok=True)
    calisma.mkdir(parents=True, exist_ok=True)
    kaynaklar = kaynaklari_hazirla()

    metin, bolum_konumlari = tam_metin_ve_bolum_konumlari(veri["bolumler"])
    print(f"Senaryo: {len(veri['bolumler'])} bölüm, {len(metin.split())} kelime")

    # 1. Seslendirme
    mp3 = calisma / "ses.mp3"
    print(f"Seslendiriliyor ({args.ses})...")
    sinirlar = seslendir(metin, SESLER[args.ses], mp3)
    ses_suresi = sure_olc(mp3)
    print(f"Ses süresi: {ses_suresi:.1f} sn")
    if not 45 <= ses_suresi <= 55:
        uyari(f"Ses süresi {ses_suresi:.1f} sn; hedef 45-55 sn aralığı")
    toplam_sure = ses_suresi + 0.3

    # 2. Altyazı
    kelimeler = kelimeleri_cikar(metin, sinirlar)
    ass = calisma / "altyazi.ass"
    altyazi_yaz(metin, kelimeler, ses_suresi, ass)

    # 3. Bölüm süreleri (her bölüm, kendi ilk kelimesi okunduğunda başlar)
    baslangiclar = [0.0]
    for konum in bolum_konumlari[1:]:
        ilk = next((k[0] for k in kelimeler if k[2] >= konum), toplam_sure)
        baslangiclar.append(max(ilk, baslangiclar[-1] + 0.5))
    baslangiclar.append(toplam_sure)

    # 4. Görseller ve parçalar
    kullanilan, liste, kullanilan_kaynaklar = set(), [], []
    for i, b in enumerate(veri["bolumler"]):
        sure = max(0.5, baslangiclar[i + 1] - baslangiclar[i])
        tur, kaynak, kaynak_adi = medya_bul_indir(kaynaklar, b["arama"], calisma, i, kullanilan)
        parca = calisma / f"parca_{i:02d}.mp4"
        try:
            parca_olustur(tur, kaynak, sure, parca, i)
        except KomutHatasi:
            uyari(f"{i + 1}. bölümün görüntüsü işlenemedi; hareketli arka plan kullanılıyor")
            tur, kaynak_adi = "arka_plan", None
            arka_plan_olustur(i, sure, parca)
        if kaynak_adi and kaynak_adi not in kullanilan_kaynaklar:
            kullanilan_kaynaklar.append(kaynak_adi)
        print(f"Bölüm {i + 1}: '{b['arama']}' -> {kaynak_adi or 'arka plan'} {tur} ({sure:.1f} sn)")
        liste.append(f"file '{parca.resolve()}'")
    (calisma / "liste.txt").write_text("\n".join(liste) + "\n", encoding="utf-8")

    # 5. Birleştir, sesi ekle, altyazıyı yak
    video = cikti / "video.mp4"
    print("Video birleştiriliyor...")
    calistir(["ffmpeg", "-y", "-loglevel", "error",
              "-f", "concat", "-safe", "0", "-i", str(calisma / "liste.txt"),
              "-i", str(mp3),
              "-vf", f"ass={ass}:fontsdir={FONT_DIZINI}",
              "-map", "0:v", "-map", "1:a",
              "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-pix_fmt", "yuv420p",
              "-r", str(FPS), "-c:a", "aac", "-b:a", "160k",
              "-t", f"{toplam_sure:.3f}", "-movflags", "+faststart", str(video)])

    youtube_bilgileri_yaz(veri, kullanilan_kaynaklar, cikti / "youtube-bilgileri.txt")
    print(f"Hazır: {video} ({sure_olc(video):.1f} sn)")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--senaryo", required=True)
    ap.add_argument("--ses", choices=sorted(SESLER), default="Emel")
    ap.add_argument("--cikti", default="cikti")
    ap.add_argument("--calisma", default="calisma")
    args = ap.parse_args()
    try:
        uret(args)
    except KomutHatasi as e:
        hata(str(e))


if __name__ == "__main__":
    main()
