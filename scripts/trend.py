#!/usr/bin/env python3
"""Trend avcısı: YouTube Data API ile son 30 günün en çok izlenen hayvan Shorts'larını bulur.

Yalnızca başlık, kanal, izlenme ve tarih kullanılır; video indirilmez, içerik kopyalanmaz.

  1. İngilizce ve Türkçe 8 arama (search.list, her biri 100 birim) + izlenme ve süre
     bilgisi (videos.list, 50 videoluk her istek 1 birim). Toplam ~810 birim; günlük
     varsayılan kota 10.000 birim. Betik EN_FAZLA_BIRIM'i asla aşmaz.
  2. 3 dakikadan uzun videolar (Shorts değil) ve evcil hayvan videoları elenir.
  3. Başlıklardaki hayvan adları sözlükle eşleştirilir; izlenmesi en yüksek 5 hayvan
     "en güçlü konu" olur.
  4. Başlıklar kanca kalıplarına göre sınıflanır (soru, rekor, gizli bilgi, tehlike...);
     ortalamanın üstünde izlenen kalıplar raporlanır.
  5. Konular konular.txt'nin en üstüne eklenir (daha önce kullanıldıysa eklenmez,
     işaretsiz olarak zaten listedeyse en üste taşınır).
  6. Sonuç yayinlar/trendler/YYYY-MM-DD.json dosyasına yazılır; haftalık özet ve
     senaryo denetleyicisi (başlık benzerliği kontrolü) bu dosyayı okur.

Kullanım: YOUTUBE_API_KEY=... python scripts/trend.py
"""
import argparse
import json
import math
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

API = "https://www.googleapis.com/youtube/v3"
EN_FAZLA_BIRIM = 1500          # bir çalıştırmada harcanabilecek en fazla kota
ARAMA_BIRIM, VIDEO_BIRIM = 100, 1
EN_UZUN_SHORT = 180            # sn (Shorts en fazla 3 dakika)
EN_AZ_IZLENME = 20_000
GUN = 30
KONU_SAYISI = 5

ARAMALAR = [
    ("en", "ocean animal facts shorts"),
    ("en", "deep sea creature shorts"),
    ("en", "wild animal facts shorts"),
    ("en", "sea creatures you didn't know"),
    ("tr", "deniz canlıları ilginç bilgiler"),
    ("tr", "vahşi hayvanlar bilgi shorts"),
    ("tr", "hayvanlar hakkında bilinmeyenler"),
    ("tr", "okyanus canlıları shorts"),
]

# Evcil/çiftlik hayvanı ve konu dışı içerik
DISLA = re.compile(r"\b(cat|cats|kitten|dog|dogs|puppy|puppies|kedi|kedisi|köpek|köpeği|"
                   r"yavru kedi|hamster|parrot pet|chicken|tavuk|recipe|tarif|minecraft|"
                   r"roblox|cartoon|çizgi film|ai generated)\b", re.I)

