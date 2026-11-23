#!/usr/bin/env python3
"""Wiki-Bibliothek: holt die Themen-Seiten des deutschen Metin2-Wikis
(Klassen, Systeme wie Drachensteinalchemie, Ausrüstung, Quests, Truhen, Maps …)
als bereinigtes HTML für die App.

Ergebnis:
  daten/seiten.json         – Inhaltsverzeichnis (Titel, Gruppe, Überschriften, Vorschau)
  daten/seiten/<id>.json    – eine Datei pro Seite mit dem bereinigten Inhalt

Monster und Metins stecken schon strukturiert in daten/wiki.json und werden hier übersprungen.
Aufruf: python tools/wiki_seiten.py [max_seiten]
"""
import hashlib, json, os, re, sys, time, datetime
from urllib.parse import unquote, quote
import requests
from bs4 import BeautifulSoup, Comment

BASE = 'https://de-wiki.metin2.gameforge.com'
UA = 'Metin2-Multiversum/1.0 (private Begleit-App; github.com/MrDocMoris/Metin2-Multiversum)'
PAUSE = 0.8
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, 'daten', 'seiten')
OUT_IDX = os.path.join(ROOT, 'daten', 'seiten.json')

# Abschnitte der Hauptseite, die in die App kommen
GRUPPEN = {
    'Aktuelle Events': 'Aktuell', 'Aktuelle Ankündigungen': 'Aktuell', 'Wichtige Direktlinks': 'Allgemein',
    'Klassen': 'Klassen', 'Charakter-Fähigkeiten': 'Fähigkeiten', 'Schmuck und Ausrüstung': 'Ausrüstung',
    'Systeme': 'Systeme', 'Sonstige Übersichten': 'Übersichten',
    'Weltkarte - Alter Kontinent': 'Maps', 'Weltkarte - Neuer Kontinent': 'Maps',
}
# Von diesen Gruppen werden auch die verlinkten Unterseiten geholt (z. B. alle Quests, Truhen, Fertigkeiten)
TIEFER = {'Systeme', 'Übersichten', 'Fähigkeiten', 'Ausrüstung', 'Klassen'}
SKIP = re.compile(r'^(Spezial|Kategorie|Datei|File|Vorlage|Benutzer|Hilfe|MediaWiki|metin2|Diskussion)[: ]|^(GameMaster|Team|Wie_helfe|Botjagd|Bots_und_Cheater)', re.I)
MAX_SEITEN = 700

S = requests.Session()
S.headers['User-Agent'] = UA


def get(page):
    url = f'{BASE}/index.php/{quote(page, safe="/:()_,-.")}' if not page.startswith('http') else page
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


def page_of(href):
    if not href or 'redlink=1' in href or not href.startswith('/index.php/'):
        return None
    p = unquote(href[len('/index.php/'):]).split('#')[0]
    return None if not p or SKIP.search(p) else p


def pid(page):
    return hashlib.md5(page.encode('utf-8')).hexdigest()[:12]


def clean_text(s):
    return re.sub(r'\s+', ' ', s or '').strip()


ALLOWED = {'h2', 'h3', 'h4', 'p', 'ul', 'ol', 'li', 'table', 'thead', 'tbody', 'tr', 'td', 'th', 'b', 'strong', 'i', 'em', 'br', 'a', 'img', 'div', 'span', 'small', 'sup', 'sub', 'center', 'dl', 'dt', 'dd', 'hr'}


def clean_html(c, title):
    """Nur einfache, sichere Tags behalten; interne Links -> data-w, Bilder -> absolute URL."""
    for bad in c.select('script, style, noscript, .toc, #toc, .mw-editsection, .navbox, .printfooter, .catlinks, .mw-jump-link, .noprint, .mw-empty-elt'):
        bad.decompose()
    for img in c.select('img[alt^="HomeNav"]'):  # Brotkrumen-Navigation oben
        ul = img.find_parent('ul')
        (ul or img).decompose()
    for cm in c.find_all(string=lambda x: isinstance(x, Comment)):
        cm.extract()
    for el in list(c.find_all(True)):
        if el.name not in ALLOWED:
            el.unwrap()
            continue
        attrs = {}
        if el.name == 'a':
            p = page_of(el.get('href'))
            if p:
                attrs['data-w'] = p
            elif (el.get('href') or '').startswith('http'):
                attrs['href'] = el['href']
            if el.find('img') and not el.get_text(strip=True):
                el.unwrap()  # Bild-Links: nur das Bild behalten
                continue
        elif el.name == 'img':
            src = el.get('src') or ''
            if not src or 'Hintergrund.png' in src:
                el.decompose()
                continue
            attrs['src'] = src if src.startswith('http') else BASE + src
            for k in ('width', 'height', 'alt'):
                if el.get(k):
                    attrs[k] = el[k]
            attrs['loading'] = 'lazy'
        elif el.name in ('td', 'th'):
            for k in ('colspan', 'rowspan'):
                if el.get(k):
                    attrs[k] = el[k]
        el.attrs = attrs
    # leere Container entfernen
    for el in c.find_all(['div', 'span', 'p']):
        if not el.get_text(strip=True) and not el.find('img'):
            el.decompose()
    html = str(c)
    html = re.sub(r'<div[^>]*id="mw-content-text"[^>]*>', '', html, count=1)
    html = re.sub(r'\s+', ' ', html)
    html = re.sub(r'(<br/?>\s*){3,}', '<br><br>', html)
    return html.strip()


