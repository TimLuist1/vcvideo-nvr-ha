# VCVideo NVR

<p align="center"><img src="icon.png" width="80"/></p>

**Lokale Home Assistant Integration für VCVideo NVR Recorder**

Alle Kanäle deines NVR werden automatisch als `camera`-Entitäten in Home Assistant verfügbar – einschließlich Kameras, die nur am NVR angeschlossen sind.

## Features
- 🔍 Automatische Erkennung aller Kanäle
- 📹 RTSP Live-Streams (Haupt- & Substream)
- 📸 Vorschaubilder – auch wenn der NVR keinen Snapshot-Endpunkt hat (Einzelbild via FFmpeg)
- 🟢 Online/Offline Status
- 💗 Session-Heartbeat inkl. erneuter Anmeldung
- 🛠️ Einrichtung komplett über die HA-UI
- 🇩🇪 Deutsch & 🇬🇧 Englisch

## Konfiguration
**Einstellungen → Geräte & Dienste → Integration hinzufügen → VCVideo NVR**

Eingeben: IP-Adresse des NVR, Benutzername, Passwort.

Über **Konfigurieren** lässt sich einstellen, woher die Vorschaubilder kommen
(automatisch, Substream, Hauptstream, HTTP-Snapshot oder aus).

## Kompatibel mit Home Assistant
✅ Getestet mit Home Assistant **2026.5.x**  
Mindestens HA 2026.5.0 erforderlich.
