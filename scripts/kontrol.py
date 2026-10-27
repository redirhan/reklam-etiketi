#!/usr/bin/env python3
"""Reklam Etiketi Kontrolü (MIT, Redirhan Studio).

Planlanan bir Instagram / TikTok / YouTube paylaşımını (açıklama, ekran yazıları, seslendirme, isteğe bağlı kareler)
Türk reklam mevzuatındaki etiket ve beyan kurallarına göre tarar; kontrol listesi + önerilen düzeltmeler yazar.
Bu bir hukuki görüş değildir; bilgilendirme amaçlıdır.

Yerel çalışır: ağ yok, hesap yok, ücretli API yok. Sadece Python 3.8+ standart kütüphanesi.
İsteğe bağlı: tesseract (kare OCR), ffmpeg/ffprobe (videodan kare çıkarma), PyYAML (yoksa dahili okuyucu).

Kullanım:
  python3 kontrol.py gonderi.yaml                     # raporu ekrana yazar
  python3 kontrol.py gonderi.yaml --cikti rapor.md    # dosyaya yazar
  python3 kontrol.py gonderi.yaml --json rapor.json   # makine okunur çıktı
  python3 kontrol.py gonderi.yaml --kareler k1.png k2.png   # kareler (OCR varsa okunur)
  python3 kontrol.py gonderi.yaml --video taslak.mp4        # ffmpeg ile kare çıkarır
  python3 kontrol.py --sablon > gonderi.yaml          # boş girdi şablonu
  python3 kontrol.py --kurallari-dogrula              # kural dosyasını denetler
Çıkış kodu: 0 = DÜZELT yok, 1 = en az bir DÜZELT, 2 = girdi hatası.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL_DIR = HERE.parent
DEFAULT_RULES = SKILL_DIR / "rules" / "kurallar.yaml"
DISCLAIMER = "Bu bir hukuki görüş değildir; bilgilendirme amaçlıdır."

DURUM_ETIKET = {
    "DUZELT": "DÜZELT",
    "UZMANA_SOR": "UZMANA SOR",
    "UYARI": "UYARI",
    "MANUEL": "GÖZLE KONTROL",
    "BILGI": "BİLGİ",
    "GECTI": "GEÇTİ",
    "UYGULANMAZ": "UYGULANMAZ",
}
DURUM_SIRA = ["DUZELT", "UZMANA_SOR", "UYARI", "MANUEL", "BILGI", "GECTI", "UYGULANMAZ"]
KATEGORI_AD = {
    "etiket": "Reklam etiketi",
    "etkileyici": "Etkileyici yükümlülükleri",
    "yapay_zeka": "Yapay zekâ beyanı",
    "indirim": "İndirim ve fiyat",
    "saglik": "Sağlık ve yasaklı ürünler",
    "cocuk": "Çocuklar",
    "karsilastirma": "Karşılaştırma ve üstünlük iddiası",
    "cevre": "Çevresel beyan",
    "diger": "Diğer",
}


# --------------------------------------------------------------------------- YAML
def load_yaml(path: Path):
    try:
        import yaml  # type: ignore

        with open(path, encoding="utf-8") as fh:
            return yaml.safe_load(fh)
    except ImportError:
        sys.path.insert(0, str(HERE))
        import mini_yaml  # noqa: E402

        return mini_yaml.load(path)


# --------------------------------------------------------------------------- Türkçe metin
_FOLD = str.maketrans({"ı": "i", "ş": "s", "ğ": "g", "ü": "u", "ö": "o", "ç": "c", "â": "a", "î": "i",
                       "û": "u", "’": "'", "‘": "'", "̇": None})


def tr_lower(s: str) -> str:
    return s.replace("I", "ı").replace("İ", "i").lower()


def fold(s: str) -> str:
    """Türkçe küçük harfe çevir + aksanları ASCII'ye indir (konum korunur)."""
    return tr_lower(s or "").translate(_FOLD)


def _phrase_regex(p: str):
    if p.startswith("r:"):
        return re.compile(p[2:].translate(_FOLD))
    exact = p.endswith("$")
    body = fold(p[:-1] if exact else p)
    pat = r"(?<![a-z0-9])" + re.escape(body) + (r"(?![a-z0-9])" if exact else "")
    return re.compile(pat)


_RX_CACHE: dict = {}


def find(text: str, phrases) -> list:
    """[(ifade, eşleşen metin, konum)] — text önceden fold edilmemiş olabilir."""
    t = fold(text)
    out = []
    for p in phrases or []:
        rx = _RX_CACHE.get(p)
        if rx is None:
            rx = _RX_CACHE[p] = _phrase_regex(str(p))
        for m in rx.finditer(t):
            out.append((p, (text or "")[m.start():m.end()], m.start()))
    return sorted(out, key=lambda x: x[2])


def uniq(seq):
    seen, out = set(), []
    for x in seq:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def yes(v) -> bool | None:
    if v is None:
        return None
    if isinstance(v, bool):
        return v
    s = fold(str(v)).strip()
    if s in ("evet", "var", "true", "yes", "1", "e"):
        return True
    if s in ("hayir", "yok", "false", "no", "0", "h"):
        return False
    return None


def as_list(v):
    if v is None:
        return []
    if isinstance(v, list):
        return v
    return [x.strip() for x in str(v).split(",") if x.strip()]


def num(v):
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).replace("TL", "").replace("₺", "").strip()
    if re.match(r"^\d{1,3}(\.\d{3})+(,\d+)?$", s):  # 1.299,90
        s = s.replace(".", "").replace(",", ".")
    else:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def fmt_tl(x: float) -> str:
    if abs(x - round(x)) < 0.005:
        s = f"{int(round(x)):,}".replace(",", ".")
    else:
        s = f"{x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{s} TL"


# --------------------------------------------------------------------------- girdi
SABLON = """# Reklam Etiketi Kontrolü — gönderi girdisi
# Bu bir hukuki görüş değildir; bilgilendirme amaçlıdır.
platform: instagram          # instagram | tiktok | youtube | podcast | diger
bicim: reels                 # reels | video | shorts | story | canli | tiktok | gonderi | carousel | podcast | sesli
hesap_turu: icerik_uretici   # icerik_uretici | marka_kendi | ajans_musteri
yayin_tarihi: "2026-11-03"
ticari_iliski: evet          # evet | hayir | bilinmiyor  (para, hediye/indirimli ürün, indirim kodu/link, çekiliş, etkinlik)
iliski_turu: [hediye_urun]   # ucret | hediye_urun | indirimli_urun | yonlendirme | cekilis | etkinlik
reklam_veren: "Marka Adı"
reklam_veren_hesap: "@markahesabi"
urun_kategorisi: diger       # gida | takviye | kozmetik | giyim | teknoloji | hizmet | saglik_hizmeti | alkol | e_sigara | tutun | ilac | diger
platform_ortaklik_etiketi: hayir   # platformun "ücretli ortaklık" aracı açık mı
urunu_deneyimledi: evet
filtre: hayir                # görüntüye filtre/efekt uygulandı mı
baslik: ""                   # YouTube başlığı (varsa)
aciklama: |
  Reklam | @markahesabi
  Açıklama metni buraya.
ekran_yazilari:              # videodaki/görseldeki yazılar; saniye cinsinden
  - metin: "REKLAM · @markahesabi"
    baslangic: 0
    bitis: 15
    konum: ust                # ust | orta | alt | sag | sol_alt | sag_alt
seslendirme: ""              # konuşma metni (varsa)
sure_sn: 15
parca_sayisi: 1              # art arda story sayısı vb.
her_parcada_etiket: evet
capraz_paylasim: []          # [tiktok, youtube_shorts, story]
yapay_zeka:
  kullanildi: hayir
  neler: []                  # urun_gorseli | sonuc | kisi | dijital_karakter | ses | arka_plan | metin | duzenleme
  gercek_kisi_kopyasi: hayir
indirim:                     # indirim yoksa bu bloğu silin
  indirimli_fiyat:
  onceki_fiyat:              # üstü çizili / "yerine" fiyat
  son_10_gun_en_dusuk:       # indirim başlangıcından önceki 10 günün en düşük fiyatı (aynı kanal)
  baslangic: ""
  bitis: ""
  stok_adedi:
  urun_turu: mal             # mal | hizmet | cabuk_bozulan
  satis_kanali: ""
  onceki_fiyat_kanali: ""
cocuk:
  hedef_kitle: hayir
  oynuyor: hayir
hedefleme:
  cocuk_profilleme: hayir
karsilastirma:
  rakip_adi_var: hayir
kareler: []                  # isteğe bağlı: ["kareler/ilk.png", "kareler/orta.png"]
"""


