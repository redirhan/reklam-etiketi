# Reklam Etiketi Kontrolü (ücretsiz Claude Code skill'i)

> **Bu bir hukuki görüş değildir; bilgilendirme amaçlıdır.**

Instagram, TikTok, YouTube ya da podcast paylaşımını **yayından önce** Türk reklam mevzuatına göre kontrol eder.
Açıklamayı, ekran yazılarını, seslendirmeyi ve isteğe bağlı olarak videonun karelerini okur. Madde numaralı bir
kontrol listesi ve kopyala-yapıştır düzeltmeler yazar.

İçerik üreticileri, markalar ve sosyal medya ajansları için. Redirhan Studio tarafından hazırlandı.
Ücretsiz, MIT lisanslı.

## Neden şimdi?

Ticari Reklam ve Haksız Ticari Uygulamalar Yönetmeliği'nde yapılan değişiklik **1 Ağustos 2026'da yürürlüğe girdi**
(Resmî Gazete 01.07.2026, sayı 33297). Etkileyici reklamlarında artık:

- **"Reklam" ya da "Tanıtım"** ifadesi ve yanında **reklam verenin adı veya @hesabı** zorunlu (m.23/A(3)).
  Tek başına "#işbirliği" bu şartı karşılamıyor.
- Etiket ilk bakışta, kaydırmadan, diğer etiketlerden önce ve zeminden ayrışacak şekilde olmalı (m.23/A(4)).
- Satın alma kararını etkileyen **yapay zekâ kullanımı** açıkça belirtilmeli (m.18(8)).
- İndirimde üstü çizili fiyat, indirimden önceki **10 günün en düşük fiyatı** ve **aynı satış kanalının** fiyatı
  olmalı (m.14(3), 14(5)).

## Ne kontrol eder?

| Kategori | Örnek kontroller |
|---|---|
| Reklam etiketi | "Reklam/Tanıtım" var mı, marka adıyla birlikte mi, ilk satırda mı, # ve @'dan önce mi; videoda ilk kareden itibaren, story'de tüm süre; YouTube'da sözlü beyan; podcast başında "[marka] hakkında reklam içerir."; çok parçalı içerik; çapraz paylaşım |
| Etkileyici yükümlülükleri | Hediye ürünü "satın aldım" diye gösterme; deneyimlemeden önerme; filtre beyanı; "reklam değil" ifadesi |
| Yapay zekâ | Ürün görseli, kişi, sonuç ya da ses YZ ile üretildiyse açıklamada ve ekranda beyan; gerçek kişinin YZ kopyası |
| İndirim ve fiyat | Önceki fiyat, tarihler, stok adedi metinde mi; 10 gün kuralı; aynı kanal; abartılı yüzde; "+KDV"; taksit; koşullu indirim |
| Sağlık | Sağlık iddiası kırmızı bayrakları, hekim/klinik tanıtımı, takviye gıda "öğün yerine", reklamı yasak ürünler (ilaç, e-sigara, tütün, alkol, bahis, fal…) |
| Çocuklar | 24. madde listesi, "sadece 99 TL", "annene söyle", çocuklara profilleme |
| Karşılaştırma | Rakip adı/logosu, belgesiz karşılaştırma, "en iyi / 1 numara" iddiaları |
| Çevre | "Çevre dostu", "karbon nötr" gibi açıklamasız ifadeler |
| Diğer | Doğrulanmamış müşteri yorumu, para karşılığı ödül, çekiliş koşulları |

Her madde şu bilgilerle gelir: durum (DÜZELT / UZMANA SOR / UYARI / GÖZLE KONTROL / GEÇTİ), bulgu, ne yapmalı,
dayanak (madde numarası), varsa belirsizlik. Raporun sonunda kaynakların URL'leri ve okunma tarihleri yer alır.

## Kurulum

```bash
unzip reklam-etiketi-v1.0.zip -d ~/.claude/skills/
```

