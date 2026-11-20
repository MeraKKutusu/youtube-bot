# youtube-bot

Türkçe YouTube Shorts hazırlayan sistem. Sen bir konu verirsin; Claude senaryoyu, başlığı, açıklamayı ve etiketleri yazıp `senaryolar/` klasörüne kaydeder. Ardından GitHub Actions videoyu üretir:

- 🎙️ Türkçe seslendirme (edge-tts, ücretsiz) — Emel ya da Ahmet
- 🎞️ Pexels'ten dikey stok videolar (bulunamazsa dikey fotoğraflar)
- 💬 Ekranın ortasında büyük, kalın, siyah kenarlıklı beyaz altyazı
- 📱 1080x1920, 30 fps MP4

Çıktı (`video.mp4` + `youtube-bilgileri.txt`) hem bir **Release** olarak hem de **artifact** olarak indirilebilir.

---

## 📱 Telefondan kurulum (bir kez)

Bu adımlar için **tarayıcıdan github.com**'u kullan. GitHub mobil uygulamasında Ayarlar menüsü yok. Sayfa sıkışık görünürse tarayıcı menüsünden **"Masaüstü sitesi"**ni açabilirsin.

### 1. Pexels API anahtarını al
1. [pexels.com/api](https://www.pexels.com/api/) adresine git ve ücretsiz hesap aç (ya da giriş yap).
2. **"Your API Key"** bölümündeki anahtarı kopyala.

### 2. Anahtarı GitHub Secret olarak ekle
1. github.com/MeraKKutusu/youtube-bot adresini aç.
2. **Settings** → **Secrets and variables** → **Actions**.
3. **New repository secret**'a dokun.
4. **Name** kutusuna tam olarak `PEXELS_API_KEY` yaz, **Secret** kutusuna anahtarı yapıştır.
5. **Add secret**'a dokun.

> 🔒 Anahtarı başka hiçbir yere yazma: ne bir dosyaya, ne commit mesajına, ne de sohbete. Yalnızca bu Secret'ta durmalı.

---

## 🎬 Her yeni video için

### 1. Konuyu ver
Claude'a konuyu söyle (ör. *"Konu: Kara delikler"*). Claude `senaryolar/kara-delikler.json` gibi bir dosya yazıp repoya kaydeder ve sana dosyanın adını verir.

### 2. Videoyu üret
1. Repoda **Actions** sekmesine gir.
2. Soldaki listeden **Shorts Üret**'i seç.
3. **Run workflow**'a dokun.
4. **Senaryo** kutusuna dosyanın adını yaz (ör. `kara-delikler`; `.json` yazmana gerek yok).
5. **Seslendiren** listesinden **Emel** ya da **Ahmet**'i seç (varsayılan Emel).
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
    { "metin": "Seslendirilecek Türkçe metin.", "arama": "english pexels keywords" }
  ]
}
```

- Tüm bölümlerin metni birlikte 45–55 saniye tutmalı (yaklaşık 110–125 kelime).
- Her bölüm kendi metni okunurken ekranda kendi görüntüsünü gösterir.
- `arama` İngilizce yazılır; Pexels İngilizce aramalarda daha iyi sonuç verir.

Örnek: [`senaryolar/ornek.json`](senaryolar/ornek.json)

## Sorun giderme

| Hata | Çözüm |
|---|---|
| `PEXELS_API_KEY secret'ı eklenmemiş` | Kurulum adım 2'yi yap. |
| `Pexels anahtarı geçersiz` | Secret'ı silip anahtarı yeniden ekle. |
| `edge-tts seslendirmesi ... başarısız` | Ücretsiz servis anlık hata vermiş olabilir. İşi aç, **Re-run jobs**'a dokun. |
| `... için görsel bulunamadı` | Claude'dan o bölümün `arama` kelimelerini değiştirmesini iste. |
| Ses süresi uyarısı | Video yine üretilir. Süre 45–55 sn dışındaysa Claude'dan metni kısaltmasını ya da uzatmasını iste. |

## Güvenlik

- API anahtarları yalnızca GitHub Secrets'ta durur; kodda yalnızca `${{ secrets.PEXELS_API_KEY }}` adıyla geçer.
- `.gitignore`, `.env`, token ve anahtar dosyalarının repoya girmesini engeller.
- `.claude/hooks/gizli-koru.py` (PreToolUse hook'u), Claude Code'un gizli dosyalara yazmasını, onları commit'lemesini ya da herhangi bir dosyaya açık bir anahtar değeri yazmasını engeller.
