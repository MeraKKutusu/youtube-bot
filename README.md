# Merak Kutusu: Vahşi Gerçekler 🐙🦈

**MERAK KUTUSU 2026** kanalları (YouTube Shorts + TikTok) için tam otomatik video sistemi.
Her gün 2 video: deniz ve vahşi doğa hayvanları hakkında az bilinen, şaşırtıcı bilgiler.

## Nasıl çalışır?

```
09:00  Claude (zamanlanmış görev) konular.txt'den 2 konu alır, senaryoları yazar,
       bilgileri iki kez kontrol eder ve main'e commit eder
  ↓    senaryolar/ klasörüne yeni dosya gelir
       GitHub Actions videoyu üretir: Türkçe ses (Ahmet), İngilizce altyazı,
       kanca yazısı, Pixabay görüntüleri, mood'a göre müzik ve efektler, -14 LUFS
  ↓    Kalite kontrolü: süre 30-45 sn, ses seviyesi, siyah kare, altyazı
  ↓    Geçerse: Release + Buffer'da ertesi gün 12:30 ya da 20:30'a sıraya konur
       Geçmezse: paylaşılmaz, sana GitHub Issue açılır
Pazar  Haftalık özet Issue'su
```

**Senin işin:** Buffer'dan gelen paylaşımları kontrol etmek, videonun altına sabit yorumu
eklemek ve pazar özetine göz atmak.

---

## 📱 Telefondan kurulum (bir kez)

Ayarlar GitHub mobil uygulamasında yok; **tarayıcıdan github.com**'u kullan
(gerekirse tarayıcı menüsünden **Masaüstü sitesi**).

### 1. Secret'lar
**Settings** → **Secrets and variables** → **Actions** → **New repository secret**

| Name | Nereden | Zorunlu mu |
|---|---|---|
| `PIXABAY_API_KEY` | pixabay.com/api/docs → `key` | Önerilir (yoksa renkli arka plan) |
| `BUFFER_API_KEY` | publish.buffer.com/settings/api → **Create API key** | Paylaşım için evet |
| `PEXELS_API_KEY` | pexels.com/api | Hayır |

> 🔒 Anahtarları başka hiçbir yere yazma: ne dosyaya, ne sohbete. Yalnızca Secret'ta dursun.

### 2. Buffer kanalları
- Buffer'da **YouTube** ve **TikTok** kanallarını bağla. TikTok için Buffer **TikTok Business**
  hesabı ister (TikTok uygulamasında: Profil → ☰ → Hesap → İşletme hesabına geç).
- Ücretsiz plan yeter: 3 kanal, kanal başına aynı anda 10 planlı gönderi. Sistem en fazla
  ~2 günlük (kanal başına 4) gönderi biriktirir.

### 3. İsteğe bağlı ayarlar (Variables)
**Settings** → **Secrets and variables** → **Actions** → **Variables** sekmesi → **New repository variable**

| Name | Değer | Ne işe yarar |
|---|---|---|
| `ALTYAZI_DILI` | `en` ya da `tr` | Otomatik videoların altyazı/başlık dili (varsayılan `en`) |
| `AI_ETIKETI` | `true` ya da `false` | YouTube/TikTok "AI ile üretildi" işareti (varsayılan `true`) |
| `BUFFER_YOUTUBE_KANAL` | Buffer'daki kanal adı | Birden çok YouTube kanalın varsa |
| `BUFFER_TIKTOK_KANAL` | Buffer'daki kanal adı | Birden çok TikTok kanalın varsa |

### 4. Zamanlanmış görev
Her sabah senaryoları yazan Claude görevi **claude.ai/code** → **Scheduled** bölümündedir.
Kurulum adımları PR açıklamasında; kapatmak için aşağıdaki **Acil durdurma**'ya bak.

---

## 📱 Günlük kullanım (kısa rehber)

| Ne yapmak istiyorsun? | Nereye dokun |
|---|---|
| Bugünün videolarını izle | **Code** → **Releases** (ya da `github.com/MeraKKutusu/youtube-bot/releases`) |
| Sabit yorumu al | Release sayfasında **PINNED COMMENT / SABİT YORUM** satırı → YouTube'da yoruma yapıştır, **⋮ → Sabitle** |
| Sorunlu video var mı? | **Issues** sekmesi (`kalite`, `buffer` etiketleri) |
| Ne zaman paylaşılacak? | Buffer uygulaması → **Queue** |
| Bir videoyu elle üret | **Actions** → **Shorts Üret** → **Run workflow** → senaryo adı (ör. `ornek`), dil, ses → **Run workflow** |
| Elle üretilen videoyu da paylaş | Aynı ekranda **buffer_paylas** kutusunu işaretle |
| Yeni konu ekle | `konular.txt` → ✏️ → listeye `- [ ] (deniz) Konu` satırı ekle → **Commit changes** |
| Haftalık özet | **Issues** → `haftalik-ozet` etiketi (her pazar 20:00) |

Elle çalıştırmada senaryo adı büyük/küçük harften ve `.json` uzantısından etkilenmez
(`ORNEK`, `ornek.json` da olur). `ornek.json` bir test senaryosudur, hiçbir zaman paylaşılmaz.

---

## ⛔ Acil durdurma

