#!/usr/bin/env python3
"""Liest die Event-Termine aus dem offiziellen deutschen Metin2-Forum
und schreibt daten/events.json für die App.

- Eventkalender (Thread 90381): Wochenplan je Server (z. B. „[Ruby]Chimera / [SAPPHIRE]Oceana“)
  mit 4 Zeitfenstern pro Tag, „zusätzliche Events“ und kurzfristige Änderungen
- News - Events (Board 1167): große Events mit Event-Start und Event-Ende

Läuft täglich in GitHub Actions (.github/workflows/events.yml).
"""
import datetime, json, os, re, sys, time
import requests
from bs4 import BeautifulSoup, NavigableString, Tag

BASE = 'https://board.de.metin2.gameforge.com/index.php'
KALENDER = BASE + '?thread/90381-eventkalender/'
NEWS = BASE + '?board/1167-news-events/'
UA = 'Mozilla/5.0 (Metin2-Multiversum; private Begleit-App; github.com/MrDocMoris/Metin2-Multiversum)'
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'daten', 'events.json')
MONATE = ['januar', 'februar', 'märz', 'april', 'mai', 'juni', 'juli', 'august', 'september', 'oktober', 'november', 'dezember']
TAGE = ['montag', 'dienstag', 'mittwoch', 'donnerstag', 'freitag', 'samstag', 'sonntag']

S = requests.Session()
S.headers['User-Agent'] = UA


def get(url):
    for i in range(3):
        try:
            r = S.get(url, timeout=30)
            if r.status_code == 200:
                return BeautifulSoup(r.text, 'html.parser')
        except requests.RequestException as e:
            print('Fehler', url, e)
        time.sleep(4 * (i + 1))
    return None


def clean(s):
    return re.sub(r'\s+', ' ', s or '').strip()


def hhmm(s):
    h, m = s.split(':')
    return f'{int(h):02d}:{m}'


def slot(text):
    m = re.search(r'(\d{1,2}:\d{2})\s*[-–]\s*(\d{1,2}:\d{2})', text)
    if not m:
        return None
    a, b = hhmm(m.group(1)), hhmm(m.group(2))
    return [a, '24:00' if b == '00:00' else b]


def posts(soup):
    out = []
    for art in soup.select('article.message'):
        body = art.select_one('.messageText, .htmlContent')
        if not body:
            continue
        t = art.select_one('time')
        out.append({'id': art.get('data-post-id') or art.get('data-object-id') or '', 'date': t.get('datetime') if t else '', 'body': body})
    return out


def thread_posts(url):
    """Alle Beiträge, auch von Folgeseiten."""
    res, seen = [], set()
    for _ in range(8):
        soup = get(url)
        if not soup:
            break
        for p in posts(soup):
            if p['id'] not in seen:
                seen.add(p['id'])
                res.append(p)
        nxt = soup.select_one('a[rel=next]')
        if not nxt or not nxt.get('href'):
            break
        url = nxt['href']
        time.sleep(2)
    return res


def month_year(day, month_name, ref):
    """Monat aus dem Text, Jahr passend zum Datum des Beitrags."""
    mo = MONATE.index(month_name.lower()) + 1
    y = ref.year + (1 if mo < ref.month - 6 else 0)
    return f'{y}-{mo:02d}-{int(day):02d}'


def parse_week_table(table):
    rows = table.find_all('tr')
    if len(rows) < 8:
        return None
    head = [clean(c.get_text(' ')) for c in rows[0].find_all(['td', 'th'])]
    slots = [slot(h) for h in head[1:]]
    if not slots or not all(slots):
        return None
    woche = {}
    for tr in rows[1:]:
        cells = [clean(c.get_text(' ')) for c in tr.find_all(['td', 'th'])]
        if not cells:
            continue
        tag = cells[0].lower()
        if tag in TAGE:
            woche[str(TAGE.index(tag))] = [{'von': s[0], 'bis': s[1], 'name': n} for s, n in zip(slots, cells[1:]) if n]
    return woche if len(woche) == 7 else None