# Kanonik ad: (deniz|kara, [eşleşen İngilizce/Türkçe adlar]) — uzun adlar önce denenir
HAYVANLAR = {
    "Great white shark": ("deniz", ["great white shark", "great white", "beyaz köpekbalığı", "büyük beyaz köpek balığı"]),
    "Greenland shark": ("deniz", ["greenland shark", "grönland köpekbalığı", "grönland köpek balığı"]),
    "Hammerhead shark": ("deniz", ["hammerhead", "çekiç başlı", "çekiçbaş"]),
    "Whale shark": ("deniz", ["whale shark", "balina köpekbalığı", "balina köpek balığı"]),
    "Megalodon": ("deniz", ["megalodon"]),
    "Shark": ("deniz", ["shark", "sharks", "köpekbalığı", "köpek balığı", "köpekbalıkları"]),
    "Blue whale": ("deniz", ["blue whale", "mavi balina"]),
    "Sperm whale": ("deniz", ["sperm whale", "kaşalot", "ispermeçet"]),
    "Humpback whale": ("deniz", ["humpback", "kambur balina"]),
    "Orca": ("deniz", ["orca", "orcas", "killer whale", "katil balina"]),
    "Whale": ("deniz", ["whale", "whales", "balina", "balinalar"]),
    "Dolphin": ("deniz", ["dolphin", "dolphins", "yunus", "yunuslar"]),
    "Narwhal": ("deniz", ["narwhal", "deniz gergedanı"]),
    "Octopus": ("deniz", ["octopus", "octopuses", "ahtapot"]),
    "Giant squid": ("deniz", ["giant squid", "colossal squid", "dev kalamar"]),
    "Squid": ("deniz", ["squid", "kalamar", "mürekkep balığı"]),
    "Cuttlefish": ("deniz", ["cuttlefish", "sübye"]),
    "Mantis shrimp": ("deniz", ["mantis shrimp", "peacock mantis", "mantis karidesi"]),
    "Pistol shrimp": ("deniz", ["pistol shrimp", "tabanca karidesi"]),
    "Box jellyfish": ("deniz", ["box jellyfish", "kutu denizanası"]),
    "Immortal jellyfish": ("deniz", ["immortal jellyfish", "ölümsüz denizanası"]),
    "Jellyfish": ("deniz", ["jellyfish", "denizanası", "deniz anası"]),
    "Anglerfish": ("deniz", ["anglerfish", "angler fish", "fener balığı"]),
    "Blobfish": ("deniz", ["blobfish", "blob fish"]),
    "Pufferfish": ("deniz", ["pufferfish", "puffer fish", "balon balığı"]),
    "Stonefish": ("deniz", ["stonefish", "taş balığı"]),
    "Moray eel": ("deniz", ["moray", "müren"]),
    "Electric eel": ("deniz", ["electric eel", "elektrikli yılan balığı"]),
    "Seahorse": ("deniz", ["seahorse", "seahorses", "denizatı", "deniz atı"]),
    "Sea otter": ("deniz", ["sea otter", "sea otters", "deniz samuru"]),
    "Sea turtle": ("deniz", ["sea turtle", "deniz kaplumbağası", "caretta"]),
    "Stingray": ("deniz", ["stingray", "manta ray", "manta", "vatoz", "rina"]),
    "Starfish": ("deniz", ["starfish", "sea star", "denizyıldızı", "deniz yıldızı"]),
    "Sea urchin": ("deniz", ["sea urchin", "deniz kestanesi"]),
    "Crab": ("deniz", ["crab", "crabs", "yengeç"]),
    "Lobster": ("deniz", ["lobster", "ıstakoz"]),
    "Seal": ("deniz", ["seal", "seals", "fok"]),
    "Walrus": ("deniz", ["walrus", "mors"]),
    "Penguin": ("deniz", ["penguin", "penguins", "penguen"]),
    "Barracuda": ("deniz", ["barracuda", "barakuda"]),
    "Swordfish": ("deniz", ["swordfish", "kılıç balığı"]),
    "Coelacanth": ("deniz", ["coelacanth", "selakant"]),
    "Isopod": ("deniz", ["giant isopod", "isopod"]),
    "Sea cucumber": ("deniz", ["sea cucumber", "deniz hıyarı"]),
    "Nudibranch": ("deniz", ["nudibranch", "deniz salyangozu"]),
    "Crocodile": ("kara", ["crocodile", "crocodiles", "alligator", "timsah"]),
    "Hippo": ("kara", ["hippo", "hippopotamus", "su aygırı", "hipopotam"]),
    "Elephant": ("kara", ["elephant", "elephants", "fil", "filler"]),
    "Lion": ("kara", ["lion", "lions", "aslan"]),
    "Tiger": ("kara", ["tiger", "tigers", "kaplan"]),
    "Cheetah": ("kara", ["cheetah", "çita"]),
    "Leopard": ("kara", ["leopard", "jaguar", "leopar", "pars"]),
    "Wolf": ("kara", ["wolf", "wolves", "kurt"]),
    "Bear": ("kara", ["bear", "grizzly", "polar bear", "ayı", "kutup ayısı"]),
    "Gorilla": ("kara", ["gorilla", "goril"]),
    "Chimpanzee": ("kara", ["chimpanzee", "chimp", "şempanze"]),
    "Giraffe": ("kara", ["giraffe", "zürafa"]),
    "Rhino": ("kara", ["rhino", "rhinoceros", "gergedan"]),
    "Zebra": ("kara", ["zebra"]),
    "Hyena": ("kara", ["hyena", "sırtlan"]),
    "Honey badger": ("kara", ["honey badger", "bal porsuğu"]),
    "Komodo dragon": ("kara", ["komodo", "komodo ejderi"]),
    "Snake": ("kara", ["snake", "snakes", "python", "cobra", "viper", "yılan", "kobra", "engerek", "piton"]),
    "Chameleon": ("kara", ["chameleon", "bukalemun"]),
    "Axolotl": ("kara", ["axolotl", "aksolotl"]),
    "Frog": ("kara", ["frog", "frogs", "poison dart", "kurbağa"]),
    "Tardigrade": ("kara", ["tardigrade", "water bear", "su ayısı"]),
    "Platypus": ("kara", ["platypus", "ornitorenk"]),
    "Kangaroo": ("kara", ["kangaroo", "kanguru"]),
    "Koala": ("kara", ["koala"]),
    "Sloth": ("kara", ["sloth", "tembel hayvan"]),
    "Pangolin": ("kara", ["pangolin"]),
    "Armadillo": ("kara", ["armadillo"]),
    "Bat": ("kara", ["bat", "bats", "yarasa"]),
    "Owl": ("kara", ["owl", "owls", "baykuş"]),
    "Eagle": ("kara", ["eagle", "kartal"]),
    "Crow": ("kara", ["crow", "crows", "raven", "karga"]),
    "Vulture": ("kara", ["vulture", "akbaba"]),
    "Ostrich": ("kara", ["ostrich", "devekuşu"]),
    "Spider": ("kara", ["spider", "tarantula", "örümcek"]),
    "Scorpion": ("kara", ["scorpion", "akrep"]),
    "Ant": ("kara", ["ant", "ants", "karınca"]),
    "Mosquito": ("kara", ["mosquito", "sivrisinek"]),
    "Bee": ("kara", ["bee", "bees", "hornet", "arı", "eşek arısı"]),
    "Mantis": ("kara", ["praying mantis", "peygamber devesi"]),
    "Camel": ("kara", ["camel", "deve"]),
    "Moose": ("kara", ["moose", "elk", "geyik"]),
    "Bison": ("kara", ["bison", "buffalo", "bizon", "manda"]),
    "Wood frog": ("kara", ["wood frog", "orman kurbağası"]),
}

