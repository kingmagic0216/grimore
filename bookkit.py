#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Shared machinery for the tools that read and rewrite grimoire.html.

Three scripts need the same handful of things -- how a page's text is folded
for searching, which forms of a word an index entry should be looked up under,
how a chapter reference is recognised -- and when two of them disagree the
symptom is a resolver and a checker arguing about an index that is fine. So
they live here and everything imports them.

    bookkit.py        this: text handling, chapter parsing, index searching
    renumber.py       recompute every chapter number from document order
    resolve_index.py  re-resolve index folios against a rebuilt PDF
    check_book.py     structural checks, run by build_book.py
"""
from __future__ import print_function

import io
import os
import re
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
SOURCE = os.path.join(HERE, 'grimoire.html')
PDF = os.path.join(HERE, 'grimoire.pdf')
EPUB = os.path.join(HERE, 'grimoire.epub')

# folio = pdf page - FOLIO_OFFSET. The front matter is unnumbered, and this
# grows if the contents page does; confirm_folio_offset() below re-derives it
# from the PDF rather than trusting the constant.
FOLIO_OFFSET = 7


def read_source(path=None):
    return io.open(path or SOURCE, encoding='utf-8', newline='').read()


def write_source(s, path=None):
    io.open(path or SOURCE, 'w', encoding='utf-8', newline='').write(s)


def strip_tags(t):
    return re.sub(r'<[^>]+>', '', t)


def fold(s):
    """Case, accents and typographic marks flattened for searching."""
    s = unicodedata.normalize('NFD', s)
    s = u''.join(c for c in s if not unicodedata.combining(c))
    for a, b in ((u'’', u"'"), (u'‘', u"'"), (u'“', u'"'), (u'”', u'"'),
                 (u'—', u' '), (u'–', u'-'), (u'‐', u'-'),
                 (u'æ', u'ae'), (u'œ', u'oe'), (u'ſ', u's')):
        s = s.replace(a, b)
    return s.lower()


# --------------------------------------------------------------------------
# roman numerals
# --------------------------------------------------------------------------

_ROMAN = [(40, 'XL'), (10, 'X'), (9, 'IX'), (5, 'V'), (4, 'IV'), (1, 'I')]


def to_roman(n):
    if not 1 <= n <= 49:
        raise ValueError('chapter number out of range: %r' % n)
    out = ''
    for v, s in _ROMAN:
        while n >= v:
            out += s
            n -= v
    return out


def from_roman(s):
    vals = {'I': 1, 'V': 5, 'X': 10, 'L': 50, 'C': 100}
    total, prev = 0, 0
    for ch in reversed(s):
        v = vals[ch]
        total += -v if v < prev else v
        prev = max(prev, v)
    return total


def render_number(n, like):
    """Number `n` written in the same system as the reference `like` used.

    The book's cross-references are overwhelmingly arabic -- 126 of them
    against 2 roman -- while the chapter headings are roman. Renumbering must
    not quietly restyle either into the other.
    """
    return str(n) if like.isdigit() else to_roman(n)


# --------------------------------------------------------------------------
# chapters
# --------------------------------------------------------------------------

HEADER_RE = re.compile(
    r'<h2 id="([^"]+)"><span class="chapnum">Chapter ([IVXLC]+)</span>'
    r'(.*?)(?:<span class="difficulty ([a-z]+)">([^<]*)</span>)?</h2>', re.S)

UNNUMBERED_H2_RE = re.compile(
    r'<h2 id="([^"]+)">(?!<span class="chapnum">)(.*?)</h2>', re.S)


class Chapter(object):
    def __init__(self, cid, roman, title, level, label, pos):
        self.id = cid
        self.roman = roman
        self.number = from_roman(roman)
        self.title = strip_tags(title).strip()
        self.level = level
        self.label = label
        self.pos = pos

    def __repr__(self):
        return '<Chapter %s %s %s>' % (self.number, self.id, self.title[:28])


def chapters(s):
    """Numbered chapters, in document order."""
    return [Chapter(m.group(1), m.group(2), m.group(3), m.group(4), m.group(5),
                    m.start())
            for m in HEADER_RE.finditer(s)]


def chapter_ids(s):
    return {c.id: c for c in chapters(s)}


# --------------------------------------------------------------------------
# chapter references
#
# Every mention of "Chapter N" in the file falls into exactly one bucket, and
# the renumberer asserts that the buckets are exhaustive. An unclassified
# mention is a hard failure: it is how a reference goes stale in silence.
# --------------------------------------------------------------------------

MENTION_RE = re.compile(r'Chapters?\s+([IVXLC]+|\d+)')

LINKED_RE = re.compile(r'<a href="#([a-z]+)">(Chapters?)\s+([IVXLC]+|\d+)</a>')

CHAPNUM_RE = re.compile(r'<span class="chapnum">Chapter ([IVXLC]+)</span>')

# a run of chapter numbers: "Chapters 6, 7, 12 and 17"
LIST_RE = re.compile(
    r'Chapters?\s+((?:[IVXLC]+|\d+)(?:\s*,\s*(?:[IVXLC]+|\d+))*'
    r'(?:\s*(?:,|and|to|through|[-–—])\s*(?:[IVXLC]+|\d+))?)')

NUM_RE = re.compile(r'[IVXLC]+|\d+')

FOREIGN = 'FOREIGN'   # a chapter of some other book; never renumber
RANGE = 'RANGE'       # a span of chapters; renumbering the endpoints is wrong

SIG_LEN = 46


def signature(s, pos):
    """The words immediately before a mention, tags stripped and space
    collapsed. Used as the key for the mentions that have to be classified by
    hand, because it survives reflowing, line breaks and inline markup.

    The window is cut at a fixed distance and can therefore begin in the
    middle of a tag, leaving a fragment like "/td>" that strip_tags cannot
    see is markup. That would make the signature depend on how far back the
    window happens to reach, so any leading fragment is dropped first.
    """
    win = s[max(0, pos - SIG_LEN * 3):pos]
    lt, gt = win.find('<'), win.find('>')
    if gt != -1 and (lt == -1 or gt < lt):
        win = win[gt + 1:]
    win = re.sub(r'\s+', u' ', strip_tags(win)).strip()
    # A signature must survive the renumbering it is used to perform, and some
    # of them sit just after another chapter reference -- "...the ritual
    # boundary of Chapter 7, the pentagram as the figure traced in Chapter 12".
    # Renumbering the first would move the key of the second, so the numbers
    # are masked out of the context before it is used as a key.
    win = re.sub(r'Chapters?\s+(?:[IVXLC]+|\d+)', u'Chapter #', win)
    # quote characters are typography, not content: a pass that curls straight
    # quotes must not invalidate every signature that contains one
    for a, b in ((u'’', u"'"), (u'‘', u"'"),
                 (u'“', u'"'), (u'”', u'"')):
        win = win.replace(a, b)
    return win[-SIG_LEN:]


# Every mention of "Chapter N" that is neither a heading nor an id-linked
# cross-reference, classified once by hand. A mention whose signature is not
# in this table stops the renumberer: that is the point, because an
# unclassified reference is exactly how one goes stale in silence.
MANUAL_REFS = {
    # this book's own chapters, referred to in prose without a link
    u' The Lemegeton and its Ars Goetia are dated in': 'solomonic',
    u'nto Hermesthe ascent in imagination, quoted in': 'introduction',
    u'mages of the Early English Books scan cited in': 'sigils',
    u'Indiana University, 2010). The ritual texts in':
        ['meditation', 'rituals', 'protection', 'practicum'],
    u'h in the public domain. The planetary herbs in': 'practicum',
    u'the book: the circle as the ritual boundary of': 'rituals',
    u'apter #, the pentagram as the figure traced in': 'protection',
    u'; light, smoke, water, edge Everything else in': 'rituals',
    u'ny table you can clear. The altar of Fig. 2 in': 'rituals',
    u'5 SaltAny salt.2 A knifeA knife you own.': 'rituals',
    u'y knife, once consecrated. The consecration in': 'rituals',
    u'or herbs. Infusion, decoction and expression (': 'healing',
    u' and an hour when you will not be interrupted.': 'practicum',
    u'rase in quotation marks. The worst sentence in': 'alchemy',
    u'ook: the text of the Emerald Tablet printed in': 'emerald',
    u"nglish of the vulgate's second verse quoted in": 'emerald',
    u'or the caution on the alchemical operations in': 'alchemy',
    u'and the authority for the derivations given in': 'protection',

    # the Egyptian Book of the Dead, in Budge's numbering, which does not map
    # onto modern spell numbers -- the page says so itself
    u' amulet, and the two do not agree. Attached to': FOREIGN,
    u'aced on the neck of the khu. And the rubric to': FOREIGN,
    u'ace it in the heart — belongs to the rubric of': FOREIGN,
    u't — belongs to the rubric of Chapter #, not to': FOREIGN,
    u'd does not map onto modern spell numbers, so "': FOREIGN,
    # Lémery's own chapter VIII, not this book's
    u'istry in 1677. Lémery gives the preparation in': FOREIGN,

}


def find_mentions(s):
    """Partition every 'Chapter N' in the file.

    Returns (buckets, unclassified). Buckets are lists of
    (start, end, detail); unclassified is a list of (match, signature) and
    must be empty before anything is rewritten.
    """
    buckets = {'header': [], 'linked': [], 'manual': [],
               'foreign': [], 'range': []}
    claimed = []

    for m in CHAPNUM_RE.finditer(s):
        buckets['header'].append((m.start(), m.end(), m.group(1)))
        claimed.append((m.start(), m.end()))
    for m in LINKED_RE.finditer(s):
        buckets['linked'].append((m.start(), m.end(),
                                  (m.group(1), m.group(2), m.group(3))))
        claimed.append((m.start(), m.end()))

    unclassified = []
    for m in MENTION_RE.finditer(s):
        if any(a <= m.start() < b for a, b in claimed):
            continue
        sig = signature(s, m.start())
        if sig not in MANUAL_REFS:
            unclassified.append((m, sig))
            continue
        target = MANUAL_REFS[sig]
        if target is FOREIGN:
            buckets['foreign'].append((m.start(), m.end(), sig))
        elif target is RANGE:
            buckets['range'].append((m.start(), m.end(), sig))
        else:
            lm = LIST_RE.match(s, m.start())
            buckets['manual'].append((m.start(), lm.end(), (sig, target, lm)))
    return buckets, unclassified


# --------------------------------------------------------------------------
# the index
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


def group_runs(nums):
    g = []
    for n in sorted(set(nums)):
        if g and n == g[-1][-1] + 1:
            g[-1].append(n)
        else:
            g.append([n])
    return g


# more than a dozen folios and the entry stops being useful as a list; the
# earlier index used this rule and it is kept so that new entries match.
PASSIM_ABOVE = 12
PASSIM_SHOW = 9


def format_folios(nums, passim=False, apply_passim_rule=False):
    nums = sorted(set(nums))
    gs = group_runs(nums)
    if apply_passim_rule and len(nums) > PASSIM_ABOVE:
        gs, passim = gs[:PASSIM_SHOW], True
    parts = [(u'%d–%d' % (g[0], g[-1])) if len(g) > 1 else (u'%d' % g[0])
             for g in gs]
    return u', '.join(parts) + (u', <em>passim</em>' if passim else u'')


# Entries whose own wording cannot be searched for, with the key that works.
# Some are inverted names, some are subjects glossed in parentheses, and five
# are entries that were once resolved on a key looser than the headword --
# "medici" matching inside "medicine" being the one that produced nine pages
# for a man named on two.
KEY_OVERRIDES = {
    # Reginald Scot's surname is a prefix of Walter Scott's, and the two share
    # no subject; confirm on words neither shares with the other entry
    # word-boundary 'scot' never matches 'Scott' (the only permitted suffixes
    # are s/es/'s), so the surname is safe as a key
    u'Scot, Reginald, Discoverie of Witchcraft': [u'scot', u'discoverie'],
    u'James VI of Scotland': [u'james vi'],
    u'Daemonologie (James VI, 1597)': [u'daemonologie'],
    u'Baëll': [u'baëll', u'baell'],
    u'Belial (Beliall)': [u'beliall', u'belial'],
    u'Berith (Beall, Bolfry)': [u'berith'],
    u'Asmoday (Sidonay)': [u'asmoday', u'sidonay'],
    u'vessel of brass, the': [u'brasen vessell', u'brazen vessel'],
    u'Triangle of Art, the': [u'triangle of art', u'triangle'],
    u"Medici, Cosimo de'": [u"cosimo de' medici"],
    u'Reading, Pennsylvania': [u'reading, pennsylvania'],
    u'Paris, BnF lat. 13951': [u'bnf lat. 13951'],
    u'Secret, The (2006)': [u'2006'],
    u'Golden Dawn, The (Regardie, 1937–40)': [u'regardie'],
    # The grimoire survey rests on this book and names its author on every
    # page of it, so confirming those references needs the surname -- and
    # the surname would sweep half the book onto the entry, so it is in
    # resolve_index's SWEEP_REJECT too. Same split as the two Casaubons.
    u'Waite, A. E., The Book of Ceremonial Magic':
        [u'book of ceremonial magic', u'waite'],
    u'assaying': [u'assay', u'assayer'],
    u'bone ash': [u'bone ash', u'bone-ash'],
    u'calomel (mercurius dulcis)': [u'calomel', u'mercurius dulcis'],
    u'corrosive sublimate (mercuric chloride)': [
        u'corrosive sublimate', u'mercuric chloride', u'sublimate corrosive'],
    u'cupellation': [u'cupellation', u'cupel'],
    u'deflagration': [u'deflagration', u'deflagrating'],
    u'fume hood': [u'fume hood', u'fume-hood'],
    u'Howard, Edward': [u'edward howard'],
    u'Sworn Book of Honorius (Liber Juratus)': ['sworn book'],
    u'Grimoire of Honorius (1629)': ['grimoire of honorius'],
    u'Honorius, the two books of': ['honorius'],
    u'Grand Grimoire (the Red Dragon)': ['grand grimoire', 'red dragon'],
    u'Black Pullet, The': ['black pullet'],
    u'True Black Magic': ['true black magic'],
    u'Alibeck the Egyptian': ['alibeck'],
    u'false imprints': ['false imprint'],
    u'Court de Gébelin, Antoine': ['court de gebelin'],
    u'Monde Primitif (Court de Gébelin, 1781)': ['monde primitif'],
    u'Lévi, Éliphas': ['levi'],
    u'Transcendental Magic (Lévi, trans. Waite)': ['transcendental magic'],
    u'Pictorial Key to the Tarot, The (Waite, 1911)': ['pictorial key'],
    u'Waite–Smith tarot (1909)': ['waite-smith', 'waite–smith'],
    u'trumps, the twenty-two': ['trump'],
    u'Fool, the (tarot)': ['the fool'],
    u'Strength and Justice, interchange of': ['interchanged with that of justice', 'interchange'],
    u'Juggler (the Magician)': ['juggler'],
    u'mansions of the Moon, the twenty-eight': ['mansion'],
    u'Alnath': ['alnath'],
    u'Aldebaran': ['aldebaran'],
    u'Teucer the Babylonian': ['teucer'],
    u'Porphyry': ['porphyry'],
    u'astral images': ['astral image', 'astral-image'],
    u'election (choosing a moment)': ['election'],
    u'Three Books of Occult Philosophy (Agrippa, 1651)': ['three books of occult philosophy'],
    u'Lilly, William':
        ['lilly'],
    u'Christian Astrology (Lilly, 1647)':
        ['christian astrology'],
    u'houses, the twelve':
        ['twelve houses', 'the houses'],
    u'aspects (conjunction, sextile, square, trine, opposition)':
        ['aspect', 'sextile', 'trine', 'opposition'],
    u'horary astrology':
        ['horary'],
    u'natal astrology (nativities)':
        ['nativit', 'natal'],
    u'domicile (planetary rulership)':
        ['domicile'],
    # Father and son, and the son edited Dee. Isaac is named in full once
    # and is plain 'Casaubon' thereafter, so confirming his references
    # needs the loose key -- but the loose key would also hand him his
    # son's chapter, so he is in resolve_index's SWEEP_REJECT as well.
    # Confirming a folio and adding one are different jobs.
    u'Casaubon, Isaac': [u'casaubon'],
    u'Casaubon, Meric': [u'meric casaubon'],
    u'Enochian system': [u'enochian'],
    u'Angelical (the Enochian language)': [u'angelical'],
    u'Watchtowers': [u'watchtower'],
    u'Cotton, Sir Thomas': [u'sir tho. cotton'],
    u'True and Faithful Relation, A (Casaubon, 1659)':
        [u'true & faithful relation', u'true and faithful relation'],
    # he is Rosenkreuz in the English, Rosencreutz on the title page of
    # the Chymische Hochzeit, and a Rosenkreuzer in the German plural
    u'Rosenkreuz, Christian': [u'rosenkreuz', u'rosencreutz',
                               u'rosenkreuzer', u'c.r.c'],
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

    # Chapter IV. The book prints several of these under more than one form --
    # En Soph beside Ein Sof, "the Christian and occult Cabala" beside
    # "Christian Cabala" -- and an entry resolved on one form must be checked
    # on all of them, or the checker and the resolver disagree about an index
    # that is correct.
    u'Ein Sof (the Boundless)': [u'ein sof', u'en soph'],
    u'Christian Cabala': [u'christian cabala', u'christian and occult cabala'],
    u'four worlds (Atziluth, Briah, Yetzirah, Assiah)':
        [u'four worlds', u'briatic', u'jetziratic', u'assiatic', u'atziluth'],
    u'Knorr von Rosenroth, Christian': [u'rosenroth'],
    u'Kabbala Denudata (Rosenroth, 1677–84)': [u'kabbala denudata'],
    u'Kabbalah Unveiled, The (Mathers, 1887)': [u'kabbalah unveiled'],
    u'León, Moses de': [u'moses de leon', u'de leon'],
    u'Simeon ben Jochai': [u'simeon ben jochai', u'simon ben jochai'],
    u'Lully, Raymond': [u'raymond lully'],
    u'emanation': [u'emanation', u'emanated'],
    u'Idra Rabba and Idra Suta': [u'idra rabba', u'idra suta'],
}


def search_keys(entry_plain, overrides=None):
    """The forms of an index entry worth searching for, longest first.

    An entry is written for a reader, not for a search: personal names are
    inverted, titles carry a date, subjects carry a gloss.
    """
    overrides = KEY_OVERRIDES if overrides is None else overrides
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
        # the tail of an inverted heading is a title in "Waite, A. E., The
        # Book of Ceremonial Magic" and a forename in "Rosenkreuz, Christian".
        # Only the first is worth searching for; a bare forename matches every
        # Christian Hebraist and Christian Cabala in the book.
        if ' ' in tail and len(tail) > 12 and tail != head:
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


def page_carries(key, norm, squeezed):
    pat = re.compile(r'(?<![a-z0-9])' + re.escape(key) +
                     r"(?:'?s|es|s)?(?![a-z0-9])")
    if pat.search(norm):
        return True
    if ' ' in key or '-' in key:
        sq = re.sub(r'[^a-z0-9]+', u'', key)
        if len(sq) > 6 and sq in squeezed:
            return True
    return False


def pdf_pages(path=None):
    """(normalised, squeezed) text for every page of the PDF."""
    import fitz
    doc = fitz.open(path or PDF)
    out = []
    for page in doc:
        t = fold(page.get_text())
        t = re.sub(r'-\s*\n\s*', u'', t)        # heal hyphenated line breaks
        n = re.sub(r'\s+', u' ', t)
        out.append((n, re.sub(r'[^a-z0-9]+', u'', n)))
    return out


def index_stop_folio(pages, offset=FOLIO_OFFSET):
    """First folio of the index itself, which is excluded from every search."""
    for i, (n, _) in enumerate(pages):
        if 'page numbers refer to the printed edition' in n:
            return i + 1 - offset
    raise LookupError('the index could not be found in the PDF')


def confirm_folio_offset(pages, source=None):
    """Re-derive the folio offset instead of trusting the constant.

    The front matter grows: another line on the contents page moves every
    printed folio by one against its PDF page, and nothing else would notice.
    """
    s = read_source() if source is None else source
    first = chapters(s)[0]
    want = fold(first.title)
    for i, (n, _) in enumerate(pages):
        if want in n and 'c h a p t e r' in n:
            return i          # pdf page i+1 carries folio 1
    return FOLIO_OFFSET


def folio_hits(keys, pages, stop, offset=FOLIO_OFFSET):
    out = []
    for i, (n, sq) in enumerate(pages):
        f = i + 1 - offset
        if f < 1 or f >= stop:
            continue
        if any(page_carries(k, n, sq) for k in keys):
            out.append(f)
    return out
