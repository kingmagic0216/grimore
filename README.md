# The Complete Hermetic & Rosicrucian Grimoire

A working grimoire of the Western esoteric tradition — twenty-one chapters, 257 pages, 43 diagrams — in which **every source is dated and attributed, and the attribution is allowed to be inconvenient.**

That last clause is the point. Where a teaching commonly presented as ancient turns out to be medieval, early modern or modern, the chapter says so and keeps the practice. Where two sources disagree, both are printed. Where this edition could not reach a text, it names the text and says why.

## Read it

| Edition | File | Best for |
|---|---|---|
| **EPUB** | [`grimoire.epub`](grimoire.epub) — 680 KB | **Phones and e-readers.** Reflowable, follows your font size and dark mode, diagrams are vector so they stay sharp. |
| **PDF** | [`grimoire.pdf`](grimoire.pdf) — 12 MB | The typeset book: 6×9, running heads, folios, a contents page with real page numbers. |
| **HTML** | [`grimoire.html`](grimoire.html) | The source of truth. One self-contained file, no dependencies, sticky navigation, dark mode. |

The PDF and EPUB are generated from the HTML. **Corrections go to `grimoire.html`**; the other two are rebuilt from it.

## What's in it

**The historical spine.** Three of the foundations this subject rests on have documented dating problems, and the book leads with them rather than burying them:

- The **Seven Hermetic Principles** come from *The Kybalion* (1908), a New Thought work — not from ancient Hermeticism. All seven are kept, explained, and dated.
- The **Corpus Hermeticum** is Greek, c. 100–300 CE. Ficino translated it in 1471 believing it older than Moses; Casaubon showed otherwise. That misdating is *why* the Renaissance took Hermeticism seriously.
- The **Rosicrucian Brotherhood** cannot be shown to have existed. Andreae, who acknowledged writing the *Chymical Wedding*, called the whole affair a *ludibrium* — a lampoon.

Meanwhile the **Greek Magical Papyri** are genuinely ancient, physically extant and provenanced — and they are the part usually left out. That inversion is the argument of the book: the material presented as ancient is mostly early modern, and the genuinely ancient material is the part nobody prints.

**The operative material.** 36 rites given in full, each dated and sourced: the Lesser Banishing Ritual of the Pentagram with Hebrew and pronunciation, the Lesser and Greater Hexagram, the Middle Pillar, godform assumption, scrying, a complete opening and closing, the Solomonic consecrations of water, salt and sword, the Headless Rite from the papyri, dream oracles, the Fourth Pentacle of the Moon, talisman construction, geomancy from the casting to the Judge, Pennsylvania Dutch charms, and the Anglo-Saxon remedies.

**Chapters.** Introduction · The Hermetica and Their Transmission · Sacred Geometry & Symbols · Alchemical Foundations · The Emerald Tablet · Meditation Practices · Ritual Foundations · The Greek Magical Papyri · The Solomonic Tradition · Rosicrucian Mysteries · Advanced Practices · Protection & Banishing · Healing & Wellness · Prosperity & Abundance · Seasonal Celebrations · Greater Mysteries · Correspondences, Timing & Materials · Sigils, Seals & Symbols · Geomancy · Folk Magic · Sources & Bibliography

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
- No laboratory alchemy with mercury, antimony, lead or corrosive acids. Doctrine, symbolism, apparatus and dating, yes; actionable toxic protocols, no.
- No quotation from a text the editor has only read through corrupt OCR. Where that blocked something, the bibliography says so and names the identifier that failed.

## Safety

The warnings in the book are specific and worth reading before practising anything — ventilation for incense, open flame, fasting, and the fact that several of the historical remedies quoted here are dangerous and none of them is medicine. They are printed as evidence of what people did, not as instructions.

## Building

```
python build_book.py
```

Regenerates the print HTML, the PDF and the EPUB from `grimoire.html`. Requires Chrome — the PDF is produced through the DevTools protocol, because Chrome's own `--print-to-pdf` snapshots before pagination finishes — and `websocket-client`. Paged.js (MIT) is vendored under `vendor/` and embedded in the print edition only, so the source file stays dependency-free.

## License

Presented for historical, educational and research purposes. The primary sources quoted are public domain and are identified individually in the bibliography; the handful of modern works consulted are cited but not reproduced, and are marked as in copyright.
