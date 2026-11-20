# youtube-bot — Claude için kurallar

Kanal: **MERAK KUTUSU 2026** (YouTube Shorts + TikTok, aynı video). Deniz ve vahşi doğa
hayvanları hakkında az bilinen, şok edici, merak uyandıran bilgiler.
Seri adı: **"Merak Kutusu: Vahşi Gerçekler #N"**.

Kullanıcıyla Türkçe konuş. Kullanıcı işleri telefondan yapıyor; adımları kısa ve tıklanacak
yerleri kalın yazarak anlat.

## Acil durdurma

Repo kökünde `DURDUR` adlı bir dosya varsa (büyük/küçük harf fark etmez) **hiçbir senaryo
yazma, commit atma**; kullanıcıya sistemin durdurulduğunu söyle ve bitir.

## Günlük senaryo görevi

1. `git pull` ile main'i güncelle. `DURDUR` dosyası varsa dur.
2. `konular.txt`'de yukarıdan aşağı ilk **2** işaretsiz (`- [ ]`) konuyu al.
3. `seri_no`: `senaryolar/` içindeki en büyük `seri_no` + 1 (ikinci senaryo bir fazlası).
4. Her konu için aşağıdaki kurallarla ve **Trendler** bölümüne uyarak senaryoyu yaz:
   `senaryolar/<seri_no 3 hane>-<kisa-ingilizce-konu>.json` (ör. `001-octopus-three-hearts.json`,
   yalnızca küçük harf, rakam ve tire).
5. **Doğruluk kontrolü (iki tur):** Senaryoyu yazdıktan sonra her bilgiyi web'de güvenilir
   kaynaklardan (üniversite, müze, NOAA, National Geographic, Smithsonian, hakemli makale)
   ikinci kez kontrol et. Emin olmadığın, kaynaklarda çelişen ya da yalnızca tek zayıf kaynakta
   geçen bilgiyi **çıkar**. Tartışmalı rakamlarda "yaklaşık" de. Kullandığın kaynak linklerini
   `kaynaklar` alanına yaz.
6. `python3 scripts/senaryo_kontrol.py senaryolar/<yeni dosyalar>` hatasız geçmeli.
7. `konular.txt`'de kullanılan konuları işaretle: `- [x] (deniz) Konu -> senaryolar/001-....json`.
8. İşaretsiz konu sayısı **5'in altına** indiyse listenin sonuna **10 yeni konu** ekle:
   yaklaşık 6 deniz, 4 kara; daha önce işlenmemiş, doğrulanabilir, şaşırtıcı bilgiler.
   Haftada en az 2 video gerilim temalı olsun (zehirli hayvanlar, derin deniz, avcılar).
9. Tek commit at ve **doğrudan main'e** push'la
   (ör. `Vahşi Gerçekler #12-#13: mantis shrimp, greenland shark`).
   main'e push reddedilirse yeni bir dalda PR aç ve bunu kullanıcıya söyle.
10. Push'tan sonra GitHub Actions videoları kendiliğinden üretir, kalite kontrolünden geçirir
    ve Buffer'da sıraya koyar. Senin başka bir şey yapman gerekmez.

## Trendler (trend avcısı)

Her pazartesi 07:00'de `Trend Avcısı` workflow'u YouTube'da son 30 günün en çok izlenen hayvan
Shorts'larını tarar, en güçlü 5 konuyu `konular.txt`'nin en üstüne ekler ve sonucu
`yayinlar/trendler/YYYY-MM-DD.json` dosyasına yazar.

- Senaryo yazarken en son trend dosyasındaki `kaliplar` (tutan kanca kalıpları) alanına bak ve
  kancayı bu kalıplardan birine **yapı olarak** uydur (soru, rekor, gizli bilgi, tehlike...).
- Trend konusu satırı yalnızca hayvanı verir ("Great white shark (trend ...)"); o hayvan
  hakkında doğrulanmış, az bilinen, **özgün** bir bilgi seç.
- **Kopyalama yasak:** `en_cok` listesindeki viral videoların başlığını, cümlesini ya da
  anlatım sırasını birebir ya da yakın biçimde kullanma; onları yalnızca hangi hayvanın ve
  hangi kalıbın ilgi gördüğünü anlamak için oku. `senaryo_kontrol.py` başlık ve cümleleri
  viral başlıklarla karşılaştırır, çok benzeyeni hata sayar.

