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
10. Push'tan sonra GitHub Actions (`Shorts Üret`) videoları üretir ve kalite kontrolünden
    geçirir ama **Buffer'a göndermez**. Sıraya koymak senin işin: aşağıdaki
    **Görsel kontrol** bölümünü uygula.

## Görsel kontrol (her video, Buffer'dan önce)

Stok görüntü etiketleri güvenilmez: "shrimp" etiketli suşi, tavada karides, "otter class"
adlı çiçekli ağaç videoya girebiliyor. Bu yüzden hiçbir video gözle bakılmadan paylaşılmaz.

1. Push'tan sonra `Shorts Üret` çalışmalarının bitmesini bekle (~4-5 dk; GitHub MCP
   `actions_list` ile izle). Her video için Release oluşur: `video-<run>-<attempt>-<ad>`.
2. Release'teki `kareler.jpg` dosyasını indir
   (`https://github.com/MeraKKutusu/youtube-bot/releases/download/<etiket>/kareler.jpg`)
   ve Read ile **kendin bak**. Her karede videonun hayvanı (ya da konuyla doğrudan ilgili
   sahne) olmalı. **Red sebebi:** yemek/tabak/mutfak, başka bir hayvan (balık, kunduz vb.),
   insan, manzara/çiçek, oyuncak/çizgi film, renkli boş arka plan, alakasız akvaryum.
   Yakın akraba tür kabul edilebilir (tabanca karidesi yerine başka resif karidesi) ama
   konunun hayvanı en az birkaç karede görünmeli.
3. **Uygunsa:** `Videoyu Onayla` workflow'unu (`onayla.yml`) `etiketler` girdisiyle çalıştır
   (iki video virgülle). Bu, Buffer'da sıradaki boş saate koyar.
4. **Uygun değilse:** Release'teki `meta.json` → `secilen_gorseller` listesinden kötü
   görüntünün `kimlik`ini bul (ör. `pixabay-f-744520`) ve senaryoya
   `"haric": ["pixabay-f-744520"]` olarak ekle; gerekirse `arama` alanlarını da değiştir
   (daha genel tür adı, farklı ortam kelimesi). Commit/push et ve `Shorts Üret`'i o senaryo için elle çalıştır
   (`senaryo`, `buffer_paylas: false`), sonra tekrar bak. İki denemede de olmazsa onaylama;
   kullanıcıya hangi videonun neden bekletildiğini söyle.
5. **Gerçek görüntüsü olmayan hayvan:** sistem önce gerçek görüntü arar; hiç bulamazsa
   gerçeğe çok yakın 3D/yapay zekâ görüntüsü dener (`meta.json`'da `yapay_goruntu: true`,
   açıklamaya "görüntüler temsilîdir" notu eklenir, AI etiketi açık). Bunu yalnızca
   görüntüler gerçekçi ise onayla; çizgi film, fantastik ya da hatalı anatomi varsa onaylama.
   Gerçek görüntüsü bulunan bir hayvanda yapay görüntü kullanılmaz.

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

## Kanal yönü (rakip analizi, `yayinlar/rakipler/`)

Benzer kanallarda (Jungle Supreme, Discover Wildlife) milyonları bulan videolar hep
**çatışma ve hayatta kalma** üzerine: av-avcı karşılaşması, yanlış rakibe bulaşan hayvan,
ölümcül savunma taktikleri, "X'ten kat kat tehlikeli" karşılaştırmaları. Uydurma "X ülkesi
milyonlarca Y saldı" hikâyeleri ise çoğunlukla tutmamış (1-20 B izlenme). Bu yüzden:

- **Her gün en az 1 video çatışma temalı olsun** (av-avcı, savunma, zehir, ölümden kaçış).
  `konular.txt`'de `(çatışma)` etiketli konular bunun için. Yeni konu eklerken de yarısını
  çatışma temalı seç.
- Çatışma videosunda kanca bir **karşılaşma** ile açılsın: iki taraf + gerilim
  ("Bir yılan, yanlış kuşu seçti." / "Köpekbalığı onu yuttu. Sonra kustu."). Sonuç ikinci
  ya da üçüncü cümlede, merak bölünerek gelsin.
