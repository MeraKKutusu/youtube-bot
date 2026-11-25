#!/usr/bin/env python3
"""Buffer API (GraphQL, https://api.buffer.com) ile videoları YouTube ve TikTok'ta sıraya koyar.

Komutlar:
  sirala   : kalite kontrolünden geçen videoyu ertesi günün boş slotuna
             (gün bazlı saatler, bkz. GUN_SLOTLARI; Europe/Istanbul) iki kanala da planlar
  kanallar : bağlı Buffer kanallarını listeler (kurulum kontrolü için)

Ortam değişkenleri:
  BUFFER_API_KEY          (zorunlu, GitHub Secret)
  BUFFER_ORG_ID           (isteğe bağlı; yoksa hesaptaki ilk organizasyon)
  BUFFER_YOUTUBE_KANAL    (isteğe bağlı; birden çok YouTube kanalı varsa adı)
  BUFFER_TIKTOK_KANAL     (isteğe bağlı; birden çok TikTok kanalı varsa adı)
  AI_ETIKETI              ("true" varsayılan; YouTube ve TikTok'ta "AI ile üretildi" işareti)
  YOUTUBE_KATEGORI        ("15" varsayılan = Pets & Animals)

Medya olarak GitHub Release asset URL'si verilir. Buffer videoyu paylaşım anında
indirdiği için Release'ler paylaşımdan önce silinmemelidir.
"""
import argparse
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

API = "https://api.buffer.com"
SAAT_DILIMI = ZoneInfo("Europe/Istanbul")
# Gün bazlı paylaşım saatleri (İstanbul). Kaynak: Buffer 2026 (1,8 M YouTube, 7,1 M TikTok
# gönderisi: akşam 18-23 güçlü, Cuma 16-19 Shorts zirvesi, hafta sonu sabahı), PostEverywhere
# 2026 Shorts çalışması (Pzt 10-13, Paz 8-11, Cuma 16-19 güçlü; 18-21 kalabalık) ve Türkiye'de
# geç akşam telefon kullanımı. 2-3 hafta sonra kanalın kendi verisiyle gözden geçirilmeli.
# weekday(): 0=Pazartesi ... 6=Pazar
GUN_SLOTLARI = {
    0: ((12, 30), (21, 30)),
    1: ((12, 30), (21, 30)),
    2: ((12, 30), (21, 30)),
    3: ((12, 30), (21, 30)),
    4: ((17, 30), (21, 30)),   # Cuma: Shorts'un en güçlü öğleden sonrası
    5: ((11, 30), (21, 30)),   # Cumartesi: hafta sonu öğlesi
    6: ((10, 30), (21, 30)),   # Pazar: hafta sonu sabahı
}
SLOTLAR = GUN_SLOTLARI[0]  # geriye dönük uyumluluk
EN_AZ_ONCE = timedelta(hours=2)   # slot en az bu kadar ileride olmalı


class BufferHatasi(RuntimeError):
    pass


def _anahtar():
    a = os.environ.get("BUFFER_API_KEY", "").strip()
    if not a:
        raise BufferHatasi("BUFFER_API_KEY secret'ı eklenmemiş")
    return a


def gql(sorgu, degiskenler=None, deneme=4):
    import requests

    for i in range(1, deneme + 1):
        try:
            r = requests.post(API, json={"query": sorgu, "variables": degiskenler or {}},
                              headers={"Authorization": f"Bearer {_anahtar()}",
                                       "Content-Type": "application/json"}, timeout=60)
        except requests.RequestException as e:
            if i == deneme:
                raise BufferHatasi(f"Buffer'a bağlanılamadı: {type(e).__name__}")
            time.sleep(5 * i)
            continue
        if r.status_code in (401, 403):
            raise BufferHatasi(f"Buffer anahtarı reddedildi (HTTP {r.status_code}); "
                               "BUFFER_API_KEY secret'ını yenileyin")
        try:
            veri = r.json()
        except ValueError:
            veri = {}
        hatalar = veri.get("errors") or []
        bekle = None
        for h in hatalar:
            ek = h.get("extensions") or {}
            if ek.get("code") == "RATE_LIMIT_EXCEEDED":
                bekle = int(ek.get("retryAfter") or 60)
        if r.status_code == 429 or bekle:
            bekle = bekle or 60
            if bekle > 180 or i == deneme:
                raise BufferHatasi(f"Buffer istek sınırı aşıldı; {bekle} sn sonra yeniden deneyin")
            time.sleep(bekle)
            continue
        if r.status_code >= 500 and i < deneme:
            time.sleep(5 * i)
            continue
        if hatalar:
            raise BufferHatasi("; ".join(str(h.get("message")) for h in hatalar)[:800])
        if r.status_code >= 400:
            raise BufferHatasi(f"Buffer HTTP {r.status_code}")
        return veri.get("data") or {}
    raise BufferHatasi("Buffer isteği başarısız")


