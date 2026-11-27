#!/usr/bin/env python3
"""Üretilen videonun kalite kontrolü.

Kontroller:
  1. Süre 24-45 sn
  2. Ses: ses akışı var, ortalama seviye -14 LUFS civarı (-16..-12), tepe ≤ -1 dBTP,
     2 sn'den uzun sessizlik yok
  3. Siyah kare: 0.5 sn'den uzun tamamen siyah bölüm yok
  4. Altyazı: altyazı dosyasında her cümle için satır var ve videoya gerçekten basılmış
     (altyazı anlarındaki karelerde alt üçte birde beyaz yazı + siyah kenarlık görünüyor)

Kullanım: python scripts/kalite.py --klasor cikti
Sonuç cikti/kalite.json ve cikti/kalite.md'ye yazılır. Çıkış kodu her zaman 0'dır;
GitHub Actions'ta `gecti=true|false` çıktısı verilir.
"""
import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ses import loudnorm_olc  # noqa: E402

SURE = (24.0, 45.0)
LUFS = (-16.0, -12.0)
EN_YUKSEK_TP = -1.0
EN_UZUN_SESSIZLIK = 2.0
EN_UZUN_SIYAH = 0.5
GENISLIK, YUKSEKLIK = 1080, 1920
# Altyazı bandı (uret.py: alt kenar y=1440 (%75), soldan 86 px, en fazla iki satır)
ALTYAZI_BANDI = (86, 1195, 854, 250)   # x, y, genişlik, yükseklik


def _ffprobe(yol, *arg):
    s = subprocess.run(["ffprobe", "-v", "error", *arg, str(yol)], capture_output=True, text=True)
    return s.stdout.strip()


def _ffmpeg_stderr(*arg):
    return subprocess.run(["ffmpeg", "-hide_banner", "-nostats", *arg],
                          capture_output=True, text=True).stderr


def sure_kontrol(video):
    try:
        sure = float(_ffprobe(video, "-show_entries", "format=duration", "-of", "default=nw=1:nk=1"))
    except ValueError:
        return False, "süre okunamadı", 0.0
    return SURE[0] <= sure <= SURE[1], f"{sure:.1f} sn (beklenen {SURE[0]:.0f}-{SURE[1]:.0f})", sure


def ses_kontrol(video):
    if not _ffprobe(video, "-select_streams", "a", "-show_entries", "stream=index", "-of", "csv=p=0"):
        return False, "videoda ses yok"
    try:
        olcum = loudnorm_olc(video)
    except Exception as e:  # noqa: BLE001
        return False, f"ses ölçülemedi: {e}"
    i, tp = float(olcum["input_i"]), float(olcum["input_tp"])
    sorunlar = []
    if not LUFS[0] <= i <= LUFS[1]:
        sorunlar.append(f"seviye {i:.1f} LUFS (beklenen {LUFS[0]:.0f}..{LUFS[1]:.0f})")
    if tp > EN_YUKSEK_TP:
        sorunlar.append(f"tepe {tp:.1f} dBTP (en fazla {EN_YUKSEK_TP})")
    log = _ffmpeg_stderr("-i", str(video), "-af", f"silencedetect=n=-50dB:d={EN_UZUN_SESSIZLIK}",
                         "-f", "null", "-")
    sessiz = re.findall(r"silence_duration: ([\d.]+)", log)
    if sessiz:
        sorunlar.append(f"{len(sessiz)} uzun sessizlik (en uzunu {max(map(float, sessiz)):.1f} sn)")
    ozet = f"{i:.1f} LUFS, tepe {tp:.1f} dBTP"
    return (not sorunlar), (ozet + ("; " + "; ".join(sorunlar) if sorunlar else ""))


def siyah_kontrol(video):
    log = _ffmpeg_stderr("-i", str(video), "-vf",
                         f"blackdetect=d={EN_UZUN_SIYAH}:pic_th=0.98:pix_th=0.06", "-an", "-f", "null", "-")
    araliklar = re.findall(r"black_start:([\d.]+) black_end:([\d.]+)", log)
    if araliklar:
        metin = ", ".join(f"{float(a):.1f}-{float(b):.1f} sn" for a, b in araliklar[:5])
        return False, f"siyah bölüm var: {metin}"
    return True, "siyah bölüm yok"


