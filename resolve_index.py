#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Re-resolve every index folio against a rebuilt PDF.

An index goes stale silently. Add a paragraph and every folio after it is
wrong, with nothing on the page to say so; this book shipped that defect for
two commits, with 490 of its 491 entries pointing at the wrong page. So the
index is not maintained by hand. It is recomputed, like this:

  1. MAP.  Locate each page of the previous printing inside the new one, by
     searching for fixed-length snippets of its text and taking the modal
     vote. Content is only ever inserted, so the map is monotonic.

  2. CONFIRM.  A page map alone is not enough: reflow is fractional, so an old
     page's content can straddle two new ones. For every reference, look for
     the entry's own term on the mapped page and its immediate neighbours, and
     take the nearest page that actually carries it. The term is its own
     alignment mark.

  3. FALL BACK.  Some entries cannot be found by their own words -- a subject
     indexed under a name the page never uses. For those, lift the sentence
     around the term on the page it used to be on and find where that sentence
     now sits. Three outcomes, three meanings:

         found elsewhere    the reference moved; use the new page
         found in place     the map was right; keep it
         not found at all   the passage was cut and the REFERENCE IS DEAD

     The third case is why this step exists. A reference to the tribikos once
     pointed at a note saying Berthelot's third livraison could not be
     obtained; the volume was found, the note was deleted, and the index went
     on pointing at it. Dead references are reported, never silently kept.

  4. SWEEP (--sweep).  Pages carrying text that did not exist in the previous
     printing have never been considered by any earlier resolution. Entries
     whose term appears there gain those pages.

    python resolve_index.py               dry run against git HEAD's PDF
    python resolve_index.py --write       apply
    python resolve_index.py --sweep       also sweep newly written pages
    python resolve_index.py --before X    compare against X.pdf instead
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
import subprocess
import tempfile

import bookkit as B

SNIPPET = 70          # characters of squeezed text used as a locating probe
NEIGHBOURHOOD = 2     # pages either side of the map's guess to accept
SENTENCE = 110        # characters lifted around a term for the fallback

