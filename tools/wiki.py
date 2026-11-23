#!/usr/bin/env python3
"""Holt Monster, Metins und ihre Drops aus dem offiziellen deutschen Metin2-Wiki
(https://de-wiki.metin2.gameforge.com) und schreibt daten/wiki.json für die App.

Läuft in GitHub Actions (siehe .github/workflows/wiki.yml). Bewusst langsam
(Pause zwischen den Seiten), damit das Wiki nicht belastet wird.
Aufruf: python tools/wiki.py [max_seiten]
"""
import json, os, re, sys, time, datetime
from urllib.parse import unquote, urljoin
import requests
from bs4 import BeautifulSoup

BASE = 'https://de-wiki.metin2.gameforge.com'
UA = 'Metin2-Multiversum/1.0 (private Begleit-App; github.com/MrDocMoris/Metin2-Multiversum)'
PAUSE = 0.8
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'daten', 'wiki.json')

S = requests.Session()
S.headers['User-Agent'] = UA


def get(page):
    url = page if page.startswith('http') else f'{BASE}/index.php/{page}'
    for i in range(3):
        try:
            r = S.get(url, timeout=30)
            if r.status_code == 200:
                return BeautifulSoup(r.text, 'html.parser')
            if r.status_code == 404:
                return None
        except requests.RequestException as e:
            print('  Fehler', url, e)
        time.sleep(3 * (i + 1))
    return None


def content(soup):
    return soup.find(id='mw-content-text') or soup.body


SKIP_NS = ('Datei:', 'File:', 'Kategorie:', 'Category:', 'Spezial:', 'Special:', 'Vorlage:', 'Template:', 'Benutzer:', 'Hilfe:', 'Metin2Wiki:')


def page_of(a):
    """Seitenname eines Wiki-Links oder None (Bilder, rote Links, externe Links …)."""
    h = a.get('href') or ''
    if 'redlink=1' in h or not h.startswith('/index.php/'):
        return None
    p = unquote(h[len('/index.php/'):]).split('#')[0]
    if not p or p.startswith(SKIP_NS):
        return None
    return p


def txt(el):
    return re.sub(r'\s+', ' ', el.get_text(' ', strip=True)).strip()


def num(s):
    m = re.search(r'\d[\d.]*', s or '')
    return int(m.group(0).replace('.', '')) if m else None


def strip_hidden(root):
    """Versteckte Sortier-Schlüssel (display:none) entfernen."""
    for el in root.find_all(style=re.compile(r'display:\s*none')):
        el.decompose()


def table_rows(table):
    return [tr for tr in table.find_all('tr') if tr.find_parent('table') is table]


def name_link(cell):
    """Erster Text-Link einer Zelle (Bild-Links überspringen)."""
    for a in cell.find_all('a'):
        if page_of(a) and txt(a):
            return a
    return None


def links_text(cell):
    return [txt(a) for a in cell.find_all('a') if page_of(a) and txt(a)]


# ---------- Übersichten: Monster und Metins ----------
def overview(page, kind):
    soup = get(page)
    if not soup:
        print(f'{page}: nicht erreichbar')
        return []
    c = content(soup)
    strip_hidden(c)
    out, seen = [], set()
    for table in c.find_all('table'):
        rows = table_rows(table)
        col = None
        for tr in rows:
            cells = tr.find_all(['td', 'th'], recursive=False)
            head = [txt(x).lower() for x in cells]
            if 'name' in head:
                col = {k: next((i for i, h in enumerate(head) if h.startswith(k)), None)
                       for k in ['rasse', 'level', 'stufe', 'name', 'ort', 'bevorzugte', 'exp', 'element']}
                continue
            if not col or col['name'] is None or len(cells) <= col['name']:
                continue
            a = name_link(cells[col['name']])
            if not a or page_of(a) in seen:
                continue
            seen.add(page_of(a))

            def cell(k):
                i = col.get(k)
                return cells[i] if i is not None and i < len(cells) else None
            e = {'n': txt(a), 'p': page_of(a), 't': kind}
            if cell('level') is not None:
                e['lv'] = num(txt(cell('level')))
            if cell('stufe') is not None:
                e['st'] = num(txt(cell('stufe')))
            if cell('exp') is not None:
                e['exp'] = num(txt(cell('exp')))
            r = cell('rasse')
            if r is not None:
                ra = name_link(r)
                e['r'] = (ra.get('title') if ra else txt(r)) or ''
            if kind == 'metin':
                e['r'] = 'Metin'
            el = cell('element')
            if el is not None:
                t = txt(el)
                img = el.find('img')
                e['el'] = t or ((img.get('alt') or '').rsplit('.', 1)[0] if img else '')
            o = cell('ort') or cell('bevorzugte')
            e['ort'] = links_text(o) if o is not None else []
            out.append(e)
    print(f'{page}: {len(out)} Einträge')
    return out