class Post:
    def __init__(self, d: dict, base: Path):
        self.d = d or {}
        self.base = base
        g = self.d.get
        self.platform = fold(str(g("platform") or "diger")).strip()
        self.bicim = fold(str(g("bicim") or "gonderi")).strip()
        self.hesap = fold(str(g("hesap_turu") or "icerik_uretici")).strip()
        self.ticari_raw = g("ticari_iliski")
        t = fold(str(self.ticari_raw)).strip() if self.ticari_raw is not None else "bilinmiyor"
        self.ticari = "evet" if yes(t) else ("hayir" if yes(t) is False else "bilinmiyor")
        self.iliski = [fold(str(x)) for x in as_list(g("iliski_turu"))]
        self.reklam_veren = str(g("reklam_veren") or "").strip()
        h = str(g("reklam_veren_hesap") or "").strip()
        self.hesap_adi = ("@" + h.lstrip("@")) if h else ""
        self.kategori = fold(str(g("urun_kategorisi") or "diger")).strip()
        self.baslik = str(g("baslik") or "")
        self.aciklama = str(g("aciklama") or "").strip("\n")
        self.seslendirme = str(g("seslendirme") or "")
        self.sure = num(g("sure_sn"))
        self.ekran = []
        for e in g("ekran_yazilari") or []:
            if isinstance(e, str):
                e = {"metin": e}
            self.ekran.append({
                "metin": str(e.get("metin") or ""),
                "bas": num(e.get("baslangic")),
                "bit": num(e.get("bitis")),
                "konum": fold(str(e.get("konum") or "")),
            })
        self.yz = g("yapay_zeka") or {}
        self.indirim = g("indirim") or {}
        if not isinstance(self.indirim, dict):
            self.indirim = {}
        self.cocuk = g("cocuk") or {}
        self.hedef = g("hedefleme") or {}
        self.krs = g("karsilastirma") or {}
        self.kareler = [str(x) for x in as_list(g("kareler"))]
        self.yayin = str(g("yayin_tarihi") or "")

    @property
    def ekran_metni(self) -> str:
        return "\n".join(e["metin"] for e in self.ekran)

    @property
    def tum_metin(self) -> str:
        return "\n".join([self.baslik, self.aciklama, self.ekran_metni, self.seslendirme])


# --------------------------------------------------------------------------- OCR / kareler
def tesseract_langs():
    exe = shutil.which("tesseract")
    if not exe:
        return None
    try:
        out = subprocess.run([exe, "--list-langs"], capture_output=True, text=True, timeout=20)
        langs = set(out.stdout.split()) | set(out.stderr.split())
    except Exception:
        return None
    return "tur+eng" if "tur" in langs else "eng"


def ocr(path: Path, lang: str) -> str:
    try:
        out = subprocess.run(["tesseract", str(path), "stdout", "-l", lang], capture_output=True, text=True,
                             timeout=60)
        return out.stdout
    except Exception:
        return ""


def frames_from_video(video: Path, outdir: Path):
    if not (shutil.which("ffmpeg") and shutil.which("ffprobe")):
        return [], "ffmpeg/ffprobe bulunamadı; kareleri kendiniz verin (--kareler)."
    try:
        dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of",
                                    "default=nw=1:nk=1", str(video)], capture_output=True, text=True,
                                   timeout=60).stdout.strip())
    except Exception:
        return [], "Video süresi okunamadı."
    times = uniq([0.0, min(1.0, dur / 2), dur / 2, max(0.0, dur - 0.5)])
    paths = []
    for i, t in enumerate(times):
        p = outdir / f"kare_{i:02d}_{t:05.1f}s.png"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.2f}", "-i", str(video), "-frames:v", "1",
                        str(p)], capture_output=True, timeout=120)
        if p.exists():
            paths.append(p)
    return paths, f"{len(paths)} kare çıkarıldı: {outdir}"


