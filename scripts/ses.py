#!/usr/bin/env python3
"""Ses tasarımı: mood'a göre arka plan müziği, efektler, ducking ve -14 LUFS.

Her şey ffmpeg ile sentezlenir; telifli ses kullanılmaz. `assets/muzik/<mood>.mp3`
(ya da .wav/.m4a/.ogg) dosyası varsa sentez yerine o döngüyle çalınır.

  Müzik     : mood'a göre (tense / mysterious / fun / epic), konuşma sırasında
              sidechain kompresörle otomatik kısılır
  Vurgu     : videonun başında (kancada) derin bir "boom"
  Whoosh    : her sahne geçişinde
  Uğultu    : tense/mysterious mood'da tüm video boyunca, diğerlerinde
              "gerilim": true işaretli bölümlerde alçak uğultu
  Yükselen  : kapanış bölümünde yükselen ses (riser)
  Seviye    : iki geçişli loudnorm ile yaklaşık -14 LUFS, en fazla -1.5 dBTP

Deneme:
  python scripts/ses.py --konusma ses.mp3 --mood tense --sure 35 \
      --gecis 5.2 --gecis 12.8 --kapanis 30 --cikti mix.wav
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

MOODLAR = ("tense", "mysterious", "fun", "epic")
ORNEKLEME = 44100
SENTEZ_ORNEKLEME = 22050   # müzik sentezi daha hızlı olsun diye
HEDEF_LUFS = -14.0
HEDEF_TP = -1.5
MUZIK_UZANTILARI = (".mp3", ".wav", ".m4a", ".ogg")

# Seviyeler (müzik önce -20 LUFS'a getirilir, sonra bu çarpanla karışır)
SEVIYE = {"muzik": 0.55, "vurgu": 0.8, "whoosh": 0.45, "ugultu": 0.5, "yukselen": 0.4}


class SesHatasi(RuntimeError):
    pass


def _calistir(komut):
    s = subprocess.run(komut, capture_output=True, text=True)
    if s.returncode != 0:
        print(s.stderr[-3000:], file=sys.stderr)
        raise SesHatasi(f"ffmpeg başarısız oldu ({komut[-1]})")
    return s


def _aeval(ifade, sure, hedef, filtre="", orneklem=ORNEKLEME):
    """aevalsrc ifadesini sure saniyelik mono wav olarak üretir."""
    kaynak = f"aevalsrc=exprs='{ifade}':s={orneklem}:d={sure:.3f}"
    komut = ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", kaynak]
    zincir = ",".join(x for x in (filtre, f"aresample={ORNEKLEME}") if x)
    komut += ["-af", zincir, "-ac", "1", str(hedef)]
    _calistir(komut)
    return hedef


# ---------------------------------------------------------------- müzik

def _sin(f, faz="t"):
    return f"sin(2*PI*{f}*{faz})"


def _zengin(f, faz="t"):
    """Biraz armonikli ton (düz sinüsten daha dolgun)."""
    return f"({_sin(f, faz)}+0.4*{_sin(2 * f, faz)}+0.15*{_sin(3 * f, faz)})"


def _akor_dizisi(akorlar, bar, zengin=True, ust=0.6):
    """Her akor bar saniye çalar; akor sınırlarında genlik sıfıra iner (tık olmaz)."""
    n = len(akorlar)
    terimler = []
    for i, akor in enumerate(akorlar):
        tonlar = "+".join((_zengin(f) if zengin else _sin(f)) for f in akor)
        terimler.append(f"eq(mod(floor(t/{bar}),{n}),{i})*({tonlar})/{len(akor)}")
    zarf = f"pow(sin(PI*mod(t,{bar})/{bar}),{ust})"
    return f"({'+'.join(terimler)})*{zarf}"


def _vurus(periyot, kayma=0.0, frek=45, egim=30, sonum=8, guc=1.0):
    """Davul benzeri alçak vuruş: her periyotta bir, frekansı hızla düşen sinüs."""
    u = f"mod(t-{kayma},{periyot})" if kayma else f"mod(t,{periyot})"
    kosul = f"gte(t,{kayma})*" if kayma else ""
    return (f"{kosul}{guc}*sin(2*PI*({frek}+{frek * 1.6}*exp(-{u}*{egim}))*{u})"
            f"*exp(-{u}*{sonum})")


def _secimli_frekans(adim, notalar_listesi, grup):
    """adim: o anki nota indeksi ifadesi; notalar_listesi: akor başına nota listesi."""
    terimler = []
    for ai, notalar in enumerate(notalar_listesi):
        for ni, f in enumerate(notalar):
            terimler.append(
                f"eq(mod(floor({adim}/{grup}),{len(notalar_listesi)}),{ai})"
                f"*eq(mod({adim},{len(notalar)}),{ni})*{f}")
    return "(" + "+".join(terimler) + ")"


def muzik_ifadesi(mood):
    """(aevalsrc ifadesi, ek filtre) döndürür."""
    if mood == "tense":
        drone = (f"({_zengin(55)}+0.8*{_sin(82.41)}+0.5*{_sin(110)}+0.35*{_sin(116.54)})"
                 f"*(0.75+0.25*sin(2*PI*0.4*t))*0.35")
        kalp = (_vurus(0.8, frek=40, egim=30, sonum=10, guc=0.9) + "+"
                + _vurus(0.8, kayma=0.22, frek=40, egim=30, sonum=10, guc=0.6))
        ince = f"0.04*{_sin(880)}*(0.5+0.5*sin(2*PI*5*t))"
        return f"{drone}+{kalp}+{ince}", "lowpass=f=1800,aecho=0.8:0.6:80|160:0.25|0.15"

    if mood == "mysterious":
        ped = _akor_dizisi([(110, 130.81, 164.81), (87.31, 130.81, 174.61),
                            (73.42, 110, 174.61), (82.41, 123.47, 164.81)], 4, ust=0.5)
        u = "mod(t,2)"
        can_f = "(eq(mod(floor(t/2),4),0)*1318.5+eq(mod(floor(t/2),4),1)*1046.5" \
                "+eq(mod(floor(t/2),4),2)*1174.7+eq(mod(floor(t/2),4),3)*987.77)"
        can = f"0.22*sin(2*PI*{can_f}*{u})*exp(-{u}*2.5)"
        return f"0.8*{ped}+{can}", "lowpass=f=2600,aecho=0.8:0.7:120|240:0.35|0.25"

    if mood == "fun":
        adim_s = 0.2
        akorlar = [(523.25, 659.25, 783.99, 1046.5), (523.25, 698.46, 880, 1046.5),
                   (493.88, 587.33, 783.99, 987.77), (523.25, 659.25, 783.99, 1046.5)]
        adim = f"floor(t/{adim_s})"
        frek = _secimli_frekans(adim, akorlar, 8)
        u = f"mod(t,{adim_s})"
        pluck = f"0.45*(sin(2*PI*{frek}*{u})+0.3*sin(4*PI*{frek}*{u}))*exp(-{u}*16)*(1-exp(-{u}*300))"
        kokler = "(eq(mod(floor(t/1.6),4),0)*130.81+eq(mod(floor(t/1.6),4),1)*174.61" \
                 "+eq(mod(floor(t/1.6),4),2)*196+eq(mod(floor(t/1.6),4),3)*130.81)"
        ub = "mod(t,0.4)"
        bas = f"0.5*sin(2*PI*{kokler}*{ub})*exp(-{ub}*5)*(1-exp(-{ub}*200))"
        zil = "0.12*(random(0)*2-1)*exp(-mod(t+0.2,0.4)*55)"
        return f"{pluck}+{bas}+{zil}", "highpass=f=60,lowpass=f=7000,aecho=0.8:0.5:60:0.15"

    if mood == "epic":
        ped = _akor_dizisi([(73.42, 110, 146.83), (58.27, 87.31, 116.54),
                            (87.31, 130.81, 174.61), (65.41, 98, 130.81)], 2.4, ust=0.35)
        davul = _vurus(0.6, frek=48, egim=28, sonum=7, guc=0.9)
        taiko = _vurus(2.4, frek=60, egim=18, sonum=4, guc=0.8)
        return f"0.75*{ped}+{davul}+{taiko}", "lowpass=f=3200,aecho=0.8:0.6:90|180:0.3|0.2"

    raise ValueError(f"bilinmeyen mood: {mood}")


def muzik_dosyasi_bul(mood, klasor="assets/muzik"):
    for uzanti in MUZIK_UZANTILARI:
        yol = Path(klasor) / f"{mood}{uzanti}"
        if yol.is_file():
            return yol
    return None


def muzik_uret(mood, sure, hedef, klasor="assets/muzik"):
    """sure saniyelik, -20 LUFS civarına getirilmiş arka plan müziği üretir."""
    sure_ek = sure + 1.0
    hazir = muzik_dosyasi_bul(mood, klasor)
    ara = Path(hedef).with_suffix(".ham.wav")
    if hazir:
        print(f"Müzik: {hazir} (döngü)")
        _calistir(["ffmpeg", "-y", "-loglevel", "error", "-stream_loop", "-1", "-i", str(hazir),
                   "-t", f"{sure_ek:.3f}", "-ac", "1", "-ar", str(ORNEKLEME), str(ara)])
    else:
        print(f"Müzik: '{mood}' mood'u için sentez")
        ifade, filtre = muzik_ifadesi(mood)
        _aeval(ifade, sure_ek, ara, filtre, orneklem=SENTEZ_ORNEKLEME)
    _calistir(["ffmpeg", "-y", "-loglevel", "error", "-i", str(ara), "-af",
               f"afade=t=in:d=0.6,afade=t=out:st={max(0.0, sure - 1.5):.3f}:d=1.5,"
               f"loudnorm=I=-20:TP=-3:LRA=11,aresample={ORNEKLEME}",
               "-ac", "1", str(hedef)])
    return hedef


# ---------------------------------------------------------------- efektler

def vurgu_uret(hedef):
    ifade = ("0.9*sin(2*PI*(38+140*exp(-t*16))*t)*exp(-t*3)"
             "+0.35*(random(0)*2-1)*exp(-t*25)")
    return _aeval(ifade, 1.6, hedef, "lowpass=f=4000")


def whoosh_uret(hedef, sure=0.7):
    ifade = f"(random(0)*2-1)*pow(sin(PI*t/{sure}),3)"
    return _aeval(ifade, sure, hedef,
                  "bandpass=f=1400:width_type=o:w=2.5,highpass=f=300,volume=3")


def ugultu_uret(sure, hedef):
    ifade = (f"({_sin(41.2)}+0.6*{_sin(61.74)}+0.3*{_sin(82.41)})"
             f"*(0.7+0.3*sin(2*PI*0.3*t))*0.6")
    sonu = max(0.0, sure - 1.0)
    return _aeval(ifade, sure, hedef,
                  f"lowpass=f=260,afade=t=in:d={min(1.0, sure / 3):.2f},"
                  f"afade=t=out:st={sonu:.3f}:d={min(1.0, sure / 3):.2f}")


def yukselen_uret(sure, hedef):
    ifade = (f"0.6*sin(2*PI*(200*t+700*t*t/(2*{sure})))*pow(t/{sure},2)"
             f"+0.25*(random(0)*2-1)*pow(t/{sure},3)")
    return _aeval(ifade, sure, hedef,
                  f"highpass=f=150,afade=t=out:st={max(0.0, sure - 0.2):.3f}:d=0.2")


# ---------------------------------------------------------------- karışım

def _aralik_birlestir(araliklar):
    sonuc = []
    for a, b in sorted(araliklar):
        if b - a < 0.5:
            continue
        if sonuc and a <= sonuc[-1][1] + 0.3:
            sonuc[-1][1] = max(sonuc[-1][1], b)
        else:
            sonuc.append([a, b])
    return sonuc


def loudnorm_olc(yol, hedef_i=HEDEF_LUFS, hedef_tp=HEDEF_TP):
    s = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(yol), "-af",
                        f"loudnorm=I={hedef_i}:TP={hedef_tp}:LRA=11:print_format=json",
                        "-f", "null", "-"], capture_output=True, text=True)
    eslesme = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", s.stderr, re.S)
    if not eslesme:
        print(s.stderr[-2000:], file=sys.stderr)
        raise SesHatasi("loudnorm ölçümü okunamadı")
    return json.loads(eslesme.group(0))


def normalize_et(giris, hedef):
    olcum = loudnorm_olc(giris)
    filtre = (f"loudnorm=I={HEDEF_LUFS}:TP={HEDEF_TP}:LRA=11"
              f":measured_I={olcum['input_i']}:measured_TP={olcum['input_tp']}"
              f":measured_LRA={olcum['input_lra']}:measured_thresh={olcum['input_thresh']}"
              f":offset={olcum['target_offset']}:linear=true,aresample=48000")
    _calistir(["ffmpeg", "-y", "-loglevel", "error", "-i", str(giris), "-af", filtre,
               "-ac", "2", "-c:a", "pcm_s16le", str(hedef)])
    return hedef


def ses_tasarimi(konusma, sure, mood, gecisler, kapanis, gerilimler, hedef, calisma,
                 muzik_klasoru="assets/muzik"):
    """Konuşmayı müzik ve efektlerle karıştırıp -14 LUFS'a getirilmiş wav yazar.

    gecisler  : sahne geçiş zamanları (sn) -> whoosh
    kapanis   : kapanış bölümünün başladığı an (sn) -> yükselen ses
    gerilimler: [(başlangıç, bitiş)] alçak uğultu aralıkları
    """
    if mood not in MOODLAR:
        mood = "mysterious"
    calisma = Path(calisma)
    calisma.mkdir(parents=True, exist_ok=True)

    girdiler = [str(konusma)]
    zincirler = [f"[0:a]aresample={ORNEKLEME},aformat=sample_fmts=fltp:channel_layouts=stereo,"
                 f"apad=whole_dur={sure:.3f},asplit=2[ses][yan]"]
    karisim = ["[ses]"]

    def ekle(yol, seviye, gecikme=0.0, etiket=None):
        i = len(girdiler)
        girdiler.append(str(yol))
        etiket = etiket or f"e{i}"
        ms = max(0, int(round(gecikme * 1000)))
        zincirler.append(f"[{i}:a]aresample={ORNEKLEME},aformat=sample_fmts=fltp:"
                         f"channel_layouts=stereo,adelay=delays={ms}:all=1,volume={seviye}[{etiket}]")
        return etiket

    # Müzik + ducking
    muzik = muzik_uret(mood, sure, calisma / "muzik.wav", muzik_klasoru)
    ekle(muzik, SEVIYE["muzik"], etiket="m0")
    zincirler.append("[m0][yan]sidechaincompress=threshold=0.012:ratio=10:attack=15:"
                     "release=450:makeup=1[muz]")
    karisim.append("[muz]")

    # Kancada vurgu
    karisim.append(f"[{ekle(vurgu_uret(calisma / 'vurgu.wav'), SEVIYE['vurgu'])}]")

    # Geçişlerde whoosh (geçiş anı whoosh'un ortasına denk gelir)
    gecisler = [g for g in gecisler if 0.5 < g < sure - 0.3]
    if gecisler:
        whoosh = whoosh_uret(calisma / "whoosh.wav")
        for g in gecisler:
            karisim.append(f"[{ekle(whoosh, SEVIYE['whoosh'], g - 0.35)}]")

    # Gerilimde alçak uğultu
    if mood in ("tense", "mysterious"):
        gerilimler = list(gerilimler) + [(0.0, sure)]
    for j, (a, b) in enumerate(_aralik_birlestir([(max(0, a), min(sure, b)) for a, b in gerilimler])):
        ugultu = ugultu_uret(b - a, calisma / f"ugultu_{j}.wav")
        karisim.append(f"[{ekle(ugultu, SEVIYE['ugultu'], a)}]")

    # Kapanışta yükselen ses
    if kapanis is not None and kapanis < sure - 1.0:
        uzunluk = min(3.5, sure - kapanis - 0.2)
        bas = sure - 0.2 - uzunluk
        yukselen = yukselen_uret(uzunluk, calisma / "yukselen.wav")
        karisim.append(f"[{ekle(yukselen, SEVIYE['yukselen'], bas)}]")

    zincirler.append(f"{''.join(karisim)}amix=inputs={len(karisim)}:normalize=0:"
                     f"duration=first,alimiter=limit=0.9:level=disabled[cikis]")
    ham = calisma / "karisim_ham.wav"
    komut = ["ffmpeg", "-y", "-loglevel", "error"]
    for g in girdiler:
        komut += ["-i", g]
    komut += ["-filter_complex", ";".join(zincirler), "-map", "[cikis]",
              "-t", f"{sure:.3f}", "-c:a", "pcm_s16le", str(ham)]
    _calistir(komut)
    return normalize_et(ham, hedef)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--konusma", required=True)
    ap.add_argument("--mood", choices=MOODLAR, default="mysterious")
    ap.add_argument("--sure", type=float, required=True)
    ap.add_argument("--gecis", type=float, action="append", default=[])
    ap.add_argument("--kapanis", type=float)
    ap.add_argument("--cikti", default="mix.wav")
    ap.add_argument("--calisma", default="calisma/ses")
    a = ap.parse_args()
    ses_tasarimi(a.konusma, a.sure, a.mood, a.gecis, a.kapanis, [], a.cikti, a.calisma)
    print(json.dumps(loudnorm_olc(a.cikti), indent=1))


if __name__ == "__main__":
    main()
