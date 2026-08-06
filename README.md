# The Complete Hermetic & Rosicrucian Grimoire

A working grimoire of the Western esoteric tradition — twenty-six chapters, 327 pages, 47 diagrams — in which **every source is dated and attributed, and the attribution is allowed to be inconvenient.**

That last clause is the point. Where a teaching commonly presented as ancient turns out to be medieval, early modern or modern, the chapter says so and keeps the practice. Where two sources disagree, both are printed. Where this edition could not reach a text, it names the text and says why.

## Read it

| Edition | File | Best for |
|---|---|---|
| **EPUB** | [`grimoire.epub`](grimoire.epub) — 715 KB | **Phones and e-readers.** Reflowable, follows your font size and dark mode, diagrams are vector so they stay sharp. |
| **PDF** | [`grimoire.pdf`](grimoire.pdf) — 13 MB | The typeset book: 6×9, running heads, folios, a contents page with real page numbers. |
| **HTML** | [`grimoire.html`](grimoire.html) | The source of truth. One self-contained file, no dependencies, sticky navigation, dark mode. |

The PDF and EPUB are generated from the HTML. **Corrections go to `grimoire.html`**; the other two are rebuilt from it.

## What's in it

**The historical spine.** Three of the foundations this subject rests on have documented dating problems, and the book leads with them rather than burying them:

- The **Seven Hermetic Principles** come from *The Kybalion* (1908), a New Thought work — not from ancient Hermeticism. All seven are kept, explained, and dated.
- The **Corpus Hermeticum** is Greek, c. 100–300 CE. Ficino translated it in 1471 believing it older than Moses; Casaubon showed otherwise. That misdating is *why* the Renaissance took Hermeticism seriously.
- The **Zohar** is assigned to a second-century sage. It appears in Castile around 1280 in the hands of Moses de León, and the case that he wrote it was in print from 1851 — reproduced, by Mathers, inside the 1887 translation that carried the text into English magic. The tradition kept the text and dropped the introduction.
- **Enochian was first printed as a warning.** Meric Casaubon published Dee’s angel diaries in 1659 with a preface confirming that the spirits were real and concluding they were evil — and he states the Kelley-was-a-fraud theory himself, as an objection, before rejecting it. The argument has been attached to the corpus since the day it entered print.
- The **Rosicrucian Brotherhood** cannot be shown to have existed. Andreae, who acknowledged writing the *Chymical Wedding*, called the whole affair a *ludibrium* — a lampoon.

Meanwhile the **Greek Magical Papyri** are genuinely ancient, physically extant and provenanced — and they are the part usually left out. That inversion is the argument of the book: the material presented as ancient is mostly early modern, and the genuinely ancient material is the part nobody prints.

**The operative material.** 36 rites given in full, each dated and sourced: the Lesser Banishing Ritual of the Pentagram with Hebrew and pronunciation, the Lesser and Greater Hexagram, the Middle Pillar, godform assumption, scrying, a complete opening and closing, the Solomonic consecrations of water, salt and sword, the Headless Rite from the papyri, dream oracles, the Fourth Pentacle of the Moon, talisman construction, geomancy from the casting to the Judge, Pennsylvania Dutch charms, and the Anglo-Saxon remedies.

**Chapters.** Introduction · The Hermetica and Their Transmission · Sacred Geometry & Symbols · Kabbalah and Its Transmission · Alchemical Foundations · The Emerald Tablet · Meditation Practices · Ritual Foundations · The Greek Magical Papyri · The Solomonic Tradition · Rosicrucian Mysteries · Advanced Practices · Enochian · Protection & Banishing · Healing & Wellness · Prosperity & Abundance · Seasonal Celebrations · Greater Mysteries · Correspondences, Timing & Materials · Astrology · Sigils, Seals & Symbols · Talismanic & Astral-Image Magic · Geomancy · Folk Magic · Materials · The Laboratory · Sources & Bibliography

## Some of what the research turned up

- **Barrett's *Magus* (1801)** advertises contents "such as is warranted never before to have been published in the English Language." Its opening chapter is Agrippa's, clause for clause, from an English translation printed in 1651. Both passages are given so you can check it yourself.
- **The heart scarab has two rubrics** prescribing different metals and different placements — and the famous wording is routinely attributed to the wrong one.
- **The buckle of Isis and the ṭeṭ of gold** — a red stone knot and a gold pillar — are consecrated identically, which makes the flower-water lustration a general rite for amulets rather than a detail of one chapter.
- **"As above, so below" is not in the Emerald Tablet.** It is a modern paraphrase, and the oldest Arabic says something materially different: that the levels derive from each other, not that they resemble each other.
- **Agrippa and Paracelsus disagree** about what a seal is indexed to — planets, versus divine names and parts of the body. Merging them is what produced a "system of planetary seals" that no source actually states.
- **The Anglo-Saxon *For elf-disease*** has two timed thresholds, a silence taboo, a consecration under an altar and a cross cut with a sword. Folk magic is not ceremonial magic's simpler cousin; the difference is access, not method.

## What it does not do

- No operations aimed at harming or coercing a named third party.
- No procedure requiring harm to an animal. Where a source contains one, the omission is stated on the page rather than closed over.
- No laboratory alchemy anywhere except Chapter XXII, which is written for a reader who already has a fume hood, a chemistry qualification and a waste-disposal route. Six operations with mercury, antimony, lead and the corrosive acids are given there in full — hazard first, with the modern controls that make them survivable, the historical toll of running them without, and, where a safer modern route exists, both routes and the difference between them.
- No quotation from a text the editor has only read through corrupt OCR. Where that blocked something, the bibliography says so and names the identifier that failed.

## Safety

The warnings in the book are specific and worth reading before practising anything — ventilation for incense, open flame, fasting, and the fact that several of the historical remedies quoted here are dangerous and none of them is medicine. They are printed as evidence of what people did, not as instructions.

## Building

```
python build_book.py
```

Regenerates the print HTML, the PDF and the EPUB from `grimoire.html`, then checks them. Requires Chrome — the PDF is produced through the DevTools protocol, because Chrome's own `--print-to-pdf` snapshots before pagination finishes — and `websocket-client`. Paged.js (MIT) is vendored under `vendor/` and embedded in the print edition only, so the source file stays dependency-free.

```
python check_book.py
```

The checks on their own, against whatever is currently built. Internal links resolve to real anchors, no id is used twice, no chapter repeats or skips a figure number, no SVG `<text>` contains markup that will not render, the EPUB is a well-formed archive whose XML parses — **and every page number in the index is a page the term is actually on.**

That last one is the reason the script exists. An index goes stale silently: add a paragraph anywhere and every folio after it is wrong, with nothing on the page to say so. This book shipped that defect for two commits, with 490 of its 491 entries pointing at the wrong page. The check re-reads the typeset PDF, searches each entry's own term, and fails the build if more references than the recorded floor cannot be found where the index says they are. Needs PyMuPDF; the other checks run without it.

## License

Presented for historical, educational and research purposes. The primary sources quoted are public domain and are identified individually in the bibliography; the handful of modern works consulted are cited but not reproduced, and are marked as in copyright.