# --------------------------------------------------------------------------- kontrol motoru
class Checker:
    def __init__(self, rules: dict, post: Post, frames: list, frame_note: str, today: str):
        self.R = rules
        self.rules = {r["id"]: r for r in rules["kurallar"]}
        self.S = rules.get("sozluk", {})
        self.p = post
        self.frames = frames
        self.frame_note = frame_note
        self.today = today
        self.results = {}
        self.eksik = []
        self.oneriler = []
        self.ocr_text = {}
        self.ocr_lang = None

    # yardımcılar ----------------------------------------------------------
    def set(self, rid, durum, bulgu="", extra=None):
        if rid not in self.rules:
            raise KeyError(f"kural dosyasında yok: {rid}")
        prev = self.results.get(rid)
        if prev and DURUM_SIRA.index(prev["durum"]) <= DURUM_SIRA.index(durum):
            if bulgu and bulgu not in prev["bulgu"]:
                prev["bulgu"] += " " + bulgu
            return
        self.results[rid] = {"id": rid, "durum": durum, "bulgu": bulgu, **(extra or {})}

    def kw(self, key, text):
        return find(text, self.S.get(key, []))

    def words(self, hits, n=6):
        return ", ".join(f"\"{h[1]}\"" for h in uniq([h for h in hits])[:n])

    def bicim_in(self, group):
        return self.p.bicim in (self.R.get("bicimler", {}).get(group) or [])

    def label_hits(self, text):
        """Geçerli etiket eşleşmeleri ('reklam değil' gibi olumsuzlar çıkarılmış)."""
        neg = self.kw("tuketici_izlenimi", text)
        masked = list(text)
        for _, m, pos in neg:
            for i in range(pos, min(len(masked), pos + len(m))):
                masked[i] = " "
        return self.kw("etiket_gecerli", "".join(masked))

    def brand_in(self, text):
        t = fold(text)
        names = []
        if self.p.reklam_veren:
            names.append(fold(self.p.reklam_veren))
        if self.p.hesap_adi:
            names += [fold(self.p.hesap_adi), fold(self.p.hesap_adi.lstrip("@"))]
        return any(n and n in t for n in names)

    def brand_label(self):
        return self.p.hesap_adi or self.p.reklam_veren or "@[reklam veren]"

    # ana akış -------------------------------------------------------------
    def run(self):
        p = self.p
        if p.kareler and not self.frames:
            self.frames = [(p.base / k) if not Path(k).is_absolute() else Path(k) for k in p.kareler]
        self.ocr_lang = tesseract_langs() if self.frames else None
        if self.ocr_lang:
            for f in self.frames:
                if Path(f).exists():
                    self.ocr_text[str(f)] = ocr(Path(f), self.ocr_lang)
        self.check_missing()
        self.etiket()
        self.etkileyici()
        self.yapay_zeka()
        self.indirim()
        self.saglik()
        self.cocuk()
        self.karsilastirma()
        self.cevre_diger()
        self.set("DGR-04", "BILGI", "Yaptırım ve sorumluluk özeti.")
        for rid in self.rules:
            if rid not in self.results:
                self.results[rid] = {"id": rid, "durum": "UYGULANMAZ", "bulgu": ""}
        return self

    def check_missing(self):
        p, d = self.p, self.p.d
        if d.get("ticari_iliski") is None:
            self.eksik.append("ticari_iliski (evet / hayir / bilinmiyor) — boş bırakıldığı için 'bilinmiyor' sayıldı")
        if not isinstance(p.yz, dict) or p.yz.get("kullanildi") is None:
            self.eksik.append("yapay_zeka.kullanildi — yapay zekâ kontrolü yalnız metindeki ifadelere göre yapıldı")
        if self.bicim_in("video") and not p.ekran and not self.frames:
            self.eksik.append("ekran_yazilari veya kareler — ekrandaki etiket kontrol edilemedi")
        if self.bicim_in("video") and p.sure is None:
            self.eksik.append("sure_sn — etiketin süre boyunca kalıp kalmadığı hesaplanamadı")
        if p.ticari != "hayir" and d.get("filtre") is None and not self.bicim_in("sesli"):
            self.eksik.append("filtre (evet / hayir)")
        if p.ticari != "hayir" and d.get("urunu_deneyimledi") is None:
            self.eksik.append("urunu_deneyimledi (evet / hayir)")
        if p.ticari != "hayir" and not (p.reklam_veren or p.hesap_adi):
            self.eksik.append("reklam_veren / reklam_veren_hesap")

    # ETİKET ---------------------------------------------------------------
    def etiket(self):
        p = self.p
        signals = self.kw("ticari_sinyal", p.tum_metin)
        if p.ticari == "evet":
            kind = ", ".join(p.iliski) if p.iliski else "türü belirtilmedi"
            self.set("ETK-01", "GECTI", f"Ticari ilişki beyan edildi ({kind}).")
        elif p.ticari == "bilinmiyor":
            self.set("ETK-01", "UZMANA_SOR",
                     "Ticari ilişki 'bilinmiyor'. Daha sıkı yorumla etiket kuralları uygulandı."
                     + (f" Metinde ticari sinyaller var: {self.words(signals)}." if signals else ""))
        else:
            if signals:
                self.set("ETK-01", "UZMANA_SOR",
                         f"'ticari_iliski: hayir' denmiş ama metinde ticari sinyaller var: {self.words(signals)}. "
                         "Yönlendirme, hediye ürün ve çekiliş de reklam sayılır.")
            else:
                self.set("ETK-01", "GECTI", "Ticari ilişki yok; etkileyici etiket kuralları uygulanmadı.")

        brand_own = p.hesap in ("marka_kendi",) and p.ticari != "evet"
        if p.ticari == "hayir" and not brand_own:
            return
        if brand_own:
            self.set("ETK-12", "UYARI", "Paylaşım markanın kendi hesabından; etiket kuralları UYARI olarak gösterildi.")
        sev = "UYARI" if brand_own else "DUZELT"
        story = self.bicim_in("kisa_sureli")
        sesli = self.bicim_in("sesli")
        video = self.bicim_in("video")
        brand = self.brand_label()

        # metin (açıklama / başlık) ----------------------------------------
        if story or sesli:
            label_src = p.ekran_metni if story else p.seslendirme
            src_name = "ekran yazılarında" if story else "seslendirmede"
        else:
            label_src = "\n".join([p.baslik, p.aciklama])
            src_name = "açıklamada" + (" / başlıkta" if p.baslik else "")
        ocr_all = "\n".join(self.ocr_text.values())
        lh = self.label_hits(label_src)
        if story and not lh and ocr_all:
            lh = self.label_hits(ocr_all)
            src_name = "kare OCR metninde"
        weak = self.kw("etiket_yetersiz", label_src + ("\n" + ocr_all if story else ""))
        neg = self.kw("tuketici_izlenimi", p.tum_metin)
        if lh:
            self.set("ETK-02", "GECTI", f"\"{lh[0][1]}\" {src_name} bulundu.")
        else:
            msg = f"{src_name.capitalize()} \"Reklam\" ya da \"Tanıtım\" yok."
            if weak:
                msg += f" Bulunan {self.words(weak)} tek başına yeterli değil (23/A(3))."
            if neg:
                msg += f" Ayrıca {self.words(neg)} ifadesi var."
            self.set("ETK-02", sev, msg)

        if self.brand_in(label_src) or (story and self.brand_in(ocr_all)):
            if lh:
                line = label_src[: lh[0][2]].count("\n")
                label_line = label_src.split("\n")[line] if label_src else ""
                if self.brand_in(label_line):
                    self.set("ETK-03", "GECTI", "Reklam veren adı/hesabı etiketle aynı satırda.")
                else:
                    self.set("ETK-03", "UYARI", "Reklam veren adı içerikte var ama etiketle aynı satırda değil "
                                                "(daha sıkı yorum: aynı satıra alın).")
            else:
                self.set("ETK-03", sev, "Reklam veren adı var ama \"Reklam/Tanıtım\" ifadesiyle birlikte değil.")
        else:
            who = p.hesap_adi or p.reklam_veren or "reklam veren"
            self.set("ETK-03", sev, f"Reklam veren ({who}) {src_name} geçmiyor.")

        # konum -----------------------------------------------------------
        if story or sesli:
            pass  # ETK-05 / ETK-09 bakar
        elif p.platform == "youtube" and self.label_hits(p.baslik):
            self.set("ETK-04", "GECTI", "Etiket YouTube başlığında.")
        elif lh:
            cap = p.aciklama.lstrip("\n ")
            hits = self.label_hits(cap)
            limit = int((self.R.get("gorunur_karakter") or {}).get(p.platform,
                        (self.R.get("gorunur_karakter") or {}).get("diger", 100)))
            if not hits:
                self.set("ETK-04", sev, "Etiket açıklamada değil (yalnız başlıkta); YouTube dışında açıklamaya koyun.")
            else:
                pos = hits[0][2]
                first_nl = cap.find("\n")
                in_first_line = first_nl == -1 or pos < first_nl
                before = cap[:pos]
                if not in_first_line or pos >= limit:
                    where = "ilk satırda değil" if not in_first_line else f"{pos}. karakterde (görünen sınır ~{limit})"
                    self.set("ETK-04", sev, f"Etiket {where}; kullanıcı \"devamı\"na basmadan görmeyebilir.")
                elif re.search(r"[#@]", before):
                    self.set("ETK-04", sev, "Etiketten önce başka etiket/hesap (# veya @) var; 23/A(4)(c) "
                                            "etiketin bunlardan önce gelmesini ister.")
                elif before.strip():
                    self.set("ETK-04", "UYARI", f"Etiket ilk satırda ama önünde metin var (\"{before.strip()[:40]}\"); "
                                                "en başa alın.")
                else:
                    self.set("ETK-04", "GECTI", "Etiket açıklamanın en başında.")
        else:
            self.set("ETK-04", sev, "Etiket olmadığı için konum kontrolü geçemedi.")

        # ekranda etiket ---------------------------------------------------
        if video:
            self._ekran_etiket(sev, story, brand)
        elif self.bicim_in("gorsel") and p.ekran:
            if any(self.label_hits(e["metin"]) for e in p.ekran):
                self.set("ETK-05", "GECTI", "Görselin üstünde de etiket var.")

        # okunabilirlik + arayüz ---------------------------------------------
        if video or (self.bicim_in("gorsel") and (p.ekran or self.frames)):
            note = "Etiketin rengi zeminden ayrışıyor mu, telefonda kolay okunuyor mu? Kareye bakın."
            if self.ocr_text:
                found = [Path(f).name for f, t in self.ocr_text.items() if self.label_hits(t)]
                note += (f" OCR etiketi şu karelerde okudu: {', '.join(found)} (okunabilirlik ipucudur, kanıt değildir)."
                         if found else " OCR hiçbir karede etiketi okuyamadı; yazı küçük ya da kontrastı düşük olabilir.")
            self.set("ETK-06", "MANUEL", note)
            bad = [e for e in p.ekran if self.label_hits(e["metin"])
                   and e["konum"] in ("alt", "sag_alt", "sol_alt", "sag", "en_alt")]
            if bad:
                self.set("ETK-07", "UYARI", f"Etiket konumu \"{bad[0]['konum']}\"; bu bölge platform arayüzüyle "
                                            "(açıklama, düğmeler) örtüşebilir.")
            elif any(self.label_hits(e["metin"]) and e["konum"] for e in p.ekran):
                self.set("ETK-07", "GECTI", "Etiket konumu arayüz bölgesinin dışında görünüyor.")
            elif p.ekran and not any(self.label_hits(e["metin"]) for e in p.ekran):
                self.set("ETK-07", "MANUEL", "Ekranda etiket yok; eklerken üst-orta bölgeye koyun, arayüzle "
                                             "çakışmadığını karede kontrol edin.")
            else:
                self.set("ETK-07", "MANUEL", "Etiket konumu belirtilmedi; kullanıcı adı, düğmeler ve açıklama ile "
                                             "çakışmadığını karede kontrol edin.")

        # sözlü beyan ---------------------------------------------------------
        if video and not story:
            spoken = p.seslendirme.strip()
            long_form = p.platform == "youtube" and self.bicim_in("uzun_video")
            if not spoken:
                if long_form:
                    self.set("ETK-08", "MANUEL", "Seslendirme metni verilmedi; videonun başında sözlü beyan var mı?")
            else:
                head = " ".join(spoken.split()[:40])
                if self.label_hits(head):
                    self.set("ETK-08", "GECTI", "Seslendirmenin başında sözlü reklam beyanı var.")
                else:
                    self.set("ETK-08", sev if long_form else "UYARI",
                             "Seslendirmenin başında \"reklam/tanıtım\" beyanı yok."
                             + ("" if long_form else " (Reels/TikTok için öneri.)"))
                    self.oneriler.append(("Sözlü beyan (videonun başında)",
                                          f"Bu video {p.reklam_veren or brand} reklamı içerir."))
        if sesli:
            spoken = p.seslendirme.strip()
            head = " ".join(spoken.split()[:30])
            if spoken and self.label_hits(head) and self.brand_in(head):
                self.set("ETK-09", "GECTI", "Kaydın başında reklam veren adıyla sözlü beyan var.")
            else:
                self.set("ETK-09", sev, "Kaydın başında \"[reklam veren] hakkında reklam/tanıtım içerir.\" beyanı "
                                        "bulunamadı." if spoken else "Seslendirme metni verilmedi.")
                self.oneriler.append(("Sözlü beyan (kaydın başında, reklamdan hemen önce, ortada ve sonda)",
                                      f"{p.reklam_veren or brand} hakkında reklam içerir."))

        # parçalar / çapraz -----------------------------------------------------
        parca = int(num(p.d.get("parca_sayisi")) or 1)
        if parca > 1:
            if yes(p.d.get("her_parcada_etiket")):
                self.set("ETK-10", "GECTI", f"{parca} parçanın her birinde etiket var (beyan).")
            else:
                self.set("ETK-10", sev, f"İçerik {parca} parçaya yayılıyor; her parçada etiket olduğu beyan edilmedi.")
        elif p.bicim == "carousel" and p.ekran and not any(self.label_hits(e["metin"]) for e in p.ekran):
            self.set("ETK-10", "UYARI", "Carousel'in ilk karesinde etiket yok (öneri).")
        cross = as_list(p.d.get("capraz_paylasim"))
        if cross:
            self.set("ETK-11", "UYARI", f"Aynı içerik şuralarda da paylaşılacak: {', '.join(map(str, cross))}. "
                                        "Her birine etiketi ayrıca ekleyin.")
        if yes(p.d.get("platform_ortaklik_etiketi")):
            self.set("ETK-13", "GECTI" if lh else "UYARI",
                     "Platformun ücretli ortaklık aracı açık" + ("; metinde de \"Reklam/Tanıtım\" var." if lh
                                                               else " ama metinde \"Reklam/Tanıtım\" yok."))

        # öneriler ---------------------------------------------------------
        if any(self.results.get(r, {}).get("durum") in ("DUZELT", "UYARI") for r in ("ETK-02", "ETK-03", "ETK-04")):
            if not (story or sesli):
                if "hediye_urun" in p.iliski:
                    line = f"Reklam | {brand} tarafından sağlandı."
                else:
                    line = f"Reklam | {brand}"
                self.oneriler.insert(0, ("Açıklamanın İLK satırı", line))

    def _ekran_etiket(self, sev, story, brand):
        p = self.p
        lab = [e for e in p.ekran if self.label_hits(e["metin"])]
        first_ocr = None
        if self.ocr_text:
            first = str(self.frames[0])
            first_ocr = bool(self.label_hits(self.ocr_text.get(first, "")))
        if not lab and first_ocr is None:
            if not p.ekran and self.frames:
                self.set("ETK-05", "MANUEL", "Ekran yazıları girilmedi ve OCR yok; ilk karede ve (story ise) tüm karelerde "
                                             "\"REKLAM · " + brand + "\" yazısı var mı, gözle bakın.")
            else:
                self.set("ETK-05", sev, "Ekranda \"Reklam/Tanıtım\" yazısı yok"
                         + (" (story'de açıklama alanı olmadığı için ekran yazısı şart)." if story else "."))
            self._oner_ekran(brand)
            return
        if not lab and first_ocr:
            self.set("ETK-05", "GECTI", "OCR ilk karede etiketi okudu (süre kontrolü için ekran_yazilari girin).")
            return
        if not lab and first_ocr is False:
            self.set("ETK-05", sev, "OCR ilk karede etiket okuyamadı ve ekran yazılarında etiket yok.")
            self._oner_ekran(brand)
            return
        starts = [e["bas"] if e["bas"] is not None else 0.0 for e in lab]
        if min(starts) > 0.5:
            self.set("ETK-05", sev, f"Ekrandaki etiket {min(starts):g}. saniyede başlıyor; ilk kareden itibaren olmalı.")
            self._oner_ekran(brand)
            return
        if not any(self.brand_in(e["metin"]) for e in lab):
            if story:
                self.set("ETK-03", sev, "Story'de reklam veren adı/hesabı ekrandaki etiketle birlikte yok.")
        covered = self._coverage(lab)
        if p.sure is None:
            self.set("ETK-05", "GECTI" if not story else "MANUEL",
                     "Etiket ilk kareden itibaren ekranda." + (" Süre bilinmiyor; story'de tüm süre boyunca "
                                                               "kalmalı." if story else ""))
            return
        if covered >= p.sure - 0.5:
            self.set("ETK-05", "GECTI", f"Etiket 0–{p.sure:g} sn boyunca ekranda.")
        elif story:
            self.set("ETK-05", sev, f"Story'de etiket {covered:g}/{p.sure:g} sn görünüyor; paylaşım süresince kalmalı.")
            self._oner_ekran(brand)
        else:
            self.set("ETK-05", "UYARI", f"Etiket ilk karede var ama {covered:g}/{p.sure:g} sn görünüyor; tüm süre "
                                        "boyunca kalması önerilir (daha sıkı yorum).")
            self._oner_ekran(brand)

    def _coverage(self, lab):
        iv = sorted(((e["bas"] or 0.0), (e["bit"] if e["bit"] is not None else (self.p.sure or 0.0))) for e in lab)
        total, cur_s, cur_e = 0.0, None, None
        for s, e in iv:
            if cur_e is None or s > cur_e:
                if cur_e is not None:
                    total += cur_e - cur_s
                cur_s, cur_e = s, e
            else:
                cur_e = max(cur_e, e)
        if cur_e is not None:
            total += cur_e - cur_s
        return round(total, 2)

    def _oner_ekran(self, brand):
        dur = f"0–{self.p.sure:g} sn" if self.p.sure else "ilk kareden sona kadar"
        self.oneriler.append(("Ekran yazısı (" + dur + ", üst-orta, düz renkli kutu üstünde)", f"REKLAM · {brand}"))

    # ETKİLEYİCİ -------------------------------------------------------------
    def etkileyici(self):
        p = self.p
        if p.ticari == "hayir":
            return
        bought = self.kw("satin_aldim", p.tum_metin)
        if "hediye_urun" in p.iliski:
            if bought:
                self.set("ETY-01", "DUZELT", f"Ürün hediye ama metinde {self.words(bought)} geçiyor.")
            else:
                self.set("ETY-01", "GECTI", "Hediye ürün satın alınmış gibi gösterilmiyor.")
        exp = yes(p.d.get("urunu_deneyimledi"))
        if exp is False:
            self.set("ETY-02", "DUZELT", "Ürünü henüz deneyimlemediğiniz belirtildi.")
        elif exp is None:
            self.set("ETY-02", "MANUEL", "Ürünü gerçekten kullandınız mı? (urunu_deneyimledi)")
        else:
            self.set("ETY-02", "GECTI", "Ürünün deneyimlendiği beyan edildi.")
        filt = yes(p.d.get("filtre"))
        if filt:
            said = self.kw("filtre_beyan", "\n".join([p.aciklama, p.ekran_metni] + list(self.ocr_text.values())))
            if said:
                self.set("ETY-03", "GECTI", "Filtre kullanımı belirtilmiş.")
            else:
                self.set("ETY-03", "DUZELT", "Filtre/efekt kullanıldı ama belirtilmemiş.")
                self.oneriler.append(("Filtre beyanı (ekranda ve açıklamada)", "Bu görüntüde filtre kullanılmıştır."))
        elif filt is False:
            self.set("ETY-03", "GECTI", "Filtre/efekt kullanılmadığı beyan edildi.")
        elif filt is None and not self.bicim_in("sesli"):
            self.set("ETY-03", "MANUEL", "Görüntüye filtre/efekt uygulandı mı? Uygulandıysa belirtin.")
        neg = self.kw("tuketici_izlenimi", p.tum_metin)
        if neg:
            self.set("ETY-04", "DUZELT", f"Metinde {self.words(neg)} geçiyor.")

    # YAPAY ZEKÂ -------------------------------------------------------------
    def yapay_zeka(self):
        p, yz = self.p, self.p.yz if isinstance(self.p.yz, dict) else {}
        used = yes(yz.get("kullanildi"))
        neler = [fold(str(x)) for x in as_list(yz.get("neler"))]
        if yes(yz.get("gercek_kisi_kopyasi")):
            self.set("YZ-03", "DUZELT", "Gerçek bir kişinin yapay zekâ kopyası kullanıldığı belirtildi; ürünü kullanmış "
                                        "ya da önermiş gibi gösteriliyorsa bu reklam yapılamaz. Beyan bunu düzeltmez.")
        if used is False:
            if self.kw("yz_beyan", p.tum_metin):
                self.set("YZ-01", "GECTI", "Yapay zekâ kullanılmadı denmiş ama metinde yapay zekâ beyanı var; "
                                           "girdiyi kontrol edin.")
            else:
                self.set("YZ-01", "GECTI", "Yapay zekâ kullanılmadığı beyan edildi.")
            return
        if not used:
            return
        heavy = {"urun_gorseli", "sonuc", "kisi", "dijital_karakter", "ses", "once_sonra", "ses_klonu"}
        light = {"arka_plan", "metin", "duzenleme", "altyazi", "renk"}
        caption_txt = "\n".join([p.baslik, p.aciklama])
        screen_txt = "\n".join([p.ekran_metni] + list(self.ocr_text.values()))
        c_ok = bool(self.kw("yz_beyan", caption_txt))
        s_ok = bool(self.kw("yz_beyan", screen_txt))
        visual = not self.bicim_in("sesli")
        hv = [n for n in neler if n in heavy] or ([] if neler else ["belirtilmedi"])
        tr = {"urun_gorseli": "ürün görselleri", "sonuc": "sonuç görüntüleri", "kisi": "kişi görüntüleri",
              "dijital_karakter": "dijital karakter", "ses": "ses", "once_sonra": "önce/sonra görüntüleri",
              "ses_klonu": "ses", "belirtilmedi": "görseller"}
        what = ", ".join(uniq(tr.get(n, n) for n in hv))
        if hv:
            where_ok = c_ok and (s_ok or not visual)
            if where_ok:
                self.set("YZ-01", "GECTI", "Yapay zekâ beyanı açıklamada" + (" ve ekranda." if visual else "."))
            else:
                missing = [x for x, ok in (("açıklamada", c_ok), ("ekranda", s_ok or not visual)) if not ok]
                self.set("YZ-01", "DUZELT", f"Yapay zekâ ile üretilen {what} için beyan {' ve '.join(missing)} yok"
                                            + (" (hem açıklama hem ekran istenir: daha sıkı yorum)." if visual else "."))
                self.oneriler.append(("Yapay zekâ beyanı (açıklamanın 2. satırı + ekranda, görselin üstünde)",
                                      f"Bu reklamdaki {what} yapay zekâ ile oluşturulmuştur."))
            if "dijital_karakter" in neler:
                self.set("YZ-02", "GECTI" if where_ok else "DUZELT",
                         "Dijital karakter için beyan " + ("var." if where_ok else "eksik."))
        light_used = [n for n in neler if n in light]
        if light_used and not hv:
            self.set("YZ-04", "UYARI", f"Yapay zekâ yalnız şu işlerde kullanılmış: {', '.join(light_used)}. "
                                       + ("Beyan var." if (c_ok or s_ok) else "Beyan yok; kapsam belirsiz."))

    # İNDİRİM ---------------------------------------------------------------
    def indirim(self):
        p = self.p
        ad_txt = "\n".join([p.baslik, p.aciklama, p.ekran_metni, p.seslendirme] + list(self.ocr_text.values()))
        f = fold(ad_txt)
        words = self.kw("indirim_sinyal", ad_txt)
        pcts = [int(x) for x in re.findall(r"%\s?(\d{1,2})(?!\d)", f) + re.findall(r"(?<!\d)(\d{1,2})\s?%", f)]
        price_rx = r"\d[\d.,]*\s*(?:tl|₺|turk lirasi)"
        has_price = bool(re.search(price_rx, f))
        ind = p.indirim
        has_block = any(v not in (None, "") for k, v in ind.items() if k not in ("urun_turu",))
        if not (words or has_block or (pcts and has_price)):
            # yalnız fiyat/vergi/taksit kuralları
            self._fiyat_genel(ad_txt)
            return
        hits = [w[1] for w in words] + [f"%{x}" for x in pcts]
        indirimli = num(ind.get("indirimli_fiyat"))
        onceki = num(ind.get("onceki_fiyat"))
        en_dusuk = num(ind.get("son_10_gun_en_dusuk"))
        tur = fold(str(ind.get("urun_turu") or "mal"))
        bas = str(ind.get("baslangic") or "")
        bit = str(ind.get("bitis") or "")
        stok = num(ind.get("stok_adedi"))

        # FYT-01: metinde önceki fiyat, tarih, stok -----------------------------
        miss = []
        prices = re.findall(r"(\d[\d.,]*)\s*(?:tl|₺)", f)
        prev_shown = (onceki is not None and any(abs((num(x) or -1) - onceki) < 0.01 for x in prices)) \
            or bool(re.search(r"onceki fiyat|indirimden once|" + r"\d[\d.,]*\s*(?:tl|₺)?\s*yerine", f)) \
            or len(set(prices)) >= 2
        if not prev_shown:
            miss.append("indirimden önceki fiyat")
        months = "ocak|subat|mart|nisan|mayis|haziran|temmuz|agustos|eylul|ekim|kasim|aralik"
        date_hits = re.findall(r"\b\d{1,2}[./-]\d{1,2}(?:[./-]\d{2,4})?\b|\b\d{1,2}\s*(?:-|–)?\s*\d{0,2}\s*(?:" + months + r")",
                               f)
        if len(date_hits) < 1 or not re.search(r"(?:-|–|ile|arasi|kadar|son gun|bitis|gecerli)", f):
            miss.append("indirimin başlangıç ve bitiş tarihleri")
        if stok is not None and not re.search(r"(?<!\d)" + str(int(stok)) + r"(?!\d)", f):
            miss.append(f"sınırlı miktar ({int(stok)} adet)")
        if miss:
            hits = list({fold(h): h for h in hits}.values())
            self.set("FYT-01", "DUZELT", f"İndirim ibaresi var ({', '.join(hits)[:80]}) ama metinde şunlar yok: "
                                         + ", ".join(miss) + ".")
        else:
            self.set("FYT-01", "GECTI", "Önceki fiyat ve tarihler metinde görünüyor.")

        # FYT-02: referans fiyat -------------------------------------------------
        start_date = bas or p.yayin
        old_rule = start_date[:10] < self.R.get("yururluk_2026", "2026-08-01") if start_date else False
        days = 30 if old_rule else 10
        ref = None
        if tur in ("hizmet", "cabuk_bozulan"):
            self.set("FYT-02", "BILGI", "Hizmet / çabuk bozulan mal: indirimli fiyattan bir önceki fiyat esas alınır.")
            ref = onceki
        elif onceki is not None and en_dusuk is not None:
            ref = min(onceki, en_dusuk)
            if onceki > en_dusuk + 0.005:
                self.set("FYT-02", "DUZELT", f"Gösterilen önceki fiyat {fmt_tl(onceki)}, ama indirimden önceki {days} günün "
                                             f"en düşük fiyatı {fmt_tl(en_dusuk)}. Referans {fmt_tl(en_dusuk)} olmalı."
                         + (" (Bu indirim 01.08.2026 öncesi başladığı için 30 gün kuralı uygulandı.)" if old_rule else ""))
            else:
                self.set("FYT-02", "GECTI", f"Önceki fiyat ({fmt_tl(onceki)}) son {days} günün en düşüğünü aşmıyor.")
        elif onceki is not None:
            self.set("FYT-02", "MANUEL", f"Önceki fiyat {fmt_tl(onceki)}; indirimden önceki {days} günün en düşük fiyatı "
                                         "girilmedi (son_10_gun_en_dusuk). Fiyat geçmişini kontrol edin.")
            ref = onceki
        else:
            self.set("FYT-02", "MANUEL", f"Önceki fiyat girilmedi; üstü çizili fiyat son {days} günün en düşük fiyatı mı?")

        # FYT-03: kanal ----------------------------------------------------------
        sk, ok_ = str(ind.get("satis_kanali") or ""), str(ind.get("onceki_fiyat_kanali") or "")
        if sk and ok_:
            if fold(sk).strip() != fold(ok_).strip():
                self.set("FYT-03", "DUZELT", f"İndirim {sk} kanalında ama önceki fiyat {ok_} kanalından alınmış.")
            else:
                self.set("FYT-03", "GECTI", f"Önceki fiyat aynı kanaldan ({sk}).")
        else:
            self.set("FYT-03", "MANUEL", "Ürün başka kanallarda da satılıyorsa önceki fiyat yalnız indirimin yapıldığı "
                                         "kanaldan alınmalı (satis_kanali / onceki_fiyat_kanali).")

        # FYT-04: oran -----------------------------------------------------------
        if ref and indirimli is not None and ref > 0:
            real = (ref - indirimli) / ref * 100
            if pcts and max(pcts) > real + 0.5:
                self.set("FYT-04", "DUZELT", f"Metinde %{max(pcts)} yazıyor; doğru referansla gerçek indirim "
                                             f"%{int(real)} ({fmt_tl(ref)} → {fmt_tl(indirimli)}).")
            elif pcts:
                self.set("FYT-04", "GECTI", f"İlan edilen oran (%{max(pcts)}) gerçek oranı (%{real:.0f}) aşmıyor.")
            dates = f"{self._tr_date(bas)}–{self._tr_date(bit)}" if (bas and bit) else "GG.AA–GG.AA.YYYY"
            line = (f"İndirimden önceki fiyat: {fmt_tl(ref)} · İndirimli: {fmt_tl(indirimli)} (%{int(real)}) · "
                    f"Kampanya: {dates}")
            if stok is not None:
                line += f" · {int(stok)} adet ile sınırlı"
            if any(self.results.get(r, {}).get("durum") == "DUZELT" for r in ("FYT-01", "FYT-02", "FYT-04")):
                self.oneriler.append(("İndirim bilgisi (açıklamada ve ekranda)", line))
        elif pcts:
            self.set("FYT-04", "MANUEL", "İndirim oranını doğrulamak için indirimli_fiyat ve son_10_gun_en_dusuk girin.")

        kos = self.kw("kosullu", ad_txt)
        if kos:
            self.set("FYT-08", "UYARI", f"Koşullu indirim ifadesi: {self.words(kos)}.")
        self._fiyat_genel(ad_txt)

    def _fiyat_genel(self, ad_txt):
        f = fold(ad_txt)
        vh = self.kw("vergi_haric", ad_txt)
        if vh:
            self.set("FYT-05", "DUZELT", f"Metinde {self.words(vh)} var; tüketici reklamında fiyat vergiler dahil olmalı.")
        st = self.kw("stok_sinyal", ad_txt)
        if st:
            if self.kw("stok_sayi", ad_txt):
                self.set("FYT-06", "GECTI", "Stok/süre sınırı sayıyla belirtilmiş.")
            else:
                self.set("FYT-06", "DUZELT", f"{self.words(st)} yazıyor ama stok miktarı yazılmamış.")
        if self.kw("taksit", ad_txt):
            if re.search(r"\d+\s*taksit", f) and "toplam" in f:
                self.set("FYT-07", "GECTI", "Taksit sayısı ve toplam fiyat var.")
            else:
                self.set("FYT-07", "DUZELT", "Taksitten söz ediliyor ama taksit sayısı ve/veya toplam fiyat yok.")

    @staticmethod
    def _tr_date(s):
        m = re.match(r"(\d{4})-(\d{2})-(\d{2})", str(s))
        return f"{m.group(3)}.{m.group(2)}.{m.group(1)}" if m else str(s)

    # SAĞLIK ----------------------------------------------------------------
    def saglik(self):
        p = self.p
        t = p.tum_metin + "\n" + "\n".join(self.ocr_text.values())
        red = self.kw("saglik_kirmizi", t)
        if red:
            self.set("SAG-01", "UZMANA_SOR", f"Sağlık iddiası olabilecek ifadeler: {self.words(red)}.")
        prof = self.kw("saglik_meslek", t)
        if prof or p.kategori == "saglik_hizmeti":
            self.set("SAG-02", "UZMANA_SOR", "Sağlık mesleği/kuruluşu geçiyor" + (f": {self.words(prof)}." if prof else "."))
        supp = p.kategori == "takviye" or bool(self.kw("takviye", t))
        if supp:
            rep = self.kw("takviye_yerine", t)
            cmp_ = self.kw("karsilastirma", t)
            if rep:
                self.set("SAG-03", "DUZELT", f"Takviye ürün ve {self.words(rep)} ifadesi: normal beslenmenin yerine "
                                             "geçer izlenimi.")
            elif cmp_ and p.kategori == "takviye":
                self.set("SAG-03", "DUZELT", f"Takviye edici gıdada karşılaştırma ifadesi: {self.words(cmp_)}.")
        yasak_kat = [fold(str(x)) for x in self.S.get("yasakli_kategori", [])]
        if p.kategori in yasak_kat:
            self.set("SAG-04", "DUZELT", f"Ürün kategorisi \"{p.kategori}\": reklamı yasak kategoride.")
        else:
            bad = self.kw("yasakli_urun", t)
            if bad:
                self.set("SAG-04", "UZMANA_SOR", f"Reklamı yasak bir ürün/hizmet olabilir: {self.words(bad)}.")

    # ÇOCUK -----------------------------------------------------------------
    def cocuk(self):
        p = self.p
        c = p.cocuk if isinstance(p.cocuk, dict) else {}
        t = p.tum_metin
        kws = self.kw("cocuk", t)
        flagged = yes(c.get("hedef_kitle")) or yes(c.get("oynuyor"))
        if flagged or kws:
            why = "girdide işaretli" if flagged else f"metinde {self.words(kws, 3)}"
            self.set("COC-01", "MANUEL",
                     f"Çocuklara yönelik olabilir ({why}). Kontrol: tehlikeli davranış yok; gerçek dışı beklenti yok; "
                     "akran üstünlüğü mesajı yok; ebeveyni ikna etmeye teşvik yok; gerekli ek ürün ve güvenlik "
                     "uyarıları var.")
            risky = self.kw("cocuk_riskli", t)
            if risky and flagged:
                self.set("COC-02", "DUZELT", f"Çocuklara yönelik reklamda {self.words(risky)} ifadesi.")
            elif risky:
                self.set("COC-02", "UYARI", f"Çocuklara yönelikse sorunlu ifade: {self.words(risky)}.")
            if p.kategori in ("gida", "atistirmalik", "icecek"):
                self.set("COC-04", "UZMANA_SOR", "Gıda ürünü + çocuk kitlesi: ürün aşırı tüketimi önerilmeyen "
                                                 "(kırmızı) kategoride mi?")
        h = p.hedef if isinstance(p.hedef, dict) else {}
        if yes(h.get("cocuk_profilleme")):
            self.set("COC-03", "DUZELT", "Çocuklara kişisel veriye dayalı profilleme ile hedefleme işaretli.")

    # KARŞILAŞTIRMA ---------------------------------------------------------
    def karsilastirma(self):
        p = self.p
        k = p.krs if isinstance(p.krs, dict) else {}
        if yes(k.get("rakip_adi_var")):
            self.set("KRS-01", "DUZELT", "Rakibin adı/markası/logosu reklamda yer alıyor (girdide işaretli).")
        cmp_ = self.kw("karsilastirma", p.tum_metin)
        if cmp_:
            self.set("KRS-02", "UZMANA_SOR", f"Karşılaştırma ifadesi: {self.words(cmp_)}. Rakip adı geçiyor mu, "
                                             "belgeli mi?")
        sup = self.kw("ustunluk", p.tum_metin)
        if sup:
            self.set("KRS-03", "UYARI", f"Üstünlük iddiası: {self.words(sup)}. İspat belgesi var mı?")

    # ÇEVRE + DİĞER ---------------------------------------------------------
    def cevre_diger(self):
        p = self.p
        t = p.tum_metin
        ce = self.kw("cevre", t)
        if ce:
            self.set("CEV-01", "UYARI", f"Çevresel beyan: {self.words(ce)}. Hangi bölüm/süreç, hangi belge, ölçüm "
                                        "yöntemi bağlantısı?")
        yo = self.kw("yorum", t)
        if yo:
            self.set("DGR-01", "UYARI", f"Tüketici değerlendirmesi kullanımı: {self.words(yo)}.")
        od = self.kw("odul", t) + self.kw("akademik", t)
        if od:
            self.set("DGR-02", "UYARI", f"Ödül/unvan ifadesi: {self.words(od)}.")
        ck = self.kw("cekilis", t)
        if ck or "cekilis" in p.iliski:
            self.set("DGR-03", "UYARI", "Çekiliş/yarışma içeriği" + (f": {self.words(ck)}." if ck else "."))


