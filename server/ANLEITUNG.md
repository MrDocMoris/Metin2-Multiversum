# Metin2-Multiversum – Abgleich über deinen eigenen Server

Die App nutzt **denselben PocketBase-Server wie TCG Multiversum** – du brauchst keinen zweiten Server.

## Einmalig einrichten
1. Die Datei `pb_migrations/1732300000_metin2_sync.js` aus diesem Ordner in den Ordner **`pb_migrations`** deines Servers kopieren
   (dort liegt schon `1732100000_tcg_multiversum.js`).
2. Server neu starten. PocketBase legt dabei die neue Tabelle `m2_sync` an.
   (Kontrolle im Admin-Bereich `/_/` → Collections → `m2_sync` ist da.)

## In der App
⚙️ Einstellungen → **Eigener Server** → Server-Adresse eintragen und mit deinem TCG-Multiversum-Konto anmelden
(oder ein neues Konto mit Einladungscode anlegen).

Danach gleicht die App automatisch ab: beim Start, nach Änderungen und wenn du sie wieder öffnest.
Auf einem zweiten Handy oder im Browser am PC einfach mit demselben Konto anmelden.

**Wenn der Server aus ist,** funktioniert die App ganz normal weiter – abgeglichen wird, sobald er wieder erreichbar ist.
