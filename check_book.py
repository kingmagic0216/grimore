#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Structural checks on grimoire.html and the built editions.

The book's claim on a reader is that its apparatus can be trusted, so the
apparatus is checked mechanically rather than by eye:

  tools        renumber.py and resolve_index.py still compile
  well-formed  tags balance
  anchors      every href="#x" resolves to an id="x", and no id is used twice
  crossrefs    every "Chapter N" that links to an id says that chapter's real
               number, and every mention in the file is classified
  contents     the navigation list names every chapter, in document order
  claims       every sentence saying the book lacks something is registered,
               with the reason it is still true
  glyphs       no character that renders as a picture; the book draws its own
  rites        the rite count printed in Chapter XXI matches the rites present
  tree count   the chapter count printed in Chapter III matches the chapters
  figures      no repeated or skipped figure number inside a chapter
  figure fit   no figure label wider than the box drawn around it
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
import io
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
# Chapter IV lowered this from 40: `Rosenkreuz, Christian` had two of its
# references confirmed only by a spurious match on the forename, and
# tightening the key exposed them. He is Rosenkreuz in the English,
# Rosencreutz on the title page of the Chymische Hochzeit, and a
# Rosenkreuzer in the German plural; the override now names all three.
# Chapter XIII lowered this from 39: giving Isaac Casaubon the loose key
# that his own pages need confirmed three references the tighter one
# could not, while SWEEP_REJECT keeps his son's chapter off his entry.
INDEX_FLOOR = 38

VOID = set('br img hr meta link input path circle line rect use polygon '
           'polyline ellipse stop source col area base'.split())


# --------------------------------------------------------------------------

def check_tools(report):
    """The sibling tools still compile.

    check_book imports bookkit, and nothing imports renumber.py or
    resolve_index.py, so a syntax error in either sits undetected until the
    day you need it -- which is the day you have just edited the book and want
    the index re-resolved. One of them was broken for three commits exactly
    that way.
    """
    errs = []
    for name in ('bookkit.py', 'renumber.py', 'resolve_index.py', 'build_book.py'):
        path = os.path.join(B.HERE, name)
        if not os.path.exists(path):
            errs.append('%s is missing' % name)
            continue
        # compile() rather than py_compile, which insists on writing a .pyc
        # somewhere and will not accept the null device on Windows
        with io.open(path, encoding='utf-8') as fh:
            src = fh.read()
        try:
            compile(src, path, 'exec')
        except SyntaxError as exc:
            errs.append('%s line %s: %s' % (name, exc.lineno, exc.msg))
    report('tools', not errs, 'the four scripts compile', errs)


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

# case-folded at the first letter: these sentences start sentences as often
# as not, and a pattern that only matched mid-sentence missed a real claim
CLAIM_PATTERNS = (r'[Nn]othing in this book|[Tt]his book does not|no procedure'
                  r'|[Tt]his (?:book|chapter) (?:refuses|declines|stops)'
                  r'|[Tt]his book gives no|[Nn]owhere in this book')

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
    'why this chapter stops':
        'Chapter XIII, which stops at the copyright line and says so',
    'This book does not attempt to establish how the reading arose':
        'the Bornless/Headless reading; the chapter shows what can be shown '
        'and declines the usual account, which it could not verify',
    'This book does not reproduce that table':
        "Liber O's path attributions; the figure marks the position and not "
        'the planet, and says so in the caption',
    'This book does not print quotations it has only read through corrupt OCR':
        'the standing rule; still true, and Chapter XIII follows it by using '
        'two scans of one edition and saying which passage came from which',
    'This book gives no Enochian operation':
        'true: the workable system is in copyright, and the public-domain '
        'source is a transcript of conversations, not a set of instructions',
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
    body = re.sub(r'<script\b.*?</script>', '', s, flags=re.S)   # vendored code
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


# --------------------------------------------------------------------------
# the rite count
#
# Chapter XXI's Materials table is a shopping list for the rites, and it says
# how many there are. Every chapter added from here on may add rites, and a
# spelled-out number in prose does not notice. So it is checked against the
# thing it counts.
#
# The laboratory operations of Chapter XXII are deliberately outside the
# table: what they need is a fume hood, not a shopping list, and that chapter
# states the requirement beside each hazard instead.
# --------------------------------------------------------------------------

