# Metin2-Multiversum

Dein Metin2-Begleiter für den Server Ruby – im gleichen Stil und mit dem gleichen Update-Weg wie TCG Multiversum und Familien-Multiversum.

## Funktionen
- **Events aus dem offiziellen Forum**: Wochenplan der Drop-Events für Ruby (Eventkalender), zusätzliche Events, kurzfristige Änderungen und große Events (News) – zweimal täglich aktualisiert, mit Push-Erinnerung für markierte Drops
- **Eigene Events** mit Push-Erinnerung (einmalig, wöchentlich, täglich), Countdown auf der Startseite
- **Farm-Sessions**: Kills zählen, Drops mit einem Tipp eintragen, Yang mitschreiben – danach Droprate („1 pro X Kills“) und Wert der Session
- **Farm-Log** mit Verlauf, Statistik nach Item und Monster
- **Preise** in Yang mit Verlauf als Diagramm, Durchschnitt der letzten 30 Tage und Hinweis „günstig“ / „teuer“ (Eingabe auch als `1,5kk`, `250k`, `2 Won`)
- **Wiki**: Monster, Metins, Fundorte und Drops aus dem offiziellen deutschen Metin2-Wiki, Item-Suche „wer droppt das?“, Vorschläge beim Tippen
- Charakter (Name, Klasse, Level), automatische Sicherung in *Dokumente/Metin2-Multiversum*, Update-Prüfung

## Aufbau
- `metin2.html` – die komplette App (HTML/CSS/JS), läuft auch im Browser zum Testen
- `assets/icon.svg` – App-Icon
- `tools/wiki.py` – liest Monster, Metins und Drops aus https://de-wiki.metin2.gameforge.com
- `daten/wiki.json` – Ergebnis davon; die App lädt es beim Start, wenn es neuer ist
- `tools/events.py` / `daten/events.json` – Event-Termine aus https://board.de.metin2.gameforge.com (Eventkalender & News - Events)
- `.github/workflows/events.yml` – holt die Event-Termine jeden Tag um ca. 6:37 und 16:37 Uhr
- `.github/workflows/wiki.yml` – holt die Wiki-Daten am 1. und 15. jedes Monats (oder per Hand)
- `.github/workflows/build-apk.yml` – baut bei jeder Änderung die Android-App, signiert sie mit `signing/debug.keystore`, veröffentlicht sie als Release und schreibt `app/version.json`

Private Fan-App ohne Verbindung zu Gameforge oder Webzen. Preise trägst du selbst ein – dafür gibt es keine offizielle Quelle.
