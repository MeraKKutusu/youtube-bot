#!/usr/bin/env python3
"""Haftalık özet: son 7 günün paylaşımları, hatalar ve (varsa) Buffer istatistikleri.

Kullanım: python scripts/ozet.py --cikti ozet.md
GitHub CLI (gh) ile kalite/buffer Issue'larını ve başarısız workflow çalışmalarını okur.
Buffer istatistik vermezse (ör. ücretsiz plan) bu bölüm atlanır.
"""
import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import buffer  # noqa: E402
import trend  # noqa: E402

GORUNTULENME = ("view", "play", "izlen")
ERISIM = ("impression", "reach", "erişim")


def _gh_json(*arg):
    s = subprocess.run(["gh", *arg], capture_output=True, text=True)
    if s.returncode != 0:
        return None
    try:
        return json.loads(s.stdout or "[]")
    except json.JSONDecodeError:
        return None


def _tarih(yazi):
    try:
        return datetime.fromisoformat(str(yazi).replace("Z", "+00:00"))
    except ValueError:
        return None


def _puan(metrikler):
    """Videonun karşılaştırma puanı: görüntülenme, yoksa erişim, yoksa tüm metriklerin toplamı."""
    for anahtarlar in (GORUNTULENME, ERISIM):
        degerler = [m["value"] for m in metrikler
                    if any(a in str(m.get("name", "")).lower() for a in anahtarlar)]
        if degerler:
            return sum(degerler), anahtarlar[0]
    return sum(m.get("value", 0) for m in metrikler), "toplam etkileşim"


