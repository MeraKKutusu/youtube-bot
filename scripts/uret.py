#!/usr/bin/env python3
"""Senaryo JSON dosyasından 1080x1920 Türkçe YouTube Shorts videosu üretir.

Adımlar:
  1. edge-tts ile Türkçe seslendirme + kelime zamanlamaları
  2. Her bölüm için Pexels'ten dikey video (yoksa dikey fotoğraf)
  3. Ekranın ortasında büyük, kalın, siyah kenarlıklı beyaz altyazı
  4. ffmpeg ile 1080x1920, 30 fps MP4

Pexels anahtarı yalnızca PEXELS_API_KEY ortam değişkeninden okunur
(GitHub Actions'ta bir Secret'tan gelir). Kodda ya da repoda tutulmaz.

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

PEXELS_VIDEO = "https://api.pexels.com/videos/search"
PEXELS_FOTO = "https://api.pexels.com/v1/search"


def hata(mesaj):
    print(f"HATA: {mesaj}", file=sys.stderr)
    sys.exit(1)


def calistir(komut):
    sonuc = subprocess.run(komut, capture_output=True, text=True)
    if sonuc.returncode != 0:
        print(sonuc.stderr[-3000:], file=sys.stderr)
        hata(f"komut başarısız oldu: {komut[0]}")
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


# ---------------------------------------------------------------- Pexels

def _pexels_get(anahtar, url, sorgu):
    import requests

    for deneme in range(1, 4):
        try:
            r = requests.get(url, headers={"Authorization": anahtar},
                             params={"query": sorgu, "orientation": "portrait", "per_page": 15},
                             timeout=30)
            if r.status_code == 401:
                hata("Pexels anahtarı geçersiz (PEXELS_API_KEY secret'ını kontrol edin)")
            if r.status_code == 429:
                time.sleep(10 * deneme)
                continue
            r.raise_for_status()
            return r.json()
        except SystemExit:
            raise
        except Exception as e:
            print(f"Pexels isteği başarısız ({sorgu}, deneme {deneme}): {e}", file=sys.stderr)
            time.sleep(3 * deneme)
    return {}


def _indir(url, hedef):
    import requests

    with requests.get(url, stream=True, timeout=120) as r:
        r.raise_for_status()
        with open(hedef, "wb") as f:
            for blok in r.iter_content(1 << 20):
                f.write(blok)


def medya_bul_indir(anahtar, sorgu, klasor, sira, kullanilan):
    """Sorgu için dikey video (yoksa fotoğraf) indirir; (tür, yol) döndürür."""
    sorgular = [sorgu]
    ilk_kelime = sorgu.split()[0] if sorgu.split() else ""
    if ilk_kelime and ilk_kelime != sorgu:
        sorgular.append(ilk_kelime)

    for s in sorgular:
        for v in _pexels_get(anahtar, PEXELS_VIDEO, s).get("videos", []):
            if ("v", v["id"]) in kullanilan:
                continue
            dosyalar = [f for f in v.get("video_files", [])
                        if f.get("file_type") == "video/mp4" and f.get("width") and f.get("height")
                        and f["height"] > f["width"] and f["width"] >= 540]
            if not dosyalar:
                continue
            dosyalar.sort(key=lambda f: abs(f["width"] - GENISLIK))
            yol = Path(klasor) / f"medya_{sira:02d}.mp4"
            _indir(dosyalar[0]["link"], yol)
            kullanilan.add(("v", v["id"]))
            return "video", yol

    for s in sorgular + ["nature"]:
        for p in _pexels_get(anahtar, PEXELS_FOTO, s).get("photos", []):
            if ("f", p["id"]) in kullanilan:
                continue
            url = p.get("src", {}).get("large2x") or p.get("src", {}).get("portrait")
            if not url:
                continue
            yol = Path(klasor) / f"medya_{sira:02d}.jpg"
            _indir(url, yol)
            kullanilan.add(("f", p["id"]))
            return "foto", yol

    hata(f"Pexels'te '{sorgu}' için görsel bulunamadı; bu bölümün 'arama' kelimelerini değiştirin")


# ---------------------------------------------------------------- video

def sure_olc(yol):
    return float(calistir(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                           "-of", "default=nw=1:nk=1", str(yol)]).strip())


def parca_olustur(tur, kaynak, sure, hedef):
    olcek = (f"scale={GENISLIK}:{YUKSEKLIK}:force_original_aspect_ratio=increase,"
             f"crop={GENISLIK}:{YUKSEKLIK},setsar=1,fps={FPS}")
    if tur == "video":
        giris = ["-stream_loop", "-1", "-i", str(kaynak)]
        filtre = olcek
    else:
        # Fotoğrafta hafif yakınlaşma efekti
        kare = max(1, round(sure * FPS))
        giris = ["-loop", "1", "-i", str(kaynak)]
        filtre = (f"scale={GENISLIK * 2}:{YUKSEKLIK * 2}:force_original_aspect_ratio=increase,"
                  f"crop={GENISLIK * 2}:{YUKSEKLIK * 2},"
                  f"zoompan=z='1+0.10*on/{kare}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
                  f":d=1:s={GENISLIK}x{YUKSEKLIK}:fps={FPS},setsar=1")
    calistir(["ffmpeg", "-y", "-loglevel", "error", *giris, "-t", f"{sure:.3f}",
              "-vf", filtre, "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
              "-pix_fmt", "yuv420p", str(hedef)])


def youtube_bilgileri_yaz(veri, yol):
    etiketler = veri["etiketler"]
    if isinstance(etiketler, list):
        etiketler = ", ".join(str(e).strip() for e in etiketler)
    Path(yol).write_text(
        f"BAŞLIK\n{veri['baslik'].strip()}\n\n"
        f"AÇIKLAMA\n{veri['aciklama'].strip()}\n\n"
        f"ETİKETLER\n{etiketler}\n",
        encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--senaryo", required=True)
    ap.add_argument("--ses", choices=sorted(SESLER), default="Emel")
    ap.add_argument("--cikti", default="cikti")
    ap.add_argument("--calisma", default="calisma")
    args = ap.parse_args()

    anahtar = os.environ.get("PEXELS_API_KEY", "").strip()
    if not anahtar:
        hata("PEXELS_API_KEY ortam değişkeni boş (GitHub Secret olarak ekleyin)")

    veri = senaryo_oku(args.senaryo)
    cikti, calisma = Path(args.cikti), Path(args.calisma)
    cikti.mkdir(parents=True, exist_ok=True)
    calisma.mkdir(parents=True, exist_ok=True)

    metin, bolum_konumlari = tam_metin_ve_bolum_konumlari(veri["bolumler"])
    kelime_sayisi = len(metin.split())
    print(f"Senaryo: {len(veri['bolumler'])} bölüm, {kelime_sayisi} kelime")

    # 1. Seslendirme
    mp3 = calisma / "ses.mp3"
    print(f"Seslendiriliyor ({args.ses})...")
    sinirlar = seslendir(metin, SESLER[args.ses], mp3)
    ses_suresi = sure_olc(mp3)
    print(f"Ses süresi: {ses_suresi:.1f} sn")
    if not 45 <= ses_suresi <= 55:
        print(f"::warning::Ses süresi {ses_suresi:.1f} sn; hedef 45-55 sn aralığı")
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
    kullanilan, liste = set(), []
    for i, b in enumerate(veri["bolumler"]):
        sure = max(0.5, baslangiclar[i + 1] - baslangiclar[i])
        print(f"Bölüm {i + 1}: '{b['arama']}' ({sure:.1f} sn)")
        tur, kaynak = medya_bul_indir(anahtar, b["arama"], calisma, i, kullanilan)
        parca = calisma / f"parca_{i:02d}.mp4"
        parca_olustur(tur, kaynak, sure, parca)
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

    youtube_bilgileri_yaz(veri, cikti / "youtube-bilgileri.txt")
    print(f"Hazır: {video} ({sure_olc(video):.1f} sn)")


if __name__ == "__main__":
    main()