# Kanca kalıpları: başlıkları sınıflamak için. Kalıp açıklamaları özgün şablonlardır,
# viral başlıklardan alınmamıştır.
KALIPLAR = {
    "soru": (r"\?|\b(why|how|what|which|who|neden|nasıl|niçin|hangi|kim)\b",
             "Soruyla açılış", "Bu hayvan neden ...? / Sence ... ne yapar?"),
    "rekor": (r"\b(most|world'?s|biggest|largest|deadliest|fastest|smallest|strongest|oldest|only|"
              r"dünyanın|en (büyük|hızlı|tehlikeli|zehirli|küçük|güçlü|yaşlı|ölümcül|tuhaf|garip))\b",
              "Rekor / 'dünyanın en ...'", "Dünyanın en ... hayvanı / Bunu yapabilen tek canlı"),
    "gizli": (r"\b(didn'?t know|never knew|nobody|no one|secret|hidden|truth|bilmiyordun|bilinmeyen|"
              r"kimse|gizli|sır|gerçek)\b",
              "Gizli bilgi / 'bunu bilmiyordun'", "Çoğu insan bunu bilmiyor: ..."),
    "tehlike": (r"\b(deadly|dangerous|terrifying|scary|horrifying|nightmare|attack|attacks|kill|kills|"
                r"venom|venomous|ölümcül|tehlikeli|korkunç|korkutucu|saldır\w*|öldür\w*|zehir\w*)\b",
                "Tehlike / korku", "Bu canlı tek dokunuşla ..."),
    "bu_hayvan": (r"\b(this (animal|creature|fish|shark)|meet the|bu (hayvan|canlı|balık))\b",
                  "'Bu hayvan...' ile gizemli tanıtım", "Bu hayvanın ... var."),
    "sayi": (r"\d", "Sayıyla somutluk", "3 kalp, 1 ton, 400 yıl gibi tek ve net bir sayı"),
    "sen": (r"\b(you|your|pov|sen|senin|seni)\b", "İzleyiciye doğrudan hitap",
            "Sen fark etmeden ... / Senin ... yapamayacağın şeyi ..."),
    "unlem": (r"!|\b[A-ZÇĞİÖŞÜ]{4,}\b", "Ünlem / büyük harf vurgusu", "Kısa ve tek kelimelik vurgu"),
}


class Kota:
    def __init__(self, sinir):
        self.sinir, self.harcanan = sinir, 0

    def harca(self, birim):
        if self.harcanan + birim > self.sinir:
            return False
        self.harcanan += birim
        return True


