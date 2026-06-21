# Lightning Eye

Blitzsensor-Station für Raspberry Pi Zero WH mit AMS AS3935 (DFRobot SEN0290), LED-Ampel, DHT22 und Buzzer.

## Hardware

| Pin | Funktion |
|-----|----------|
| 3/5 | I2C SDA/SCL (Blitzsensor) |
| 7 | IRQ |
| 11/13/15 | LED Rot/Gelb/Grün |
| 12 | DHT22 Data (10 kΩ → Pin 17) |
| 16 | Buzzer Signal |
| 17 | DHT22 3,3 V |

## Pi vorbereiten

1. Pi OS 32-bit mit Desktop flashen, WLAN einrichten
2. I2C aktivieren: `sudo raspi-config` → Interface Options → I2C → Enable
3. Neustart
4. Optional: `sudo apt install git python3-venv python3-tk i2c-tools`

## Installation (WinSCP + PuTTY)

1. **WinSCP:** `main.py` nach `/home/pi/main.py` kopieren
2. **PuTTY:** einmal ausführen:

   ```bash
   python3 ~/main.py
   ```

3. Beim ersten Lauf: Repo wird von GitHub geklont, Pakete installiert, Autostart eingerichtet, LED-Boot-Sequenz, Neustart
4. Danach startet die GUI automatisch beim Boot

## Bedienung

- **Hauptbildschirm:** Status, Zähler, Zeitfenster, Block, Umgebung, Sparkline
- **Menü Details:** Statistik, Block, System, Export/QR
- **Escape:** Vollbild verlassen | **F11:** Vollbild

## Konfiguration

Schwellwerte in `config.yaml` im Installationsverzeichnis (`~/lightning_eye/`):

- `relevance.max_distance_km: 40` — relevant bis 40 km
- `relevance.min_energy: 0` — später anheben wenn bekannt
- `blocks.timeout_minutes: 5` — neuer Block nach 5 Min Pause

## Updates

Automatisch alle 6 Stunden von GitHub. Wenn in den letzten 60 Minuten relevante Messungen stattfanden, wird das Update um 60 Minuten verschoben.

## Logs & Export

- SQLite: `~/lightning_eye/data/events.db`
- CSV-Export über Menü **Details → Export / QR**
- Status-URL: `http://<pi-ip>:8765/status`

## Repository

<https://github.com/tnt-nitro/lightning_eye>