def _ass_satirlari(ass):
    satirlar = []
    for satir in Path(ass).read_text(encoding="utf-8").splitlines():
        m = re.match(r"Dialogue: \d+,(\d+):(\d+):([\d.]+),(\d+):(\d+):([\d.]+),Ana,", satir)
        if m:
            a = int(m[1]) * 3600 + int(m[2]) * 60 + float(m[3])
            b = int(m[4]) * 3600 + int(m[5]) * 60 + float(m[6])
            satirlar.append((a, b))
    return satirlar


def _kare_yazi_var_mi(video, an):
    x, y, w, h = ALTYAZI_BANDI
    veri = subprocess.run(["ffmpeg", "-loglevel", "error", "-ss", f"{an:.2f}", "-i", str(video),
                           "-frames:v", "1", "-vf", f"crop={w}:{h}:{x}:{y},format=gray",
                           "-f", "rawvideo", "-"], capture_output=True).stdout
    if not veri:
        return False
    beyaz = sum(1 for p in veri if p > 235) / len(veri)
    siyah = sum(1 for p in veri if p < 25) / len(veri)
    return beyaz > 0.004 and siyah > 0.004


def altyazi_kontrol(video, ass, cumle_sayisi, ses_suresi):
    if not Path(ass).is_file():
        return False, "altyazı dosyası yok"
    satirlar = _ass_satirlari(ass)
    if not satirlar:
        return False, "altyazı satırı yok"
    if cumle_sayisi and len(satirlar) < cumle_sayisi:
        return False, f"{len(satirlar)} altyazı satırı, {cumle_sayisi} cümle var"
    kapsam = sum(b - a for a, b in satirlar)
    if ses_suresi and kapsam < 0.6 * ses_suresi:
        return False, f"altyazı konuşmanın yalnızca %{100 * kapsam / ses_suresi:.0f}'ini kapsıyor"
    ornekler = [satirlar[len(satirlar) * k // 4] for k in (0, 1, 2, 3)]
    gorunen = sum(_kare_yazi_var_mi(video, (a + b) / 2) for a, b in ornekler)
    if gorunen < 3:
        return False, f"altyazı videoda görünmüyor ({gorunen}/4 örnek karede bulundu)"
    return True, f"{len(satirlar)} satır, konuşmanın %{min(100, 100 * kapsam / max(ses_suresi, 0.1)):.0f}'i, {gorunen}/4 karede görünüyor"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--klasor", default="cikti")
    k = Path(ap.parse_args().klasor)
    video = k / "video.mp4"
    meta = json.loads((k / "meta.json").read_text(encoding="utf-8")) if (k / "meta.json").is_file() else {}

    sonuclar = []
    if not video.is_file():
        sonuclar.append(("Video", False, "video.mp4 yok"))
    else:
        ok, metin, _ = sure_kontrol(video)
        sonuclar.append(("Süre", ok, metin))
        sonuclar.append(("Ses", *ses_kontrol(video)))
        sonuclar.append(("Siyah kare", *siyah_kontrol(video)))
        sonuclar.append(("Altyazı", *altyazi_kontrol(video, k / "altyazi.ass",
                                                      meta.get("cumle_sayisi", 0),
                                                      meta.get("ses_suresi", 0))))
    if meta.get("goruntu_kaynagi_var"):
        iyi, toplam = meta.get("gercek_goruntu", 0), meta.get("bolum_sayisi", 0)
        # Hayvanın gerçek görüntüsü hiç yoksa ya da tek görüntü her şeyi taşıyorsa paylaşma
        ok = iyi >= min(2, toplam)
        sonuclar.append(("Görüntü", ok, f"{iyi}/{toplam} bölümde hayvanın kendi görüntüsü"
                         + ("" if ok else "; renkli arka planla paylaşılmaz")))
    gecti = all(ok for _, ok, _ in sonuclar)
    rapor = {"gecti": gecti, "kontroller": [{"ad": a, "gecti": ok, "detay": d} for a, ok, d in sonuclar]}
    (k / "kalite.json").write_text(json.dumps(rapor, ensure_ascii=False, indent=2), encoding="utf-8")

    md = [f"### Kalite kontrolü: {'✅ geçti' if gecti else '❌ geçmedi'}", "",
          "| Kontrol | Sonuç | Detay |", "|---|---|---|"]
    md += [f"| {a} | {'✅' if ok else '❌'} | {d} |" for a, ok, d in sonuclar]
    (k / "kalite.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n".join(md))

    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as f:
            f.write(f"gecti={'true' if gecti else 'false'}\n")
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as f:
            f.write("\n".join(md) + "\n")


if __name__ == "__main__":
    main()