def _api(yol, parametreler, anahtar):
    import requests

    for deneme in range(1, 4):
        try:
            r = requests.get(f"{API}/{yol}", params={**parametreler, "key": anahtar}, timeout=30)
        except requests.RequestException as e:
            print(f"İstek hatası ({type(e).__name__}), deneme {deneme}", file=sys.stderr)
            time.sleep(3 * deneme)
            continue
        if r.status_code == 200:
            return r.json()
        try:
            neden = r.json()["error"]["errors"][0].get("reason", "")
        except (ValueError, KeyError, IndexError):
            neden = ""
        if neden in ("quotaExceeded", "dailyLimitExceeded", "rateLimitExceeded"):
            raise RuntimeError("YouTube API kotası doldu; yarın yeniden denenir")
        if r.status_code in (400, 403) and neden in ("keyInvalid", "forbidden", "accessNotConfigured", "badRequest"):
            raise RuntimeError(f"YOUTUBE_API_KEY reddedildi ({neden}); anahtarı ve "
                               "YouTube Data API v3'ün açık olduğunu kontrol edin")
        if r.status_code >= 500:
            time.sleep(3 * deneme)
            continue
        raise RuntimeError(f"YouTube API HTTP {r.status_code} ({neden or 'bilinmeyen'})")
    raise RuntimeError("YouTube API'ye ulaşılamadı")


def _sure_sn(iso):
    m = re.fullmatch(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso or "")
    if not m:
        return 10**6
    g, s, d, sn = (int(x or 0) for x in m.groups())
    return g * 86400 + s * 3600 + d * 60 + sn


def videolari_topla(anahtar, kota, simdi):
    baslangic = (simdi - timedelta(days=GUN)).strftime("%Y-%m-%dT%H:%M:%SZ")
    idler, kaynak = [], {}
    for dil, sorgu in ARAMALAR:
        if not kota.harca(ARAMA_BIRIM):
            print(f"Kota sınırı ({kota.sinir}) nedeniyle kalan aramalar atlandı")
            break
        veri = _api("search", {"part": "snippet", "q": sorgu, "type": "video",
                               "videoDuration": "short", "order": "viewCount",
                               "publishedAfter": baslangic, "maxResults": 50,
                               "relevanceLanguage": dil, "safeSearch": "strict"}, anahtar)
        for oge in veri.get("items", []):
            vid = (oge.get("id") or {}).get("videoId")
            if vid and vid not in kaynak:
                idler.append(vid)
                kaynak[vid] = dil
    videolar = []
    for i in range(0, len(idler), 50):
        if not kota.harca(VIDEO_BIRIM):
            break
        veri = _api("videos", {"part": "snippet,statistics,contentDetails",
                               "id": ",".join(idler[i:i + 50])}, anahtar)
        for v in veri.get("items", []):
            sn = v.get("snippet") or {}
            videolar.append({
                "id": v["id"],
                "baslik": sn.get("title", ""),
                "kanal": sn.get("channelTitle", ""),
                "tarih": (sn.get("publishedAt") or "")[:10],
                "izlenme": int((v.get("statistics") or {}).get("viewCount") or 0),
                "sure": _sure_sn((v.get("contentDetails") or {}).get("duration")),
                "dil": kaynak.get(v["id"], ""),
            })
    return videolar


def _kucuk(yazi):
    return yazi.replace("I", "ı").replace("İ", "i").lower()


# Türkçe ekler (köpekbalığının, yunuslar, ahtapotu...) için isteğe bağlı ek; ardından kelime sonu
_EK = r"(?:(?:l[ae]r)?(?:n[ıiuü]n|[ıiuü]n|s[ıiuü]n?|[ıiuü]|y?[ae]|d[ae]n?|t[ae]n?|n[ıiuü]))?(?!\w)"


def _desen(d):
    return re.compile(rf"(?<!\w){re.escape(d)}{_EK}")


_DESENLER = sorted(((ad, d) for ad, (_, adlar) in HAYVANLAR.items() for d in adlar),
                   key=lambda x: -len(x[1]))


def hayvan_bul(baslik):
    b = _kucuk(baslik)
    for ad, desen in _DESENLER:
        if _desen(desen).search(b):
            return ad
    return None


