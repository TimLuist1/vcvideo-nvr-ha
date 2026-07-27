# Changelog

## v1.1.0 – Vorschaubilder

### 🖼️ Vorschaubilder werden endlich angezeigt

Der Live-Stream lief, das Vorschaubild blieb leer. Ursache: die Integration
holte Standbilder von `/cgi-bin/snapshot.cgi` – einem Endpunkt, den diese
NVR-Baureihe gar nicht kennt. `async_camera_image` lieferte deshalb immer
`None` und Home Assistant meldete *"Unable to get image"*.

Neu:

- Die Integration prüft **einmalig im Hintergrund**, ob der NVR überhaupt einen
  HTTP-Snapshot-Endpunkt anbietet. Antworten werden anhand der Magic Bytes
  geprüft, damit eine als `image/jpeg` ausgelieferte HTML-Fehlerseite nicht
  als Bild durchgeht.
- Hat der NVR keinen Endpunkt (der Normalfall), wird das Vorschaubild per
  **FFmpeg als Einzelbild aus dem RTSP-Substream** geholt – innerhalb der
  10 Sekunden, die Home Assistant dafür einräumt.
- Bilder werden kurz zwischengespeichert und Anfragen pro Kamera serialisiert,
  damit ein Dashboard mit vielen Karten nicht für jede Karte einen eigenen
  FFmpeg-Prozess startet.
- Neuer **Optionen-Dialog**: Quelle für Vorschaubilder (automatisch, Substream,
  Hauptstream, HTTP-Snapshot, aus) sowie die FFmpeg-Eingabeoptionen
  (Standard `-rtsp_transport tcp`).

### 🐛 Weitere Fehlerbehebungen

- Benutzername und Passwort werden in RTSP-URLs **URL-kodiert**. Ein Passwort
  mit `@`, `:` oder Leerzeichen erzeugte bisher eine unbrauchbare Stream-URL.
- Die Substream-URL (inklusive Passwort) wird **nicht mehr als Zustandsattribut**
  veröffentlicht.
- Abgelaufene Sitzungen, die der NVR mit HTTP 200 und einem Fehlercode meldet,
  werden erkannt und lösen eine **erneute Anmeldung** aus.
- Der Schritt **"Neu konfigurieren"** brach immer mit *already_configured* ab,
  weil er die Prüfung des Einrichtungs-Schritts wiederverwendet hat.
- Neuer **Reauth-Dialog**, wenn der NVR die Zugangsdaten nicht mehr akzeptiert.
- `channel_param` wird sowohl als Objekt mit `items` als auch als reine Liste
  akzeptiert.
- Der Login-Token wird auch aus dem JSON-Body gelesen, falls eine Firmware den
  Header `X-csrftoken` nicht sendet.
- Ein überflüssiger dritter Kanal-Abruf beim Setup entfällt; das Entladen der
  Integration verträgt einen fehlenden Koordinator.
- Kanäle, die der NVR als getrennt meldet, werden als **nicht verfügbar**
  markiert.
- Die API-Tests prüften eine Token-Quelle, die es im Code nie gab. Sie sind
  neu geschrieben und laufen jetzt in der CI mit.

### ⚠️ Hinweis

Für die Vorschaubilder wird **FFmpeg** benötigt. In Home Assistant OS,
Container und Supervised ist es bereits enthalten.

## v1.0.1 – Connection fixes

- `aiohttp.DigestAuth` durch `DigestAuthMiddleware` ersetzt (aiohttp 3.10+)
- CSRF-Token wird aus dem Response-Header `X-csrftoken` gelesen
- Korrekter RTSP-Pfad `/chNN/0` (Haupt-) bzw. `/chNN/1` (Substream)

## v1.0.0 – Initial Release

- Lokale Integration für VCVideo NVR Recorder
- Auto-Discovery aller Kamera-Kanäle
- RTSP Live-Streams (Haupt- und Substream)
- Online-/Offline-Status pro Kanal
- Heartbeat zur Session-Erhaltung
- Konfiguration komplett über die HA-UI