# ---------- Einzelseite: Drops, Spawns, Werte ----------
CATS = [
    ('w', re.compile(r'^waffen-?dropp?s?$', re.I)),
    ('r', re.compile(r'^r(ü|ue)stungs?-?dropp?s?$', re.I)),
    ('s', re.compile(r'^schmuck-?dropp?s?$', re.I)),
    ('u', re.compile(r'^upp-?items?-?dropp?s?$', re.I)),
    ('b', re.compile(r'^(lehren|b(ü|ue)cher|lehrb(ü|ue)cher)-?dropp?s?$', re.I)),
    ('o', re.compile(r'^(sonstiges?|andere)-?dropp?s?$', re.I)),
    ('sp', re.compile(r'^spawns?$', re.I)),
]


def cat_of(text):
    t = (text or '').strip().rstrip(':').strip()
    if len(t) > 30:
        return None
    for k, rx in CATS:
        if rx.match(t):
            return k
    return None


def parse_page(entry):
    soup = get(entry['p'])
    if not soup:
        return False
    c = content(soup)
    strip_hidden(c)
    d = {k: [] for k in ['w', 'r', 's', 'u', 'b', 'o']}
    spawns = []
    # Kopfzeile mit Kategorien -> nächste Zeile enthält die Listen (Spalte für Spalte)
    for table in c.find_all('table'):
        colcat = None
        for tr in table_rows(table):
            cells = tr.find_all(['td', 'th'], recursive=False)
            cats = [cat_of(txt(x)) for x in cells]
            if any(cats):
                colcat = cats
                continue
            if not colcat:
                continue
            for i, cell in enumerate(cells):
                k = colcat[i] if i < len(colcat) else None
                if not k:
                    continue
                for li in cell.find_all('li'):
                    if k == 'sp':
                        g = li.find_previous(string=re.compile('Gruppierung'))
                        if g and cell in g.parents:
                            continue
                    a = name_link(li)
                    if not a:
                        continue
                    if k == 'sp':
                        rest = txt(li).replace(txt(a), '', 1).strip()
                        name = txt(a) + (f' ({rest})' if rest and len(rest) < 25 else '')
                        if name not in spawns:
                            spawns.append(name)
                    else:
                        name = a.get('title') or txt(a)
                        if name not in d[k] and name != entry['n']:
                            d[k].append(name)
            colcat = None
    # Werte aus dem Infokasten ("Level 75 Stufe BOSS EXP 12.040 …")
    text = txt(c)
    m = re.search(r'\bStufe\s+(BOSS|Boss|\d+)', text)
    if m:
        if m.group(1).lower() == 'boss':
            entry['st'] = max(entry.get('st') or 0, 5)
            entry['boss'] = 1
        elif not entry.get('st'):
            entry['st'] = int(m.group(1))
    for key, rx in [('lv', r'\bLevel\s+(\d+)'), ('exp', r'\bEXP\s+([\d.]+)'), ('hp', r'Trefferpunkte\s*:?\s*([\d.]+)')]:
        if not entry.get(key):
            m = re.search(rx, text)
            if m:
                entry[key] = int(m.group(1).replace('.', ''))
    if spawns:
        entry['ort'] = spawns[:15]
    entry['d'] = {k: v for k, v in d.items() if v}
    return True


def main():
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    mons = overview('Monster', 'm')
    time.sleep(PAUSE)
    known = {m['p'] for m in mons}
    mets = [e for e in overview('Metins', 'metin') if e['p'] not in known]
    all_ = mons + mets
    if limit:
        all_ = all_[:limit]
    ok = 0
    for i, e in enumerate(all_):
        time.sleep(PAUSE)
        if parse_page(e):
            ok += 1
        if i % 50 == 0:
            print(f'{i}/{len(all_)} … {e["n"]}: {sum(len(v) for v in e.get("d", {}).values())} Drops')
    with_drops = sum(1 for e in all_ if e.get('d'))
    print(f'Fertig: {ok}/{len(all_)} Seiten gelesen, {with_drops} mit Drops')
    if len(all_) < 50 or with_drops < 20:
        raise SystemExit('Zu wenig Daten – Wiki-Aufbau geändert? Alte Datei bleibt.')
    for e in all_:
        for k in [k for k, v in e.items() if v in (None, '', [], {})]:
            del e[k]
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    data = {'stand': datetime.date.today().isoformat(), 'quelle': BASE, 'eintraege': all_}
    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, separators=(',', ':'))
    print(f'{OUT}: {os.path.getsize(OUT) // 1024} KB')


if __name__ == '__main__':
    main()