# Yalnızca İngilizce/Türkçe başlıklar: Latin dışı harf (Devanagari, Bengalce, Tamilce,
# Arapça, Kiril...) içeren başlıklar elenir. Emoji ve noktalama serbest.
LATIN_DISI = re.compile(r"[\u0370-\u03ff\u0400-\u052f\u0590-\u08ff\u0900-\u0dff"
                        r"\u0e00-\u0fff\u1000-\u109f\u1100-\u11ff\u3040-\u30ff"
                        r"\u3400-\u9fff\uac00-\ud7af]")
TAMIL_VB = re.compile(r"#(tamil|hindi|telugu|bangla|bengali|urdu|malayalam|kannada)\b", re.I)


def uygun_baslik(baslik):
    return not (LATIN_DISI.search(baslik) or TAMIL_VB.search(baslik) or DISLA.search(baslik))


def analiz(videolar):
    shorts = [v for v in videolar
              if v["sure"] <= EN_UZUN_SHORT and v["izlenme"] >= EN_AZ_IZLENME
              and uygun_baslik(v["baslik"])]
    for v in shorts:
        v["hayvan"] = hayvan_bul(v["baslik"])
    hayvanli = [v for v in shorts if v["hayvan"]]
    hayvanli.sort(key=lambda v: -v["izlenme"])

    puan = {}
    for v in hayvanli:
        p = puan.setdefault(v["hayvan"], {"izlenme": 0, "video": 0, "kanallar": set()})
        p["izlenme"] += v["izlenme"]
        p["video"] += 1
        p["kanallar"].add(v["kanal"])
    # Tek bir dev viral videonun tüm sıralamayı belirlememesi için puan, izlenmelerin
    # karekökleri toplamıdır (çok video + çok kanal = daha güçlü konu). En az 2 videosu
    # olan konular önce gelir; 5'e tamamlanamazsa tek videoluklar eklenir.
    for v in hayvanli:
        puan[v["hayvan"]].setdefault("puan", 0.0)
        puan[v["hayvan"]]["puan"] += math.sqrt(v["izlenme"])
    sirali = sorted(puan.items(), key=lambda x: (x[1]["video"] < 2, -x[1]["puan"]))
    # Aynı aileden (Shark / Great white shark gibi) yalnızca en güçlüsü alınır
    konular, aileler = [], set()
    for ad, p in sirali:
        aile = ad.split()[-1].lower()
        if aile in aileler:
            continue
        aileler.add(aile)
        konular.append({"hayvan": ad, "tur": HAYVANLAR[ad][0], "izlenme": p["izlenme"],
                        "video": p["video"], "kanal": len(p["kanallar"])})
        if len(konular) == KONU_SAYISI:
            break

    ortalama = sum(v["izlenme"] for v in hayvanli) / len(hayvanli) if hayvanli else 0
    kaliplar = []
    for anahtar_, (desen, ad, sablon) in KALIPLAR.items():
        uyan = [v for v in hayvanli if re.search(desen, v["baslik"], re.I if anahtar_ != "unlem" else 0)]
        if len(uyan) >= 3 and ortalama:
            ort = sum(v["izlenme"] for v in uyan) / len(uyan)
            kaliplar.append({"kalip": anahtar_, "ad": ad, "sablon": sablon,
                             "oran": round(len(uyan) / len(hayvanli), 2),
                             "kat": round(ort / ortalama, 2), "video": len(uyan)})
    kaliplar.sort(key=lambda k: -k["kat"])
    return shorts, hayvanli, konular, kaliplar


def konulari_ekle(konular, yol, tarih):
    """Konuları konular.txt'nin en üstüne (açıklamaların hemen altına) ekler."""
    satirlar = Path(yol).read_text(encoding="utf-8").splitlines()
    ilk_madde = next((i for i, s in enumerate(satirlar) if s.startswith("- [")), len(satirlar))
    ust, maddeler = satirlar[:ilk_madde], satirlar[ilk_madde:]
    eklenen, tasinan, atlanan, yeni = [], [], [], []
    for k in konular:
        ad = k["hayvan"]
        desenler = [_kucuk(d) for d in HAYVANLAR[ad][1]] + [_kucuk(ad)]

        def ilgili(s):
            return any(_desen(d).search(_kucuk(s)) for d in desenler)

        if any(s.startswith("- [x]") and ilgili(s) for s in maddeler):
            atlanan.append(ad)
            continue
        bekleyen = [s for s in maddeler if s.startswith("- [ ]") and ilgili(s)]
        if bekleyen:
            for s in bekleyen:
                maddeler.remove(s)
                yeni.append(s)
            tasinan.append(ad)
        else:
            yeni.append(f"- [ ] ({k['tur']}) {ad} (trend {tarih}; özgün bir şaşırtıcı bilgi seç)")
            eklenen.append(ad)
    Path(yol).write_text("\n".join(ust + yeni + maddeler) + "\n", encoding="utf-8")
    return eklenen, tasinan, atlanan


