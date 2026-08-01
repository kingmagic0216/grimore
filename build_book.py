#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Build the book editions from grimoire.html.

    python build_book.py

Outputs, all generated - never edit them by hand:

    grimoire-book.html   print edition, paginated in-browser by Paged.js
    grimoire.pdf         6x9 trade-paperback PDF, via headless Chrome
    grimoire.epub        EPUB 3, reflowable, for e-readers

grimoire.html is the single source of truth. Corrections go there.

Paged.js (MIT) is fetched once into vendor/paged.polyfill.js and embedded in the
print edition only, so the source file stays dependency-free. It supplies the
running heads and folios that Chrome's own print engine cannot produce.
"""

import io
import os
import re
import shutil
import subprocess
import sys
import zipfile

ROOT = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(ROOT, 'grimoire.html')
VENDOR = os.path.join(ROOT, 'vendor', 'paged.polyfill.js')
PAGEDJS_URL = 'https://unpkg.com/pagedjs@0.4.3/dist/paged.polyfill.js'

BOOK_HTML = os.path.join(ROOT, 'grimoire-book.html')
PDF = os.path.join(ROOT, 'grimoire.pdf')
EPUB = os.path.join(ROOT, 'grimoire.epub')

TITLE = 'The Complete Hermetic & Rosicrucian Grimoire'


# ----------------------------------------------------------------- helpers

def read_source():
    with io.open(SRC, encoding='utf-8') as fh:
        return fh.read()


def split_document(html):
    """Return (head_css, body_inner)."""
    css = re.search(r'<style>(.*?)</style>', html, re.S).group(1)
    body = re.search(r'<main id="content">(.*?)</main>', html, re.S).group(1)
    return css, body


def chapters(body):
    """Split the body at each <h2 id=...> into (id, title, html)."""
    marks = [(m.start(), m.group(1), m.group(2))
             for m in re.finditer(r'<h2 id="([a-z]+)">(?:<span class="chapnum">([^<]*)</span>)?', body)]
    out = []
    for i, (pos, cid, chapnum) in enumerate(marks):
        end = marks[i + 1][0] if i + 1 < len(marks) else len(body)
        chunk = body[pos:end]
        t = re.search(r'<h2[^>]*>(.*?)</h2>', chunk, re.S).group(1)
        t = re.sub(r'<span class="difficulty[^>]*>.*?</span>', '', t, flags=re.S)
        # the chapter number lives in its own span inside the <h2>; leaving it in
        # glues "Chapter III" onto the title in the printed contents
        t = re.sub(r'<span class="chapnum">.*?</span>', '', t, flags=re.S)
        t = re.sub(r'<[^>]+>', '', t).strip()
        out.append({'id': cid, 'num': chapnum or '', 'title': t, 'html': chunk})
    front = body[:marks[0][0]] if marks else body
    return front, out


# ----------------------------------------------------------------- print edition

PRINT_CSS = u"""
@page {
    size: 6in 9in;
    margin: 0.8in 0.7in 0.9in 0.7in;

    /* No `content:` here. Paged.js resolves counter(page)/string() itself, and it
       counts front matter and flattens the whole <h2> (chapter number and
       difficulty badge included) into the running head. FOLIO_JS below fills
       these boxes instead. The single space is deliberate: with no `content:`
       at all Paged.js omits the margin boxes entirely and there is nothing left
       to fill. */
    @bottom-center {
        content: " ";
        font-family: Georgia, "Times New Roman", serif;
        font-size: 9pt;
        color: #555;
    }
}

@page :left {
    @top-left {
        content: " ";
        font-family: Georgia, "Times New Roman", serif;
        font-size: 8pt;
        letter-spacing: 0.09em;
        text-transform: uppercase;
        color: #6d6a64;
    }
}

@page :right {
    @top-right {
        content: " ";
        font-family: Georgia, "Times New Roman", serif;
        font-size: 8pt;
        letter-spacing: 0.09em;
        text-transform: uppercase;
        font-style: italic;
        color: #6d6a64;
    }
}

