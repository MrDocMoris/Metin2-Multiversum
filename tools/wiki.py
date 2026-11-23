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
from bs4 import BeautifulSoup, NavigableString, Tag

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


# ---------- Übersicht: alle Monster ----------
def monster_list():
    soup = get('Monster')
    if not soup:
        raise SystemExit('Monster-Seite nicht erreichbar')
    out, seen = [], set()
    for table in content(soup).find_all('table'):
        rows = table.find_all('tr')
        if not rows:
            continue
        head = [txt(c).lower() for c in rows[0].find_all(['th', 'td'])]
        if 'name' not in head:
            continue
        col = {k: (head.index(k) if k in head else None) for k in ['rasse', 'level', 'stufe', 'name', 'ort', 'exp', 'element']}
        for tr in rows[1:]:
            cells = tr.find_all(['td', 'th'])
            if len(cells) <= col['name']:
                continue
            nc = cells[col['name']]
            a = next((x for x in nc.find_all('a') if page_of(x)), None)
            if not a:
                continue
            p = page_of(a)
            if p in seen:
                continue
            seen.add(p)

            def cell(k):
                i = col[k]
                if i is None or i >= len(cells):
                    return ''
                c = cells[i]
                t = txt(c)
                if not t:  # nur Symbol -> Bildtitel nehmen
                    img = c.find('img')
                    t = (img.get('alt') or '').rsplit('.', 1)[0] if img else ''
                    a2 = c.find('a')
                    if a2 and a2.get('title'):
                        t = a2['title']
                return t
            out.append({'n': txt(nc), 'p': p, 'lv': num(cell('level')), 'st': num(cell('stufe')), 'r': cell('rasse'),
                        'el': cell('element'), 'ort': [o.strip() for o in re.split(r'\s*/\s*|,\s*', cell('ort')) if o.strip()],
                        'exp': num(cell('exp')), 't': 'm'})
    print(f'{len(out)} Monster in der Übersicht')
    return out


# ---------- Übersicht: Metinsteine ----------
def metin_list(known):
    soup = get('Metins')
    out = []
    if not soup:
        print('Metins-Seite nicht erreichbar')
        return out
    seen = set(known)
    for a in content(soup).find_all('a'):
        p = page_of(a)
        name = txt(a)
        if not p or p in seen or 'metin' not in (name + p).lower() or len(name) < 4:
            continue
        seen.add(p)
        row = a.find_parent(['tr', 'li'])
        lv = None
        if row:
            m = re.match(r'\s*(\d+)', txt(row))
            lv = int(m.group(1)) if m else None
        out.append({'n': name, 'p': p, 'lv': lv, 'st': None, 'r': 'Metin', 'el': '', 'ort': [], 'exp': None, 't': 'metin'})
    print(f'{len(out)} Metins in der Übersicht')
    return out


# ---------- Einzelseite: Drops, Spawns, Werte ----------
CATS = [
    ('w', re.compile(r'^waffen-?dropp?s?$', re.I)),
    ('r', re.compile(r'^r(ü|ue)stungs?-?dropp?s?$', re.I)),
    ('s', re.compile(r'^schmuck-?dropp?s?$', re.I)),
    ('u', re.compile(r'^upp-?items?-?dropp?s?$', re.I)),
    ('b', re.compile(r'^(lehren|b(ü|ue)cher|lehrb(ü|ue)cher)-?dropp?s?$', re.I)),
    ('o', re.compile(r'^(sonstiges?|andere|weitere)-?dropp?s?$', re.I)),
    ('o', re.compile(r'^dropp?s?$', re.I)),
    ('sp', re.compile(r'^(spawns?|fundorte?|vorkommen)$', re.I)),
]
STOP = re.compile(r'^(weitere informationen|statuswerte|status|trefferpunkte|quests?|gruppierung|bonus|siehe auch)$', re.I)


def cat_of(text):
    t = text.strip().rstrip(':').strip()
    if len(t) > 40:
        return None
    if STOP.match(t):
        return 'stop'
    for k, rx in CATS:
        if rx.match(t):
            return k
    return None


def own_text(tag):
    return ''.join(s for s in tag.find_all(string=True, recursive=True)).strip()


def parse_page(entry):
    soup = get(entry['p'])
    if not soup:
        return False
    c = content(soup)
    for bad in c.select('.toc, .navbox, .printfooter, .catlinks, script, style'):
        bad.decompose()
    d = {k: [] for k in ['w', 'r', 's', 'u', 'b', 'o']}
    spawns = []
    used = set()

    def add(k, a):
        p = page_of(a)
        name = txt(a)
        if not p or not name or id(a) in used:
            return
        used.add(id(a))
        if k == 'sp':
            if name not in spawns:
                spawns.append(name)
        elif k in d and name not in d[k] and name != entry['n']:
            d[k].append(name)

    # 1) Tabellen, deren Kopfzeile die Kategorien als Spalten hat
    for table in c.find_all('table'):
        rows = table.find_all('tr', recursive=False) or table.find_all('tr')
        colcat = None
        for tr in rows:
            cells = tr.find_all(['th', 'td'], recursive=False)
            cats = [cat_of(own_text(x)) for x in cells]
            if sum(1 for x in cats if x and x != 'stop') >= 2:
                colcat = cats
                continue
            if colcat:
                for i, cell in enumerate(cells):
                    k = colcat[i] if i < len(colcat) else None
                    if k and k != 'stop':
                        for a in cell.find_all('a'):
                            add(k, a)

    # 2) Alles andere der Reihe nach: Überschrift setzt die Kategorie, Links danach gehören dazu
    cur = None
    for el in c.descendants:
        if isinstance(el, NavigableString):
            if isinstance(el.parent, Tag) and el.parent.name == 'a':
                continue
            k = cat_of(str(el))
            if k == 'stop':
                cur = None
            elif k:
                cur = k
        elif isinstance(el, Tag) and el.name == 'a' and cur:
            add(cur, el)

    # Werte aus dem Infokasten
    text = txt(c)
    for key, rx in [('lv', r'\bLevel\s*:?\s*(\d+)'), ('st', r'\bStufe\s*:?\s*(\d+)'), ('exp', r'\bEXP\s*:?\s*([\d.]+)'), ('hp', r'Trefferpunkte\s*:?\s*([\d.]+)')]:
        if entry.get(key) is None:
            m = re.search(rx, text)
            if m:
                entry[key] = int(m.group(1).replace('.', ''))
    if spawns and not entry['ort']:
        entry['ort'] = spawns[:12]
    elif spawns:
        entry['ort'] = list(dict.fromkeys(entry['ort'] + spawns))[:12]
    entry['d'] = {k: v for k, v in d.items() if v}
    return True


def main():
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    mons = monster_list()
    time.sleep(PAUSE)
    mets = metin_list({m['p'] for m in mons})
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
