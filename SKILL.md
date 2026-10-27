---
name: reklam-etiketi
description: Reklam Etiketi Kontrolü — planlanan bir Instagram, TikTok, YouTube ya da podcast paylaşımını (açıklama, ekran yazıları, seslendirme, isteğe bağlı kareler) Türk reklam mevzuatına göre yayından ÖNCE tarar. 01.08.2026'da yürürlüğe giren Ticari Reklam Yönetmeliği değişikliği (RG 33297) ve Reklam Kurulu etkileyici kılavuzuna göre "Reklam/Tanıtım + @marka" etiketinin varlığı ve yeri, ekranda ilk kareden itibaren görünürlük, story'de tüm süre, sözlü beyan, yapay zekâ beyanı, indirimde son 10 günün en düşük fiyatı ve aynı kanal kuralı, sağlık iddiası kırmızı bayrakları, çocuklar, karşılaştırmalı reklam ve çevresel beyanlara bakar; madde numaralı kontrol listesi ve kopyala-yapıştır düzeltmeler yazar. Her çıktı "Bu bir hukuki görüş değildir; bilgilendirme amaçlıdır" der. Kullan: "reklam etiketi", "işbirliği etiketi yeterli mi", "bu paylaşım reklam yönetmeliğine uygun mu", "influencer reklam kontrolü", "yapay zekâ beyanı lazım mı", "indirim fiyatı doğru mu", "Reklam Kurulu", "story'ye reklam yazmalı mıyım".
---

# Reklam Etiketi Kontrolü

Planlanan bir paylaşımı yayından önce Türk reklam mevzuatına göre kontrol eder ve düzeltme önerir.

**Her çıktının başında ve sonunda şu cümle yer alır: "Bu bir hukuki görüş değildir; bilgilendirme amaçlıdır."**
Bu bir kontrol listesidir. Hukuki tavsiye vermez, kesin "yasal" ya da "yasadışı" hükmü kurmaz.

## Sınırlar (her zaman)

- Yerel çalışır. Paylaşım yapmaz, hiçbir hesaba girmez, ağa çıkmaz, ücretli API çağırmaz.
- Tarayıcı açmaz. Chrome/Chromium hiçbir koşulda başlatılmaz.
- Kullanıcının verdiği metin ve dosyalar dışında veri toplamaz. Başkasının hesabını taramaz.
- Emin olmadığı konuda "UZMANA SOR" der. Müşterinin iş modeli ya da sözleşmesi hakkında görüş bildirmez.

## Dosyalar

```
SKILL.md                 bu dosya
rules/kurallar.yaml      45 kural: id, koşul, düzeltme, kaynak (belge + madde + URL + okunma tarihi), belirsizlik
                         + anahtar kelime sözlüğü (genişletilebilir)
scripts/kontrol.py       denetleyici (Python 3.8+, yalnız standart kütüphane)
scripts/mini_yaml.py     PyYAML yoksa kullanılan küçük YAML okuyucu
examples/                3 kurgusal gönderi + raporları (uyumlu, etiketi eksik, yapay zekâ + indirim)
tests/                   birim testleri
```

İsteğe bağlı araçlar: `tesseract` (kare OCR), `ffmpeg` (videodan kare). Yoksa denetleyici gözle kontrol
listesi yazar; sen de kareleri Read aracıyla açıp bakarsın.

## Akış

