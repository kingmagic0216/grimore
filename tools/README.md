# tools/

Maintenance helpers for `grimoire.html`. These are **not** part of the book build
(`build_book.py`); run them by hand when editing the book's structure.

## renumber.py

Recomputes every chapter number from document order after you insert, remove, or
reorder a chapter. It rewrites the `<span class="chapnum">` headers and every
`<a href="#chapterid">Chapter N</a>` cross-reference (preserving roman/arabic
style), and reports bare prose `Chapter N` references for manual review. It never
rewrites citations of other works' chapters (Key of Solomon "Book II, chapter 9",
Book of the Dead "Chapter LXIV").

```
python tools/renumber.py            # dry run: report changes + bare refs to review
python tools/renumber.py --apply    # rewrite grimoire.html in place
```

Always follow with `python build_book.py` and the usual checks (anchors, figure
collisions, the chapter-number cross-ref check, index re-resolution).