html { --bg:#fff; --fg:#1a1a1a; --accent:#6b3410; --rule:#c9c2ae;
       --panel:#f6f4ee; --panel-edge:#8a7b5c; --link:#1a1a1a;
       --warn-bg:#f7f0ee; --warn-edge:#8a3a2a; --note-bg:#f6f3ea;
       --note-edge:#8a7b5c; --muted:#54504a; }

body { background: #fff; color: #1a1a1a; font-size: 10.5pt; line-height: 1.42; }

.layout { display: block; }
.toc, .totop, .skip, .legend { display: none !important; }
main { max-width: none; padding: 0; margin: 0; }

h2 {
    break-before: page;
    font-size: 1.5em;
    border: none;
    text-align: center;
    margin: 2.2em 0 1.6em;
    letter-spacing: 0.02em;
}

h2 .difficulty { display: none; }

h2 .chapnum {
    display: block;
    font-size: 0.5em;
    letter-spacing: 0.3em;
    text-transform: uppercase;
    color: #7a7268;
    margin-bottom: 1.1em;
}

h3 { font-size: 1.05em; margin-top: 1.7em; break-after: avoid; }
h4 { break-after: avoid; }
p  { orphans: 3; widows: 3; text-align: justify; hyphens: auto; }

/* front matter: each on its own page, vertically centred, no rules */
.frontmatter .halftitle,
.frontmatter .titlepage,
.frontmatter .copyrightpage,
.frontmatter .epigraph {
    break-after: page;
    border-bottom: none;
    padding: 0;
    display: flex;
    flex-direction: column;
    justify-content: center;
    min-height: 6.6in;
}
.frontmatter .copyrightpage { display: block; padding-top: 2in; font-size: 8.5pt; }
.frontmatter { break-after: page; }

/* the contents page, rebuilt for print */
.printtoc { break-before: page; break-after: page; }
.printtoc h2 { break-before: avoid; }
.printtoc ol { list-style: none; padding: 0; margin: 2em 0 0; }
.printtoc li { margin: 0.55em 0; display: flex; align-items: baseline; }
.printtoc .n { width: 3.3em; color: #7a7268; font-size: 0.85em; letter-spacing: .1em; }
.printtoc .t { flex: 1; }
.printtoc .dots { flex: 1; border-bottom: 1px dotted #bbb; margin: 0 0.5em; transform: translateY(-0.25em); }
.printtoc .pg { width: 2.2em; text-align: right; font-size: 0.85em; color: #7a7268; }

figure.fig { break-inside: avoid; max-width: 100%; }
figure.fig svg { max-width: 3.9in; }
figure.fig .ink   { stroke: #1a1a1a; }
figure.fig .hi    { stroke: #6b3410; }
figure.fig .faint { stroke: #8a857c; opacity: .75; }
figure.fig .solid { fill: #6b3410; }
figure.fig .solidfg { fill: #1a1a1a; }
figure.fig text { fill: #1a1a1a; }
figure.fig text.lbl { fill: #6b3410; }
figure.fig text.tiny { fill: #54504a; }

.warning, .note, .modern, .rite { break-inside: avoid; background: #f7f5ef; }
.rite { border-left: 3px solid #6b3410; }
table.tbl { font-size: 9pt; }
table.tbl th { background: #f2efe6; }
a { color: inherit; text-decoration: none; }
.bib li { font-size: 9pt; margin-bottom: 0.5em; }

/* the index: two columns, tight, and never orphan a letter heading */
#index + p.idxnote, .idxnote { font-size: 8.5pt; }
h3.idxletter { font-size: 9.5pt; break-after: avoid; margin: 1.1em 0 0.4em; }
ul.idx { column-count: 2; column-gap: 1.4em; font-size: 8.2pt; }
ul.idx li { break-inside: avoid; margin: 0.06em 0; line-height: 1.25; }
.pd { font-size: 7.5pt; }
"""


# Paged.js 0.4.3 does resolve `content:` in @page margin boxes, but it resolves
# it wrongly for this book: counter(page) counts the front matter, and
# string(chaptitle) flattens the whole <h2>, chapter number and difficulty badge
# included. Those declarations are therefore gone from PRINT_CSS and the boxes
# are filled here instead. Runs once pagination has settled; also sets a flag
# the PDF step waits on.
FOLIO_JS = u"""
(function () {
  var BOOK = 'The Complete Hermetic \\u0026 Rosicrucian Grimoire';

  function fill() {
    var pages = Array.prototype.slice.call(document.querySelectorAll('.pagedjs_page'));
    if (!pages.length) return false;

    var firstNumbered = pages.findIndex(function (p) {
      return p.querySelector('h2[id]') && !p.querySelector('.printtoc');
    });
    if (firstNumbered < 0) firstNumbered = 0;

    // first pass: which folio does each chapter open on? The contents page
    // has no way to know this until pagination has actually run.
    var folioOf = {};
    pages.forEach(function (page, i) {
      var h = page.querySelector('h2[id]');
      if (h && i >= firstNumbered) folioOf[h.id] = i - firstNumbered + 1;
    });
    Array.prototype.forEach.call(document.querySelectorAll('.printtoc li[data-ch]'),
      function (li) {
        var n = folioOf[li.getAttribute('data-ch')];
        var cell = li.querySelector('.pg');
        if (cell && n) cell.textContent = String(n);
      });

    var chapter = '';
    pages.forEach(function (page, i) {
      var h2 = page.querySelector('h2[id]');
      if (h2) {
        var t = h2.cloneNode(true);
        Array.prototype.forEach.call(t.querySelectorAll('.difficulty, .chapnum'),
                                     function (n) { n.remove(); });
        chapter = t.textContent.trim();
      }

      // With no `content:` declared, Paged.js leaves both the margin box and its
      // content div hidden, so each must be forced visible before it is filled.
      var box = function (cls) {
        var outer = page.querySelector('.pagedjs_margin-' + cls);
        if (!outer) return null;
        outer.style.display = 'flex';
        var e = outer.querySelector('.pagedjs_margin-content');
        if (e) { e.style.display = 'block'; e.style.width = '100%'; }
        return e;
      };

      if (i >= firstNumbered) {
        var f = box('bottom-center');
        if (f) {
          f.textContent = String(i - firstNumbered + 1);
          f.style.textAlign = 'center';
          f.style.font = '9pt Georgia, "Times New Roman", serif';
          f.style.color = '#555';
        }
      }

      // running heads: verso carries the book, recto the chapter; never on an opener
      if (i >= firstNumbered && !h2) {
        var verso = page.classList.contains('pagedjs_left_page');
        var e = box(verso ? 'top-left' : 'top-right');
        if (e) {
          e.textContent = verso ? BOOK : chapter;
          e.style.textAlign = verso ? 'left' : 'right';
          e.style.font = '8pt Georgia, "Times New Roman", serif';
          e.style.letterSpacing = '0.09em';
          e.style.textTransform = 'uppercase';
          e.style.color = '#6d6a64';
          e.style.whiteSpace = 'nowrap';
          if (!verso) e.style.fontStyle = 'italic';
        }
      }
    });
    return true;
  }

  // Paged.js calls this once the whole flow is laid out. Watching the page
  // count instead snapshots early: on a large document the count plateaus
  // mid-render and any stability heuristic fires while text is still flowing.
  window.PagedConfig = window.PagedConfig || {};
  window.PagedConfig.after = function () {
    try { fill(); } finally { window.__grimoireFolios = true; }
  };
})();
"""


def ensure_pagedjs():
    if os.path.exists(VENDOR):
        return io.open(VENDOR, encoding='utf-8', errors='replace').read()
    os.makedirs(os.path.dirname(VENDOR), exist_ok=True)
    sys.stderr.write('fetching Paged.js ...\n')
    import urllib.request
    with urllib.request.urlopen(PAGEDJS_URL, timeout=120) as r:
        data = r.read().decode('utf-8', 'replace')
    with io.open(VENDOR, 'w', encoding='utf-8') as fh:
        fh.write(data)
    return data


def build_print(html):
    css, body = split_document(html)
    front, chs = chapters(body)

    toc_rows = []
    n = 0
    for c in chs:
        if c['id'] == 'sources':
            toc_rows.append(u'<li data-ch="%s"><span class="n"></span><span class="t">%s</span>'
                            u'<span class="dots"></span><span class="pg"></span></li>'
                            % (c['id'], c['title']))
        else:
            n += 1
            toc_rows.append(u'<li data-ch="%s"><span class="n">%s</span><span class="t">%s</span>'
                            u'<span class="dots"></span><span class="pg"></span></li>'
                            % (c['id'], c['num'].replace('Chapter ', ''), c['title']))
    printtoc = (u'<section class="printtoc"><h2>Contents</h2><ol>%s</ol></section>\n'
                % u''.join(toc_rows))

    # front matter, then the print contents page, then the chapters
    newbody = front + printtoc + u''.join(c['html'] for c in chs)

    paged = FOLIO_JS + u'\n' + ensure_pagedjs()
    out = html
    out = out.replace(u'<main id="content">' + body + u'</main>',
                      u'<main id="content">' + newbody + u'</main>')
    out = out.replace(u'</style>', u'</style>\n<style>' + PRINT_CSS + u'</style>')
    out = out.replace(u'</body>', u'<script>\n' + paged + u'\n</script>\n</body>')
    out = out.replace(u'<title>', u'<title>Print edition &#8212; ', 1)

    with io.open(BOOK_HTML, 'w', encoding='utf-8', newline='') as fh:
        fh.write(out)
    return BOOK_HTML


# ----------------------------------------------------------------- PDF

def find_chrome():
    cands = [
        r'C:\Program Files\Google\Chrome\Application\chrome.exe',
        r'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe',
        os.path.expanduser(r'~\AppData\Local\Google\Chrome\Application\chrome.exe'),
        shutil.which('google-chrome'), shutil.which('chromium'),
    ]
    for c in cands:
        if c and os.path.exists(c):
            return c
    return None


def build_pdf(book_html):
    """Print via the DevTools Protocol.

    Chrome's --print-to-pdf snapshots at the load event, which is long before
    Paged.js has finished laying the text into pages - it yields a blank file.
    So: launch with a debugging port, wait until the page count stops changing,
    then call Page.printToPDF. preferCSSPageSize honours the @page rule, and the
    margins are zero because Paged.js has already drawn them inside each page box.
    """
    chrome = find_chrome()
    if not chrome:
        sys.stderr.write('  ! Chrome not found; skipping PDF\n')
        return None
    try:
        import websocket
    except ImportError:
        sys.stderr.write('  ! websocket-client not installed; skipping PDF\n')
        sys.stderr.write('    pip install websocket-client\n')
        return None

    import base64
    import json
    import tempfile
    import time
    import urllib.request

    port = 9333
    profile = tempfile.mkdtemp(prefix='grimoire-chrome-')
    proc = subprocess.Popen(
        [chrome, '--headless=new', '--disable-gpu', '--no-sandbox', '--mute-audio',
         '--remote-debugging-port=%d' % port, '--remote-allow-origins=*',
         '--user-data-dir=' + profile, 'about:blank'],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    try:
        ws_url = None
        for _ in range(60):
            try:
                raw = urllib.request.urlopen('http://127.0.0.1:%d/json/list' % port, timeout=2).read()
                for t in json.loads(raw):
                    if t.get('type') == 'page':
                        ws_url = t['webSocketDebuggerUrl']
                        break
                if ws_url:
                    break
            except Exception:
                pass
            time.sleep(0.5)
        if not ws_url:
            sys.stderr.write('  ! could not reach Chrome DevTools; skipping PDF\n')
            return None

        ws = websocket.create_connection(ws_url, timeout=180)
        seq = {'n': 0}

        def cmd(method, params=None):
            seq['n'] += 1
            mid = seq['n']
            ws.send(json.dumps({'id': mid, 'method': method, 'params': params or {}}))
            while True:
                msg = json.loads(ws.recv())
                if msg.get('id') == mid:
                    if 'error' in msg:
                        raise RuntimeError('%s: %s' % (method, msg['error']))
                    return msg.get('result', {})

        cmd('Page.enable')
        cmd('Page.navigate', {'url': 'file:///' + book_html.replace('\\', '/')})

        # Wait for the `after` hook, which the folio pass turns into
        # window.__grimoireFolios. That is the real completion signal;
        # page-count polling produced a 26-page PDF from a 139-page document
        # once the plates made layout slow enough to plateau mid-render.
        last = 0
        for _ in range(600):
            time.sleep(0.5)
            try:
                done = cmd('Runtime.evaluate',
                           {'expression': '!!window.__grimoireFolios',
                            'returnByValue': True}).get('result', {}).get('value')
                last = cmd('Runtime.evaluate',
                           {'expression': 'document.querySelectorAll(".pagedjs_page").length',
                            'returnByValue': True}).get('result', {}).get('value', 0) or 0
            except Exception:
                done = False
            if done:
                break
        sys.stderr.write('    paginated: %d pages\n' % last)
        if not last:
            sys.stderr.write('  ! Paged.js produced no pages; skipping PDF\n')
            return None

        res = cmd('Page.printToPDF', {
            'printBackground': True,
            'preferCSSPageSize': True,
            'paperWidth': 6.0, 'paperHeight': 9.0,
            'marginTop': 0, 'marginBottom': 0, 'marginLeft': 0, 'marginRight': 0,
        })
        with open(PDF, 'wb') as fh:
            fh.write(base64.b64decode(res['data']))
        ws.close()
        return PDF
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except Exception:
            proc.kill()
        shutil.rmtree(profile, ignore_errors=True)


# ----------------------------------------------------------------- EPUB

NAMED = {'nbsp': '160', 'mdash': '8212', 'ndash': '8211', 'hellip': '8230',
         'lsquo': '8216', 'rsquo': '8217', 'ldquo': '8220', 'rdquo': '8221',
         'copy': '169', 'deg': '176', 'middot': '183', 'times': '215',
         'eacute': '233', 'egrave': '232', 'agrave': '224', 'ccedil': '231',
         'auml': '228', 'ouml': '246', 'uuml': '252', 'szlig': '223'}


def xhtmlify(frag):
    """Make an HTML fragment XHTML-parseable."""
    for name, num in NAMED.items():
        frag = frag.replace('&%s;' % name, '&#%s;' % num)
        frag = frag.replace('&%s' % name, '&#%s;' % num)
    frag = re.sub(r'&(?!(?:amp|lt|gt|quot|apos|#\d+|#x[0-9a-fA-F]+);)', '&amp;', frag)
    frag = re.sub('<(br|hr|img|meta|link|input|col)\\b((?:[^>"\']|"[^"]*"|\'[^\']*\')*?)/?>', '<\\1\\2 />', frag)
    frag = re.sub(r'\s+/>', ' />', frag)
    return frag


PAGE = (u'<?xml version="1.0" encoding="utf-8"?>\n'
        u'<!DOCTYPE html>\n'
        u'<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" lang="en">\n'
        u'<head><meta charset="utf-8" /><title>%s</title>'
        u'<link rel="stylesheet" type="text/css" href="style.css" /></head>\n'
        u'<body>%s</body>\n</html>\n')

EPUB_CSS = u"""
body { font-family: Georgia, "Times New Roman", serif; line-height: 1.5; margin: 0 5%; }
h1, h2, h3, h4 { font-weight: normal; line-height: 1.25; }
h2 { text-align: center; margin: 1.4em 0 1.2em; font-size: 1.4em; }
h2 .chapnum { display: block; font-size: .5em; letter-spacing: .28em;
              text-transform: uppercase; color: #777; margin-bottom: 1em; }
h2 .difficulty, .skip, .totop { display: none; }
h3 { font-size: 1.05em; margin-top: 1.6em; }
p { text-align: justify; margin: 0 0 .85em; }
blockquote { margin: 1.2em 1.4em; font-style: italic; }
.warning, .note, .modern, .rite { background: #f6f4ee; border-left: 3px solid #8a7b5c;
                                  padding: .8em 1em; margin: 1.3em 0; }
.rite { border-left-color: #6b3410; }
.rite h4, .note h4, .modern h4 { margin-top: 0; text-transform: uppercase;
                                 font-size: .8em; letter-spacing: .05em; color: #6b3410; }
.say { display: block; font-style: italic; color: #6b3410; margin: .35em 0; }
.say .heb { font-style: normal; font-weight: bold; }
.say .pron { font-style: normal; font-size: .85em; color: #666; }
.sources { font-size: .85em; color: #555; border-top: 1px solid #ccc;
           padding-top: .6em; margin-top: 1.6em; }
table.tbl { border-collapse: collapse; width: 100%; font-size: .9em; }
table.tbl th, table.tbl td { border: 1px solid #ccc; padding: .4em .5em;
                             text-align: left; vertical-align: top; }
table.tbl th { background: #f2efe6; }
figure.fig { margin: 1.6em 0; text-align: center; }
figure.fig svg { max-width: 100%; height: auto; }
figure.fig .ink { stroke: #1a1a1a; fill: none; stroke-width: 1.4; }
figure.fig .hi { stroke: #6b3410; fill: none; stroke-width: 1.8; }
figure.fig .faint { stroke: #8a857c; fill: none; stroke-width: 1; opacity: .7; }
figure.fig .solid { fill: #6b3410; }
figure.fig .solidfg { fill: #1a1a1a; }
figure.fig text { fill: #1a1a1a; font-size: 13px; font-family: Georgia, serif; }
figure.fig text.lbl { fill: #6b3410; font-size: 12px; }
figure.fig text.tiny { fill: #54504a; font-size: 10.5px; }
figure.fig figcaption { font-size: .84em; color: #555; text-align: left; margin-top: .6em; }
.bib { font-size: .92em; }
.pd { font-size: .78em; color: #666; text-transform: uppercase; letter-spacing: .05em; }
.frontmatter div { text-align: center; margin: 3em 0; page-break-after: always; }
.copyrightpage { text-align: left; font-size: .85em; color: #444; }
a { color: inherit; }
"""


def build_epub(html):
    _, body = split_document(html)
    front, chs = chapters(body)

    files = []
    files.append(('front.xhtml', 'Title Page', PAGE % ('Title Page', xhtmlify(front))))
    for i, c in enumerate(chs, 1):
        name = 'ch%02d.xhtml' % i
        files.append((name, c['title'], PAGE % (c['title'], xhtmlify(c['html']))))

    nav_items = u''.join(u'<li><a href="%s">%s</a></li>' % (n, t) for n, t, _ in files[1:])
    nav = PAGE % ('Contents',
                  u'<nav epub:type="toc" id="toc"><h1>Contents</h1><ol>%s</ol></nav>' % nav_items)

    manifest = u''.join(
        u'<item id="i%d" href="%s" media-type="application/xhtml+xml"/>' % (i, n)
        for i, (n, _, _) in enumerate(files))
    spine = u''.join(u'<itemref idref="i%d"/>' % i for i in range(len(files)))

    opf = (u'<?xml version="1.0" encoding="utf-8"?>\n'
           u'<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="bookid">\n'
           u'<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">\n'
           u'<dc:identifier id="bookid">urn:uuid:grimoire-hermetic-rosicrucian</dc:identifier>\n'
           u'<dc:title>%s</dc:title>\n<dc:language>en</dc:language>\n'
           u'<meta property="dcterms:modified">2026-07-30T00:00:00Z</meta>\n'
           u'</metadata>\n<manifest>%s'
           u'<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>'
           u'<item id="css" href="style.css" media-type="text/css"/>'
           u'</manifest>\n<spine>%s</spine>\n</package>\n') % (TITLE.replace('&', '&amp;'), manifest, spine)

    if os.path.exists(EPUB):
        os.remove(EPUB)
    with zipfile.ZipFile(EPUB, 'w') as z:
        z.writestr(zipfile.ZipInfo('mimetype'), 'application/epub+zip',
                   compress_type=zipfile.ZIP_STORED)
        z.writestr('META-INF/container.xml',
                   '<?xml version="1.0" encoding="utf-8"?>\n'
                   '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
                   '<rootfiles><rootfile full-path="OEBPS/content.opf" '
                   'media-type="application/oebps-package+xml"/></rootfiles></container>',
                   compress_type=zipfile.ZIP_DEFLATED)
        z.writestr('OEBPS/content.opf', opf, compress_type=zipfile.ZIP_DEFLATED)
        z.writestr('OEBPS/nav.xhtml', nav, compress_type=zipfile.ZIP_DEFLATED)
        z.writestr('OEBPS/style.css', EPUB_CSS, compress_type=zipfile.ZIP_DEFLATED)
        for name, _, content in files:
            z.writestr('OEBPS/' + name, content, compress_type=zipfile.ZIP_DEFLATED)
    return EPUB


# ----------------------------------------------------------------- main

def main():
    html = read_source()
    print('source: %s (%d bytes)' % (os.path.basename(SRC), len(html)))

    book = build_print(html)
    print('  print edition -> %s (%d bytes)' % (os.path.basename(book), os.path.getsize(book)))

    pdf = build_pdf(book)
    if pdf:
        print('  pdf           -> %s (%d bytes)' % (os.path.basename(pdf), os.path.getsize(pdf)))

    ep = build_epub(html)
    print('  epub          -> %s (%d bytes)' % (os.path.basename(ep), os.path.getsize(ep)))


if __name__ == '__main__':
    main()