**Her şeyi tek dokunuşla durdur** (senaryo yazımı, video üretimi ve Buffer'a gönderim):
1. Repo ana sayfasında **Add file** → **Create new file**
2. Dosya adı: `DURDUR` (içine bir şey yazman gerekmez)
3. **Commit changes** → **Commit changes**

Tekrar başlatmak için: `DURDUR` dosyasını aç → **⋮** → **Delete file** → **Commit changes**.

**Zaten sıraya konmuş paylaşımlar** Buffer'da durur; onları iptal etmek için:
Buffer uygulaması → **Queue** → gönderiye dokun → **Delete**
(ya da Buffer'da kanalın **Pause Queue** düğmesi).

**Daha kesin durdurma:**
- Zamanlanmış görev: **claude.ai/code** → **Scheduled** → görevi aç → kapat (toggle).
- Workflow: **Actions** → **Shorts Üret** → **⋯** → **Disable workflow**.
- Buffer bağlantısını kes: Secret'lardan `BUFFER_API_KEY`'i sil (ya da Buffer'da anahtarı iptal et).

---

## Sorun giderme

| Ne görüyorsun | Ne yap |
|---|---|
| Issue: **Kalite kontrolü geçmedi** | Tablodaki ❌ satırına bak. Süre sorunuysa Claude'a "şu senaryoyu kısalt/uzat" de; dosya değişince yeni ad vermesi gerekir (otomatik çalışma yalnızca **yeni** dosyalarda tetiklenir). Elle de üretebilirsin. |
| Issue: **Buffer'a gönderilemedi** | Mesajı oku. "anahtar reddedildi" → `BUFFER_API_KEY`'i yenile. "kanal bulunamadı" → Buffer'da kanalın bağlı mı bak. Video Release'te duruyor, elle de paylaşabilirsin. |
| Sarı uyarı: `BUFFER_API_KEY secret'ı yok` | Video üretildi ama paylaşıma gönderilmedi. Kurulum adım 1. |
| Sarı uyarı: `PIXABAY_API_KEY yok` | Görüntüler yerine renkli arka plan kullanıldı. |
| `edge-tts seslendirmesi ... başarısız` | Ücretsiz servis anlık hata vermiş olabilir. İşi aç → **Re-run jobs**. |
| Sabah senaryo gelmedi | claude.ai/code → **Scheduled** → görevin son çalışmasına bak. |

> ℹ️ Buffer videoyu paylaşım anında Release'ten indirir. **Paylaşılmamış videoların
> Release'lerini silme.** Repo herkese açık olduğu için Release'ler de herkese açıktır.

---

## Teknik ayrıntılar

| Dosya | Görevi |
|---|---|
| `scripts/uret.py` | Seslendirme, görüntü, altyazı, kanca yazısı, montaj |
| `scripts/ses.py` | Mood müziği, efektler, ducking, -14 LUFS |
| `scripts/kalite.py` | Kalite kontrolü |
| `scripts/buffer.py` | Buffer GraphQL API ile sıraya koyma (`kanallar` komutu kurulumu kontrol eder) |
| `scripts/ozet.py` | Haftalık özet |
| `scripts/senaryo_kontrol.py` | Senaryo kurallarını denetler |
| `CLAUDE.md` | Claude için senaryo kuralları, JSON biçimi ve günlük görev adımları |
| `konular.txt` | Konu listesi (kullanılanlar `[x]`) |
| `yayinlar/kayit.jsonl` | Buffer'a gönderilen videoların kaydı (slot seçimi ve özet için) |
| `assets/muzik/` | İsteğe bağlı kendi müziğin |

**Video:** 1080x1920, 30 fps. Altyazı alt üçte birde (büyük, kalın, beyaz, siyah kenarlık),
her Türkçe cümle okunurken karşılığı ekranda. Kanca yazısı ilk cümle boyunca üstte (sarı).
Sahne geçişleri cümle sonlarında, ilk sahnede hafif zoom. Görüntü sırası: Pixabay video →
Pixabay foto → Pexels (anahtar varsa) → renkli hareketli arka plan.

**Ses:** Türkçe seslendirme (edge-tts Ahmet, isteğe bağlı Emel). Mood (`tense`, `mysterious`,
`fun`, `epic`) müziği ffmpeg ile sentezlenir, konuşmada sidechain ile kısılır. Kancada vurgu,
geçişlerde whoosh, gerilimde alçak uğultu, kapanışta yükselen ses. Telifli ses yok.
İki geçişli loudnorm ile -14 LUFS, en fazla -1.5 dBTP.

**Yayın metinleri:** `youtube.txt` (başlık + "| Vahşi Gerçekler #N", açıklama, hashtag'ler,
etiketler, sabit yorum, "Footage/Görüntüler: Pixabay") ve `tiktok.txt` (en fazla 5 hashtag).
Altyazı diliyle aynı dilde. Release adı: `Vahşi Gerçekler #N - konu`.

**Buffer:** GraphQL API (`https://api.buffer.com`), `createPost` + `customScheduled`.
YouTube kategorisi 15 (Pets & Animals), herkese açık, çocuklara yönelik değil.
Buffer API'si YouTube'da yorum sabitlemeyi desteklemediği için sabit yorumu sen eklersin.

## Güvenlik

- API anahtarları yalnızca GitHub Secrets'ta durur; hata mesajlarında `***` ile gizlenir.
- `.gitignore` gizli dosyaların repoya girmesini engeller.
- `.claude/hooks/gizli-koru.py` Claude Code'un gizli dosyalara ya da dosyalara açık anahtar
  yazmasını engeller.
