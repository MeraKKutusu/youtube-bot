#!/usr/bin/env python3
"""Senaryo JSON dosyasından 1080x1920 Shorts/TikTok videosu üretir:
Türkçe seslendirme, İngilizce (ya da Türkçe) altyazı, mood'a göre müzik ve efektler.

Adımlar:
  1. edge-tts ile Türkçe seslendirme (Ahmet varsayılan, Emel) + kelime zamanlamaları
  2. Her bölüm için görüntü, bu sırayla denenir:
       a. Pixabay video (dikey olanlar önce), yoksa Pixabay dikey fotoğraf
       b. Pexels video/fotoğraf (isteğe bağlı; yalnızca anahtar varsa)
       c. Hiçbiri olmazsa ffmpeg ile renkli, hareketli arka plan
     Sahne geçişleri cümle sonlarında; ilk sahnede hafif yakınlaşma (zoom).
  3. Altyazı: her Türkçe cümle seslendirilirken seçilen dildeki karşılığı (en/tr)
     alt üçte birde, büyük kalın beyaz yazı + siyah kenarlık. Kanca yazısı
     (3-5 kelime) ilk cümle boyunca ekranın üstünde.
  4. Ses: scripts/ses.py (müzik, ducking, efektler, -14 LUFS)
  5. Çıktılar: video.mp4, youtube.txt, tiktok.txt, meta.json, altyazi.ass

API anahtarları yalnızca ortam değişkenlerinden okunur (PIXABAY_API_KEY,
PEXELS_API_KEY); GitHub Actions'ta Secret'lardan gelir. Kodda ya da repoda
tutulmaz ve loglara yazılmaz.

Kullanım:
  python scripts/uret.py --senaryo ornek --ses Ahmet --altyazi-dili en \
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

sys.path.insert(0, str(Path(__file__).resolve().parent))
from senaryo_kontrol import kontrol as senaryo_denetle  # noqa: E402
from ses import ses_tasarimi, SesHatasi  # noqa: E402

GENISLIK, YUKSEKLIK, FPS = 1080, 1920, 30
SERI_ADI = "Merak Kutusu: Vahşi Gerçekler"
SERI_KISA = "Vahşi Gerçekler"
ALTYAZI_DILLERI = ("en", "tr")
SURE_HEDEF = (30.0, 40.0)   # seslendirme hedefi (kalite kontrolü 30-45 sn video ister)
TIKTOK_EN_FAZLA_HASHTAG = 5
GORUNTU_SATIRI = {"en": "Footage", "tr": "Görüntüler"}

# Kanca yazısı (ekranın üstü): Shorts/TikTok'un üstteki arama/kamera ikonlarının altında
KANCA_FONT_BOYUTU = 104
KANCA_UST_BOSLUK = 300
KANCA_EN_AZ, KANCA_EN_COK = 2.2, 4.5   # ekranda kalma süresi (sn)
GIRIS_ZOOM = 0.08                       # ilk sahnede %8 yakınlaşma
# Türkçe seslendirenler: Ahmet (erkek, varsayılan) ve Emel (kadın)
SESLER = {"Ahmet": "tr-TR-AhmetNeural", "Emel": "tr-TR-EmelNeural"}
VARSAYILAN_SES = "Ahmet"
# Belgesel anlatıcısı: biraz yavaş ve daha pes; cümle aralarında duraklama
ANLATICI_HIZ = "-8%"
ANLATICI_TON = "-6Hz"
DURAKLAMA = {"kanca": 0.7, "soru": 0.6, "sahne": 0.45, "cumle": 0.3}   # saniye
TTS_ORNEKLEME = 24000

# Altyazı ayarları
FONT_DIZINI = "/usr/share/fonts/truetype/dejavu"
FONT_ADI = "DejaVu Sans"
FONT_DOSYASI = f"{FONT_DIZINI}/DejaVuSans-Bold.ttf"
FONT_BOYUTU = 84
KENARLIK = 7               # siyah kenarlık kalınlığı (piksel)
YAN_BOSLUK = 150           # kanca yazısının yan boşluğu
# Altyazı kutusu: soldan %8; sağda Shorts/TikTok'un beğen/yorum butonları
# bulunduğu için biraz daha fazla boşluk.
ALTYAZI_SOL = round(GENISLIK * 0.08)    # 86 px
ALTYAZI_SAG = 140
ALTYAZI_GENISLIK = GENISLIK - ALTYAZI_SOL - ALTYAZI_SAG
ALTYAZI_EN_FAZLA_SATIR = 2
# Altyazının alt kenarı yüksekliğin %75'inde (y=1440) sabit durur: TikTok alttan
# 480 px'i açıklama/kullanıcı adı için kullanır. İki satıra taşarsa yukarı doğru
# büyür; böylece Shorts/TikTok'un alttaki başlık alanına inmez.
ALTYAZI_ALT_KENAR = round(YUKSEKLIK * 0.75)  # 1440
ALT_BOSLUK = YUKSEKLIK - ALTYAZI_ALT_KENAR  # ASS MarginV (alttan uzaklık)
# libass yazı boyutunu satır yüksekliğine göre ölçekler (DejaVu: 2384/2048 em)
ASS_OLCEK = 2048 / 2384

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

def senaryo_yolu_bul(girdi, klasor="senaryolar"):
    """'ornek', 'Ornek', 'ORNEK.JSON', 'senaryolar/ornek.json' gibi girdileri
    gerçek dosya yoluna çevirir. Önce birebir eşleşme, sonra harf duyarsız arar."""
    girdi = str(girdi).strip()
    if Path(girdi).is_file():
        return Path(girdi)
    ad = re.sub(r"\.json$", "", Path(girdi).name, flags=re.IGNORECASE)
    tam = Path(klasor) / f"{ad}.json"
    if tam.is_file():
        return tam
    for dosya in sorted(Path(klasor).glob("*")):
        if dosya.is_file() and dosya.suffix.lower() == ".json" and dosya.stem.lower() == ad.lower():
            return dosya
    hata(f"senaryo bulunamadı: {girdi} ({klasor}/ klasöründe {ad}.json yok)")


def senaryo_oku(yol):
    yol = senaryo_yolu_bul(yol)
    try:
        veri = json.loads(Path(yol).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        hata(f"senaryo okunamadı ({yol}): {e}")
    veri["_dosya"] = str(yol)
    veri["_ad"] = Path(yol).stem
    yeni = "yayin" in veri or "mood" in veri
    if not yeni:
        for alan in ("baslik", "aciklama", "etiketler"):
            if alan not in veri:
                hata(f"senaryoda '{alan}' alanı eksik")
    if "bolumler" not in veri:
        hata("senaryoda 'bolumler' alanı eksik")
    hatalar, uyarilar = senaryo_denetle(veri, str(yol))
    for u in uyarilar:
        uyari(f"Senaryo: {u}")
    for h in hatalar:
        # Kurallara uymayan ama üretilebilir senaryo videoyu durdurmaz;
        # asıl ölçüt kalite kontrolündeki gerçek süredir.
        uyari(f"Senaryo kuralı: {h}")
    if not veri["bolumler"]:
        hata("senaryoda hiç bölüm yok")
    for i, b in enumerate(veri["bolumler"], 1):
        if not str(b.get("arama", "")).strip():
            hata(f"{i}. bölümde 'arama' boş")
        if "cumleler" in b:
            if not isinstance(b["cumleler"], list) or not b["cumleler"]:
                hata(f"{i}. bölümde 'cumleler' boş bir liste olamaz")
            for j, c in enumerate(b["cumleler"], 1):
                if not isinstance(c, dict) or not str(c.get("tr", "")).strip():
                    hata(f"{i}. bölümün {j}. cümlesinde 'tr' (Türkçe metin) boş")
                if not str(c.get("en", "")).strip():
                    hata(f"{i}. bölümün {j}. cümlesinde 'en' (İngilizce çeviri) boş")
        elif str(b.get("metin", "")).strip():
            # Eski biçim: çevirisiz tek metin
            b["cumleler"] = [{"tr": b["metin"], "en": ""}]
        else:
            hata(f"{i}. bölümde 'cumleler' (ya da eski biçimde 'metin') yok")
    return veri


def buyuk_harf(yazi, dil):
    if dil == "tr":
        yazi = yazi.replace("i", "İ").replace("ı", "I")
    return yazi.upper()


def yayin_bilgisi(veri, dil):
    """Seçilen dildeki başlık/açıklama/hashtag/sabit yorum/kanca yazısını döndürür."""
    def secim(alan):
        deger = veri.get(alan)
        if isinstance(deger, dict):
            return str(deger.get(dil) or deger.get("en") or deger.get("tr") or "").strip()
        return str(deger or "").strip()

    yayin = (veri.get("yayin") or {}).get(dil) or {}
    if yayin:
        baslik = str(yayin.get("baslik", "")).strip()
        aciklama = str(yayin.get("aciklama", "")).strip()
        hashtagler = [str(h).strip() for h in yayin.get("hashtagler", []) if str(h).strip()]
        etiketler = [str(e).strip() for e in yayin.get("etiketler", []) if str(e).strip()]
    else:  # eski biçim
        baslik = str(veri.get("baslik", "")).strip()
        aciklama = str(veri.get("aciklama", "")).strip()
        hashtagler = re.findall(r"#[^\s#]+", aciklama)
        aciklama = re.sub(r"\s*#[^\s#]+", "", aciklama).strip()
        etiketler = veri.get("etiketler", [])
        if isinstance(etiketler, str):
            etiketler = [e.strip() for e in etiketler.split(",")]
    hashtagler = [h if h.startswith("#") else f"#{h}" for h in hashtagler]
    if not etiketler:
        etiketler = [h.lstrip("#") for h in hashtagler if h.lower() != "#shorts"]
    return {
        "baslik": baslik,
        "aciklama": aciklama,
        "hashtagler": list(dict.fromkeys(hashtagler)),
        "etiketler": etiketler,
        "sabit_yorum": secim("sabit_yorum"),
        "kanca_yazisi": secim("kanca_yazisi"),
    }


def _tek_satir(yazi):
    return " ".join(str(yazi).split())


def tam_metin_ve_konumlar(bolumler, dil="en"):
    """Türkçe cümleleri tek metinde birleştirir.

    Döndürür: (metin, bölüm_başlangıç_konumları, cümleler)
    cümleler: her biri {"bas", "son", "bolum", "alt"}; bas/son cümlenin metindeki
    konumu, alt ekranda gösterilecek altyazı (seçilen dilde; yoksa Türkçe).
    """
    parcalar, bolum_konumlari, cumleler, konum = [], [], [], 0
    for bi, b in enumerate(bolumler):
        bolum_konumlari.append(konum)
        for c in b["cumleler"]:
            tr = _tek_satir(c["tr"])
            alt = _tek_satir(c.get(dil, "")) or tr
            cumleler.append({"bas": konum, "son": konum + len(tr), "bolum": bi,
                             "alt": alt, "ceviri_var": bool(_tek_satir(c.get(dil, "")))})
            parcalar.append(tr)
            konum += len(tr) + 1
    return " ".join(parcalar), bolum_konumlari, cumleler


# ---------------------------------------------------------------- seslendirme

async def _seslendir(metin, ses, mp3_yolu, hiz, ton):
    import edge_tts

    try:
        iletisim = edge_tts.Communicate(metin, ses, rate=hiz, pitch=ton, boundary="WordBoundary")
    except TypeError:  # eski sürümler kelime sınırlarını zaten varsayılan verir
        iletisim = edge_tts.Communicate(metin, ses, rate=hiz, pitch=ton)
    sinirlar = []
    with open(mp3_yolu, "wb") as f:
        async for parca in iletisim.stream():
            if parca["type"] == "audio":
                f.write(parca["data"])
            elif parca["type"] in ("WordBoundary", "SentenceBoundary"):
                sinirlar.append((parca["type"], parca["offset"] / 1e7,
                                 parca["duration"] / 1e7, parca["text"]))
    return sinirlar


def _cumle_seslendir(metin, ses, mp3_yolu, hiz, ton):
    for deneme in range(1, 4):
        try:
            sinirlar = asyncio.run(_seslendir(metin, ses, mp3_yolu, hiz, ton))
            if sinirlar and Path(mp3_yolu).stat().st_size > 0:
                return sinirlar
            print(f"Seslendirme boş döndü (deneme {deneme})", file=sys.stderr)
        except Exception as e:  # ağ hataları vb.
            print(f"Seslendirme hatası (deneme {deneme}): {e}", file=sys.stderr)
        time.sleep(5 * deneme)
    hata("edge-tts seslendirmesi 3 denemede de başarısız oldu; workflow'u yeniden çalıştırın")


def duraklama_suresi(bolumler, bi, ci):
    """Bölüm bi'deki ci. cümleden sonra eklenecek sessizlik (sn)."""
    son_bolum = bi == len(bolumler) - 1
    son_cumle = ci == len(bolumler[bi]["cumleler"]) - 1
    if son_bolum and son_cumle:
        return 0.0
    metin = str(bolumler[bi]["cumleler"][ci]["tr"]).strip()
    if bi == 0 and ci == 0:
        return DURAKLAMA["kanca"]
    if metin.endswith("?"):
        return DURAKLAMA["soru"]
    if son_cumle:
        return DURAKLAMA["sahne"]
    return DURAKLAMA["cumle"]


