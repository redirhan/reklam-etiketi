# Reklam Etiketi Kontrolü — Turkish ad-disclosure checker (free Claude Code skill)

> **Bu bir hukuki görüş değildir; bilgilendirme amaçlıdır.** (This is not legal advice; it is for information only.)

A Claude Code skill that checks a **planned** Instagram, TikTok, YouTube or podcast post against Turkish
advertising disclosure rules before it goes live. It reads the caption, on-screen text, voice-over transcript and,
optionally, key frames, and writes a checklist with article numbers plus copy-paste fixes. Output is in Turkish.

Made by Redirhan Labs. Free, MIT licence.

## Why now

Turkey's Commercial Advertising and Unfair Commercial Practices Regulation was amended in the Official Gazette of
1 July 2026 (no. 33297), **in force since 1 August 2026**. For influencer content it now requires:

- the word **"Reklam" (advertisement) or "Tanıtım" (promotion)** together with the **advertiser's name or @handle**
  (Art. 23/A(3)); "#işbirliği" (collaboration) alone does not meet this,
- a label visible at first sight, without scrolling, before other tags, distinguishable from the background
  (Art. 23/A(4)),
- clear disclosure of **AI use** that significantly affects purchase decisions, and of human-like AI characters
  (Art. 18(8)); AI clones of real people pretending to use/recommend a product are banned (Art. 27(12)),
- for discounts, the reference price = **lowest price in the 10 days** before the discount, **on the same sales
  channel** (Art. 14(3), 14(5)).

## What it checks

45 rules in 9 groups: disclosure label (word, advertiser, position, on-screen from the first frame, whole duration
for stories, spoken disclosure, audio-only wording, multi-part and cross-posted content), influencer duties
(gifted-as-bought, no experience, filters), AI disclosure, discounts and prices (reference price, channel, inflated
percentage, VAT-exclusive prices, stock limits, instalments), health red flags and banned products, children,
comparative ads, green claims, reviews/awards/giveaways.

Every rule in `rules/kurallar.yaml` carries the source document, article, URL and the date it was read
(27 Oct 2026). Where sources conflict, the stricter rule is encoded and the conflict is written in `belirsizlik`.

## Install

```bash
unzip reklam-etiketi-v1.0.zip -d ~/.claude/skills/
```

Needs Python 3.8+ only. Optional: `tesseract` (frame OCR), `ffmpeg` (frame extraction), PyYAML.

## Use

Ask Claude Code in plain language (Turkish or English): *"Is this reel compliant with the Turkish ad label rules?
Caption: … The brand sent me the product."* Or run it yourself:

```bash
python3 ~/.claude/skills/reklam-etiketi/scripts/kontrol.py --sablon > gonderi.yaml
python3 ~/.claude/skills/reklam-etiketi/scripts/kontrol.py gonderi.yaml --cikti rapor.md --json rapor.json
```

Exit code 1 means at least one "DÜZELT" (fix) item.

## What it does not do

No legal opinion (unclear points are marked "UZMANA SOR", ask an expert). It does not assess sector-specific rules
(health, food, cosmetics). It never posts, never logs in to any account, makes no network or paid API calls, and
never opens a browser.

## Known uncertainties

1. The Official Gazette text makes only "Reklam" or "Tanıtım" mandatory; the 2021 Advertising Board guideline and
   some news reports also list "iş birliği"/"sponsor". The stricter regulation text is encoded.
2. The regulation does not say how long a video label must stay on screen; the checker requires the first frame,
   the whole duration for stories, and recommends the whole duration elsewhere.
3. The scope of the AI-disclosure duty ("significantly affects") is undefined; no prescribed wording.
4. Whether Art. 23/A applies to a brand's own account is unclear.
5. No official record found that the 2021 guideline was updated after the 2026 amendment; its full text was read
   from IAB Türkiye's copy.

## Licence

MIT, see `LICENSE`.