- Gövde sırası: karşılaşma → silah/taktik → beklenmedik sonuç. `mood` çoğunlukla `tense`
  ya da `epic`; saldırı anını anlatan bölüme `"gerilim": true`.
- Karşılaştırma ve rekor kalıbı ("100 kat", "en hızlı", "tek bir ısırıkta") yalnızca
  kaynakta açıkça geçen rakamla kullanılır; tartışmalıysa "yaklaşık" de ya da kullanma.
- **Yasak:** uydurma senaryo, sahnelenmiş/yapay olay, "hükümet X saldı" tarzı yalan hikâye,
  rakip başlıklarını çevirip kullanmak. Gerçek, kaynaklı bir olay ya da araştırma anlat.
  `senaryo_kontrol.py` rakip başlıklarını da kopya denetimine katar.

## Erişim kuralları (izlenme için)

YouTube Shorts ve TikTok yeni videoyu önce küçük bir izleyici grubuna gösterir; ilk
saniyelerde kaydırılmayan ve sonuna kadar izlenen video daha geniş kitleye açılır. TikTok
aramada konuşmayı (transkript), ekrandaki yazıyı ve açıklamayı okur. Bu yüzden:

- **Hayvanın Türkçe adı ilk 2 cümlede sesli geçsin** (ör. "Bu bir aksolotl."), mümkünse
  ilk cümlede. `kanca_yazisi.tr` da merak uyandırsın ama boş vaat olmasın.
- **`yayin.tr.baslik`:** insanların arayacağı ifadeyle başla, hayvanın adı ilk 3 kelimede
  olsun ("Aksolotl kalbini nasıl yeniden yapar?"). En fazla 60 karakter, 0-1 emoji.
- **`yayin.tr.hashtagler`:** `#shorts` + hayvanın Türkçe adı (`#aksolotl`) + konu
  (`#hayvanlar`, `#doğa`, `#deniz`, `#belgesel`) + en fazla bir İngilizce tür etiketi.
  `#fyp`, `#keşfet` gibi genel etiket yok.
- **Kalıp tekrarı yok:** YouTube aynı şablonla seri üretilmiş görünen videoların gelirini
  kısıtlıyor. Son 3 senaryoyu oku; aynı geçiş cümlesini ("Asıl şaşırtıcı olan şu.",
  "Ama iş burada bitmiyor.") ve aynı kapanışı art arda kullanma. Kanca biçimini
  (soru / karşılaşma / rekor / gizli bilgi) her videoda değiştir.
- **Özgün değer:** her senaryoda kaynakta geçen en az bir somut ayrıntı (yer, yıl,
  araştırmacı, ölçüm) olsun; genel geçer "ilginç bilgi" tekrarı değil.
- **TikTok sürümü:** TikTok verisinde (Kasım 2026) izleyicilerin çoğu 0:02'de kaydırıyordu; ortalama
  izlenme %27. Bu yüzden her videonun ayrıca %12 hızlı `video_tiktok.mp4` sürümü üretilir ve TikTok'a o
  gider. Kancadan sonra uzun duraklama yok, ilk cümle bitince görüntüde ani yakınlaştırma (jump cut) var,
  kanca yazısı ilk iki cümle boyunca ekranda. Kanca yazısı cevabı vermesin, merak bıraksın.
  TikTok açıklamasında seri numarası hashtag'siz yazılır (`Bölüm 16`).
- AI etiketi açık kalır (`AI_ETIKETI=true`); YouTube açıklamasına göre etiket tek başına
  erişimi düşürmez.

## Senaryo kuralları (30-40 sn)