# --------------------------------------------------------------------------- rapor
def cite(k: dict) -> str:
    return f"{k['belge']}, m.{k['madde']}"


def verdict(counts):
    if counts.get("DUZELT"):
        return "DÜZELTME GEREKLİ"
    if counts.get("UZMANA_SOR"):
        return "UZMANA DANIŞIN"
    if counts.get("UYARI") or counts.get("MANUEL"):
        return "KONTROL LİSTESİNİ TAMAMLAYIN"
    return "BELİRGİN BİR SORUN BULUNMADI"


def build_caption_draft(ch: Checker):
    """Etiket satırı en üstte; yapay zekâ beyanı ikinci satırda; indirim rakamları düzeltilmiş."""
    p = ch.p
    if ch.bicim_in("kisa_sureli") or ch.bicim_in("sesli"):
        return None
    st = {rid: ch.results.get(rid, {}).get("durum") for rid in ch.results}
    need = [rid for rid in ("ETK-02", "ETK-03", "ETK-04", "YZ-01", "FYT-01", "FYT-02", "FYT-04", "FYT-06", "ETY-03")
            if st.get(rid) in ("DUZELT", "UYARI")]
    if not need:
        return None
    sug = dict(uniq(ch.oneriler))
    first = next((v for k, v in ch.oneriler if k.startswith("Açıklamanın İLK")), None)
    body = p.aciklama.strip("\n")
    if first:
        # yeni etiket satırına taşınan etiketleri gövdeden çıkar
        body = re.sub(r"(?im)^\s*#?(reklam|tan[ıi]t[ıi]m)\s*[|:·-]?\s*(@\S+)?\s*$\n?", "", body)
        body = re.sub(r"(?i)(?<!\w)#(reklam|tan[ıi]t[ıi]m)(?!\w)\s?", "", body)
        head, rest = first, body
    else:
        lines = body.split("\n")
        head, rest = lines[0], "\n".join(lines[1:])
    ind = p.indirim
    ref = None
    onceki, en_dusuk, indirimli = num(ind.get("onceki_fiyat")), num(ind.get("son_10_gun_en_dusuk")), \
        num(ind.get("indirimli_fiyat"))
    if onceki is not None and en_dusuk is not None:
        ref = min(onceki, en_dusuk)
    if ref is not None and st.get("FYT-02") == "DUZELT" and onceki is not None:
        for form in uniq([fmt_tl(onceki), f"{int(onceki)} TL", f"{int(onceki)}TL", f"{int(onceki)} ₺"]):
            rest = rest.replace(form, fmt_tl(ref))
    if ref and indirimli is not None and st.get("FYT-04") == "DUZELT":
        real = int((ref - indirimli) / ref * 100)
        rest = re.sub(r"%\s?\d{1,2}(?!\d)", f"%{real}", rest)
        rest = re.sub(r"(?<!\d)\d{1,2}\s?%", f"%{real}", rest)
    if st.get("FYT-06") == "DUZELT":
        rest = re.sub(r"(?i)stoklarla sınırlı", "[N] adet ile sınırlı", rest)
    out = [head]
    yz = next((v for k, v in ch.oneriler if k.startswith("Yapay zekâ")), None)
    if yz:
        out.append(yz)
    if rest.strip():
        out.append(rest.strip("\n"))
    indl = next((v for k, v in ch.oneriler if k.startswith("İndirim bilgisi")), None)
    if indl:
        out.append(indl)
    fl = sug.get("Filtre beyanı (ekranda ve açıklamada)")
    if fl:
        out.append(fl)
    return "\n".join(x for x in out if x)


