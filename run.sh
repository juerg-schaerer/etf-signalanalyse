#!/bin/bash

# Verzeichnis dieses Skripts (Projektverzeichnis)
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$PROJECT_DIR/.venv"
SCRIPT="etf.py"
LOGFILE="$PROJECT_DIR/cron.log"

# Wechsle ins Projektverzeichnis
cd "$PROJECT_DIR" || exit 1

# Aktiviere das virtuelle Environment
source "$VENV_DIR/bin/activate"

# Führe das Skript aus und logge alles
echo "🕒 Starte ETF-Analyse am $(date)" >> "$LOGFILE"
python "$SCRIPT" >> "$LOGFILE" 2>&1

# Ausgabe für die Konsole
if [ $? -eq 0 ]; then
    echo "✅ ETF-Analyse abgeschlossen: $(date)"
else
    echo "❌ Fehler bei ETF-Analyse: $(date)"
fi