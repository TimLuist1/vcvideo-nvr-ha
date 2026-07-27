# VCVideo NVR – Home Assistant Integration

<p align="center">
  <img src="icon.png" alt="VC Germany Logo" width="80"/>
</p>

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![GitHub release](https://img.shields.io/github/v/release/TimLuist1/vcvideo-nvr-ha)](https://github.com/TimLuist1/vcvideo-nvr-ha/releases)
[![Validate](https://github.com/TimLuist1/vcvideo-nvr-ha/actions/workflows/validate.yml/badge.svg)](https://github.com/TimLuist1/vcvideo-nvr-ha/actions/workflows/validate.yml)
[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](LICENSE)

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=TimLuist1&repository=vcvideo-nvr-ha&category=integration)

Unofficial **Home Assistant** integration for **VCVideo NVR** recorders (developed by [VC Germany](https://vcgermany.de)).  
Alle Kamera-Kanäle des NVR werden automatisch als `camera`-Entitäten in Home Assistant eingebunden – einschließlich der Kameras, die **nur am NVR** verfügbar sind und nicht direkt im LAN erreichbar sind.

> **Hinweis:** Diese Integration kommuniziert über die lokale HTTP-API des NVR (Port 80/554) und benötigt keine Cloud-Verbindung.

**Mindestanforderung:** Home Assistant **2026.5.0** oder neuer (aktuelle Version: 2026.5.2)

---

## Features

- Automatische Erkennung aller Kanäle nach dem Login  
- Live-Stream via RTSP (Hauptstream + Substream)  
- Vorschaubilder auch ohne Snapshot-Endpunkt am NVR (Einzelbild via FFmpeg)  
- Online-/Offline-Status der Kameras  
- Session-Heartbeat damit die Verbindung stabil bleibt  
- Erneute Anmeldung, wenn der NVR die Sitzung verwirft  
- Vollständig konfigurierbar über die UI (kein YAML nötig)  
- Deutsch und Englisch unterstützt  

---

## Installation via HACS

1. HACS öffnen → **Integrationen** → Drei-Punkte-Menü → **Custom Repositories**  
2. URL `https://github.com/TimLuist1/vcvideo-nvr-ha` einfügen, Kategorie `Integration` → **Add**  
3. Nach `VCVideo NVR` suchen → **Download**  
4. Home Assistant neu starten  

### Manuell

Ordner `custom_components/vcvideo_nvr/` in dein HA `config/custom_components/`-Verzeichnis kopieren und HA neu starten.

---

## Einrichtung

1. **Einstellungen** → **Geräte & Dienste** → **Integration hinzufügen** → `VCVideo NVR`  
2. Eingeben:
   - **IP-Adresse** des NVR (z. B. `192.168.0.20`)  
   - **HTTP-Port** (Standard: `80`)  
   - **RTSP-Port** (Standard: `554`)  
   - **Benutzername** (Standard: `admin`)  
   - **Passwort**  

---

## Bekannte NVR-API-Endpunkte

| Aktion | Endpunkt |
|---|---|
| Login | `POST /API/Web/Login` (HTTP Digest Auth) |
| Kanal-Info | `POST /API/Login/ChannelInfo/Get` |
| Geräte-Info | `POST /API/Login/DeviceInfo/Get` |
| Stream-URL | `POST /API/Preview/StreamUrl` |
| Heartbeat | `POST /API/Login/Heartbeat` |
| Logout | `POST /API/Web/Logout` |

Alle Anfragen nach dem Login benötigen den Header `X-csrftoken: <token>`.

---

## RTSP-Stream-URLs

Die Stream-URLs werden nach folgendem Muster gebildet (`NN` = zweistellige Kanalnummer):

```
Hauptstream: rtsp://<user>:<pass>@<host>:554/chNN/0
Substream:   rtsp://<user>:<pass>@<host>:554/chNN/1
```

Benutzername und Passwort werden dabei URL-kodiert, Sonderzeichen wie `@` oder `:`
im Passwort sind also kein Problem.

---

## Vorschaubilder (Thumbnails)

Die meisten NVR dieser Baureihe besitzen **keinen HTTP-Endpunkt für Standbilder**.
Deshalb blieb das Vorschaubild in Home Assistant leer, obwohl der Live-Stream lief.

Ab Version 1.1.0 ermittelt die Integration einmalig im Hintergrund, ob der NVR
einen Snapshot-Endpunkt anbietet. Ist keiner vorhanden, wird das Vorschaubild
mit **FFmpeg** als Einzelbild aus dem RTSP-Substream geholt. Die Bilder werden
kurz zwischengespeichert, damit ein Dashboard mit vielen Kameras nicht für jede
Karte einen eigenen FFmpeg-Prozess startet.

Über **Einstellungen → Geräte & Dienste → VCVideo NVR → Konfigurieren** lässt
sich das Verhalten anpassen:

| Option | Bedeutung |
|---|---|
| Automatisch | HTTP-Snapshot, wenn der NVR einen anbietet, sonst Einzelbild aus dem Substream (Standard) |
| Einzelbild aus dem Substream | Immer FFmpeg auf dem Substream – schnell und ressourcenschonend |
| Einzelbild aus dem Hauptstream | Immer FFmpeg auf dem Hauptstream – bessere Auflösung, mehr Last |
| HTTP-Snapshot vom NVR | Nur den HTTP-Endpunkt verwenden |
| Keine Vorschaubilder | Standbilder komplett deaktivieren |

Zusätzlich lassen sich die FFmpeg-Eingabeoptionen setzen (Standard
`-rtsp_transport tcp`). Wenn der NVR nur UDP spricht, kann das Feld geleert werden.

---

## Anforderungen

- Home Assistant 2026.5.0+  
- FFmpeg (in Home Assistant OS, Container und Supervised bereits enthalten)  
- HACS (für einfache Installation)  
- NVR muss im LAN erreichbar sein  

---

## Lizenz

Dieses Projekt steht unter der **GNU General Public License v3.0** – der
vollständige Lizenztext liegt in [LICENSE](LICENSE).

```
VCVideo NVR – Home Assistant Integration
Copyright (C) 2026 Tim Luis Techert

Dieses Programm ist freie Software: Sie können es unter den Bedingungen der
GNU General Public License, Version 3, weitergeben und/oder modifizieren.
Die Veröffentlichung erfolgt in der Hoffnung, dass es nützlich ist, jedoch
OHNE JEDE GEWÄHRLEISTUNG.
```

Home Assistant selbst steht unter der Apache-2.0-Lizenz, die mit der GPLv3
verträglich ist.

Das Icon der Integration (`custom_components/vcvideo_nvr/brand/icon.png`) ist
eine eigene, generische Darstellung eines Rekorders und **kein Logo von
VC Germany**.