def kalender():
    ps = thread_posts(KALENDER)
    print(f'Eventkalender: {len(ps)} Beiträge')
    plaene, hinweise = {}, []
    for p in ps:
        body = p['body']
        ref = datetime.datetime.fromisoformat(p['date']) if p['date'] else datetime.datetime.now()
        for table in body.find_all('table'):
            # Servername = Text direkt vor der Tabelle
            name = ''
            for el in table.find_all_previous(string=True):
                t = clean(el)
                if t:
                    name = t
                    break
            if '[' not in name:
                continue
            woche = parse_week_table(table)
            if not woche:
                continue
            # „zusätzliche Events“ nach der Tabelle
            after = ' '.join(clean(s) for s in table.find_all_next(string=True) if body in s.parents)
            extra = []
            for m in re.finditer(r'(\d{1,2})\.\s*(' + '|'.join(MONATE) + r')\s*:\s*(.+?)\s(\d{1,2}:\d{2})\s*[-–]\s*(\d{1,2}:\d{2})', after, re.I):
                text = clean(m.group(3)).replace('( ', '(').replace(' )', ')')
                extra.append({'datum': month_year(m.group(1), m.group(2), ref), 'name': text, 'von': hhmm(m.group(4)), 'bis': '24:00' if hhmm(m.group(5)) == '00:00' else hhmm(m.group(5))})
            plaene[name] = {'server': name, 'beitrag': p['date'], 'woche': woche, 'extra': extra}
        recent = (datetime.datetime.now(ref.tzinfo) - ref).days <= 21
        if not body.find('table') and recent:
            text = clean(body.get_text(' '))
            if re.search(r'\[(ruby|sapphire|dia)', text, re.I) and len(text) < 1200:
                hinweise.append({'datum': p['date'], 'text': text})
    return list(plaene.values()), hinweise[-5:]


def news_events():
    soup = get(NEWS)
    out = []
    if not soup:
        return out
    links, seen = [], set()
    for a in soup.select('a[href*="?thread/"]'):
        h = a['href'].split('&')[0]
        title = clean(a.get_text())
        if not title or h in seen or 'eventkalender' in h.lower() or len(title) < 6:
            continue
        seen.add(h)
        links.append((title, h))
    for title, url in links[:6]:
        time.sleep(2)
        ps = thread_posts(url)
        if not ps:
            continue
        body = ps[0]['body']
        # Text mit Überschriften-Markern, damit jedes Start/Ende seinem Event zugeordnet wird
        parts = []
        for el in body.descendants:
            if isinstance(el, Tag) and el.name in ('h1', 'h2'):
                parts.append('\n§' + clean(el.get_text(' ')) + '§\n')
            elif isinstance(el, NavigableString) and not (el.parent and el.parent.name in ('h1', 'h2')):
                parts.append(str(el))
        text = re.sub(r'[ \t\r\f\v]+', ' ', ''.join(parts))
        cur, found = title, {}
        for m in re.finditer(r'§([^§]+)§|Event-(Start|Ende)\s*:\s*(\d{1,2})\.(\d{1,2})\.(\d{4})\s*(?:um\s*(\d{1,2}:\d{2}))?', text):
            if m.group(1):
                h = m.group(1).strip()
                if h.lower().startswith(('event', 'das event')):
                    cur = re.sub(r'^(das\s+)?event\s*:?\s*', '', h, flags=re.I).strip() or title
                continue
            d = f'{m.group(5)}-{int(m.group(4)):02d}-{int(m.group(3)):02d}'
            t = hhmm(m.group(6)) if m.group(6) else ('00:00' if m.group(2) == 'Start' else '23:59')
            e = found.setdefault(cur, {'name': cur, 'thread': title, 'url': url})
            e['start' if m.group(2) == 'Start' else 'ende'] = f'{d}T{t}'
        for e in found.values():
            if e.get('start') or e.get('ende'):
                out.append(e)
    today = datetime.date.today().isoformat()
    return [e for e in out if (e.get('ende') or e.get('start', ''))[:10] >= today]


def main():
    plaene, hinweise = kalender()
    news = news_events()
    print(f'{len(plaene)} Wochenpläne: {[p["server"] for p in plaene]} · {len(news)} aktuelle Events · {len(hinweise)} Hinweise')
    if not plaene and not news:
        raise SystemExit('Keine Daten gefunden – Forum-Aufbau geändert? Alte Datei bleibt.')
    data = {'quelle': KALENDER, 'plaene': plaene, 'news': news, 'hinweise': hinweise}
    old = None
    if os.path.exists(OUT):
        try:
            old = json.load(open(OUT, encoding='utf-8'))
        except Exception:
            pass
    if old and {k: v for k, v in old.items() if k != 'stand'} == data:
        print('Unverändert')
        return
    data = {'stand': datetime.datetime.now().strftime('%Y-%m-%dT%H:%M'), **data}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    print('Gespeichert:', OUT)


if __name__ == '__main__':
    main()