def render_md(ch: Checker, post_name: str) -> str:
    R, p = ch.R, ch.p
    res = ch.results
    counts = {d: sum(1 for r in res.values() if r["durum"] == d) for d in DURUM_SIRA}
    out = []
    w = out.append
    w("# Reklam Etiketi Kontrol Raporu\n")
    w(f"> **{DISCLAIMER}** Bu rapor, kural dosyasındaki maddelere göre otomatik bir kontrol listesidir; "
      f"kesin sonuç için bir hukukçuya danışın. Kural dosyası sürümü {R.get('surum')} "
      f"(kaynaklar {Checker._tr_date(R.get('kural_tarihi'))} tarihinde okundu).\n")
    w("| | |\n|---|---|")
    w(f"| Gönderi | `{post_name}` |")
    w(f"| Platform / biçim | {p.platform} / {p.bicim} |")
    who = " ".join(x for x in [p.reklam_veren, f"({p.hesap_adi})" if p.hesap_adi else ""] if x) or "belirtilmedi"
    w(f"| Reklam veren | {who} |")
    rel = p.ticari + (f" ({', '.join(p.iliski)})" if p.iliski else "")
    w(f"| Ticari ilişki | {rel} |")
    if p.yayin:
        w(f"| Planlanan yayın | {Checker._tr_date(p.yayin)} |")
    w(f"| Kontrol tarihi | {Checker._tr_date(ch.today)} |\n")
    if p.yayin and p.yayin[:10] < R.get("yururluk_2026", "2026-08-01"):
        w("> Not: yayın tarihi 01.08.2026'dan önce. 23/A, 18(8) gibi 2026 hükümleri o tarihte yürürlükte değildi; "
          "rapor yine de güncel (daha sıkı) kurallara göre yazıldı.\n")
    w(f"## Sonuç: {verdict(counts)}\n")
    w(" · ".join(f"{DURUM_ETIKET[d]} {counts[d]}" for d in DURUM_SIRA if d != "UYGULANMAZ")
      + f" · uygulanmayan {counts['UYGULANMAZ']}\n")

    w("## Kontrol listesi\n")
    order = list(KATEGORI_AD)
    shown = [r for r in res.values() if r["durum"] not in ("GECTI", "UYGULANMAZ", "BILGI")]
    shown.sort(key=lambda r: (order.index(ch.rules[r["id"]]["kategori"]), DURUM_SIRA.index(r["durum"]), r["id"]))
    if not shown:
        w("Açık madde yok.\n")
    cur = None
    for r in shown:
        rule = ch.rules[r["id"]]
        if rule["kategori"] != cur:
            if cur is not None:
                w("")
            cur = rule["kategori"]
            w(f"### {KATEGORI_AD[cur]}\n")
        w(f"- **[{DURUM_ETIKET[r['durum']]}] {r['id']}: {rule['baslik']}**")
        if r["bulgu"]:
            w(f"  - Bulgu: {r['bulgu']}")
        w(f"  - Ne yapmalı: {str(rule['duzeltme']).strip()}")
        w(f"  - Dayanak: {'; '.join(cite(k) for k in rule['kaynak'])}")
        if rule.get("belirsizlik"):
            w(f"  - Belirsizlik: {str(rule['belirsizlik']).strip()}")
    w("")

    if ch.oneriler:
        w("## Önerilen düzeltmeler (kopyala-yapıştır)\n")
        for k, v in uniq(ch.oneriler):
            w(f"- {k}:\n\n  ```text\n  {v}\n  ```")
        draft = build_caption_draft(ch)
        if draft:
            w("\n**Düzeltilmiş açıklama taslağı** (yalnız etiket, beyan ve indirim satırlarını düzeltir; sağlık, "
              "karşılaştırma gibi diğer maddeleri siz düzeltin; kendi üslubunuza uyarlayın):\n")
            w("```text\n" + draft + "\n```")
        w("")

    passed = [r for r in res.values() if r["durum"] in ("GECTI", "BILGI")]
    if passed:
        w("## Geçen kontroller ve bilgiler\n")
        for r in sorted(passed, key=lambda r: (order.index(ch.rules[r["id"]]["kategori"]), r["id"])):
            rule = ch.rules[r["id"]]
            w(f"- [{DURUM_ETIKET[r['durum']]}] {r['id']}: {rule['baslik']} — {r['bulgu'] or ''} "
              f"(Dayanak: {'; '.join(cite(k) for k in rule['kaynak'])})")
        w("")

    if ch.frames or ch.bicim_in("video") or ch.bicim_in("gorsel"):
        w("## Kareler için gözle kontrol listesi\n")
        if ch.frame_note:
            w(f"{ch.frame_note}\n")
        if ch.frames:
            w(("OCR: " + ch.ocr_lang + " ile okundu.") if ch.ocr_lang else
              "OCR yok (tesseract kurulu değil); kareleri gözle kontrol edin.")
            w("")
            for f in ch.frames:
                w(f"- `{f}`")
        else:
            w("Kare verilmedi. Yayından önce taslağın ilk, orta ve son karesine bakın (ya da `--video` / `--kareler`).")
        w("")
        brand = ch.brand_label()
        for item in [
            f"İlk karede \"REKLAM · {brand}\" (ya da \"TANITIM\") yazısı var.",
            "Story ise yazı her karede ve tüm süre boyunca var; çok parçalıysa her parçada var.",
            "Yazı zeminden ayrışıyor (düz renkli kutu), telefonda rahat okunuyor.",
            "Yazı kullanıcı adı, açıklama, beğen/yorum düğmeleri ve ilerleme çubuğuyla örtüşmüyor (üst-orta bölge).",
            "Etiket başka etiketlerden (#, @, çıkartma) önce ve onlardan ayrı görünüyor.",
            "Yapay zekâ ile üretilmiş ürün/kişi/sonuç görüntüsü varsa beyan yazısı o görüntünün üstünde.",
            "İndirim varsa önceki fiyat, indirimli fiyat ve tarihler ekranda okunuyor.",
            "Rakip marka adı, logosu ya da tanınır ambalajı görünmüyor.",
        ]:
            w(f"- [ ] {item}")
        w("")

    if ch.eksik:
        w("## Eksik bilgiler\n")
        for e in ch.eksik:
            w(f"- {e}")
        w("")

    na = sorted(r["id"] for r in res.values() if r["durum"] == "UYGULANMAZ")
    if na:
        w(f"Bu gönderi için uygulanmayan kurallar: {', '.join(na)}.\n")

    # kaynak listesi (gösterilen tüm maddelerin URL'leri)
    used = []
    for r in res.values():
        if r["durum"] == "UYGULANMAZ":
            continue
        for k in ch.rules[r["id"]]["kaynak"]:
            used.append((k["url"], k.get("okunma", "")))
    meta = {s["url"]: s for s in R.get("kaynaklar", [])}
    meta.update({s.get("tam_metin_url"): s for s in R.get("kaynaklar", []) if s.get("tam_metin_url")})
    w("## Dayanak kaynaklar\n")
    for i, (url, ok) in enumerate(uniq(used), 1):
        title = meta.get(url, {}).get("belge", url)
        w(f"{i}. {title} — {url} (okunma: {Checker._tr_date(ok)})")
    w("")
    w("---\n")
    w(f"**{DISCLAIMER}** Mevzuat değişebilir; yayından önce Resmî Gazete ve Ticaret Bakanlığı Reklam Kurulu "
      "duyurularını kontrol edin. Bu araç paylaşım yapmaz, hesaplara bağlanmaz, ağa çıkmaz.")
    return "\n".join(out) + "\n"