def organizasyon_id():
    if os.environ.get("BUFFER_ORG_ID", "").strip():
        return os.environ["BUFFER_ORG_ID"].strip()
    veri = gql("query { account { organizations { id name } } }")
    orglar = (veri.get("account") or {}).get("organizations") or []
    if not orglar:
        raise BufferHatasi("Buffer hesabında organizasyon bulunamadı")
    return orglar[0]["id"]


def kanallari_getir(org):
    veri = gql("""query K($org: OrganizationId!) {
      channels(input: { organizationId: $org }) {
        id name displayName service isDisconnected isLocked
      }
    }""", {"org": org})
    return veri.get("channels") or []


def kanal_sec(kanallar, servis, istenen_ad=""):
    adaylar = [k for k in kanallar if str(k.get("service")).lower() == servis
               and not k.get("isDisconnected") and not k.get("isLocked")]
    if istenen_ad:
        ad = istenen_ad.strip().lower()
        adaylar = [k for k in adaylar if ad in (str(k.get("name", "")).lower(),
                                                str(k.get("displayName", "")).lower())] or []
    if not adaylar:
        raise BufferHatasi(f"Buffer'da bağlı ve aktif bir {servis} kanalı bulunamadı")
    return adaylar[0]


# ---------------------------------------------------------------- kayıt ve slot

def kayitlari_oku(yol):
    kayitlar = []
    if Path(yol).is_file():
        for satir in Path(yol).read_text(encoding="utf-8").splitlines():
            satir = satir.strip()
            if satir:
                try:
                    kayitlar.append(json.loads(satir))
                except json.JSONDecodeError:
                    pass
    return kayitlar


def kayit_ekle(yol, kayit):
    Path(yol).parent.mkdir(parents=True, exist_ok=True)
    with open(yol, "a", encoding="utf-8") as f:
        f.write(json.dumps(kayit, ensure_ascii=False) + "\n")


def slot_sec(kayitlar, simdi=None):
    """Ertesi günden başlayarak o günün GUN_SLOTLARI saatlerinden ilk boş olanı (UTC) döndürür."""
    simdi = simdi or datetime.now(timezone.utc)
    dolu = {k.get("due_at") for k in kayitlar if k.get("durum") in ("planlandi", "kismi")}
    gunluk = {}   # yerel tarih -> o gün planlı gönderi sayısı (saatler değişse de günde en fazla 2)
    for iso in dolu:
        try:
            t = datetime.fromisoformat(str(iso).replace("Z", "+00:00")).astimezone(SAAT_DILIMI).date()
        except ValueError:
            continue
        gunluk[t] = gunluk.get(t, 0) + 1
    bugun = simdi.astimezone(SAAT_DILIMI).date()
    for gun in range(1, 31):
        tarih = bugun + timedelta(days=gun)
        if gunluk.get(tarih, 0) >= len(GUN_SLOTLARI[tarih.weekday()]):
            continue
        for saat, dakika in GUN_SLOTLARI[tarih.weekday()]:
            yerel = datetime(tarih.year, tarih.month, tarih.day, saat, dakika, tzinfo=SAAT_DILIMI)
            utc = yerel.astimezone(timezone.utc)
            iso = utc.strftime("%Y-%m-%dT%H:%M:%S.000Z")
            if iso not in dolu and utc - simdi >= EN_AZ_ONCE:
                return iso, yerel
    raise BufferHatasi("30 gün içinde boş slot bulunamadı")


