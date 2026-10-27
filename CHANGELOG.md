# Değişiklik günlüğü / Changelog

## 1.0.0 — 2026-10-27

İlk sürüm. / First release.

- 45 kural, 9 kategori: reklam etiketi (23/A), etkileyici yükümlülükleri (Kılavuz m.6), yapay zekâ beyanı (18(8),
  27(12)), indirim ve fiyat (13, 14), sağlık ve yasaklı ürünler, çocuklar (24, 24/A, 25/A), karşılaştırma (8, 9),
  çevresel beyan (17), yorum/ödül/çekiliş.
- Her kuralda belge + madde + URL + okunma tarihi (27.10.2026). Birincil kaynaklar: Resmî Gazete 01.07.2026/33297,
  10.01.2015/29232, 01.02.2022/31737; Ticaret Bakanlığı işlenmiş metin; Reklam Kurulu etkileyici kılavuzu (2021);
  6502 sayılı Kanun (mevzuat.gov.tr).
- Kaynaklar çeliştiğinde daha sıkı kural kodlandı ve `belirsizlik` alanında yazıldı.
- `scripts/kontrol.py`: Markdown + JSON rapor, kopyala-yapıştır düzeltmeler, düzeltilmiş açıklama taslağı,
  isteğe bağlı tesseract OCR ve ffmpeg kare çıkarma; yalnız standart kütüphane (PyYAML isteğe bağlı).
- 3 kurgusal örnek ve raporları; 25 birim testi.
- Her çıktıda: "Bu bir hukuki görüş değildir; bilgilendirme amaçlıdır."