def render_json(ch: Checker, post_name: str) -> dict:
    counts = {d: sum(1 for r in ch.results.values() if r["durum"] == d) for d in DURUM_SIRA}
    items = []
    for r in ch.results.values():
        rule = ch.rules[r["id"]]
        items.append({"id": r["id"], "durum": r["durum"], "baslik": rule["baslik"], "kategori": rule["kategori"],
                      "bulgu": r["bulgu"], "duzeltme": str(rule["duzeltme"]).strip(), "kaynak": rule["kaynak"],
                      "belirsizlik": str(rule.get("belirsizlik") or "").strip()})
    return {"uyari": DISCLAIMER, "gonderi": post_name, "kural_surumu": ch.R.get("surum"), "kontrol_tarihi": ch.today,
            "sonuc": verdict(counts), "sayilar": counts, "maddeler": items,
            "oneriler": [{"ne": k, "metin": v} for k, v in uniq(ch.oneriler)], "eksik_bilgiler": ch.eksik}


# --------------------------------------------------------------------------- kural doğrulama
IMPLEMENTED = {
    "ETK-01", "ETK-02", "ETK-03", "ETK-04", "ETK-05", "ETK-06", "ETK-07", "ETK-08", "ETK-09", "ETK-10", "ETK-11",
    "ETK-12", "ETK-13", "ETY-01", "ETY-02", "ETY-03", "ETY-04", "YZ-01", "YZ-02", "YZ-03", "YZ-04", "FYT-01",
    "FYT-02", "FYT-03", "FYT-04", "FYT-05", "FYT-06", "FYT-07", "FYT-08", "SAG-01", "SAG-02", "SAG-03", "SAG-04",
    "COC-01", "COC-02", "COC-03", "COC-04", "KRS-01", "KRS-02", "KRS-03", "CEV-01", "DGR-01", "DGR-02", "DGR-03",
    "DGR-04",
}


