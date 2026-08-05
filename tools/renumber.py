#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Recompute every chapter number in grimoire.html from document order.

Maintenance helper for inserting/removing/reordering chapters. It is NOT part of
the book build (build_book.py) — run it by hand after you edit chapter structure.

Workflow when adding a chapter:
  1. Insert the new <h2 id="newid"><span class="chapnum">Chapter ?</span>Title …</h2>
     at its final position in grimoire.html (the placeholder number is ignored).
  2. Add references to it as <a href="#newid">Chapter ?</a> (number also ignored).
  3. Run:  python tools/renumber.py --apply
     This rewrites EVERY chapter number — the <span class="chapnum"> headers and
     every <a href="#chapterid">Chapter N</a> link text — to match document order,
     preserving each reference's roman/arabic numeral style.

What it deliberately never touches:
  * bare prose "Chapter N" that is not an id-linked anchor (reported for manual review)
  * citations of OTHER works' chapters — Key of Solomon "Book II, chapter 9",
    Book of the Dead "Chapter LXIV/XXXB/CLV" — these are not this book's chapters.

Default (no --apply) is a dry run: it reports what would change and lists bare
prose chapter references for you to check by hand. Exit status is nonzero if the
file is out of sync (useful in a pre-commit check).
"""
import os
import re
import io
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, 'grimoire.html')

ROMAN = ['I', 'II', 'III', 'IV', 'V', 'VI', 'VII', 'VIII', 'IX', 'X', 'XI', 'XII',
         'XIII', 'XIV', 'XV', 'XVI', 'XVII', 'XVIII', 'XIX', 'XX', 'XXI', 'XXII',
         'XXIII', 'XXIV', 'XXV', 'XXVI', 'XXVII', 'XXVIII', 'XXIX', 'XXX',
         'XXXI', 'XXXII', 'XXXIII', 'XXXIV', 'XXXV', 'XXXVI']
R2A = {r: str(i + 1) for i, r in enumerate(ROMAN)}

# id-linked refs whose target is not a numbered chapter are left alone. We learn
# the set of chapter ids from the <h2> headers, so no hard-coding is needed.


def split_body(html):
    return re.search(r'<main id="content">(.*?)</main>', html, re.S).group(1)


def chapter_ids(body):
    """Chapter ids in document order (only <h2> that carry a chapnum span)."""
    return [m.group(1) for m in re.finditer(
        r'<h2 id="([a-z]+)"><span class="chapnum">Chapter [IVX]+</span>', body)]


def renumber(body):
    """Rewrite chapnum spans and id-linked chapter refs from document order.

    Returns (new_body, n_changes)."""
    order = chapter_ids(body)
    id2new = {cid: ROMAN[i] for i, cid in enumerate(order)}
    chapter_id_set = set(order)
    changes = [0]

    def fix_span(m):
        cid = m.group(1)
        new = id2new[cid]
        if new != m.group(2):
            changes[0] += 1
        return '<h2 id="%s"><span class="chapnum">Chapter %s</span>' % (cid, new)

    body = re.sub(r'<h2 id="([a-z]+)"><span class="chapnum">Chapter ([IVX]+)</span>',
                  fix_span, body)

    def fix_link(m):
        cid, num = m.group(1), m.group(2)
        if cid not in chapter_id_set:          # link to a non-chapter anchor: leave
            return m.group(0)
        new_roman = id2new[cid]
        new = R2A[new_roman] if num.isdigit() else new_roman
        if new != num:
            changes[0] += 1
        return '<a href="#%s">Chapter %s</a>' % (cid, new)

    body = re.sub(r'<a href="#([a-z]+)">Chapter ([IVX0-9]+)</a>', fix_link, body)
    return body, changes[0]


def bare_prose_refs(body):
    """'Chapter N' occurrences that are NOT id-linked anchors, minus other-work
    citations. Returned for human review — the tool won't rewrite these."""
    stripped = re.sub(r'<a href="#[a-z]+">Chapter [IVX0-9]+</a>', '', body)
    stripped = re.sub(r'<span class="chapnum">Chapter [IVX]+</span>', '', stripped)
    out = []
    for m in re.finditer(r'(?:Book [IVX]+,\s*)?[Cc]hapter\s+([IVX0-9]+[A-Z]?)', stripped):
        ref = m.group(0)
        # skip Key-of-Solomon internal ("Book II, chapter 9") and Book-of-the-Dead
        # roman-with-letter / high-roman citations that are not this book's chapters.
        if ref.lower().startswith('book '):
            continue
        val = m.group(1)
        if re.search(r'[A-Z]$', val) or val in ('XXX', 'LXIV', 'CLV', 'CLVI'):
            continue
        ctx = re.sub(r'\s+', ' ', stripped[max(0, m.start() - 40):m.start() + 30])
        out.append(ctx)
    return out


def main():
    apply = '--apply' in sys.argv
    html = io.open(SRC, encoding='utf-8').read()
    body = split_body(html)
    order = chapter_ids(body)
    print('chapters (%d): %s' % (
        len(order), ', '.join('%s=%s' % (ROMAN[i], c) for i, c in enumerate(order))))

    new_body, n = renumber(body)
    print('chapter-number changes needed: %d' % n)

    bare = bare_prose_refs(new_body)
    if bare:
        print('\n%d bare prose "Chapter N" refs (review by hand — NOT auto-fixed):' % len(bare))
        for c in bare:
            print('   …%s…' % c)

    if apply:
        if n:
            html = html.replace(body, new_body)
            io.open(SRC, 'w', encoding='utf-8', newline='').write(html)
            print('\napplied: grimoire.html rewritten.')
        else:
            print('\nnothing to apply; already in sync.')
        return 0
    else:
        print('\n(dry run — pass --apply to write changes)')
        return 1 if n else 0


if __name__ == '__main__':
    sys.exit(main())