NUMBER_WORDS = {
    'three': 3, 'four': 4, 'five': 5, 'six': 6, 'seven': 7, 'eight': 8,
    'nine': 9, 'ten': 10, 'eleven': 11, 'twelve': 12, 'thirteen': 13,
    'fourteen': 14, 'fifteen': 15, 'sixteen': 16,
    'thirty-six': 36, 'thirty-seven': 37, 'thirty-eight': 38, 'thirty-nine': 39,
    'forty': 40, 'forty-one': 41, 'forty-two': 42, 'forty-three': 43,
    'forty-four': 44, 'forty-five': 45, 'forty-six': 46, 'forty-seven': 47,
    'forty-eight': 48, 'forty-nine': 49, 'fifty': 50, 'fifty-one': 51,
    'fifty-two': 52, 'fifty-three': 53, 'fifty-four': 54, 'fifty-five': 55,
}


def check_rite_count(s, report):
    m = re.search(r'It covers all ([a-z-]+) rites this book gives outside the laboratory', s)
    if not m:
        report('rites', False,
               'the sentence in the Materials chapter that states the rite count has '
               'been reworded; update check_rite_count', [])
        return
    claimed_word = m.group(1)
    claimed = NUMBER_WORDS.get(claimed_word)
    total = s.count('class="rite"')
    a = s.index('<h2 id="laboratory"')
    b = s.index('<h2 id="sources"')
    lab = s[a:b].count('class="rite"')
    actual = total - lab
    ok = claimed == actual
    extra = []
    if claimed is None:
        extra.append('%r is not in NUMBER_WORDS; add it' % claimed_word)
    elif not ok:
        extra.append('Materials says %s (%d); the book has %d rites outside '
                     'the laboratory (%d in all, %d of them laboratory '
                     'operations)' % (claimed_word, claimed, actual, total, lab))
        for w, v in sorted(NUMBER_WORDS.items(), key=lambda kv: kv[1]):
            if v == actual:
                extra.append('the sentence should read "all %s rites"' % w)
    report('rites', ok,
           '%d rites, %d of them laboratory operations; Materials says %s'
           % (total, lab, claimed_word), extra)


def check_contents(s, report):
    """The navigation list names every chapter, in document order.

    A chapter can be written, numbered, cross-referenced and indexed and still
    be missing from the list a reader navigates by, and nothing else here would
    notice.
    """
    i = s.index('<li><a href="#introduction"')
    j = s.index('</ol>', i)
    listed = re.findall(r'<li><a href="#([a-z]+)">', s[i:j])
    want = [c.id for c in B.chapters(s)]
    errs = []
    missing = [c for c in want if c not in listed]
    extra = [c for c in listed if c not in want and c not in ('sources', 'index')]
    if missing:
        errs.append('chapters absent from the contents list: %s' % missing)
    if extra:
        errs.append('listed but not a numbered chapter: %s' % extra)
    order = [c for c in listed if c in want]
    if not errs and order != want:
        errs.append('the contents list is out of document order')
    report('contents', not errs, '%d chapters listed, in order' % len(order), errs)


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


# Per-character advance in the figure founts, in units of font-size. One
# average will not do: the labels are Georgia with letter-spacing, where a
# capital runs to about 0.78em and a lowercase letter to about 0.46em, so a
# single factor either passes an overflowing run of capitals or fails a
# comfortable line of lowercase. Measured off the rendered pages, and left
# slightly generous, because this exists to catch a label overrunning its box
# and not to typeset one.
_ADV_UPPER, _ADV_LOWER, _ADV_OTHER = 0.78, 0.46, 0.45


def _estimate_width(label, size):
    em = 0.0
    for ch in label:
        if ch.isupper():
            em += _ADV_UPPER
        elif ch.islower():
            em += _ADV_LOWER
        else:
            em += _ADV_OTHER
    return em * size

_RECT = re.compile(r'<rect x="([\d.]+)" y="([\d.]+)" width="([\d.]+)" height="([\d.]+)"')
_TEXT = re.compile(r'<text\b([^>]*)>([^<]+)</text>')
_ATTR = re.compile(r'(\w[\w-]*)="([^"]*)"')