1. **Bilgiyi topla.** Kullanıcıdan şunları al (eksikse sor, tahmin etme):
   - platform ve biçim (reels, story, TikTok, YouTube videosu, carousel, podcast…)
   - **ticari ilişki**: para, hediye ya da indirimli ürün, indirim kodu veya bağlantı (yönlendirme), çekiliş,
     menfaat karşılığı etkinlik. Bilinmiyorsa `bilinmiyor` yaz; denetleyici daha sıkı davranır.
   - reklam verenin adı ve @hesabı
   - açıklama metni, YouTube başlığı, ekran yazıları (başlangıç ve bitiş saniyesiyle), seslendirme metni, süre
   - yapay zekâ ile neyin üretildiği (ürün görseli, kişi, sonuç, ses, arka plan, metin)
   - indirim varsa: indirimli fiyat, üstü çizili fiyat, **indirimden önceki 10 günün en düşük fiyatı**, başlangıç
     ve bitiş tarihi, stok adedi, indirimin yapıldığı kanal ve önceki fiyatın alındığı kanal
   - çocuk kitlesi, rakip adı, filtre kullanımı, ürünü gerçekten deneyimleyip deneyimlemediği
   Video dosyası ya da kareler varsa yolunu al.

2. **Girdi dosyasını yaz.** Şablonu al ve doldur:
   ```bash
   python3 <skill klasörü>/scripts/kontrol.py --sablon > gonderi.yaml
   ```
   Ekran yazılarını videoda gördüğün gibi gir; görmediğin şeyi uydurma.

3. **Denetleyiciyi çalıştır.**
   ```bash
   python3 <skill klasörü>/scripts/kontrol.py gonderi.yaml --cikti rapor.md --json rapor.json
   # video varsa:   --video taslak.mp4      kareler varsa:   --kareler ilk.png orta.png son.png
   ```
   Çıkış kodu 1 = en az bir DÜZELT maddesi var.

4. **Kareleri gözle kontrol et.** Tesseract yoksa ya da rapor "GÖZLE KONTROL" diyorsa, kareleri Read aracıyla aç.
   Rapordaki listeyi tek tek işaretle: ilk karede "REKLAM · @marka" var mı, zeminden ayrışıyor mu, arayüzle
   çakışıyor mu, yapay zekâ beyanı ilgili görüntünün üstünde mi, indirim bilgisi okunuyor mu, rakip logosu var mı.
   Ne gördüğünü kısaca yaz; görmediğin kareyi yorumlama.

5. **Kullanıcıya sun.** Sırayla:
   - ilk satır: "Bu bir hukuki görüş değildir; bilgilendirme amaçlıdır."
   - sonuç (DÜZELTME GEREKLİ / UZMANA DANIŞIN / KONTROL LİSTESİNİ TAMAMLAYIN / BELİRGİN BİR SORUN BULUNMADI)
   - DÜZELT ve UZMANA SOR maddeleri: bulgu + ne yapmalı + dayanak (madde numarası)
   - kopyala-yapıştır düzeltmeler (etiket satırı, ekran yazısı, sözlü beyan, yapay zekâ beyanı, indirim satırı)
   - ilgili belirsizlikler (aşağıda)
   - son satır: aynı uyarı cümlesi + "Mevzuat değişebilir; yayından önce Resmî Gazete ve Reklam Kurulu
     duyurularını kontrol edin."
   Tam raporu `rapor.md` olarak bırak.

## Temel kurallar (özet; tamamı ve kaynaklar rules/kurallar.yaml'da)