def url_kontrol(url, deneme=6):
    import requests

    for i in range(1, deneme + 1):
        try:
            r = requests.head(url, allow_redirects=True, timeout=30)
            if r.status_code == 200:
                return
        except requests.RequestException:
            pass
        time.sleep(5 * i)
    raise BufferHatasi(f"video adresine erişilemiyor: {url}")


# ---------------------------------------------------------------- gönderi

GONDERI = """mutation G($input: CreatePostInput!) {
  createPost(input: $input) {
    __typename
    ... on PostActionSuccess { post { id dueAt } }
    ... on MutationError { message }
  }
}"""


def gonderi_olustur(girdi):
    try:
        veri = gql(GONDERI, {"input": girdi})
    except BufferHatasi as e:
        # Şema bu alanı tanımıyorsa onsuz bir kez daha dene
        if "aiAssisted" in str(e) and "aiAssisted" in girdi:
            girdi = {k: v for k, v in girdi.items() if k != "aiAssisted"}
            veri = gql(GONDERI, {"input": girdi})
        else:
            raise
    sonuc = veri.get("createPost") or {}
    if sonuc.get("post"):
        return sonuc["post"]["id"]
    raise BufferHatasi(sonuc.get("message") or f"beklenmeyen yanıt: {sonuc}")


def _dogru_mu(deger, varsayilan=True):
    if deger is None or str(deger).strip() == "":
        return varsayilan
    return str(deger).strip().lower() in ("1", "true", "evet", "yes", "on")


def sirala(args):
    meta = json.loads(Path(args.meta).read_text(encoding="utf-8"))
    kayitlar = kayitlari_oku(args.kayit)
    for k in kayitlar:
        if k.get("senaryo") == meta["senaryo"] and k.get("durum") == "planlandi":
            print(f"{meta['senaryo']} zaten planlanmış ({k.get('saat_ist')}); atlanıyor")
            return 0

    ai = _dogru_mu(os.environ.get("AI_ETIKETI"), True)
    kategori = os.environ.get("YOUTUBE_KATEGORI", "").strip() or "15"
    # Daha önce yalnızca bir kanala gidebilmişse (kismi): aynı saate yalnızca eksik kanalı ekle
    onceki = next((k for k in reversed(kayitlar)
                   if k.get("senaryo") == meta["senaryo"] and k.get("durum") == "kismi"
                   and k.get("due_at")), None)
    if onceki:
        due_at = onceki["due_at"]
        yerel = datetime.fromisoformat(due_at.replace("Z", "+00:00")).astimezone(SAAT_DILIMI)
        print(f"Kısmi kayıt bulundu; eksik kanal aynı saate ekleniyor: {yerel:%Y-%m-%d %H:%M}")
    else:
        due_at, yerel = slot_sec(kayitlar)
    print(f"Slot: {yerel:%Y-%m-%d %H:%M} (İstanbul) = {due_at}")

    url_kontrol(args.video_url)
    org = organizasyon_id()
    kanallar = kanallari_getir(org)

    ortak = {"schedulingType": "automatic", "mode": "customScheduled", "dueAt": due_at,
             "aiAssisted": True, "assets": [{"video": {"url": args.video_url}}]}
    hedefler = {
        "youtube": (os.environ.get("BUFFER_YOUTUBE_KANAL", ""), {
            "text": meta["youtube_aciklama"],
            "metadata": {"youtube": {
                "title": meta["youtube_baslik"][:100], "categoryId": kategori,
                "privacy": "public", "madeForKids": False, "notifySubscribers": True,
                "isAiGenerated": ai}}}),
        "tiktok": (os.environ.get("BUFFER_TIKTOK_KANAL", ""), {
            "text": meta["tiktok_metin"],
            "metadata": {"tiktok": {"isAiGenerated": ai}}}),
    }

    sonuc, hatalar = {}, []
    if onceki:
        for servis in list(hedefler):
            if "id" in (onceki.get(servis) or {}):
                sonuc[servis] = onceki[servis]          # zaten planlı; tekrar gönderme
                del hedefler[servis]
    for servis, (ad, ek) in hedefler.items():
        try:
            kanal = kanal_sec(kanallar, servis, ad)
            post_id = gonderi_olustur({**ortak, **ek, "channelId": kanal["id"]})
            sonuc[servis] = {"id": post_id, "kanal": kanal.get("name")}
            print(f"✓ {servis}: {kanal.get('name')} -> {post_id}")
        except BufferHatasi as e:
            sonuc[servis] = {"hata": str(e)}
            hatalar.append(f"{servis}: {e}")
            print(f"✗ {servis}: {e}", file=sys.stderr)

    basarili = sum(1 for v in sonuc.values() if "id" in v)
    durum = "planlandi" if not hatalar else ("kismi" if basarili else "hata")
    kayit_ekle(args.kayit, {
        "zaman": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "senaryo": meta["senaryo"], "seri_no": meta.get("seri_no"), "konu": meta.get("konu"),
        "release": args.release_url, "video_url": args.video_url,
        "due_at": due_at if durum != "hata" else None, "saat_ist": f"{yerel:%Y-%m-%d %H:%M}",
        "durum": durum, **sonuc,
    })

    md = [f"### Buffer: {'✅ planlandı' if not hatalar else '⚠️ sorun var'}", "",
          f"**{meta.get('release_adi')}** → {yerel:%d.%m.%Y %H:%M} (İstanbul)", ""]
    for servis, s in sonuc.items():
        md.append(f"- {servis}: " + (f"✅ {s.get('kanal')}" if "id" in s else f"❌ {s['hata']}"))
    md += ["", f"📌 Sabit yorum: {meta.get('sabit_yorum', '')}"]
    Path(args.rapor).write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n".join(md))
    return 0 if not hatalar else 2