def seslendir(bolumler, ses, wav_yolu, calisma, hiz=ANLATICI_HIZ, ton=ANLATICI_TON):
    """Cümleleri ayrı ayrı belgesel tonunda seslendirir, aralarına duraklama koyup
    tek wav'da birleştirir. (tür, başlangıç_sn, süre_sn, yazı) listesi döndürür."""
    import wave

    klasor = Path(calisma) / "tts"
    klasor.mkdir(parents=True, exist_ok=True)
    tum_sinirlar, kareler, t = [], [], 0.0
    sira = 0
    for bi, b in enumerate(bolumler):
        for ci, c in enumerate(b["cumleler"]):
            metin = _tek_satir(c["tr"])
            mp3 = klasor / f"c{sira:02d}.mp3"
            wav = klasor / f"c{sira:02d}.wav"
            sira += 1
            sinirlar = _cumle_seslendir(metin, ses, mp3, hiz, ton)
            calistir(["ffmpeg", "-y", "-loglevel", "error", "-i", str(mp3),
                      "-ac", "1", "-ar", str(TTS_ORNEKLEME), "-c:a", "pcm_s16le", str(wav)])
            with wave.open(str(wav), "rb") as w:
                veri = w.readframes(w.getnframes())
            # Sondaki boşluğu kırp: son kelime biter bitmez (küçük bir payla) kes
            son = max(bas + sure for _, bas, sure, _ in sinirlar) + 0.08
            veri = veri[:min(len(veri), int(son * TTS_ORNEKLEME) * 2)]
            for tur, bas, sure, yazi in sinirlar:
                tum_sinirlar.append((tur, t + bas, sure, yazi))
            dur = duraklama_suresi(bolumler, bi, ci)
            kareler.append(veri + b"\x00\x00" * int(dur * TTS_ORNEKLEME))
            t += len(veri) / 2 / TTS_ORNEKLEME + dur
    with wave.open(str(wav_yolu), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(TTS_ORNEKLEME)
        w.writeframes(b"".join(kareler))
    return tum_sinirlar


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


def _ass_basligi():
    # Alignment 2 = alt orta (MarginV alttan uzaklık). Bold -1 = kalın.
    # BorderStyle 1 + Outline = kenarlık.
    return f"""[Script Info]
ScriptType: v4.00+
PlayResX: {GENISLIK}
PlayResY: {YUKSEKLIK}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Ana,{FONT_ADI},{FONT_BOYUTU},&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,{KENARLIK},2,2,{ALTYAZI_SOL},{ALTYAZI_SAG},{ALT_BOSLUK},1
Style: Kanca,{FONT_ADI},{KANCA_FONT_BOYUTU},&H0000E5FF,&H0000E5FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,{KENARLIK + 2},3,8,{YAN_BOSLUK - 40},{YAN_BOSLUK - 40},{KANCA_UST_BOSLUK},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def _dialog(bas, bit, yazi, stil="Ana", efekt=""):
    """yazi bir metin ya da satır listesi olabilir (satırlar \\N ile ayrılır)."""
    if isinstance(yazi, (list, tuple)):
        metin = "\\N".join(_ass_kacis(s) for s in yazi)
    else:
        metin = _ass_kacis(yazi)
    return f"Dialogue: 0,{_ass_zaman(bas)},{_ass_zaman(bit)},{stil},,0,0,0,,{efekt}{metin}"


def kanca_satiri(yazi, bit):
    """Ekranın üstündeki kanca yazısı: küçükten büyüyerek gelir, sonunda söner."""
    efekt = r"{\fscx70\fscy70\t(0,180,\fscx108\fscy108)\t(180,300,\fscx100\fscy100)\fad(0,250)}"
    return _dialog(0.0, bit, yazi, "Kanca", efekt)


_FONT = None


def yazi_genisligi(yazi):
    """Altyazı satırının videodaki yaklaşık genişliği (piksel, kenarlık dahil)."""
    global _FONT
    if _FONT is None:
        try:
            from PIL import ImageFont
            _FONT = ImageFont.truetype(FONT_DOSYASI, max(1, round(FONT_BOYUTU * ASS_OLCEK)))
        except Exception:  # Pillow ya da yazı tipi yoksa kaba tahmin
            _FONT = False
    if _FONT:
        return _FONT.getlength(yazi) + 2 * KENARLIK
    return len(yazi) * FONT_BOYUTU * 0.53 + 2 * KENARLIK


def _sigar(kelimeler):
    return yazi_genisligi(" ".join(kelimeler)) <= ALTYAZI_GENISLIK


def _dengeli_bol(kelimeler):
    """Kelimeleri en fazla 2 satıra, satırlar olabildiğince eşit olacak şekilde böler.
    Sığmazsa None döndürür."""
    if _sigar(kelimeler):
        return [" ".join(kelimeler)]
    en_iyi = None
    for i in range(1, len(kelimeler)):
        ust, alt = kelimeler[:i], kelimeler[i:]
        if _sigar(ust) and _sigar(alt):
            fark = max(yazi_genisligi(" ".join(ust)), yazi_genisligi(" ".join(alt)))
            if en_iyi is None or fark < en_iyi[0]:
                en_iyi = (fark, [" ".join(ust), " ".join(alt)])
    return en_iyi[1] if en_iyi else None


def _acgozlu_parcala(kelimeler):
    parcalar = []
    while kelimeler:
        n = 1
        while n < len(kelimeler) and _dengeli_bol(kelimeler[:n + 1]):
            n += 1
        parcalar.append(kelimeler[:n])
        kelimeler = kelimeler[n:]
    return parcalar


def _dengeli_parcala(kelimeler, k):
    """Kelimeleri k parçaya, parça uzunlukları birbirine yakın olacak şekilde böler.
    Noktalamadan (virgül vb.) sonra kesmeyi tercih eder."""
    toplam = len(" ".join(kelimeler))
    hedef = toplam / k
    parcalar, mevcut = [], []
    for i, kel in enumerate(kelimeler):
        mevcut.append(kel)
        kalan_parca = k - len(parcalar) - 1
        uzunluk = len(" ".join(mevcut))
        kalan_kelime = len(kelimeler) - i - 1
        if kalan_parca <= 0 or kalan_kelime < kalan_parca:
            continue
        noktalama = kel[-1:] in ",;:" and uzunluk >= hedef * 0.6
        sonraki = len(" ".join(mevcut + [kelimeler[i + 1]]))
        if noktalama or (uzunluk >= hedef * 0.85 and sonraki > hedef * 1.1) or uzunluk >= hedef * 1.15:
            parcalar.append(mevcut)
            mevcut = []
    if mevcut:
        parcalar.append(mevcut)
    if len(parcalar) == k and all(_dengeli_bol(p) for p in parcalar):
        return parcalar
    return None


def ceviri_parcala(yazi):
    """Altyazı cümlesini ekrana sığan parçalara böler. Her parça en fazla 2 satırdır
    (satır listesi). Cümle tek ekrana sığıyorsa bölünmez; sığmıyorsa parçalar eşit
    uzunlukta tutulmaz; ekran olabildiğince dolu kullanılır, yalnızca tek kelimelik
    kuyruk önlenir."""
    kelimeler = yazi.split()
    if not kelimeler:
        return []
    parcalar = _acgozlu_parcala(kelimeler)
    # Ekranda tek başına bir kelime kalmasın: son iki parçayı dengele
    if len(parcalar) > 1 and len(parcalar[-1]) == 1:
        son_iki = _dengeli_parcala(parcalar[-2] + parcalar[-1], 2)
        if son_iki:
            parcalar[-2:] = son_iki
    return [_dengeli_bol(p) or [" ".join(p)] for p in parcalar]


def _zaman_bul(cumle_kelimeleri, oran):
    """Türkçe cümlenin harf oranına (0-1) denk gelen seslendirme zamanı.
    Kelime zamanları kullanıldığı için duraklamalar da hesaba katılır."""
    bas_konum = cumle_kelimeleri[0][2]
    son_konum = cumle_kelimeleri[-1][2] + 1
    hedef = bas_konum + oran * (son_konum - bas_konum)
    for k in cumle_kelimeleri:
        if k[2] >= hedef:
            return k[0]
    return cumle_kelimeleri[-1][0]


def ceviri_altyazi_yaz(kelimeler, cumleler, ses_suresi, ass_yolu, kanca=""):
    """Her Türkçe cümle seslendirilirken onun altyazısını (en ya da tr) gösterir.
    kanca verilirse ilk cümle boyunca ekranın üstünde durur.
    Altyazı satır sayısını döndürür."""
    # Her cümlenin kelimelerini bul
    for c in cumleler:
        c["kelimeler"] = [k for k in kelimeler if c["bas"] <= k[2] < c["son"]]
    # Kelimesi bulunamayan (çok nadir) cümleyi bir öncekiyle birleştir
    gecerli = []
    for c in cumleler:
        if c["kelimeler"]:
            gecerli.append(c)
        elif gecerli:
            gecerli[-1]["alt"] += " " + c["alt"]
    if not gecerli:
        hata("cümleler seslendirme zamanlarıyla eşleştirilemedi")

    satirlar = []
    for i, c in enumerate(gecerli):
        bas = c["kelimeler"][0][0]
        if i + 1 < len(gecerli):
            bit = gecerli[i + 1]["kelimeler"][0][0]
        else:
            bit = min(ses_suresi, c["kelimeler"][-1][1] + 0.6)
        bit = max(bit, bas + 0.3)
        parcalar = ceviri_parcala(c["alt"])
        toplam = sum(len(" ".join(p)) for p in parcalar) or 1
        birikmis = 0
        zamanlar = []
        for p in parcalar:
            zamanlar.append(max(bas, _zaman_bul(c["kelimeler"], birikmis / toplam)))
            birikmis += len(" ".join(p))
        zamanlar.append(bit)
        for j, p in enumerate(parcalar):
            pb, pson = zamanlar[j], zamanlar[j + 1]
            if pson - pb < 0.4:  # çok kısa kalan parçaya biraz süre ver
                pson = min(bit, pb + 0.4)
            satirlar.append(_dialog(pb, pson, p))
    altyazi_sayisi = len(satirlar)
    if kanca:
        ilk_bit = gecerli[0]["kelimeler"][-1][1] + 0.3
        satirlar.insert(0, kanca_satiri(kanca, min(KANCA_EN_COK, max(KANCA_EN_AZ, ilk_bit))))
    Path(ass_yolu).write_text(_ass_basligi() + "\n".join(satirlar) + "\n", encoding="utf-8")
    return altyazi_sayisi


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


def parca_olustur(tur, kaynak, sure, hedef, sira, giris_zoom=False):
    if tur == "arka_plan":
        arka_plan_olustur(sira, sure, hedef)
    else:
        olcek = (f"scale={GENISLIK}:{YUKSEKLIK}:force_original_aspect_ratio=increase,"
                 f"crop={GENISLIK}:{YUKSEKLIK},setsar=1,fps={FPS}")
        if tur == "video":
            _kodla(["-stream_loop", "-1", "-i", str(kaynak)], olcek, sure, hedef)
        else:
            # Fotoğrafta hafif yakınlaşma efekti (ilk sahnede zaten zoom var)
            kare = max(1, round(sure * FPS))
            filtre = (f"scale={GENISLIK * 2}:{YUKSEKLIK * 2}:force_original_aspect_ratio=increase,"
                      f"crop={GENISLIK * 2}:{YUKSEKLIK * 2},"
                      f"zoompan=z='1+0.10*on/{kare}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
                      f":d=1:s={GENISLIK}x{YUKSEKLIK}:fps={FPS},setsar=1")
            _kodla(["-loop", "1", "-i", str(kaynak)], filtre, sure, hedef)
            return
    if giris_zoom:
        zoom_uygula(hedef, sure)


def zoom_uygula(yol, sure):
    """Sahneye yavaşlayarak biten hafif bir yakınlaşma ekler (girişte)."""
    kare = max(1, round(sure * FPS))
    gecici = Path(yol).with_name(Path(yol).stem + "_zoom.mp4")
    filtre = (f"zoompan=z='1+{GIRIS_ZOOM}*(1-pow(1-min(on/{kare},1),2))'"
              f":x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1"
              f":s={GENISLIK}x{YUKSEKLIK}:fps={FPS},setsar=1")
    _kodla(["-i", str(yol)], filtre, sure, gecici)
    Path(gecici).replace(yol)


def _hashtag_satiri(hashtagler):
    return " ".join(hashtagler)


def yayin_dosyalari_yaz(veri, dil, kaynak_adlari, cikti):
    """youtube.txt, tiktok.txt yazar; meta için yayın bilgilerini döndürür."""
    y = yayin_bilgisi(veri, dil)
    no = veri.get("seri_no")
    seri = f"{SERI_ADI} #{no}" if isinstance(no, int) and no > 0 else SERI_ADI

    baslik = y["baslik"]
    if isinstance(no, int) and no > 0:
        ekli = f"{baslik} | {SERI_KISA} #{no}"
        if len(ekli) <= 100:
            baslik = ekli
    baslik = baslik[:100]

    yt_hashtag = list(y["hashtagler"])
    if "#shorts" not in [h.lower() for h in yt_hashtag]:
        yt_hashtag.insert(0, "#shorts")
    aciklama = f"{seri}\n\n{y['aciklama']}\n\n{_hashtag_satiri(yt_hashtag[:5])}"
    if kaynak_adlari:
        aciklama += f"\n\n{GORUNTU_SATIRI[dil]}: {', '.join(kaynak_adlari)}"

    tt_hashtag = [h for h in y["hashtagler"] if h.lower() != "#shorts"]
    tt_hashtag = (tt_hashtag + ["#fyp"])[:TIKTOK_EN_FAZLA_HASHTAG]
    tiktok = f"{y['baslik']}\n{seri}\n\n{_hashtag_satiri(tt_hashtag)}"

    etiket_basligi = {"en": ("TITLE", "DESCRIPTION", "TAGS", "PINNED COMMENT"),
                      "tr": ("BAŞLIK", "AÇIKLAMA", "ETİKETLER", "SABİT YORUM")}[dil]
    Path(cikti, "youtube.txt").write_text(
        f"{etiket_basligi[0]}\n{baslik}\n\n"
        f"{etiket_basligi[1]}\n{aciklama}\n\n"
        f"{etiket_basligi[2]}\n{', '.join(y['etiketler'])}\n\n"
        f"{etiket_basligi[3]}\n{y['sabit_yorum']}\n",
        encoding="utf-8")
    Path(cikti, "tiktok.txt").write_text(
        f"{tiktok}\n\n{etiket_basligi[3]}\n{y['sabit_yorum']}\n", encoding="utf-8")
    return {"youtube_baslik": baslik, "youtube_aciklama": aciklama, "tiktok_metin": tiktok,
            "sabit_yorum": y["sabit_yorum"], "hashtagler": y["hashtagler"],
            "etiketler": y["etiketler"]}


def sahne_sinirlari(bolum_sayisi, cumleler, toplam_sure):
    """Her bölümün [başlangıç, bitiş) zamanları. Geçişler cümle sonlarında olur:
    önceki bölümün son kelimesi biter bitmez (sessizliğin ortasında) sahne değişir."""
    sinirlar = [0.0]
    for bi in range(1, bolum_sayisi):
        onceki = [k for c in cumleler if c["bolum"] == bi - 1 for k in c.get("kelimeler", [])]
        bu = [k for c in cumleler if c["bolum"] == bi for k in c.get("kelimeler", [])]
        if onceki and bu:
            an = (onceki[-1][1] + bu[0][0]) / 2
        elif bu:
            an = bu[0][0]
        else:
            an = sinirlar[-1] + 0.5
        sinirlar.append(min(max(an, sinirlar[-1] + 0.5), toplam_sure - 0.3))
    sinirlar.append(toplam_sure)
    return sinirlar


def uret(args):
    dil = args.altyazi_dili
    veri = senaryo_oku(args.senaryo)
    cikti, calisma = Path(args.cikti), Path(args.calisma)
    cikti.mkdir(parents=True, exist_ok=True)
    calisma.mkdir(parents=True, exist_ok=True)
    kaynaklar = kaynaklari_hazirla()
    mood = veri.get("mood") or "mysterious"

    metin, bolum_konumlari, cumleler = tam_metin_ve_konumlar(veri["bolumler"], dil)
    print(f"Senaryo: {veri['_dosya']} — {len(veri['bolumler'])} bölüm, "
          f"{len(metin.split())} kelime, mood={mood}, altyazı={dil}")
    if not all(c["ceviri_var"] for c in cumleler):
        uyari(f"Bazı cümlelerde '{dil}' altyazısı yok; o cümlelerde Türkçe metin gösteriliyor")

    # 1. Seslendirme
    mp3 = calisma / "ses.wav"
    print(f"Seslendiriliyor ({args.ses}, hız {args.hiz}, ton {args.ton})...")
    sinirlar = seslendir(veri["bolumler"], SESLER[args.ses], mp3, calisma, args.hiz, args.ton)
    ses_suresi = sure_olc(mp3)
    print(f"Ses süresi: {ses_suresi:.1f} sn")
    if not SURE_HEDEF[0] <= ses_suresi <= SURE_HEDEF[1]:
        uyari(f"Ses süresi {ses_suresi:.1f} sn; hedef {SURE_HEDEF[0]:.0f}-{SURE_HEDEF[1]:.0f} sn")
    toplam_sure = ses_suresi + 0.8   # kapanış efekti ve son kare için kısa kuyruk

    # 2. Altyazı + kanca yazısı
    kelimeler = kelimeleri_cikar(metin, sinirlar)
    ass = calisma / "altyazi.ass"
    kanca = buyuk_harf(yayin_bilgisi(veri, dil)["kanca_yazisi"], dil)
    altyazi_sayisi = ceviri_altyazi_yaz(kelimeler, cumleler, ses_suresi, ass, kanca)
    print(f"Altyazı: {altyazi_sayisi} satır ({dil}), kanca yazısı: {kanca or '-'}")

    # 3. Sahne sınırları (cümle sonlarında)
    sinir = sahne_sinirlari(len(veri["bolumler"]), cumleler, toplam_sure)

    # 4. Görseller ve parçalar
    kullanilan, liste, kullanilan_kaynaklar = set(), [], []
    for i, b in enumerate(veri["bolumler"]):
        sure = max(0.5, sinir[i + 1] - sinir[i])
        tur, kaynak, kaynak_adi = medya_bul_indir(kaynaklar, b["arama"], calisma, i, kullanilan)
        parca = calisma / f"parca_{i:02d}.mp4"
        try:
            parca_olustur(tur, kaynak, sure, parca, i, giris_zoom=(i == 0))
        except KomutHatasi:
            uyari(f"{i + 1}. bölümün görüntüsü işlenemedi; hareketli arka plan kullanılıyor")
            tur, kaynak_adi = "arka_plan", None
            arka_plan_olustur(i, sure, parca)
        if kaynak_adi and kaynak_adi not in kullanilan_kaynaklar:
            kullanilan_kaynaklar.append(kaynak_adi)
        print(f"Bölüm {i + 1}: '{b['arama']}' -> {kaynak_adi or 'arka plan'} {tur} "
              f"({sinir[i]:.1f}-{sinir[i + 1]:.1f} sn)")
        liste.append(f"file '{parca.resolve()}'")
    (calisma / "liste.txt").write_text("\n".join(liste) + "\n", encoding="utf-8")

    # 5. Ses tasarımı: müzik, efektler, ducking, -14 LUFS
    gerilimler = [(sinir[i], sinir[i + 1]) for i, b in enumerate(veri["bolumler"]) if b.get("gerilim")]
    kapanis = sinir[-2] if len(veri["bolumler"]) > 1 else max(0.0, toplam_sure - 3.5)
    karisim = calisma / "karisim.wav"
    print(f"Ses tasarımı ({mood})...")
    try:
        ses_tasarimi(mp3, toplam_sure, mood, sinir[1:-1], kapanis, gerilimler,
                     karisim, calisma / "ses", args.muzik_klasoru)
    except SesHatasi as e:
        raise KomutHatasi(str(e))

    # 6. Birleştir, sesi ekle, altyazıyı yak
    video = cikti / "video.mp4"
    print("Video birleştiriliyor...")
    calistir(["ffmpeg", "-y", "-loglevel", "error",
              "-f", "concat", "-safe", "0", "-i", str(calisma / "liste.txt"),
              "-i", str(karisim),
              "-vf", f"ass={ass}:fontsdir={FONT_DIZINI}",
              "-map", "0:v", "-map", "1:a",
              "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-pix_fmt", "yuv420p",
              "-r", str(FPS), "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
              "-t", f"{toplam_sure:.3f}", "-movflags", "+faststart", str(video)])

    # 7. Yayın dosyaları ve meta
    yayin = yayin_dosyalari_yaz(veri, dil, kullanilan_kaynaklar, cikti)
    Path(ass).replace(cikti / "altyazi.ass")
    no = veri.get("seri_no")
    konu = str(veri.get("konu") or veri["_ad"]).strip()
    release_adi = f"{SERI_KISA} #{no} - {konu}" if isinstance(no, int) and no > 0 else f"{konu} (test)"
    meta = {
        "senaryo": veri["_dosya"], "ad": veri["_ad"], "seri_no": no, "konu": konu,
        "test": bool(veri.get("test")), "mood": mood, "altyazi_dili": dil, "ses": args.ses,
        "ses_suresi": round(ses_suresi, 2), "video_suresi": round(sure_olc(video), 2),
        "cumle_sayisi": len(cumleler), "altyazi_sayisi": altyazi_sayisi,
        "kanca_yazisi": kanca, "goruntu_kaynaklari": kullanilan_kaynaklar,
        "release_adi": release_adi, **yayin,
    }
    Path(cikti, "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Hazır: {video} ({meta['video_suresi']:.1f} sn) — {release_adi}")


def ses_adi(deger):
    """Ses adını büyük/küçük harf duyarsız kabul eder (ahmet, AHMET, Ahmet)."""
    for ad in SESLER:
        if ad.lower() == str(deger).strip().lower():
            return ad
    raise argparse.ArgumentTypeError(f"geçersiz ses: {deger} (seçenekler: {', '.join(SESLER)})")


def dil_adi(deger):
    d = str(deger).strip().lower()
    if d not in ALTYAZI_DILLERI:
        raise argparse.ArgumentTypeError(f"geçersiz altyazı dili: {deger} (en ya da tr)")
    return d


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--senaryo", required=True)
    ap.add_argument("--ses", type=ses_adi, default=VARSAYILAN_SES,
                    help="Ahmet (erkek, varsayılan) ya da Emel (kadın)")
    ap.add_argument("--hiz", default=ANLATICI_HIZ, help="edge-tts hızı (varsayılan -8%%)")
    ap.add_argument("--ton", default=ANLATICI_TON, help="edge-tts tonu (varsayılan -6Hz)")
    ap.add_argument("--altyazi-dili", type=dil_adi, default="en", help="en (varsayılan) ya da tr")
    ap.add_argument("--muzik-klasoru", default="assets/muzik")
    ap.add_argument("--cikti", default="cikti")
    ap.add_argument("--calisma", default="calisma")
    args = ap.parse_args()
    try:
        uret(args)
    except KomutHatasi as e:
        hata(str(e))


if __name__ == "__main__":
    main()
