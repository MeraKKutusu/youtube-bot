# youtube-bot

**Türkçe seslendirmeli, İngilizce altyazılı** YouTube Shorts hazırlayan sistem. Sen bir konu verirsin; Claude Türkçe senaryoyu ve cümle cümle İngilizce çevirisini, ayrıca başlığı, açıklamayı ve etiketleri yazıp `senaryolar/` klasörüne kaydeder. Ardından GitHub Actions videoyu üretir:

- 🎙️ Türkçe seslendirme (edge-tts, ücretsiz) — Ahmet (erkek, varsayılan) ya da Emel (kadın)
- 🎞️ Pixabay'den stok videolar (bulunamazsa dikey fotoğraflar). Pexels isteğe bağlı yedek kaynak.
- 🌈 Görüntü bulunamazsa ya da anahtar yoksa renkli hareketli arka plan; video her durumda tamamlanır
- 💬 Alt üçte birlik bölümde (yüksekliğin ~%70'i) büyük, kalın, siyah kenarlıklı beyaz İngilizce altyazı. Her Türkçe cümlenin çevirisi, o cümle seslendirilirken ekranda görünür; uzun çeviriler en fazla iki satırlık parçalara bölünür. Altyazı Shorts'un alttaki başlık/kanal alanına ve sağdaki butonlara değmez
- 📱 1080x1920, 30 fps MP4

Çıktı (`video.mp4` + `youtube-bilgileri.txt`) hem bir **Release** olarak hem de **artifact** olarak indirilebilir.

---

## 📱 Telefondan kurulum (bir kez)

Bu adımlar için **tarayıcıdan github.com**'u kullan. GitHub mobil uygulamasında Ayarlar menüsü yok. Sayfa sıkışık görünürse tarayıcı menüsünden **"Masaüstü sitesi"**ni açabilirsin.

### 1. Pixabay API anahtarını al
1. [pixabay.com](https://pixabay.com) adresinde ücretsiz hesap aç (ya da giriş yap).
2. [pixabay.com/api/docs](https://pixabay.com/api/docs/) sayfasını aç.
3. Sayfadaki **Parameters** tablosunda, `key` satırında yeşil renkte yazan anahtarı kopyala.

### 2. Anahtarı GitHub Secret olarak ekle
1. github.com/MeraKKutusu/youtube-bot adresini aç.
2. **Settings** → **Secrets and variables** → **Actions**.
3. **New repository secret**'a dokun.
4. **Name** kutusuna tam olarak `PIXABAY_API_KEY` yaz, **Secret** kutusuna anahtarı yapıştır.
5. **Add secret**'a dokun.

> 🔒 Anahtarı başka hiçbir yere yazma: ne bir dosyaya, ne commit mesajına, ne de sohbete. Yalnızca bu Secret'ta durmalı.

> İsteğe bağlı: Bir Pexels anahtarın varsa aynı yolla `PEXELS_API_KEY` adıyla ekleyebilirsin. Pixabay'de bulunamayan görüntüler için yedek kaynak olarak kullanılır. Gerekli değildir.
>
> Hiç anahtar eklemesen bile workflow çalışır; görüntülerin yerine renkli hareketli arka plan kullanılır.

---

## 🎬 Her yeni video için

### 1. Konuyu ver
Claude'a konuyu söyle (ör. *"Konu: Kara delikler"*). Claude `senaryolar/kara-delikler.json` gibi bir dosya yazıp repoya kaydeder ve sana dosyanın adını verir.

### 2. Videoyu üret
1. Repoda **Actions** sekmesine gir.
2. Soldaki listeden **Shorts Üret**'i seç.
3. **Run workflow**'a dokun.
4. **Senaryo** kutusuna dosyanın adını yaz (ör. `kara-delikler`). Büyük harf (`Kara-Delikler`) ya da `.json` uzantısı (`kara-delikler.json`) da kabul edilir.
5. **Seslendiren** listesinden **Ahmet** (erkek) ya da **Emel** (kadın) seç (varsayılan Ahmet).
6. Yeşil **Run workflow** düğmesine dokun.

İş 3–6 dakika sürer. Yeşil tik ✅ çıkınca video hazırdır.

### 3. İndir
**En kolay yol: Releases**
1. Repo ana sayfasında **Releases** bölümüne (ya da `github.com/MeraKKutusu/youtube-bot/releases` adresine) gir.
2. En üstteki sürümü aç; adı `video-<numara>-<senaryo>` biçimindedir.
3. **video.mp4**'e dokun; video doğrudan iner.
4. Başlık, açıklama ve etiketler sürüm sayfasında da yazılıdır, oradan kopyalayabilirsin.

**Alternatif: Artifact**
Actions'ta biten işe gir, sayfanın altındaki **Artifacts** bölümünden zip'i indir. Artifact'lar 7 gün saklanır.

> ℹ️ Repo herkese açıksa Release'ler de herkese açıktır. Yüklediğin videoları sonradan sürüm sayfasından silebilirsin.

---

## Senaryo dosyası biçimi

```json
{
  "konu": "Konu adı",
  "baslik": "YouTube başlığı (100 karakterden kısa)",
  "aciklama": "Açıklama metni\n\n#shorts #etiket",
  "etiketler": ["etiket1", "etiket2"],
  "bolumler": [
    {
      "arama": "english search keywords",
      "cumleler": [
        { "tr": "Seslendirilecek Türkçe cümle.", "en": "English subtitle for this sentence." },
        { "tr": "İkinci Türkçe cümle.", "en": "Second sentence in English." }
      ]
    }
  ]
}
```

- Her bölüm `cumleler` listesinden oluşur: `tr` seslendirilen Türkçe cümle, `en` ekranda görünen İngilizce çevirisi. Her `tr` için bir `en` zorunludur; çeviri, o Türkçe cümle başladığı anda ekrana gelir ve sonraki cümle başlayana kadar kalır.
- Çeviriler kısa ve doğal olmalı; sesle uyum için Türkçe cümleden çok daha uzun olmamalı.
- `baslik`, `aciklama` ve `etiketler` İngilizce yazılır (altyazılar İngilizce olduğu için). İstersen Türkçe de yazılabilir; sistem içeriği olduğu gibi kullanır.
- Tüm Türkçe cümleler birlikte 45–55 saniye tutmalı (yaklaşık 110–125 Türkçe kelime).
- Eski biçimdeki (`"metin": "..."`) senaryolar da çalışır; çeviri olmadığı için altyazı Türkçe gösterilir ve sarı bir uyarı çıkar.
- Her bölüm kendi metni okunurken ekranda kendi görüntüsünü gösterir.
- `arama` da İngilizce yazılır; stok görsel siteleri İngilizce aramalarda daha iyi sonuç verir.
- Her bölüm için sıra: Pixabay video (önce dikey, yoksa yatay video ortadan kırpılır) → Pixabay dikey fotoğraf → Pexels (anahtar varsa) → renkli hareketli arka plan.
- Pixabay ya da Pexels kullanıldıysa `youtube-bilgileri.txt`'deki açıklamanın sonuna `Footage: Pixabay` (ya da `Footage: Pixabay, Pexels`) satırı eklenir. Dosyadaki bölümler `TITLE`, `DESCRIPTION` ve `TAGS` başlıklarıyla ayrılır.

Örnek: [`senaryolar/ornek.json`](senaryolar/ornek.json)

## Sorun giderme

| Hata | Çözüm |
|---|---|
| Sarı uyarı: `PIXABAY_API_KEY yok` | Video arka planla üretildi. Görüntü istiyorsan kurulum adım 2'yi yap. |
| Sarı uyarı: `Pixabay anahtarı reddedildi` | Secret'ı silip anahtarı yeniden ekle; başında ya da sonunda boşluk olmasın. |
| Sarı uyarı: `... için görüntü bulunamadı` | O bölüm arka planla üretildi. İstersen Claude'dan o bölümün `arama` kelimelerini değiştirmesini iste. |
| `edge-tts seslendirmesi ... başarısız` | Ücretsiz servis anlık hata vermiş olabilir. İşi aç, **Re-run jobs**'a dokun. |
| Ses süresi uyarısı | Video yine üretilir. Süre 45–55 sn dışındaysa Claude'dan metni kısaltmasını ya da uzatmasını iste. |

## Güvenlik

- API anahtarları yalnızca GitHub Secrets'ta durur; kodda yalnızca `${{ secrets.PIXABAY_API_KEY }}` ve `${{ secrets.PEXELS_API_KEY }}` adlarıyla geçer. Hata mesajlarında anahtar `***` ile gizlenir.
- `.gitignore`, `.env`, token ve anahtar dosyalarının repoya girmesini engeller.
- `.claude/hooks/gizli-koru.py` (PreToolUse hook'u), Claude Code'un gizli dosyalara yazmasını, onları commit'lemesini ya da herhangi bir dosyaya açık bir anahtar değeri yazmasını engeller.