def hauptseite():
    soup = get('Hauptseite')
    if not soup:
        raise SystemExit('Hauptseite nicht erreichbar')
    c = soup.find(id='mw-content-text')
    cur, out = None, []
    for el in c.descendants:
        name = getattr(el, 'name', None)
        if name in ('h1', 'h2', 'h3', 'h4') or (name == 'div' and 'font-weight' in (el.get('style') or '') and not el.find('div') and len(el.get_text(strip=True)) < 40):
            t = clean_text(el.get_text(' '))
            if t:
                cur = t
        elif name == 'a' and el.get_text(strip=True):
            p = page_of(el.get('href'))
            g = GRUPPEN.get(cur)
            if p and g and p not in [x[0] for x in out]:
                out.append((p, g))
    return out


def main():
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else MAX_SEITEN
    skip = set()
    wj = os.path.join(ROOT, 'daten', 'wiki.json')
    if os.path.exists(wj):  # Monster & Metins gibt es schon strukturiert
        skip = {e['p'] for e in json.load(open(wj, encoding='utf-8')).get('eintraege', [])}
    queue = hauptseite()
    print(f'Hauptseite: {len(queue)} Themen-Seiten')
    seen, index = set(), []
    os.makedirs(OUT_DIR, exist_ok=True)
    i = 0
    while i < len(queue) and len(index) < limit:
        page, group = queue[i]
        i += 1
        if page in seen or page in skip:
            continue
        seen.add(page)
        time.sleep(PAUSE)
        soup = get(page)
        if not soup:
            continue
        c = soup.find(id='mw-content-text')
        if not c:
            continue
        title = clean_text((soup.find(id='firstHeading') or soup.find('h1') or soup.title).get_text()).replace(' – Metin2 Wiki', '')
        # Unterseiten merken (bevor das HTML bereinigt wird)
        if group in TIEFER and len(queue) < limit * 3:
            for a in c.find_all('a'):
                p = page_of(a.get('href'))
                if p and p not in seen and p not in skip and a.get_text(strip=True):
                    queue.append((p, group))
        heads = [clean_text(h.get_text(' ')) for h in c.find_all(['h2', 'h3'])][:25]
        html = clean_html(c, title)
        text = clean_text(BeautifulSoup(html, 'html.parser').get_text(' '))
        if len(text) < 40:
            continue
        k = pid(page)
        with open(os.path.join(OUT_DIR, k + '.json'), 'w', encoding='utf-8') as f:
            json.dump({'t': title, 'p': page, 'g': group, 'html': html}, f, ensure_ascii=False, separators=(',', ':'))
        index.append({'id': k, 't': title, 'p': page, 'g': group, 'h': heads, 's': text[:220], 'n': len(html)})
        if len(index) % 50 == 0:
            print(f'{len(index)} Seiten … {title}')
    if len(index) < 30:
        raise SystemExit('Zu wenig Seiten – Wiki-Aufbau geändert? Alte Daten bleiben.')
    # alte Seiten-Dateien entfernen, die nicht mehr vorkommen
    keep = {e['id'] + '.json' for e in index}
    for fn in os.listdir(OUT_DIR):
        if fn.endswith('.json') and fn not in keep:
            os.remove(os.path.join(OUT_DIR, fn))
    with open(OUT_IDX, 'w', encoding='utf-8') as f:
        json.dump({'stand': datetime.date.today().isoformat(), 'quelle': BASE, 'seiten': index}, f, ensure_ascii=False, separators=(',', ':'))
    total = sum(os.path.getsize(os.path.join(OUT_DIR, x)) for x in os.listdir(OUT_DIR))
    print(f'Fertig: {len(index)} Seiten, {total // 1024} KB, Gruppen: {sorted({e["g"] for e in index})}')


if __name__ == '__main__':
    main()
