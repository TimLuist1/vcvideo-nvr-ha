# VCVideo NVR – Home Assistant Integration

<p align="center">
  <img src="icon.png" alt="VC Germany Logo" width="80"/>
</p>

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![GitHub release](https://img.shields.io/github/v/release/TimLuist1/vcvideo-nvr-ha)](https://github.com/TimLuist1/vcvideo-nvr-ha/releases)

Unofficial **Home Assistant** integration for **VCVideo NVR** recorders (developed by [VC Germany](https://vcgermany.de)).  
Alle Kamera-Kanäle des NVR werden automatisch als `camera`-Entitäten in Home Assistant eingebunden – einschließlich der Kameras, die **nur am NVR** verfügbar sind und nicht direkt im LAN erreichbar sind.

> **Hinweis:** Diese Integration kommuniziert über die lokale HTTP-API des NVR (Port 80/554) und benötigt keine Cloud-Verbindung.

**Mindestanforderung:** Home Assistant **2026.5.0** oder neuer (aktuelle Version: 2026.5.2)

---

## Features

- Automatische Erkennung aller Kanäle nach dem Login  
- Live-Stream via RTSP (Hauptstream + Substream)  
- Snapshot-Bilder direkt aus HA  
- Online-/Offline-Status der Kameras  
- Session-Heartbeat damit die Verbindung stabil bleibt  
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

Falls die API keinen Stream-URL zurückgibt, werden folgende Fallback-URLs verwendet:

```
Hauptstream: rtsp://<user>:<pass>@<host>:554/stream/<CH>/main
Substream:   rtsp://<user>:<pass>@<host>:554/stream/<CH>/sub
```

---

## Anforderungen

- Home Assistant 2023.1.0+  
- HACS (für einfache Installation)  
- NVR muss im LAN erreichbar sein  