- Seslendirme Türkçe (edge-tts, Ahmet), **belgesel anlatıcısı** tonunda: hafif yavaş (-3%),
  pes (-6Hz); cümle aralarında, kancadan ve sorulardan sonra kısa duraklamalar sistem
  tarafından eklenir. Bu yüzden metin kısa tutulur: toplam **52-62 Türkçe kelime** (hız -3%; hedef ~35 sn, kalite kontrolü 30 sn altını reddeder;
  kısa Shorts'ta izlenme oranı yükselir).
- **Anlatıcı üslubu:** kısa, vurucu cümleler (çoğunlukla 3-8 kelime); her cümle tek bir bilgi.
  Merak uyandıran duraklama için bilgiyi ikiye böl: önce merak ettiren yarım cümle, sonra
  cevap ("Ama bir sorun var." → "Yüzerken kalbi durur."). Gerilimi artıran kelimeler
  ("ama", "üstelik", "asıl şaşırtıcı olan") cümle başında. Uzun yan cümle, parantez,
  sayı yığını yok. Sesli okunduğunda ağır ve dramatik bir belgesel gibi akmalı.
- **0-2 sn kanca:** ilk cümle tek başına şok edici bir iddia ya da soru olsun, kısa olsun.
  `kanca_yazisi`: ekranın üstünde görünen **3-5 kelimelik** yazı (en ve tr).
- **Gövde:** 2-3 şaşırtıcı detay. Her bölüm bir sahne; sahne cümle sonunda değişir.
- **Kapanış:** sondan bir önceki cümle izleyiciye soru, son cümle şunlardan **biri**
  (bir önceki senaryodakinden farklı olanı seç):
  `Takip et, yarın daha şaşırtıcısı var.` / `Takip et, sıradaki daha da şaşırtıcı.` /
  `Takip et, vahşi gerçekler bitmiyor.` / `Takip et, yarın yeni bir sır var.`
- Her cümlenin `tr` (seslendirilen) ve `en` (altyazı) hali olsun. İngilizce çeviri kısa ve
  doğal olsun, Türkçe cümleden çok uzun olmasın.
- `mood`: `tense` | `mysterious` | `fun` | `epic`. Gerilimli bölümlere `"gerilim": true`
  ekleyebilirsin (alçak uğultu çalar).
- `sabit_yorum`: izleyiciye soru (en ve tr). Kullanıcı bunu videonun altına sabitler.
- `yayin.en` ve `yayin.tr`: `baslik` (en fazla 70 karakter, seri numarasını yazma; sistem
  ekler), `aciklama` (1-2 cümle), `hashtagler` (3-5 adet, ilki `#shorts`).
  TikTok'a en fazla 5 hashtag gider; sistem sona `#merakkutusu` ekler.
  **Yayın dili Türkçe** (`ALTYAZI_DILI` varsayılanı `tr`): seslendirme Türkçe olduğu için
  izleyicinin gördüğü başlık, açıklama, altyazı ve sabit yorum `tr` alanlarından gelir;
  `tr` alanlarını asıl metin gibi özenle yaz. `en` alanları yedek olarak yine doldurulur.
- `hayvan`: videodaki hayvanın İngilizce adı (ör. `greenland shark`, `box jellyfish`, `lion`).
  Görseller yalnızca etiketinde bu adın son kelimesi (`shark`, `jellyfish`, `lion`) geçenlerden
  seçilir; böylece ilgisiz hayvan ya da manzara görüntüsü gelmez.
- `arama`: Pixabay için İngilizce, **her birinde hayvanın adı geçen** 2-4 kelime
  (ör. `mantis shrimp reef`). Yer adı (`arctic`, `greenland`), soyut kavram (`sleeping`,
  `heat`) ya da başka hayvan (`lioness` yerine `lion female`) tek başına kullanma; tür adı
  her zaman aramada olsun. Nadir hayvanlarda stok görüntü az olabilir; o zaman genel tür
  adıyla ara (`greenland shark` yerine bazı bölümlerde `shark deep sea`).
- Mit, abartı ve tık tuzağı yalan yok. Başlık şaşırtıcı olabilir ama doğru olmalı.

## Senaryo JSON biçimi

```json
{
  "seri_no": 12,
  "konu": "Mantis shrimp punch",
  "hayvan": "mantis shrimp",
  "mood": "epic",
  "kanca_yazisi": { "en": "Fastest punch on Earth", "tr": "Dünyanın en hızlı yumruğu" },
  "sabit_yorum": { "en": "Would you keep one in an aquarium? 👇", "tr": "Akvaryumda besler miydin? 👇" },
  "yayin": {
    "en": { "baslik": "...", "aciklama": "...", "hashtagler": ["#shorts", "#mantisshrimp", "#animalfacts"] },
    "tr": { "baslik": "...", "aciklama": "...", "hashtagler": ["#shorts", "#mantiskarides", "#hayvanlar", "#deniz"] }
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