# Sweep hits reviewed and rejected: the term is on the page, but not in the
# sense the entry indexes.
SWEEP_REJECT = {
    ('shield (geomantic chart)', 'the shield there is a face shield'),
    ('Spare, Austin Osman', 'the Spare there is "room to spare"'),
    ('sprinkler, nine-herb (Key of Solomon)', 'matched via its parenthetical'),
    ('Green Egg (magazine)', 'matched "magazine" in a publisher name'),
    ('pelican (vessel)', 'matched the word "vessel"'),
    ('Rosenkreuz, Christian', 'matched the forename in "Christian Cabala", "Christian Hebraist", "Christian D. Ginsburg"'),
    ('Bull, Christian H.', 'the same, through the squeezed fallback'),
    ('Moses', 'matched "Moses de Leon", who is not that Moses'),
    ('Casaubon, Isaac', 'the loose key that confirms his own pages would also hand him Meric's Enochian chapter'),
}
_REJECT_NAMES = {n for n, _ in SWEEP_REJECT}


def squeezed_pages(path):
    return [sq for _, sq in B.pdf_pages(path)]


def previous_pdf(before):
    """The PDF as it was before this round of edits."""
    if before:
        return before, 'given on the command line'
    tmp = os.path.join(tempfile.gettempdir(), 'grimoire_prev.pdf')
    with open(tmp, 'wb') as fh:
        fh.write(subprocess.check_output(['git', 'show', 'HEAD:grimoire.pdf'],
                                         cwd=B.HERE))
    return tmp, "git HEAD's grimoire.pdf"


def build_page_map(old, new, offset):
    """old folio -> new folio, by modal snippet vote, forced monotonic."""
    full = u''.join(new)
    starts, acc = [], 0
    for p in new:
        starts.append(acc)
        acc += len(p)

    def page_of(off):
        lo, hi = 0, len(starts) - 1
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if starts[mid] <= off:
                lo = mid
            else:
                hi = mid - 1
        return lo

    mapping, unmapped, lower = {}, [], 0
    for i, p in enumerate(old):
        votes = []
        for frac in (0.10, 0.25, 0.40, 0.55, 0.70, 0.85):
            st = int(len(p) * frac)
            sn = p[st:st + SNIPPET]
            if len(sn) < SNIPPET:
                continue
            j = full.find(sn, max(0, lower - 6000))
            if j != -1:
                votes.append(page_of(j))
        if votes:
            mapping[i] = collections.Counter(votes).most_common(1)[0][0]
            lower = max(lower, starts[mapping[i]])
        else:
            unmapped.append(i)

    keys = sorted(mapping)
    for a, b in zip(keys, keys[1:]):
        if mapping[b] < mapping[a]:
            mapping[b] = mapping[a]
    for i in unmapped:
        prev = [k for k in keys if k < i]
        mapping[i] = (mapping[prev[-1]] + (i - prev[-1])) if prev else i
    return {i + 1 - offset: mapping[i] + 1 - offset
            for i in sorted(mapping) if i + 1 - offset >= 1}, unmapped


def fresh_pages(old, new, offset):
    """Folios carrying text that is not in the previous printing."""
    full = u''.join(old)
    out = {}
    for i, p in enumerate(new):
        f = i + 1 - offset
        if f < 1 or len(p) < 400:
            continue
        step = max(1, (len(p) - SNIPPET) // 12)
        probes = [p[j:j + SNIPPET] for j in range(0, len(p) - SNIPPET, step)][:12]
        miss = sum(1 for pr in probes if full.find(pr) == -1)
        if probes and miss >= len(probes) // 3:
            out[f] = int(round(100.0 * miss / len(probes)))
    return out


def locate_by_sentence(term_keys, old_folio, oldsq, newsq, offset):
    """Where the sentence around this term has ended up. None if it is gone."""
    i = old_folio + offset - 1
    if not 0 <= i < len(oldsq):
        return None
    page = oldsq[i]
    full = u''.join(newsq)
    starts, acc = [], 0
    for p in newsq:
        starts.append(acc)
        acc += len(p)
    located = False
    for k in term_keys:
        ksq = re.sub(r'[^a-z0-9]+', u'', k)
        if not ksq or ksq not in page:
            continue
        located = True
        pos = page.index(ksq)
        lo = max(0, pos - SENTENCE // 2)
        for snip in (page[lo:lo + SENTENCE], page[max(0, pos - 30):pos + 60]):
            if len(snip) < 40:
                continue
            j = full.find(snip)
            if j != -1:
                off = j + (pos - lo)
                for n in range(len(starts) - 1, -1, -1):
                    if starts[n] <= off:
                        return n + 1 - offset
    # A term that was never on the old page cannot have been deleted from it.
    # Those entries index a subject the page names some other way, and the
    # only honest answer is to keep what the page map said.
    return 'dead' if located else None


def main(argv):
    write = '--write' in argv
    sweep = '--sweep' in argv
    before = None
    if '--before' in argv:
        before = argv[argv.index('--before') + 1]

    s = B.read_source()
    new_pages = B.pdf_pages()
    offset = B.confirm_folio_offset(new_pages, s)
    stop = B.index_stop_folio(new_pages, offset)
    if offset != B.FOLIO_OFFSET:
        print('note: folio offset is %d, not the recorded %d -- the front '
              'matter has grown' % (offset, B.FOLIO_OFFSET))
    print('new printing: %d pages, folios 1-%d, index opens at %d'
          % (len(new_pages), len(new_pages) - offset, stop))

    prev, whence = previous_pdf(before)
    oldsq = squeezed_pages(prev)
    newsq = [sq for _, sq in new_pages]
    print('previous printing: %d pages, from %s' % (len(oldsq), whence))

    fmap, unmapped = build_page_map(oldsq, newsq, offset)
    deltas = sorted(set(v - k for k, v in fmap.items()))
    print('page map: %d folios, shifts %s%s'
          % (len(fmap), deltas,
             ', %d pages interpolated' % len(unmapped) if unmapped else ''))

    fresh = fresh_pages(oldsq, newsq, offset) if sweep else {}
    if sweep:
        print('newly written pages: %s'
              % (', '.join('%d (%d%%)' % (f, p) for f, p in sorted(fresh.items()))
                 or 'none'))

    rows, moved, dead, kept = [], 0, [], 0
    for entry, plist in B.load_index(s):
        plain = B.strip_tags(entry)
        folios, passim = B.parse_folios(plist)
        keys = B.search_keys(plain)
        carried = set(B.folio_hits(keys, new_pages, stop, offset))

        out = []
        for f in folios:
            guess = fmap.get(f, f)
            pick = None
            for c in [guess] + [guess + d for d in range(1, NEIGHBOURHOOD + 1)
                                for d in (d, -d)]:
                if c >= 1 and c in carried:
                    pick = c
                    break
            if pick is None:
                found = locate_by_sentence(keys, f, oldsq, newsq, offset)
                if found == 'dead':
                    dead.append((plain, f))
                    continue
                elif found is not None and found != guess:
                    pick = found
                else:
                    pick = guess
                    kept += 1
            out.append(pick)

        if sweep and not passim and plain not in _REJECT_NAMES:
            out.extend(f for f in carried if f in fresh)

        new_plist = B.format_folios(out, passim)
        if new_plist != plist:
            moved += 1
        rows.append((entry, plist, new_plist))

    print('\nentries whose folios change: %d of %d' % (moved, len(rows)))
    print('references kept from the map, unconfirmable either way: %d' % kept)
    if dead:
        print('\nDEAD references -- the passage is gone from the book:')
        for plain, f in dead:
            print('   %-46s p. %d' % (plain[:46], f))

    if not write:
        print('\ndry run; pass --write to apply.')
        return 0
    if not moved and not dead:
        print('nothing to write.')
        return 0

    for entry, old, new in rows:
        if old == new:
            continue
        o = u'<li><span class="e">%s</span> <span class="p">%s</span></li>' % (entry, old)
        n = u'<li><span class="e">%s</span> <span class="p">%s</span></li>' % (entry, new)
        assert s.count(o) == 1, '%s occurs %d times' % (B.strip_tags(entry), s.count(o))
        s = s.replace(o, n)
    B.write_source(s)
    print('\nwritten. rebuild, then run check_book.py.')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