def _sayi(n):
    return f"{n / 1e6:.1f}M" if n >= 1e6 else f"{n / 1e3:.0f}B"


def ozet_md(veri):
    """Haftalık özet için "Bu hafta viral olanlar" bölümü."""
    md = ["### 🔥 Bu hafta viral olanlar", "",
          f"Son {GUN} günün hayvan Shorts'ları ({veri['tarih']} taraması, "
          f"{veri['incelenen']} Shorts, {veri['kota']} kota birimi)", ""]
    if not veri["konular"]:
        md.append("Bu taramada öne çıkan bir hayvan konusu bulunamadı.")
        return md
    md += ["**En güçlü 5 konu:**", ""]
    for i, k in enumerate(veri["konular"], 1):
        durum = {"eklendi": "konular.txt'ye eklendi", "tasindi": "listede vardı, en üste taşındı",
                 "kullanildi": "daha önce işlendi, eklenmedi"}.get(k.get("durum"), "")
        md.append(f"{i}. **{k['hayvan']}** ({k['tur']}) — {_sayi(k['izlenme'])} izlenme, "
                  f"{k['video']} video, {k['kanal']} kanal. {durum}")
    if veri["kaliplar"]:
        md += ["", "**Tutan kanca kalıpları** (ortalama izlenmeye göre):", ""]
        for k in veri["kaliplar"][:4]:
            md.append(f"- {k['ad']}: videoların %{int(k['oran'] * 100)}'i, ortalamanın "
                      f"{k['kat']:.1f} katı izlenme. Bizim şablon: _{k['sablon']}_")
    md += ["", "**En çok izlenen 5 Short** (yalnızca referans; başlıklar kopyalanmaz):", ""]
    for v in veri["en_cok"][:5]:
        md.append(f"- {_sayi(v['izlenme'])} — {v['baslik']} · {v['kanal']} · {v['tarih']}")
    return md


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--konular", default="konular.txt")
    ap.add_argument("--klasor", default="yayinlar/trendler")
    ap.add_argument("--kota", type=int, default=EN_FAZLA_BIRIM)
    a = ap.parse_args()

    anahtar = os.environ.get("YOUTUBE_API_KEY", "").strip()
    if not anahtar:
        print("::warning::YOUTUBE_API_KEY secret'ı yok; trend taraması atlandı.")
        return 0
    simdi = datetime.now(timezone.utc)
    tarih = simdi.strftime("%Y-%m-%d")
    kota = Kota(min(a.kota, EN_FAZLA_BIRIM))
    try:
        videolar = videolari_topla(anahtar, kota, simdi)
    except RuntimeError as e:
        print(f"::error::{e}")
        return 1
    shorts, hayvanli, konular, kaliplar = analiz(videolar)

    eklenen, tasinan, atlanan = konulari_ekle(konular, a.konular, tarih)
    for k in konular:
        k["durum"] = ("eklendi" if k["hayvan"] in eklenen else
                      "tasindi" if k["hayvan"] in tasinan else "kullanildi")

    veri = {"tarih": tarih, "kota": kota.harcanan, "toplanan": len(videolar),
            "incelenen": len(shorts), "hayvanli": len(hayvanli), "konular": konular,
            "kaliplar": kaliplar,
            "en_cok": [{k: v[k] for k in ("baslik", "kanal", "izlenme", "tarih", "hayvan", "dil")}
                       for v in hayvanli[:30]]}
    Path(a.klasor).mkdir(parents=True, exist_ok=True)
    Path(a.klasor, f"{tarih}.json").write_text(json.dumps(veri, ensure_ascii=False, indent=2) + "\n",
                                               encoding="utf-8")
    md = "\n".join(ozet_md(veri))
    print(md)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as f:
            f.write(md + "\n")
    print(f"\nKota: {kota.harcanan} birim; {len(videolar)} video, {len(shorts)} Shorts, "
          f"{len(hayvanli)} hayvan videosu. Eklendi: {eklenen}, taşındı: {tasinan}, atlandı: {atlanan}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