def sil_komutu(args):
    """Planlı Buffer gönderilerini siler (uygulamada silinemeyenler için)."""
    hata = 0
    for pid in [x.strip() for x in args.id.split(",") if x.strip()]:
        try:
            veri = gql("""mutation S($input: DeletePostInput!) {
              deletePost(input: $input) { __typename ... on MutationError { message } }
            }""", {"input": {"id": pid}})
            print(f"✓ {pid}: {veri.get('deletePost')}")
        except BufferHatasi as e:
            hata = 2
            print(f"✗ {pid}: {e}", file=sys.stderr)
    if hata:
        # Şema farklıysa mevcut mutation adlarını göster
        try:
            sema = gql('query { __schema { mutationType { fields { name args { name type { name kind ofType { name } } } } } } }')
            for f in sema["__schema"]["mutationType"]["fields"]:
                if "post" in f["name"].lower() or "delete" in f["name"].lower():
                    print("mutation:", f["name"], [(a["name"], a["type"].get("name") or (a["type"].get("ofType") or {}).get("name")) for a in f["args"]])
        except Exception as e:  # noqa: BLE001
            print(f"şema okunamadı: {e}", file=sys.stderr)
    return hata


def kanallar_komutu(_args):
    org = organizasyon_id()
    print(f"Organizasyon: {org}")
    for k in kanallari_getir(org):
        durum = "bağlantı kopuk" if k.get("isDisconnected") else ("kilitli" if k.get("isLocked") else "aktif")
        print(f"- {k.get('service')}: {k.get('name')} ({durum})")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    alt = ap.add_subparsers(dest="komut", required=True)
    s = alt.add_parser("sirala")
    s.add_argument("--meta", default="cikti/meta.json")
    s.add_argument("--video-url", required=True)
    s.add_argument("--release-url", default="")
    s.add_argument("--kayit", default="yayinlar/kayit.jsonl")
    s.add_argument("--rapor", default="cikti/buffer.md")
    alt.add_parser("kanallar")
    sl = alt.add_parser("sil")
    sl.add_argument("--id", required=True, help="Buffer gönderi id'leri, virgülle")
    args = ap.parse_args()
    if args.komut == "sil":
        try:
            return sil_komutu(args)
        except BufferHatasi as e:
            print(f"HATA: {e}", file=sys.stderr)
            return 2
    try:
        return sirala(args) if args.komut == "sirala" else kanallar_komutu(args)
    except BufferHatasi as e:
        print(f"HATA: {e}", file=sys.stderr)
        if args.komut == "sirala":
            Path(args.rapor).write_text(f"### Buffer: ❌ gönderilemedi\n\n{e}\n", encoding="utf-8")
        return 2


if __name__ == "__main__":
    sys.exit(main())
