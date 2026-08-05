#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Structural checks on grimoire.html and the built editions.

The book's claim on a reader is that its apparatus can be trusted, so the
apparatus is checked mechanically rather than by eye:

  well-formed  tags balance
  anchors      every href="#x" resolves to an id="x", and no id is used twice
  crossrefs    every "Chapter N" that links to an id says that chapter's real
               number, and every mention in the file is classified
  claims       every sentence saying the book lacks something is registered,
               with the reason it is still true
  glyphs       no character that renders as a picture; the book draws its own
  figures      no repeated or skipped figure number inside a chapter
  svg          no markup inside an SVG <text>, which does not render
  epub         the archive is well formed and its XML parses
  index        every page number in the index is a page the term is on

The last two matter most, and for the same reason: both go wrong silently.
Insert a chapter and 150 cross-references are off by one with nothing on the
page to say so; insert a paragraph and every folio after it is wrong the same
way. This book shipped the second defect for two commits.

Shared machinery lives in bookkit.py, which renumber.py and resolve_index.py
also import -- when a checker and a resolver keep their own copies of the same
rule, the symptom is the two of them arguing about an index that is fine.

    python check_book.py            everything
    python check_book.py --index    the index check on its own

Requires PyMuPDF for the index check; the rest runs without it.
"""
from __future__ import print_function

import sys

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except (AttributeError, ValueError):
    pass

import collections
import os
import re
import zipfile

import bookkit as B

# References the index cannot confirm by searching for the term itself. Only
# some of these are irreducible: an entry that indexes a subject under a name
# the page never uses -- "the archangels of the quarters", "the ring of
# Solomon" -- can never be found by searching for its own words.
#
# The rest are findable another way, which resolve_index.py does for you: lift
# the sentence around the term on the page it used to be on, and find where
# that sentence now sits. Three outcomes, three meanings:
#
#   found on another page   the reference moved and the index is stale
#   found on the same page  the search is too narrow; give it a KEY_OVERRIDE
#   not found at all        the passage was cut, and the reference is dead
#
# That third case is real. A reference here once pointed at a note saying a
# volume could not be obtained; the volume was found, the note was deleted, and
# the index went on pointing at it for two commits. Diagnose a rise by running
# `python resolve_index.py`. Do not absorb it into the floor.
INDEX_FLOOR = 40

VOID = set('br img hr meta link input path circle line rect use polygon '
           'polyline ellipse stop source col area base'.split())


# --------------------------------------------------------------------------

def check_wellformed(s, report):
    from html.parser import HTMLParser
    stack, errs = [], []

    class P(HTMLParser):
        def handle_starttag(self, t, a):
            if t not in VOID:
                stack.append((t, self.getpos()))

        def handle_endtag(self, t):
            if t in VOID:
                return
            if not stack:
                errs.append('stray </%s> at %s' % (t, self.getpos()))
            elif stack[-1][0] != t:
                errs.append('<%s> at %s closed by </%s> at %s'
                            % (stack[-1][0], stack[-1][1], t, self.getpos()))
                stack.pop()
            else:
                stack.pop()

    p = P(convert_charrefs=True)
    p.feed(s)
    errs += ['unclosed <%s> at %s' % (t, pos) for t, pos in stack]
    report('well-formed', not errs, 'tags balanced', errs[:6])


def check_anchors(s, report):
    ids = re.findall(r'\bid="([^"]+)"', s)
    idset = set(ids)
    hrefs = set(re.findall(r'href="#([^"]+)"', s))
    dangling = sorted(h for h in hrefs if h not in idset)
    dupes = sorted(i for i, c in collections.Counter(ids).items() if c > 1)
    report('anchors', not dangling and not dupes,
           '%d ids, %d internal links' % (len(idset), len(hrefs)),
           (['dangling: %s' % dangling] if dangling else []) +
           (['duplicate id: %s' % dupes] if dupes else []))


def check_crossrefs(s, report):
    """Every linked "Chapter N" says the number that chapter actually has.

    Renumbering is automated, but nothing stops a hand-written reference from
    naming the wrong chapter, and the link makes the intent checkable: the id
    says which chapter is meant, and the heading says what it is called.
    """
    numbers = {c.id: i + 1 for i, c in enumerate(B.chapters(s))}
    buckets, unclassified = B.find_mentions(s)
    errs = []
    for a, b, (cid, word, num) in buckets['linked']:
        if cid not in numbers:
            errs.append('#%s is linked as a chapter but is not one' % cid)
            continue
        got = int(num) if num.isdigit() else B.from_roman(num)
        if got != numbers[cid]:
            errs.append('"%s %s" links to #%s, which is chapter %d'
                        % (word, num, cid, numbers[cid]))
    # prose references carry no link, but the reviewed table says which
    # chapter each one means, so they are checkable too
    for a, b, (sig, target, lm) in buckets['manual']:
        targets = target if isinstance(target, list) else [target]
        nums = B.NUM_RE.findall(lm.group(1))
        if len(nums) != len(targets):
            errs.append('prose reference %r names %d chapters, the table gives %d'
                        % (B.strip_tags(lm.group(0))[:44], len(nums), len(targets)))
            continue
        for num, t in zip(nums, targets):
            if t not in numbers:
                errs.append('prose reference points at unknown id %r' % t)
                continue
            got = int(num) if num.isdigit() else B.from_roman(num)
            if got != numbers[t]:
                errs.append('prose "Chapter %s" after %r means #%s, which is '
                            'chapter %d' % (num, sig[-28:], t, numbers[t]))
    for m, sig in unclassified:
        errs.append('unclassified mention %r (signature %r) -- classify it in '
                    'bookkit.MANUAL_REFS' % (m.group(0), sig))
    total = sum(len(v) for v in buckets.values())
    report('crossrefs', not errs,
           '%d mentions: %d headings, %d linked, %d prose, %d other books, '
           '%d ranges' % (total, len(buckets['header']), len(buckets['linked']),
                          len(buckets['manual']), len(buckets['foreign']),
                          len(buckets['range'])),
           errs[:8])


# --------------------------------------------------------------------------
# claims about what the book does not contain
#
# Adding a chapter can make a sentence elsewhere untrue without touching it,
# and this book has now shipped that defect three separate times: Chapter XXII
# arrived, and Chapter IV went on saying the book stopped at the third degree
# of fire, Chapter XXI went on saying nothing in the book required a toxic
# material, and a table cell went on printing "Nothing in this book" for the
# fourth degree in red. None of those greps for the same phrase, which is why
# they were found one at a time by eye.
#
# So every sentence that claims the book lacks something is registered here
# with the reason it is still true. A new or reworded one fails the check
# until somebody has looked at it against the current chapter list.
# --------------------------------------------------------------------------

CLAIM_PATTERNS = (r'[Nn]othing in this book|this book does not|no procedure'
                  r'|this (?:book|chapter) (?:refuses|declines|stops)|this book gives no'
                  r'|nowhere in this book')

REVIEWED_CLAIMS = {
    'this book does not treat it as settled':
        "about an attribution, not about the book's contents",
    'this book does not assert one':
        "about a line of transmission, not about the book's contents",
    'this book does not claim':
        'about a living tradition the book does not speak for',
    'Nothing in this book claims the plant acts':
        'about what the correspondences assert, not about coverage',
    'this book does not reproduce as procedure':
        'blood sacrifice; still true and stated as an omission',
    'no procedure for handling any of it':
        'scoped to Chapter XXI and points at Chapter XXII',
    'this book does not give you':
        'the fulminates; still true, and Chapter XXII says why',
    'this book does not assert it':
        "about Newton's mercury and his breakdown; a causal claim",
    'this chapter prints history and no procedure':
        'scoped to Chapter IV, which does stop at the third degree',
    'why this chapter stops there':
        'scoped to Chapter IV; the book does not stop there',
}


def check_claims(s, report):
    text = re.sub(r'\s+', ' ', B.strip_tags(s))
    errs, seen = [], set()
    for m in re.finditer(CLAIM_PATTERNS, text):
        window = text[m.start():m.start() + 90]
        hit = None
        for known in REVIEWED_CLAIMS:
            # the pattern can match at the tail of the registered sentence,
            # so look back far enough to see the whole of it
            if window.startswith(known) or known in text[max(0, m.start() - 60):m.start() + 90]:
                hit = known
                break
        if hit is None:
            errs.append('unreviewed claim: %r' % text[max(0, m.start() - 30):m.start() + 80])
        else:
            seen.add(hit)
    stale = sorted(set(REVIEWED_CLAIMS) - seen)
    for k in stale:
        errs.append('registered claim no longer in the book, drop it: %r' % k)
    report('claims', not errs,
           '%d absence claims, all reviewed against the chapter list' % len(seen),
           errs[:8])


# --------------------------------------------------------------------------
# pictographic characters
#
# The book draws its own symbols. A character that renders as a picture is
# therefore always a mistake here, and it is a mistake that hides: U+FE0F on a
# warning sign printed a colour emoji in a monochrome book for months, and the
# four elemental signs were soap, urine, horse dung and ashes under a column
# whose rule text says "triangle, apex up".
#
# So the whole pictographic space is refused and the handful of legitimate
# exceptions are registered. Vendored script is skipped: Paged.js draws
# linked-list diagrams in box-drawing characters inside its own comments, and
# none of that reaches a page.
# --------------------------------------------------------------------------

PICTOGRAPHIC = (
    (0x00A9, 0x00A9), (0x00AE, 0x00AE), (0x2122, 0x2122),
    (0x2049, 0x2049), (0x203C, 0x203C),
    (0x2190, 0x21FF),          # arrows
    (0x2300, 0x23FF),          # technical, including the clocks
    (0x2460, 0x24FF),          # enclosed alphanumerics
    (0x2500, 0x25FF),          # box drawing, blocks, geometric shapes
    (0x2600, 0x27BF),          # miscellaneous symbols and dingbats
    (0x2900, 0x297F), (0x2B00, 0x2BFF),
    (0x3030, 0x3030), (0x303D, 0x303D), (0x3297, 0x3299),
    (0xFE0E, 0xFE0F),          # the text and emoji presentation selectors
    (0x1F000, 0x1FBFF),
)

# character -> why it is allowed to stay
ALLOWED_PICTOGRAPHIC = {
    u'→': 'a typographic arrow inside figure labels: "ash: black -> white", '
                '"Yod = 10 -> 1". It sets in the figure font, monochrome.',
    u'↑': 'the back-to-top control in the HTML edition; display:none in '
                'print and absent from the EPUB.',
}


def check_glyphs(s, report):
    body = re.sub(r'<script.*?</script>', '', s, flags=re.S)   # vendored code
    body = re.sub(r'&#(\d+);', lambda m: chr(int(m.group(1))), body)
    found = collections.Counter(
        c for c in body
        if any(a <= ord(c) <= b for a, b in PICTOGRAPHIC))
    errs = []
    for ch, n in found.items():
        if ch not in ALLOWED_PICTOGRAPHIC:
            errs.append('U+%04X x%d -- draw it, or register it in '
                        'ALLOWED_PICTOGRAPHIC with a reason' % (ord(ch), n))
    allowed = sum(n for c, n in found.items() if c in ALLOWED_PICTOGRAPHIC)
    report('glyphs', not errs,
           'no pictographic characters except %d registered '
           '(%s)' % (allowed, ', '.join('U+%04X' % ord(c) for c in sorted(
               c for c in found if c in ALLOWED_PICTOGRAPHIC))),
           errs[:8])


def check_figures(s, report):
    parts = re.split(r'(<h2 id="[^"]+")', s)
    bad, total = [], 0
    for i in range(1, len(parts), 2):
        cid = re.search(r'id="([^"]+)"', parts[i]).group(1)
        body = parts[i] + parts[i + 1]
        labels = re.findall(
            r'<b>(Fig\.\s*\d+|Plate\s+[IVXLC]+)\s*(?:&#8212;|&mdash;|[—–-])', body)
        total += len(labels)
        dup = [l for l, c in collections.Counter(labels).items() if c > 1]
        nums = sorted(int(re.search(r'\d+', l).group())
                      for l in labels if l.startswith('Fig'))
        if dup:
            bad.append('%s: repeated %s' % (cid, dup))
        if nums and nums != list(range(1, len(nums) + 1)):
            bad.append('%s: numbering %s' % (cid, nums))
    report('figures', not bad, '%d labels, none repeated or skipped' % total, bad)


def check_svg_text(s, report):
    bad = [t for t in re.findall(r'<text[^>]*>(.*?)</text>', s, re.S)
           if '<em' in t or '<strong' in t or '<a ' in t]
    report('svg text', not bad, 'no markup inside <text>',
           ['<text> contains markup: %r' % t[:60] for t in bad[:5]])


def check_epub(report):
    if not os.path.exists(B.EPUB):
        report('epub', True, 'skipped, not built', [])
        return
    z = zipfile.ZipFile(B.EPUB)
    names = z.namelist()
    errs = []
    if z.testzip() is not None:
        errs.append('corrupt member: %s' % z.testzip())
    if not names or names[0] != 'mimetype':
        errs.append('mimetype is not the first entry')
    import xml.dom.minidom as md
    parts = 0
    for n in names:
        if n.endswith(('.xhtml', '.opf', '.ncx', '.xml')):
            try:
                md.parseString(z.read(n))
                parts += 1
            except Exception as exc:
                errs.append('%s: %s' % (n, exc))
    report('epub', not errs,
           '%d entries, %d xml parts parse' % (len(names), parts), errs[:5])


def check_index(s, report):
    try:
        pages = B.pdf_pages()
    except ImportError:
        report('index', True, 'skipped, PyMuPDF not installed', [])
        return
    except Exception as exc:
        report('index', False, 'could not read the PDF: %s' % exc, [])
        return
    offset = B.confirm_folio_offset(pages, s)
    try:
        stop = B.index_stop_folio(pages, offset)
    except LookupError as exc:
        report('index', False, str(exc), [])
        return

    entries = B.load_index(s)
    total = 0
    misses = collections.OrderedDict()
    for entry, plist in entries:
        plain = B.strip_tags(entry)
        folios, _ = B.parse_folios(plist)
        carried = set(B.folio_hits(B.search_keys(plain), pages, stop, offset))
        for f in folios:
            total += 1
            if f not in carried:
                misses.setdefault(plain, []).append(f)

    n_miss = sum(len(v) for v in misses.values())
    ok = n_miss <= INDEX_FLOOR
    extra = []
    if offset != B.FOLIO_OFFSET:
        extra.append('folio offset is %d, not the recorded %d -- the front '
                     'matter has grown; update bookkit.FOLIO_OFFSET'
                     % (offset, B.FOLIO_OFFSET))
    if not ok:
        extra.append('the index has drifted; run: python resolve_index.py')
        for k in list(misses)[:12]:
            extra.append('   %-44s %s' % (k[:44], misses[k]))
    report('index', ok,
           '%d entries, %d references, %d unconfirmed (floor %d)'
           % (len(entries), total, n_miss, INDEX_FLOOR), extra)


def main(argv):
    only_index = '--index' in argv
    results = []

    def report(name, ok, detail, extra):
        results.append(ok)
        print('  %s  %-12s %s' % ('ok  ' if ok else 'FAIL', name, detail))
        for line in extra:
            print('        %s' % line)

    s = B.read_source()
    print('checking %s' % os.path.basename(B.SOURCE))
    if not only_index:
        check_wellformed(s, report)
        check_anchors(s, report)
        check_crossrefs(s, report)
        check_claims(s, report)
        check_glyphs(s, report)
        check_figures(s, report)
        check_svg_text(s, report)
        check_epub(report)
    check_index(s, report)
    ok = all(results)
    print('\n%s' % ('all checks passed' if ok else 'CHECKS FAILED'))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