def buffer_metrikleri(post_idleri):
    """{post_id: [metrik]} döndürür; alınamazsa (None, sebep)."""
    if not os.environ.get("BUFFER_API_KEY", "").strip():
        return None, "BUFFER_API_KEY yok"
    try:
        org = buffer.organizasyon_id()
        kanal_idleri = [k["id"] for k in buffer.kanallari_getir(org)
                        if str(k.get("service")).lower() in ("youtube", "tiktok")]
        veri = buffer.gql("""query P($org: OrganizationId!, $kanallar: [ChannelId!]) {
          posts(first: 100, input: { organizationId: $org, filter: { channelIds: $kanallar } }) {
            edges { node { id status metrics { name value } } }
          }
        }""", {"org": org, "kanallar": kanal_idleri})
    except buffer.BufferHatasi as e:
        return None, str(e)
    sonuc = {}
    for kenar in ((veri.get("posts") or {}).get("edges") or []):
        dugum = kenar.get("node") or {}
        if dugum.get("id") in post_idleri and dugum.get("metrics"):
            sonuc[dugum["id"]] = dugum["metrics"]
    if not sonuc:
        return None, "Buffer bu gönderiler için istatistik vermedi (ücretsiz planda olabilir)"
    return sonuc, ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kayit", default="yayinlar/kayit.jsonl")
    ap.add_argument("--cikti", default="ozet.md")
    ap.add_argument("--gun", type=int, default=7)
    ap.add_argument("--trendler", default="yayinlar/trendler")
    a = ap.parse_args()

    simdi = datetime.now(timezone.utc)
    bas = simdi - timedelta(days=a.gun)
    bas_tarih = bas.strftime("%Y-%m-%d")
    kayitlar = [k for k in buffer.kayitlari_oku(a.kayit)
                if (_tarih(k.get("zaman")) or simdi) >= bas]

    md = [f"## Haftalık özet ({bas:%d.%m} – {simdi:%d.%m.%Y})", ""]

    planli = [k for k in kayitlar if k.get("durum") in ("planlandi", "kismi")]
    md += [f"### 📅 Paylaşımlar ({len(planli)} video)", ""]
    if planli:
        md += ["| # | Konu | Yayın (İstanbul) | YouTube | TikTok |", "|---|---|---|---|---|"]
        for k in sorted(planli, key=lambda x: x.get("due_at") or ""):
            yt = "✅" if "id" in (k.get("youtube") or {}) else "❌"
            tt = "✅" if "id" in (k.get("tiktok") or {}) else "❌"
            md.append(f"| {k.get('seri_no')} | [{k.get('konu')}]({k.get('release')}) | "
                      f"{k.get('saat_ist')} | {yt} | {tt} |")
    else:
        md.append("Bu hafta Buffer'a gönderilen video yok.")
    md.append("")

    md += ["### ⚠️ Hatalar", ""]
    hata_sayisi = 0
    for k in kayitlar:
        for servis in ("youtube", "tiktok"):
            h = (k.get(servis) or {}).get("hata")
            if h:
                hata_sayisi += 1
                md.append(f"- Buffer {servis} — {k.get('konu')}: {h}")
    for etiket in ("kalite", "buffer"):
        issues = _gh_json("issue", "list", "--label", etiket, "--state", "all", "--limit", "50",
                          "--search", f"created:>={bas_tarih}", "--json", "number,title,url,state")
        for i in issues or []:
            hata_sayisi += 1
            md.append(f"- [{i['title']}]({i['url']}) ({'açık' if i['state'] == 'OPEN' else 'kapalı'})")
    calismalar = _gh_json("run", "list", "--workflow", "shorts-uret.yml", "--status", "failure",
                          "--created", f">={bas_tarih}", "--limit", "50",
                          "--json", "displayTitle,url,createdAt")
    for c in calismalar or []:
        hata_sayisi += 1
        md.append(f"- Başarısız çalışma: [{c['displayTitle']}]({c['url']})")
    if not hata_sayisi:
        md.append("Hata yok 🎉")
    md.append("")

    md += ["### 📊 En iyi ve en kötü videolar", ""]
    idler = {s["id"]: k for k in planli for s in (k.get("youtube") or {}, k.get("tiktok") or {})
             if "id" in s}
    metrikler, sebep = buffer_metrikleri(set(idler)) if idler else (None, "planlanmış video yok")
    if metrikler:
        puanlar, tur = {}, ""
        for k in planli:
            toplam, var = 0, False
            for servis in ("youtube", "tiktok"):
                pid = (k.get(servis) or {}).get("id")
                if pid in metrikler:
                    p, tur = _puan(metrikler[pid])
                    toplam += p
                    var = True
            if var:
                puanlar[k.get("senaryo")] = (toplam, k)
        sirali = sorted(puanlar.items(), key=lambda x: x[1][0], reverse=True)
        if sirali:
            md.append(f"Ölçüt: {tur} (YouTube + TikTok)")
            md.append("")
            md.append("**En iyi 2:**")
            md += [f"- #{k.get('seri_no')} {k.get('konu')}: {int(p)}" for _, (p, k) in sirali[:2]]
            md.append("")
            md.append("**En kötü 2:**")
            md += [f"- #{k.get('seri_no')} {k.get('konu')}: {int(p)}" for _, (p, k) in sirali[-2:][::-1]]
        else:
            md.append("İstatistik henüz yok (yeni paylaşımlarda veriler ~24 saat gecikir).")
    else:
        md.append(f"İstatistik alınamadı: {sebep}. YouTube Studio ve TikTok Studio'dan bakabilirsin.")
    md.append("")

    # Trend avcısı (pazartesi taraması)
    trend_dosyalari = sorted(Path(a.trendler).glob("*.json"))
    if trend_dosyalari:
        son = json.loads(trend_dosyalari[-1].read_text(encoding="utf-8"))
        if (_tarih(son.get("tarih", "") + "T00:00:00Z") or bas) >= bas - timedelta(days=1):
            md += trend.ozet_md(son) + [""]
        else:
            md += ["### 🔥 Bu hafta viral olanlar", "", "Bu hafta trend taraması yapılmadı "
                   "(YOUTUBE_API_KEY eksik olabilir).", ""]
    else:
        md += ["### 🔥 Bu hafta viral olanlar", "", "Henüz trend taraması yok.", ""]

    Path(a.cikti).write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n".join(md))
    return 0


if __name__ == "__main__":
    sys.exit(main())
