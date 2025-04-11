# 📊 ETF Signal Analyse mit Python

Dieses Projekt analysiert täglich einen ETF (z. B. EUNL.DE – iShares MSCI World) auf Basis technischer Indikatoren und erstellt:

- Technische Auswertungen (RSI, MACD, Volatilität, 200-Tage-Linie)
- Täglichen HTML-Report mit Trendanalyse, Farbcodierung und Interpretation
- Chart mit RSI- und MACD-Verlauf
- SQLite-Logging aller Signale
- E-Mail-Benachrichtigungen bei Signal- oder Ampeländerung
- Automatische Bereinigung alter Dateien (90 Tage)
- Einen `index.html` für Webserver-Integration

---

## 🚀 Funktionsweise

1. Ruft Kursdaten über [`yfinance`](https://github.com/ranaroussi/yfinance) ab
2. Berechnet Indikatoren:
   - **RSI** (14 Tage)
   - **MACD + Signal** (12/26/9 EMA)
   - **Volatilität** (14 Tage Std-Abw.)
   - **200-Tage-Durchschnitt**
3. Generiert tägliches Signal: `BUY`, `SELL`, `HOLD`, oder `n/v`
4. Ampelstatus: `"grün"`, `"rot"` oder `"grau"` basierend auf Kurs/MA
5. Speichert Chart & HTML-Bericht
6. Versendet E-Mail mit Chart-Anhang bei Signal-/Ampeländerung
7. Optionaler Abbruch an Wochenenden/Feiertagen (NYSE)

---

## ⚠️ Rechtlicher Hinweis

Dieses Projekt enthält keinen Finanzrat.  
Bitte lies den vollständigen [Disclaimer](DISCLAIMER.md), bevor du die Ergebnisse nutzt oder darauf basierende Entscheidungen triffst.

---

## 📦 Voraussetzungen

```bash
pip install -r requirements.txt

---