| Konu | Kural | Dayanak |
|---|---|---|
| Etiket kelimesi | "Reklam" ya da "Tanıtım" zorunlu. "#işbirliği", "#sponsor", "ücretli ortaklık" tek başına yetmez; ancak onlardan SONRA eklenebilir. | Yön. 23/A(3) |
| Reklam veren | Etiketle birlikte marka adı/unvanı ya da "@marka tarafından sağlandı." / "@markaya teşekkürler." | Yön. 23/A(3) |
| Yer | İlk bakışta, kaydırmadan ve "devamı"na basmadan; diğer etiketlerden önce; zeminden ayrışan, okunur boyutta; arayüzle çakışmayan. | Yön. 23/A(4)(a)-(ç) |
| Video / story | Ekranda ilk kareden itibaren; story'de paylaşım süresince; YouTube videosunda yazılı + sözlü. | Yön. 23/A(4)(b); Kılavuz 7, 10 |
| Parçalar | Çok parçalı içerikte her parçada; başka biçime aktarılan her paylaşımda. | Yön. 23/A(4)(d)-(e) |
| Sesli | Başta ve reklamdan önce: "[reklam veren] hakkında reklam/tanıtım içerir." | Yön. 23/A(5) |
| Yapay zekâ | Satın alma kararını önemli ölçüde etkileyen YZ kullanımı ve insandan ayırt edilemeyen dijital karakter açıkça belirtilir. Gerçek kişinin YZ kopyasıyla "kullandı/önerdi" izlenimi yasak. | Yön. 18(8), 27(12) |
| İndirim | Önceki fiyat = indirimden önceki 10 günün en düşüğü (mal), aynı kanal; tarihler ve sınırlı miktar yazılır; oran abartılmaz. | Yön. 14(1)-(3), (5) |
| Sağlık | Mevzuata aykırı sağlık beyanı yok; hekim/sağlık kuruluşu tanıtımı yok; takviye gıda "öğün yerine" değil; ilaç, e-sigara, tütün, alkol reklamı yasak. | Kılavuz 6; Yön. 16(3), 27(10)-(11) |
| Çocuk | 24. madde listesi; çocuklara profilleme ile hedefli reklam yok. | Yön. 24, 25/A(3) |
| Karşılaştırma | Rakibin adı/logosu yok; iddialar belgeli. | Yön. 8, 9 |
| Çevre | "Çevre dostu" gibi genel ifadeler açıklamasız kullanılmaz; süreç, belge, ölçüm yöntemi. | Yön. 17 |

## Belirsizlikler (kullanıcıya dürüstçe söyle)

1. **"İş birliği" / "Sponsorlu" yeterli mi?** Resmî Gazete metni yalnız "Reklam" ya da "Tanıtım" için "zorunludur"
   diyor. 2021 Kılavuzu ve bazı haberler başka ifadeleri de sayıyor. Daha sıkı olan Yönetmelik kodlandı.
2. **Videoda ne kadar süre?** Yönetmelik "ilk karşılaşılan anda" diyor, süre vermiyor. Story için Kılavuz
   "paylaşım süresince" diyor. Kontrol: ilk kare zorunlu, story'de tüm süre zorunlu, diğer videolarda tüm süre önerilir.
3. **Yapay zekâ beyanının kapsamı.** "Önemli ölçüde etkileyecek şekilde" tanımlı değil, hazır beyan metni yok.
   Kontrol ürün, kişi, sonuç ya da ses YZ ile üretildiyse açıklama + ekranda beyan ister.
4. **Markanın kendi hesabı.** Etkileyici tanımı tüzel kişileri ve "kendisi adına" paylaşımı da kapsıyor; markanın
   kendi hesabında etiketin zorunlu olup olmadığı net değil (UYARI olarak gösterilir).
5. **Kılavuz hâlâ geçerli mi?** 2026 sonrası güncellendiğine ya da kaldırıldığına dair resmî kayıt bulunamadı.
   Kılavuz kendi metninde Yönetmeliğe aykırı yorumlanamayacağını söylüyor; çelişkide Yönetmelik esas alındı.
6. **Sağlık beyanı.** RG 33297 Yönetmeliğin 26. maddesini ve Ek A-13'ü kaldırdı; sektör mevzuatı yine geçerli.
   Bu araç sektör mevzuatını değerlendirmez, UZMANA SOR der.
7. **Platformların "ücretli ortaklık" aracı** "Reklam/Tanıtım" kelimesini içermediği için tek başına yeterli
   olmayabilir.

## Bakım

- Kural ekle/değiştir: `rules/kurallar.yaml` (her kurala kaynak + okunma tarihi şart), sonra
  `python3 scripts/kontrol.py --kurallari-dogrula` ve `python3 -m unittest discover -s tests`.
- Kaynaklar 27.10.2026'da okundu. Yeni bir Resmî Gazete değişikliği ya da Reklam Kurulu kararı çıkarsa
  `surum` ve `kural_tarihi` alanlarını güncelle, CHANGELOG'a yaz.