def validate_rules(rules: dict) -> list:
    errs = []
    ids = [r.get("id") for r in rules.get("kurallar", [])]
    if len(ids) != len(set(ids)):
        errs.append("tekrarlanan kural id'si")
    for r in rules.get("kurallar", []):
        rid = r.get("id", "?")
        for f in ("id", "baslik", "kategori", "siddet", "kosul", "duzeltme", "kaynak"):
            if not r.get(f):
                errs.append(f"{rid}: '{f}' eksik")
        if r.get("siddet") not in ("DUZELT", "UYARI", "UZMANA_SOR", "MANUEL", "BILGI"):
            errs.append(f"{rid}: geçersiz siddet {r.get('siddet')}")
        if r.get("kategori") not in KATEGORI_AD:
            errs.append(f"{rid}: geçersiz kategori {r.get('kategori')}")
        for k in r.get("kaynak") or []:
            if not str(k.get("url", "")).startswith("https://"):
                errs.append(f"{rid}: kaynak URL'si https değil")
            if not re.match(r"^\d{4}-\d{2}-\d{2}$", str(k.get("okunma", ""))):
                errs.append(f"{rid}: okunma tarihi YYYY-AA-GG değil")
            if not k.get("madde") or not k.get("belge"):
                errs.append(f"{rid}: kaynakta belge/madde eksik")
    missing_code = set(ids) - IMPLEMENTED
    missing_rule = IMPLEMENTED - set(ids)
    if missing_code:
        errs.append(f"kodda karşılığı olmayan kurallar: {sorted(missing_code)}")
    if missing_rule:
        errs.append(f"kural dosyasında olmayan kod kuralları: {sorted(missing_rule)}")
    if rules.get("uyari_metni") != DISCLAIMER:
        errs.append("uyari_metni beklenen ifade değil")
    return errs