Ya da `reklam-etiketi/` klasörünü `~/.claude/skills/` içine kopyalayın. Claude Code'u yeniden başlatın.

Gereken: Python 3.8+. Başka bir paket gerekmez.
İsteğe bağlı: `tesseract` (karelerdeki yazıyı okur), `ffmpeg` (videodan kare çıkarır), PyYAML.

## Kullanım

Claude Code'da doğal dille isteyin:

> Bu reels'i yarın atacağım, reklam etiketi kurallarına uygun mu? Açıklama şu: … Markadan ürün hediye geldi.

Claude eksik bilgileri sorar, girdi dosyasını yazar, denetleyiciyi çalıştırır, kareleri gözle kontrol eder ve raporu
sunar.

Elle çalıştırmak isterseniz:

```bash
python3 ~/.claude/skills/reklam-etiketi/scripts/kontrol.py --sablon > gonderi.yaml   # şablonu doldurun
python3 ~/.claude/skills/reklam-etiketi/scripts/kontrol.py gonderi.yaml --cikti rapor.md
python3 ~/.claude/skills/reklam-etiketi/scripts/kontrol.py gonderi.yaml --video taslak.mp4   # kareler de
```

## Örnekler

`examples/` klasöründe üç kurgusal gönderi ve raporları var:

| Örnek | Sonuç |
|---|---|
| `01-uyumlu` (kahve reels'i, hediye ürün) | Düzeltme yok; yalnız etiketin okunurluğu gözle kontrol edilmeli |
| `02-etiket-eksik` (serum TikTok'u, sadece #işbirliği) | 4 DÜZELT: "Reklam" yok, marka adı etiketle değil, konum, ekranda etiket yok; sağlık iddiası için UZMANA SOR |
| `03-yapay-zeka-indirim` (YZ ürün görseli + %50 indirim) | 6 DÜZELT: YZ beyanı yok, tarih yok, önceki fiyat 10 günün en düşüğü değil, farklı kanal, gerçek indirim %33, stok adedi yok |

## Neyi yapmaz?

- Hukuki görüş vermez. Belirsiz konularda "UZMANA SOR" der.
- Sağlık, gıda, kozmetik gibi sektörlerin kendi reklam mevzuatını değerlendirmez.
- Paylaşım yapmaz, hesaplara bağlanmaz, ağa çıkmaz, ücretli bir servis kullanmaz, tarayıcı açmaz.

## Bilinen belirsizlikler

1. Resmî Gazete metni yalnız "Reklam" ya da "Tanıtım" için "zorunludur" diyor. 2021 Kılavuzu ve bazı haberler
   "iş birliği", "sponsor" gibi ifadeleri de sayıyor. Daha sıkı olan Yönetmelik esas alındı.
2. Yönetmelik videoda etiketin ne kadar süre kalacağını yazmıyor. Kontrol ilk kareyi zorunlu, story'de tüm süreyi
   zorunlu, diğer videolarda tüm süreyi önerilen sayar.
3. Yapay zekâ beyanının kapsamı ("önemli ölçüde etkileyecek şekilde") tanımlı değil; hazır beyan metni yok.
4. Markanın kendi hesabında 23/A'nın uygulanıp uygulanmayacağı net değil.
5. Reklam Kurulu kılavuzunun 2026 sonrası güncellendiğine dair resmî kayıt bulunamadı.
6. Kılavuzun tam metni Bakanlık sitesinde bulunamadı; IAB Türkiye'nin yayımladığı kopyadan okundu.

Ayrıntılar ve kaynaklar: `rules/kurallar.yaml`. Kaynaklar 27.10.2026'da okundu.

## Lisans

MIT. Bkz. `LICENSE`. Kural dosyasındaki mevzuat alıntıları kamuya açık resmî metinlerdendir.

> **Bu bir hukuki görüş değildir; bilgilendirme amaçlıdır.** Mevzuat değişebilir; yayından önce Resmî Gazete ve
> Ticaret Bakanlığı Reklam Kurulu duyurularını kontrol edin.