## Senaryo kuralları (30-40 sn)

- Seslendirme Türkçe (edge-tts, Ahmet), **belgesel anlatıcısı** tonunda: biraz yavaş (-8%),
  pes (-6Hz); cümle aralarında, kancadan ve sorulardan sonra kısa duraklamalar sistem
  tarafından eklenir. Bu yüzden metin kısa tutulur: toplam **52-70 Türkçe kelime** (73 kelime ≈ 40 sn).
- **Anlatıcı üslubu:** kısa, vurucu cümleler (çoğunlukla 3-8 kelime); her cümle tek bir bilgi.
  Merak uyandıran duraklama için bilgiyi ikiye böl: önce merak ettiren yarım cümle, sonra
  cevap ("Ama bir sorun var." → "Yüzerken kalbi durur."). Gerilimi artıran kelimeler
  ("ama", "üstelik", "asıl şaşırtıcı olan") cümle başında. Uzun yan cümle, parantez,
  sayı yığını yok. Sesli okunduğunda ağır ve dramatik bir belgesel gibi akmalı.
- **0-2 sn kanca:** ilk cümle tek başına şok edici bir iddia ya da soru olsun, kısa olsun.
  `kanca_yazisi`: ekranın üstünde görünen **3-5 kelimelik** yazı (en ve tr).
- **Gövde:** 2-3 şaşırtıcı detay. Her bölüm bir sahne; sahne cümle sonunda değişir.
- **Kapanış:** sondan bir önceki cümle izleyiciye soru, son cümle tam olarak:
  `Takip et, yarın daha şaşırtıcısı var.`
- Her cümlenin `tr` (seslendirilen) ve `en` (altyazı) hali olsun. İngilizce çeviri kısa ve
  doğal olsun, Türkçe cümleden çok uzun olmasın.
- `mood`: `tense` | `mysterious` | `fun` | `epic`. Gerilimli bölümlere `"gerilim": true`
  ekleyebilirsin (alçak uğultu çalar).
- `sabit_yorum`: izleyiciye soru (en ve tr). Kullanıcı bunu videonun altına sabitler.
- `yayin.en` ve `yayin.tr`: `baslik` (en fazla 70 karakter, seri numarasını yazma; sistem
  ekler), `aciklama` (1-2 cümle), `hashtagler` (3-5 adet, ilki `#shorts`).
  TikTok'a en fazla 5 hashtag gider.
- `arama`: Pixabay için İngilizce, **hayvanın adını içeren** 2-4 kelime
  (ör. `mantis shrimp reef`).
- Mit, abartı ve tık tuzağı yalan yok. Başlık şaşırtıcı olabilir ama doğru olmalı.

## Senaryo JSON biçimi

```json
{
  "seri_no": 12,
  "konu": "Mantis shrimp punch",
  "mood": "epic",
  "kanca_yazisi": { "en": "Fastest punch on Earth", "tr": "Dünyanın en hızlı yumruğu" },
  "sabit_yorum": { "en": "Would you keep one in an aquarium? 👇", "tr": "Akvaryumda besler miydin? 👇" },
  "yayin": {
    "en": { "baslik": "...", "aciklama": "...", "hashtagler": ["#shorts", "#mantisshrimp", "#animalfacts"] },
    "tr": { "baslik": "...", "aciklama": "...", "hashtagler": ["#shorts", "#hayvanlar", "#bilgi"] }
  },
  "kaynaklar": ["https://..."],
  "bolumler": [
    { "arama": "mantis shrimp", "cumleler": [ { "tr": "...", "en": "..." } ] },
    { "arama": "mantis shrimp reef", "gerilim": true, "cumleler": [ { "tr": "...", "en": "..." } ] }
  ]
}
```

`"test": true` olan senaryolar (ör. `ornek.json`) üretilir ama Buffer'a gönderilmez.

## Güvenlik

API anahtarları yalnızca GitHub Secrets'ta durur (`PIXABAY_API_KEY`, `PEXELS_API_KEY`,
`BUFFER_API_KEY`). Hiçbir dosyaya, commit'e ya da sohbete yazma.