# --------------------------------------------------------------------------- main
def main(argv=None):
    ap = argparse.ArgumentParser(description="Reklam Etiketi Kontrolü — " + DISCLAIMER)
    ap.add_argument("gonderi", nargs="?", help="gönderi YAML/JSON dosyası")
    ap.add_argument("--kurallar", default=str(DEFAULT_RULES))
    ap.add_argument("--cikti", help="Markdown raporu bu dosyaya yaz")
    ap.add_argument("--json", dest="json_out", help="JSON raporu bu dosyaya yaz")
    ap.add_argument("--kareler", nargs="*", default=[], help="kare görselleri (PNG/JPG)")
    ap.add_argument("--video", help="videodan kare çıkar (ffmpeg gerekir)")
    ap.add_argument("--ocr", choices=["auto", "kapali"], default="auto")
    ap.add_argument("--tarih", help="rapordaki kontrol tarihi (YYYY-AA-GG); varsayılan bugün")
    ap.add_argument("--sablon", action="store_true", help="boş gönderi şablonunu yaz")
    ap.add_argument("--kurallari-dogrula", action="store_true")
    a = ap.parse_args(argv)

    if a.sablon:
        sys.stdout.write(SABLON)
        return 0
    rules = load_yaml(Path(a.kurallar))
    if a.kurallari_dogrula:
        errs = validate_rules(rules)
        for e in errs:
            print("HATA:", e)
        print(f"{len(rules.get('kurallar', []))} kural, {len(errs)} hata.")
        return 1 if errs else 0
    if not a.gonderi:
        ap.error("gönderi dosyası gerekli (ya da --sablon)")
    gp = Path(a.gonderi)
    if not gp.exists():
        print(f"Dosya yok: {gp}", file=sys.stderr)
        return 2
    try:
        data = json.loads(gp.read_text(encoding="utf-8")) if gp.suffix.lower() == ".json" else load_yaml(gp)
    except Exception as exc:  # noqa: BLE001
        print(f"Girdi okunamadı: {exc}", file=sys.stderr)
        return 2
    if not isinstance(data, dict):
        print("Girdi bir eşleme (anahtar: değer) olmalı.", file=sys.stderr)
        return 2
    post = Post(data, gp.parent)
    frames, note = [Path(x) for x in a.kareler], ""
    if a.video:
        outdir = Path(tempfile.mkdtemp(prefix="reklam-etiketi-kareler-"))
        vf, note = frames_from_video(Path(a.video), outdir)
        frames += vf
    ch = Checker(rules, post, frames, note, a.tarih or _dt.date.today().isoformat())
    if a.ocr == "kapali":
        ch.ocr_lang = None
        tesseract = globals()["tesseract_langs"]
        globals()["tesseract_langs"] = lambda: None
        try:
            ch.run()
        finally:
            globals()["tesseract_langs"] = tesseract
    else:
        ch.run()
    md = render_md(ch, gp.name)
    if a.cikti:
        Path(a.cikti).write_text(md, encoding="utf-8")
        print(f"rapor yazıldı: {a.cikti}")
    else:
        sys.stdout.write(md)
    if a.json_out:
        Path(a.json_out).write_text(json.dumps(render_json(ch, gp.name), ensure_ascii=False, indent=2) + "\n",
                                    encoding="utf-8")
    return 1 if any(r["durum"] == "DUZELT" for r in ch.results.values()) else 0


if __name__ == "__main__":
    sys.exit(main())
