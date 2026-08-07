#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Recompute every chapter number in grimoire.html from document order.

Insert a chapter anywhere but the end and 150-odd references go wrong at once.
Most of them are id-linked, so they can be fixed with certainty: the link says
which chapter it means and the heading says what that chapter is now called.
The rest are prose, and those are classified by hand once, in bookkit's
MANUAL_REFS, keyed by the words in front of them.

The script does nothing it cannot do safely:

  headings        rewritten from document order, roman, always
  id-linked       rewritten to the target's new number, in whatever numeral
                  system that reference already used -- the book writes 126 of
                  them in arabic and 2 in roman, and neither gets restyled
  prose refs      rewritten from the reviewed table
  other books     left alone (the Book of the Dead's chapters, Lemery's)
  ranges          NOT rewritten. "Chapters III to XX" means the rite chapters;
                  inserting a chapter inside it changes what it means, and no
                  renumbering can fix a sentence that has become untrue. The
                  script stops and tells you to reword it.

Any mention it cannot classify is a hard failure. That is the whole point: an
unclassified reference is how one goes stale in silence.

    python renumber.py            report what would change
    python renumber.py --write    make the changes
"""
from __future__ import print_function

import re
import sys

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except (AttributeError, ValueError):
    pass

import bookkit as B


def plan(s):
    """Return (edits, problems). Edits are (start, end, old, new, why),
    non-overlapping and in document order."""
    buckets, unclassified = B.find_mentions(s)
    problems = []

    for m, sig in unclassified:
        problems.append(
            'unclassified reference %r at offset %d\n'
            '        signature: %r\n'
            '        add it to bookkit.MANUAL_REFS, or to FOREIGN if it belongs '
            'to another book' % (m.group(0), m.start(), sig))

    chapters = B.chapters(s)
    by_id = {c.id: i + 1 for i, c in enumerate(chapters)}
    edits = []

    # headings: the number is the position in the document, always roman
    for i, ((a, b, old_roman), c) in enumerate(zip(buckets['header'], chapters)):
        want = B.to_roman(i + 1)
        if want != old_roman:
            edits.append((a, b, s[a:b],
                          u'<span class="chapnum">Chapter %s</span>' % want,
                          'heading %s' % c.id))

    # id-linked references: certain, because the link names the target
    for a, b, (cid, word, num) in buckets['linked']:
        if cid not in by_id:
            problems.append('link to #%s, which is not a numbered chapter' % cid)
            continue
        want = B.render_number(by_id[cid], num)
        if want != num:
            edits.append((a, b, s[a:b],
                          u'<a href="#%s">%s %s</a>' % (cid, word, want),
                          'link -> #%s' % cid))

    # prose references, from the reviewed table
    for a, b, (sig, target, lm) in buckets['manual']:
        targets = target if isinstance(target, list) else [target]
        nums = list(B.NUM_RE.finditer(lm.group(1)))
        if len(nums) != len(targets):
            problems.append(
                'prose reference %r names %d chapters but the table gives %d'
                % (lm.group(0)[:50], len(nums), len(targets)))
            continue
        missing = [t for t in targets if t not in by_id]
        if missing:
            problems.append('prose reference points at unknown id(s) %s' % missing)
            continue
        body, off = lm.group(1), 0
        out = []
        for nm, t in zip(nums, targets):
            out.append(body[off:nm.start()])
            out.append(B.render_number(by_id[t], nm.group(0)))
            off = nm.end()
        out.append(body[off:])
        newbody = u''.join(out)
        if newbody != body:
            head = lm.group(0)[:lm.start(1) - lm.start(0)]
            edits.append((a, b, s[a:b], head + newbody,
                          'prose -> %s' % '/'.join(targets)))

    # bare numeral links: <a href="#id">XI</a> with no "Chapter" in the text.
    # find_mentions never sees these (nothing says "Chapter"), which is how
    # the Materials table's Ch. column once survived a renumbering unchanged.
    # The href names the target, so the numeral is mechanical.
    for lm in re.finditer(r'<a href="#([a-z-]+)">([IVXLC]+)</a>', s):
        cid, rom = lm.groups()
        if cid not in by_id:
            problems.append('bare numeral link to #%s, which is not a chapter'
                            % cid)
            continue
        want = B.to_roman(by_id[cid])
        if rom != want:
            edits.append((lm.start(), lm.end(), lm.group(0),
                          u'<a href="#%s">%s</a>' % (cid, want),
                          'bare link -> %s' % cid))

    # ranges: refuse
    for a, b, sig in buckets['range']:
        text = B.strip_tags(s[a:b])
        problems.append(
            'a chapter RANGE is present and cannot be renumbered mechanically:\n'
            '        %r\n'
            '        Inserting a chapter inside a range changes what the range\n'
            '        means, not just what it is called. Reword the sentence to\n'
            '        enumerate the chapters it means, then remove the RANGE\n'
            '        entry from bookkit.MANUAL_REFS.' % text)

    edits.sort()
    for (a1, b1, _, _, _), (a2, _, _, _, _) in zip(edits, edits[1:]):
        if b1 > a2:
            problems.append('overlapping edits at %d and %d' % (a1, a2))
    return edits, problems


def apply_edits(s, edits):
    out, last = [], 0
    for a, b, old, new, _ in edits:
        assert s[a:b] == old, 'source moved under the planner at %d' % a
        out.append(s[last:a])
        out.append(new)
        last = b
    out.append(s[last:])
    return u''.join(out)


def main(argv):
    write = '--write' in argv
    s = B.read_source()
    chs = B.chapters(s)
    print('%d numbered chapters' % len(chs))

    edits, problems = plan(s)

    # a range that is still worded as a range is a warning while the chapter
    # order is unchanged, and an error the moment anything moves
    order_changed = any(w.startswith('heading') for *_, w in edits)
    hard = [p for p in problems if 'RANGE' not in p or order_changed]
    soft = [p for p in problems if p not in hard]

    for p in soft:
        print('\n  note: %s' % p)
    if hard:
        for p in hard:
            print('\n  FAIL: %s' % p)
        print('\nnothing written.')
        return 1

    if not edits:
        print('every chapter number is already correct; nothing to do.')
        return 0

    print('\n%d edits:' % len(edits))
    for a, b, old, new, why in edits:
        print('  %-22s %-42s -> %s' % (why, B.strip_tags(old)[:42],
                                       B.strip_tags(new)[:42]))
    if not write:
        print('\ndry run; pass --write to apply.')
        return 0

    B.write_source(apply_edits(s, edits))
    after, left = B.find_mentions(B.read_source())
    assert not left, 'unclassified references after writing'
    print('\nwritten. re-run build_book.py: the index will need re-resolving.')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
