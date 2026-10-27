"""Reklam Etiketi Kontrolü — birim testleri (python3 -m unittest discover -s tests)."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import kontrol  # noqa: E402
import mini_yaml  # noqa: E402

RULES = kontrol.load_yaml(kontrol.DEFAULT_RULES)


def run(post: dict):
    ch = kontrol.Checker(RULES, kontrol.Post(post, ROOT), [], "", "2026-10-27").run()
    return {k: v["durum"] for k, v in ch.results.items()}, ch


BASE = {"platform": "instagram", "ticari_iliski": "evet", "iliski_turu": ["ucret"], "reklam_veren": "Örnek Marka",
        "reklam_veren_hesap": "@ornekmarka", "urunu_deneyimledi": "evet", "filtre": "hayir",
        "yapay_zeka": {"kullanildi": "hayir"}}


class Tests(unittest.TestCase):
    def test_rules_valid(self):
        self.assertEqual(kontrol.validate_rules(RULES), [])

    def test_every_output_has_disclaimer_and_urls(self):
        st, ch = run({**BASE, "bicim": "gonderi", "aciklama": "Reklam | @ornekmarka\nmetin"})
        md = kontrol.render_md(ch, "x.yaml")
        self.assertEqual(md.count(kontrol.DISCLAIMER), 2)
        self.assertIn("https://www.resmigazete.gov.tr/eskiler/2026/07/20260701-9.htm", md)
        self.assertEqual(kontrol.render_json(ch, "x.yaml")["uyari"], kontrol.DISCLAIMER)

    def test_isbirligi_alone_fails(self):
        st, _ = run({**BASE, "bicim": "gonderi", "aciklama": "Harika ürün #işbirliği @ornekmarka"})
        self.assertEqual(st["ETK-02"], "DUZELT")

    def test_label_after_hashtag_fails(self):
        st, _ = run({**BASE, "bicim": "gonderi", "aciklama": "#yeni Reklam | @ornekmarka metin"})
        self.assertEqual(st["ETK-04"], "DUZELT")

    def test_label_in_second_line_fails(self):
        st, _ = run({**BASE, "bicim": "gonderi", "aciklama": "Selam\nReklam | @ornekmarka"})
        self.assertEqual(st["ETK-04"], "DUZELT")

    def test_reklam_degil_is_not_a_label(self):
        st, _ = run({**BASE, "bicim": "gonderi", "aciklama": "Bu bir reklam değil, @ornekmarka çok iyi"})
        self.assertEqual(st["ETK-02"], "DUZELT")
        self.assertEqual(st["ETY-04"], "DUZELT")

    def test_turkish_case_folding(self):
        st, _ = run({**BASE, "bicim": "gonderi", "aciklama": "TANITIM | @ORNEKMARKA"})
        self.assertEqual(st["ETK-02"], "GECTI")
        self.assertEqual(st["ETK-03"], "GECTI")

    def test_story_needs_label_whole_duration(self):
        st, _ = run({**BASE, "bicim": "story", "sure_sn": 15,
                     "ekran_yazilari": [{"metin": "REKLAM · @ornekmarka", "baslangic": 0, "bitis": 5, "konum": "ust"}]})
        self.assertEqual(st["ETK-05"], "DUZELT")
        self.assertEqual(st["ETK-04"], "UYGULANMAZ")

    def test_story_ok(self):
        st, _ = run({**BASE, "bicim": "story", "sure_sn": 15,
                     "ekran_yazilari": [{"metin": "REKLAM · @ornekmarka", "baslangic": 0, "bitis": 15, "konum": "ust"}]})
        self.assertEqual(st["ETK-05"], "GECTI")
        self.assertEqual(st["ETK-02"], "GECTI")

    def test_reels_label_late_start(self):
        st, _ = run({**BASE, "bicim": "reels", "sure_sn": 20, "aciklama": "Reklam | @ornekmarka",
                     "ekran_yazilari": [{"metin": "Reklam @ornekmarka", "baslangic": 3, "bitis": 20}]})
        self.assertEqual(st["ETK-05"], "DUZELT")

    def test_podcast_spoken_disclosure(self):
        st, _ = run({**BASE, "platform": "podcast", "bicim": "podcast",
                     "seslendirme": "Merhaba, bugün kahveden konuşacağız."})
        self.assertEqual(st["ETK-09"], "DUZELT")
        st, _ = run({**BASE, "platform": "podcast", "bicim": "podcast",
                     "seslendirme": "Bu bölüm Örnek Marka hakkında reklam içerir. Merhaba."})
        self.assertEqual(st["ETK-09"], "GECTI")

    def test_brand_own_account_is_warning(self):
        st, _ = run({**BASE, "ticari_iliski": "hayir", "hesap_turu": "marka_kendi", "bicim": "gonderi",
                     "aciklama": "Yeni ürünümüz çıktı"})
        self.assertEqual(st["ETK-12"], "UYARI")
        self.assertEqual(st["ETK-02"], "UYARI")

    def test_no_commercial_with_code_asks(self):
        st, _ = run({**BASE, "ticari_iliski": "hayir", "bicim": "gonderi", "aciklama": "Kodumla al: ABC @ornekmarka"})
        self.assertEqual(st["ETK-01"], "UZMANA_SOR")

    def test_ai_requires_caption_and_screen(self):
        st, _ = run({**BASE, "bicim": "reels", "aciklama": "Reklam | @ornekmarka\nBu reklamdaki görseller yapay zekâ ile oluşturulmuştur.",
                     "yapay_zeka": {"kullanildi": "evet", "neler": ["urun_gorseli"]},
                     "ekran_yazilari": [{"metin": "REKLAM · @ornekmarka", "baslangic": 0}]})
        self.assertEqual(st["YZ-01"], "DUZELT")  # ekranda yok

    def test_ai_clone_banned(self):
        st, _ = run({**BASE, "bicim": "gonderi", "aciklama": "Reklam | @ornekmarka",
                     "yapay_zeka": {"kullanildi": "evet", "neler": ["kisi"], "gercek_kisi_kopyasi": "evet"}})
        self.assertEqual(st["YZ-03"], "DUZELT")

    def test_discount_reference_and_ratio(self):
        st, ch = run({**BASE, "bicim": "gonderi",
                      "aciklama": "Reklam | @ornekmarka\n%40 indirim! 1.000 TL yerine 600 TL. 1-7 Kasım arası.",
                      "indirim": {"indirimli_fiyat": 600, "onceki_fiyat": 1000, "son_10_gun_en_dusuk": 900,
                                  "baslangic": "2026-11-01", "bitis": "2026-11-07"}})
        self.assertEqual(st["FYT-01"], "GECTI")
        self.assertEqual(st["FYT-02"], "DUZELT")
        self.assertEqual(st["FYT-04"], "DUZELT")  # gerçek oran %33

    def test_discount_before_aug_uses_30_days(self):
        _, ch = run({**BASE, "bicim": "gonderi", "aciklama": "Reklam | @ornekmarka indirim 1.000 TL yerine 600 TL",
                     "indirim": {"indirimli_fiyat": 600, "onceki_fiyat": 1000, "son_10_gun_en_dusuk": 900,
                                 "baslangic": "2026-07-20"}})
        self.assertIn("30 gün", ch.results["FYT-02"]["bulgu"])

    def test_percent_without_price_is_not_discount(self):
        st, _ = run({**BASE, "bicim": "gonderi", "aciklama": "Reklam | @ornekmarka\n%100 pamuk tişört"})
        self.assertEqual(st["FYT-01"], "UYGULANMAZ")

    def test_kdv_and_installments(self):
        st, _ = run({**BASE, "bicim": "gonderi", "aciklama": "Reklam | @ornekmarka\n2.000 TL + KDV, taksit imkânı"})
        self.assertEqual(st["FYT-05"], "DUZELT")
        self.assertEqual(st["FYT-07"], "DUZELT")

    def test_health_supplement_children_banned(self):
        st, _ = run({**BASE, "bicim": "gonderi", "urun_kategorisi": "takviye",
                     "aciklama": "Reklam | @ornekmarka\nBu vitamin öğün yerine geçer, bağışıklığı güçlendirir."})
        self.assertEqual(st["SAG-01"], "UZMANA_SOR")
        self.assertEqual(st["SAG-03"], "DUZELT")
        st, _ = run({**BASE, "bicim": "gonderi", "urun_kategorisi": "alkol", "aciklama": "Reklam | @ornekmarka"})
        self.assertEqual(st["SAG-04"], "DUZELT")
        st, _ = run({**BASE, "bicim": "gonderi", "cocuk": {"hedef_kitle": "evet"},
                     "aciklama": "Reklam | @ornekmarka\nOyuncak sadece 99 TL, annene söyle!"})
        self.assertEqual(st["COC-02"], "DUZELT")
        self.assertEqual(st["COC-01"], "MANUEL")

    def test_comparative_and_green(self):
        st, _ = run({**BASE, "bicim": "gonderi", "karsilastirma": {"rakip_adi_var": "evet"},
                     "aciklama": "Reklam | @ornekmarka\nRakip markadan 2 kat daha iyi, çevre dostu ambalaj."})
        self.assertEqual(st["KRS-01"], "DUZELT")
        self.assertEqual(st["KRS-02"], "UZMANA_SOR")
        self.assertEqual(st["CEV-01"], "UYARI")

    def test_gift_shown_as_bought(self):
        st, _ = run({**BASE, "bicim": "gonderi", "iliski_turu": ["hediye_urun"],
                     "aciklama": "Reklam | @ornekmarka\nKendi paramla satın aldım, bayıldım."})
        self.assertEqual(st["ETY-01"], "DUZELT")

    def test_ocr_path_simulated(self):
        orig_l, orig_o = kontrol.tesseract_langs, kontrol.ocr
        try:
            kontrol.tesseract_langs = lambda: "tur+eng"
            texts = {"a.png": "REKLAM @ornekmarka\nyeni sezon", "b.png": "yeni sezon"}
            kontrol.ocr = lambda path, lang: texts[Path(path).name]
            post = {**BASE, "bicim": "reels", "aciklama": "Reklam | @ornekmarka"}
            ch = kontrol.Checker(RULES, kontrol.Post(post, ROOT), [Path("a.png"), Path("b.png")], "", "2026-10-27")
            ch.frames = [Path("a.png"), Path("b.png")]
            orig_exists = Path.exists
            Path.exists = lambda self: self.name in texts or orig_exists(self)
            try:
                ch.run()
            finally:
                Path.exists = orig_exists
            self.assertEqual(ch.results["ETK-05"]["durum"], "GECTI")
            self.assertIn("a.png", ch.results["ETK-06"]["bulgu"])
        finally:
            kontrol.tesseract_langs, kontrol.ocr = orig_l, orig_o

    def test_mini_yaml_matches_examples(self):
        for f in sorted((ROOT / "examples").glob("*/gonderi.yaml")):
            self.assertIsInstance(mini_yaml.load(f), dict)

    def test_cli_template_roundtrip_and_json(self):
        with tempfile.TemporaryDirectory() as td:
            tpl = subprocess.run([sys.executable, str(ROOT / "scripts/kontrol.py"), "--sablon"], capture_output=True,
                                 text=True, check=True).stdout
            p = Path(td) / "g.yaml"
            p.write_text(tpl, encoding="utf-8")
            r = subprocess.run([sys.executable, str(ROOT / "scripts/kontrol.py"), str(p), "--json", str(Path(td) / "o.json"),
                                "--tarih", "2026-10-27"], capture_output=True, text=True)
            self.assertIn(r.returncode, (0, 1))
            data = json.loads((Path(td) / "o.json").read_text(encoding="utf-8"))
            self.assertEqual(data["uyari"], kontrol.DISCLAIMER)
            pj = Path(td) / "g.json"
            pj.write_text(json.dumps({**BASE, "bicim": "gonderi", "aciklama": "Reklam | @ornekmarka"}), encoding="utf-8")
            r = subprocess.run([sys.executable, str(ROOT / "scripts/kontrol.py"), str(pj)], capture_output=True, text=True)
            self.assertIn("Sonuç:", r.stdout)


if __name__ == "__main__":
    unittest.main()
