#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Structural checks on grimoire.html and the built editions.

The book's claim on a reader is that its apparatus can be trusted, so the
apparatus is checked mechanically rather than by eye. What is checked:

  anchors      every href="#x" resolves to an id="x", and no id is used twice
  figures      no repeated or skipped figure number inside a chapter
  svg          no markup inside an SVG <text>, which does not render
  index        every page number in the index is a page the term is on
  epub         the archive is well formed and its XML parses

The index check is the one that matters. An index goes stale silently: add a
paragraph anywhere and every folio after it is wrong, with nothing on the page
to say so. That happened to this book once, across two commits, and 490 of 491
entries were pointing at the wrong page before anyone noticed. INDEX_FLOOR is
the number of index references that could not be confirmed the last time the
index was deliberately resolved; if the figure rises, something moved and the
index has not been re-resolved to match.

    python check_book.py            check the current build
    python check_book.py --index    the index check on its own

Requires PyMuPDF for the index check; the rest runs without it.
"""
from __future__ import print_function

# the book is full of characters a Windows console will not encode
import sys as _sys
try:
    _sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except (AttributeError, ValueError):
    pass

import collections
import io
import os
import re
import sys
import unicodedata
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
SOURCE = os.path.join(HERE, 'grimoire.html')
PDF = os.path.join(HERE, 'grimoire.pdf')
EPUB = os.path.join(HERE, 'grimoire.epub')

# folio = pdf page - FOLIO_OFFSET; the front matter is unnumbered
FOLIO_OFFSET = 7

# references the index cannot confirm by searching for the term itself. Some
# entries index a subject under a name the page never uses -- "the archangels
# of the quarters", "the ring of Solomon" -- and no search will find those.
# Raise this only when you have looked at what was added and know why.
INDEX_FLOOR = 40

VOID = set('br img hr meta link input path circle line rect use polygon '
           'polyline ellipse stop source col area base'.split())


# --------------------------------------------------------------------------
# text handling, shared with the index check
# --------------------------------------------------------------------------

def fold(s):
    """Case, accents and the typographic marks flattened for searching."""
    s = unicodedata.normalize('NFD', s)
    s = u''.join(c for c in s if not unicodedata.combining(c))
    for a, b in ((u'’', u"'"), (u'‘', u"'"), (u'“', u'"'),
                 (u'”', u'"'), (u'—', u' '), (u'–', u'-'),
                 (u'‐', u'-'), (u'æ', u'ae'), (u'œ', u'oe'),
                 (u'ſ', u's')):
        s = s.replace(a, b)
    return s.lower()


def strip_tags(t):
    return re.sub(r'<[^>]+>', '', t)


def read_source():
    return io.open(SOURCE, encoding='utf-8', newline='').read()


# --------------------------------------------------------------------------
# checks that need only the source
# --------------------------------------------------------------------------

def check_anchors(s, report):
    ids = re.findall(r'\bid="([^"]+)"', s)
    idset = set(ids)
    dangling = sorted(set(h for h in re.findall(r'href="#([^"]+)"', s)
                          if h not in idset))
    dupes = sorted(i for i, c in collections.Counter(ids).items() if c > 1)
    report('anchors', not dangling and not dupes,
           '%d ids, %d internal links' % (len(idset), len(set(re.findall(r'href="#([^"]+)"', s)))),
           ['dangling: %s' % dangling] if dangling else [] +
           (['duplicate id: %s' % dupes] if dupes else []))


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


def check_figures(s, report):
    parts = re.split(r'(<h2 id="[^"]+")', s)
    bad = []
    total = 0
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


# --------------------------------------------------------------------------
# the index check
# --------------------------------------------------------------------------

def load_index(s):
    a = s.index(u'<h2 id="index"')
    return re.findall(
        r'<li><span class="e">(.*?)</span> <span class="p">(.*?)</span></li>',
        s[a:], re.S)


def parse_folios(p):
    p = strip_tags(p)
    out = []
    for chunk in p.split(','):
        chunk = chunk.strip()
        m = re.match(r'^(\d+)\s*[–—-]\s*(\d+)$', chunk)
        if m:
            out.extend(range(int(m.group(1)), int(m.group(2)) + 1))
        elif chunk.isdigit():
            out.append(int(chunk))
    return out, 'passim' in p


def search_keys(entry_plain, overrides):
    """The forms of an entry worth searching for, longest first.

    An index entry is written for a reader, not for a search: personal names
    are inverted, titles carry a date, subjects carry a gloss. Overrides exist
    because some entries cannot be searched from their own wording at all.
    """
    if entry_plain in overrides:
        return overrides[entry_plain]
    e = fold(entry_plain).strip()
    keys = []
    base = re.sub(r'\s*\([^)]*\)\s*$', u'', e).strip().rstrip('.,')
    if base:
        keys.append(base)
    if ',' in base:
        head = base.split(',')[0].strip()
        tail = base.split(',')[-1].strip()
        if head and head != base:
            keys.append(head)
        if len(tail) > 8 and tail != head:
            keys.append(tail)
    m = re.search(r'\(([^)]*)\)', e)
    if m:
        alt = m.group(1).strip().rstrip('.,')
        # a single word in parentheses is a gloss, not another name for the
        # thing, and searching for it matches the world
        if alt and ' ' in alt and not re.search(r'\d', alt) and len(alt) > 8:
            keys.append(alt)
    seen, out = set(), []
    for k in keys:
        if k and k not in seen:
            seen.add(k)
            out.append(k)
    return out


# entries whose own wording cannot be searched for, with the key that works
KEY_OVERRIDES = {
    u"Medici, Cosimo de'": [u"cosimo de' medici"],
    u'Reading, Pennsylvania': [u'reading, pennsylvania'],
    u'Paris, BnF lat. 13951': [u'bnf lat. 13951'],
    u'Secret, The (2006)': [u'2006'],
    u'Golden Dawn, The (Regardie, 1937–40)': [u'regardie'],
    u'Waite, A. E., The Book of Ceremonial Magic': [u'book of ceremonial magic'],
    u'assaying': [u'assay', u'assayer'],
    u'bone ash': [u'bone ash', u'bone-ash'],
    u'calomel (mercurius dulcis)': [u'calomel', u'mercurius dulcis'],
    u'corrosive sublimate (mercuric chloride)': [
        u'corrosive sublimate', u'mercuric chloride', u'sublimate corrosive'],
    u'cupellation': [u'cupellation', u'cupel'],
    u'deflagration': [u'deflagration', u'deflagrating'],
    u'fume hood': [u'fume hood', u'fume-hood'],
    u'Howard, Edward': [u'edward howard'],
    u'Kerckring, Theodore': [u'kerckring', u'kerckringius'],
    u'occupational disease': [u'occupational disease', u'occupational toll',
                              u'occupational history'],
    u'regulus of antimony': [u'regulus'],
    u'saltpetre (nitre)': [u'saltpetre', u'spirit of nitre', u'spirit of niter'],
    u'star regulus (regulus stellatus)': [u'star regulus', u'regulus stellatus'],
    u'sublimation': [u'sublimation', u'sublimate'],
    u'tartar, crude': [u'crude tartar', u'potassium bitartrate'],
    u'vitriol, calcined': [u'vitriol'],
    u'salt, decrepitated': [u'decrepitated'],
    u'muffle furnace': [u'muffle'],
    u'mineral acids': [u'mineral acid'],
    u'amalgamation': [u'amalgamation', u'amalgam'],
    u'aqua regia': [u'aqua regia', u'royal water'],
    u'aqua valens (the strong water)': [u'aqua valens', u'strong water'],
    u'Course of Chymistry, A (Lémery, 1677)': [u'course of chymistry',
                                                    u'cours de chymie'],
}


def pdf_pages():
    import fitz
    doc = fitz.open(PDF)
    out = []
    for page in doc:
        t = fold(page.get_text())
        t = re.sub(r'-\s*\n\s*', u'', t)          # heal hyphenated line breaks
        n = re.sub(r'\s+', u' ', t)
        out.append((n, re.sub(r'[^a-z0-9]+', u'', n)))
    return out


def page_carries(key, norm, squeezed):
    pat = re.compile(r'(?<![a-z0-9])' + re.escape(key) + r"(?:'?s|es|s)?(?![a-z0-9])")
    if pat.search(norm):
        return True
    if ' ' in key or '-' in key:
        sq = re.sub(r'[^a-z0-9]+', u'', key)
        if len(sq) > 6 and sq in squeezed:
            return True
    return False


def check_index(s, report):
    try:
        pages = pdf_pages()
    except ImportError:
        report('index', True, 'skipped, PyMuPDF not installed', [])
        return
    stop = None
    for i, (n, _) in enumerate(pages):
        if 'page numbers refer to the printed edition' in n:
            stop = i + 1 - FOLIO_OFFSET
            break
    if stop is None:
        report('index', False, 'could not find the index in the PDF', [])
        return

    entries = load_index(s)
    total = 0
    misses = collections.OrderedDict()
    for entry, plist in entries:
        plain = strip_tags(entry)
        folios, _ = parse_folios(plist)
        keys = search_keys(plain, KEY_OVERRIDES)
        carried = set()
        for i, (n, sq) in enumerate(pages):
            f = i + 1 - FOLIO_OFFSET
            if f < 1 or f >= stop:
                continue
            if any(page_carries(k, n, sq) for k in keys):
                carried.add(f)
        for f in folios:
            total += 1
            if f not in carried:
                misses.setdefault(plain, []).append(f)

    n_miss = sum(len(v) for v in misses.values())
    ok = n_miss <= INDEX_FLOOR
    detail = ('%d entries, %d references, %d unconfirmed (floor %d)'
              % (len(entries), total, n_miss, INDEX_FLOOR))
    extra = []
    if not ok:
        extra.append('the index has drifted: re-resolve it against this PDF')
        for k in list(misses)[:12]:
            extra.append('   %-44s %s' % (k[:44], misses[k]))
    report('index', ok, detail, extra)


# --------------------------------------------------------------------------

def check_epub(report):
    if not os.path.exists(EPUB):
        report('epub', True, 'skipped, not built', [])
        return
    z = zipfile.ZipFile(EPUB)
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
    report('epub', not errs, '%d entries, %d xml parts parse' % (len(names), parts), errs[:5])


def main(argv):
    only_index = '--index' in argv
    results = []

    def report(name, ok, detail, extra):
        results.append(ok)
        print('  %s  %-12s %s' % ('ok  ' if ok else 'FAIL', name, detail))
        for line in extra:
            print('        %s' % line)

    s = read_source()
    print('checking %s' % os.path.basename(SOURCE))
    if not only_index:
        check_wellformed(s, report)
        check_anchors(s, report)
        check_figures(s, report)
        check_svg_text(s, report)
        check_epub(report)
    check_index(s, report)
    ok = all(results)
    print('\n%s' % ('all checks passed' if ok else 'CHECKS FAILED'))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