def check_tree_count(s, report):
    """Chapter III says how many chapters use the Tree of Life. Count them.

    It is a whole-book claim made from inside one chapter, which is the kind
    that goes stale without being touched: a Tarot chapter cannot be written
    without the Tree, and the sentence would not notice. The definition is
    deliberately mechanical -- a chapter counts if it names the Tree or the
    sephiroth at all -- so that the number and the check cannot drift apart on
    a judgement call.
    """
    m = re.search(r'This book uses the Tree of Life in ([a-z-]+) chapters', s)
    if not m:
        report('tree count', False,
               'the sentence in Chapter III that counts them has been '
               'reworded; update check_tree_count', [])
        return
    word = m.group(1)
    claimed = NUMBER_WORDS.get(word)
    chs = B.chapters(s)
    ends = [chs[i + 1].pos for i in range(len(chs) - 1)] + [s.index('<h2 id="sources"')]
    using = [c.id for c, e in zip(chs, ends)
             if re.search(r'Tree of Life|sephir', s[c.pos:e], re.I)]
    ok = claimed == len(using)
    extra = []
    if claimed is None:
        extra.append('%r is not in NUMBER_WORDS; add it' % word)
    elif not ok:
        extra.append('Chapter III says %s (%d); %d chapters use it: %s'
                     % (word, claimed, len(using), ', '.join(using)))
        for w, v in sorted(NUMBER_WORDS.items(), key=lambda kv: kv[1]):
            if v == len(using):
                extra.append('the sentence should read "in %s chapters"' % w)
    report('tree count', ok,
           '%d chapters use the Tree; Chapter III says %s' % (len(using), word),
           extra)


def check_figure_fit(s, report):
    """No figure label wider than the box it is drawn inside.

    A label that overruns its rect is invisible in the source and obvious on
    the page, which is the worst combination to debug. Widths are estimated
    from the character count and the font size rather than measured in a
    browser, so the margin is loose and only gross overflow is reported.

    A label counts as inside a box only if it falls within it on both axes.
    Checking the horizontal alone flags every axis tick and every caption that
    happens to sit under a rectangle.
    """
    errs, checked = [], 0
    for fig in re.findall(r'<svg\b.*?</svg>', s, re.S):
        rects = [tuple(float(g) for g in m.groups()) for m in _RECT.finditer(fig)]
        if not rects:
            continue
        for m in _TEXT.finditer(fig):
            attrs = dict(_ATTR.findall(m.group(1)))
            if attrs.get('text-anchor') != 'middle':
                continue
            try:
                x, y = float(attrs['x']), float(attrs['y'])
            except (KeyError, ValueError):
                continue
            cls = attrs.get('class')
            size = 12.0 if cls == 'lbl' else 9.0
            fs = re.search(r'font-size:([\d.]+)px', attrs.get('style', ''))
            if fs:
                size = float(fs.group(1))
            inside = [(rx, rw) for rx, ry, rw, rh in rects
                      if rx <= x <= rx + rw and ry <= y <= ry + rh]
            if not inside:
                continue
            checked += 1
            rx, rw = inside[0]
            # &#8211; is one dash on the page and eight characters here
            label = re.sub(r'&#(\d+);', lambda e: chr(int(e.group(1))), m.group(2))
            label = re.sub(r'&\w+;', 'x', label)
            width = _estimate_width(label, size)
            if width > rw:
                errs.append('%r is about %dpx wide in a %dpx box'
                            % (label[:36], round(width), round(rw)))
    report('figure fit', not errs,
           '%d labels sit inside a box, none overflowing it' % checked, errs[:6])


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
        check_tools(report)
        check_wellformed(s, report)
        check_anchors(s, report)
        check_crossrefs(s, report)
        check_contents(s, report)
        check_claims(s, report)
        check_glyphs(s, report)
        check_rite_count(s, report)
        check_tree_count(s, report)
        check_figures(s, report)
        check_figure_fit(s, report)
        check_svg_text(s, report)
        check_epub(report)
    check_index(s, report)
    ok = all(results)
    print('\n%s' % ('all checks passed' if ok else 'CHECKS FAILED'))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
