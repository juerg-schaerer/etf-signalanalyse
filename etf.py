import yfinance as yf
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import smtplib
import sqlite3
import os
import glob
from datetime import datetime, timedelta
from email.message import EmailMessage
from dotenv import load_dotenv
import pandas_market_calendars as mcal
import sys

# Abbruch bei Wochenende oder Feiertag (NYSE)
nyse = mcal.get_calendar("NYSE")
today_pd = pd.Timestamp.today().normalize()

if nyse.valid_days(start_date=today_pd, end_date=today_pd).empty:
    print("🚫 Heute ist kein Börsentag (NYSE) – Skript wird beendet.")
    sys.exit(0)

# Konfiguration laden
load_dotenv()

EMAIL_SENDER = os.getenv("EMAIL_SENDER")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
EMAIL_RECEIVER = os.getenv("EMAIL_RECEIVER")
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))

TICKER = "EUNL.DE" # IE00B4L5Y983, iShares Core MSCI World UCITS ETF, https://www.boerse-frankfurt.de/etf/ishares-core-msci-world-ucits-etf?currency=EUR
RSI_BUY_THRESHOLD = 30
VOLATILITY_THRESHOLD = 0.03
DB_PATH = "signals.db"
CHART_DIR = "reports"
HTML_DIR = "reports"
RETENTION_DAYS = 90

os.makedirs(CHART_DIR, exist_ok=True)
os.makedirs(HTML_DIR, exist_ok=True)

print("📈 Lade Kursdaten...")
# Holt 1 Jahr Kursdaten (adjustiert für Dividenden/Splits) vom Ticker EUNL.DE.
df = yf.download(TICKER, period="1y", auto_adjust=True)

# Indikator  #Aussage #Wann relevant?
# 200_MA # Trendfilter (langfristig) # Einstieg nur bei AufwÃ¤rtstrend (Ampel grÃ¼n)
# RSI # Überkauft/überverkauft “ wie heiß ist der Markt" # Einstieg bei <30, Ausstieg bei >70
# MACD # Momentumindikator # Einstieg bei MACD > Signal
# Volatility # Schwankung (Risiko) # Einstieg nur bei ruhiger Marktphase

# Berechnet den 200-Tage gleitenden Durchschnitt des Schlusskurses – ein Trendindikator.
# Wird oft genutzt, um langfristige Trends zu erkennen:
# - Kurs über 200-Tage-Linie → Aufwärtstrend (“grüne Ampel”)
# - Kurs unter → Abwärtstrend (“rote Ampel”)
df["200_MA"] = df["Close"].rolling(window=200).mean()

#       Relative Stärke Index
# Tagesveränderung des Kurses – Differenz zum Vortag.
delta = df["Close"].diff()

# Trenne positive und negative Veränderungen (Gewinne/Verluste) auf.
gain = delta.clip(lower=0)
loss = -delta.clip(upper=0)

# Berechne den Durchschnitt der Gewinne/Verluste über 14 Tage.
avg_gain = gain.rolling(window=14, min_periods=14).mean()
avg_loss = loss.rolling(window=14, min_periods=14).mean()

# RSI-Formel:
# - RSI < 30 → überverkauft (möglicher Einstiegspunkt)
# - RSI > 70 → überkauft (Ausstiegssignal)
rs = avg_gain / avg_loss
df["RSI"] = 100 - (100 / (1 + rs))

#      MACD – Moving Average Convergence Divergence
# Berechne exponentielle gleitende Durchschnitte (EMAs) über 12 und 26 Tage.
ema12 = df["Close"].ewm(span=12, adjust=False).mean()
ema26 = df["Close"].ewm(span=26, adjust=False).mean()

# MACD-Linie: Differenz zwischen den beiden EMAs → zeigt Momentum.
df["MACD"] = ema12 - ema26

# Signallinie: 9-Tage-EMA des MACD.
# Kreuzt MACD nach oben über die Signallinie → Kaufimpuls
# Kreuzt nach unten → Verkaufsimpuls
df["MACD_Signal"] = df["MACD"].ewm(span=9, adjust=False).mean()

#     MA20 Moving Average
# Der gleitende Durchschnitt (Moving Average, MA) über 20 Tage ist ein sehr beliebter technischer Indikator – auch für Trader und Anleger mit kurzfristiger bis mittelfristiger Ausrichtung
# Was bringt dir der 20-Tage-MA konkret?
# 1. Trendfilter für kurzfristige Marktbewegungen
#	•	Zeigt dir, ob ein kurzfristiger Auf- oder Abwärtstrend vorliegt.
#	•	Beispiel: Liegt der Kurs über dem 20-Tage-MA → kurzfristig bullisch.
# 2. Unterstützungs-/Widerstandszonen
#	•	Der MA kann als eine Art „dynamischer Widerstand“ oder „Unterstützung“ wirken.
#	•	Viele Marktteilnehmer achten auf diesen MA → kann also selbst Bewegungen beeinflussen.
# 3. Kreuzung mit anderen MAs (z. B. 200-Tage)
#	•	Kreuzt der 20er über den 200-Tage-MA = Golden Cross → bullisches Signal.
#	•	Kreuzt er darunter = Death Cross → bärisches Signal.
# 4. Signalbestätigung
#	•	Ergänzt RSI oder MACD:
#	•	RSI sagt „überverkauft“?
#	•	Liegt der Kurs aber noch deutlich unter dem 20er MA? → vielleicht abwarten.
# Trading-Einstieg: Kurs durchbricht 20er MA von unten nach oben → Einstiegssignal.
# Trailing Stop: Kurs fällt unter 20-Tage-MA → möglicher Ausstieg oder engerer Stopp.
df["20_MA"] = df["Close"].rolling(window=20).mean()

#     Volatilität
#Berechnet die Standardabweichung der Schlusskurse über 14 Tage – misst die Schwankungsbreite.
# Wird in deinem Skript verwendet, um übertriebene Bewegungen (hohes Risiko) auszuschließen.
df["Volatility"] = df["Close"].rolling(window=14).std()

def debug_rsi(df):
    print("\n📋 Debug: Letzte 14 RSI-Werte:")
    rsi_check = df[["Close", "RSI"]].tail(14)
    print(rsi_check.to_string(index=True, float_format=lambda x: f"{x:6.2f}"))

# Nach Berechnung aufrufen
# debug_rsi(df)

def generate_signal(row):
    try:
        # rsi = float(row["RSI"])
        rsi = float(row["RSI"].iloc[0]) if isinstance(row["RSI"], pd.Series) else float(row["RSI"])
        # macd = float(row["MACD"])
        macd = float(row["MACD"].iloc[0]) if isinstance(row["MACD"], pd.Series) else float(row["MACD"])
        #macd_sig = float(row["MACD_Signal"])
        macd_sig = float(row["MACD_Signal"].iloc[0]) if isinstance(row["MACD_Signal"], pd.Series) else float(row["MACD_Signal"])
        # close = float(row["Close"])
        close= float(row["Close"].iloc[0]) if isinstance(row["Close"], pd.Series) else float(row["Close"])
        # ma200 = float(row["200_MA"])
        ma200= float(row["200_MA"].iloc[0]) if isinstance(row["200_MA"], pd.Series) else float(row["200_MA"])
        # vola = float(row["Volatility"])
        vola= float(row["Volatility"].iloc[0]) if isinstance(row["Volatility"], pd.Series) else float(row["Volatility"])

        if pd.isna([rsi, macd, macd_sig, close, ma200, vola]).any():
            return "n/v"  # nicht verfügbar


        # if (rsi < RSI_BUY_THRESHOLD and macd > macd_sig and close > ma200 and vola < 0.03):
        # Neue Logik: Dadurch werden nur starke, mehrfache Bestätigungen als BUY ausgegeben.
        if (rsi < RSI_BUY_THRESHOLD and 
                macd > macd_sig and 
                close > ma200 and 
                close > ma20 and
                vola < VOLATILITY_THRESHOLD):    
            # BUY-Kriterium:
            # Das ist eine konservative Kaufstrategie, die nur bei günstiger Konstellation mehrerer Indikatoren ein „BUY“ liefert.
	        # 1.	rsi < 30        → Der Markt ist überverkauft – könnte ein günstiger Einstieg sein.
	        # 2.	macd > macd_sig → Das Momentum dreht nach oben – bestärkt den Aufwärtstrend.
	        # 3.	close > ma200   → Langfristiger Aufwärtstrend ist intakt – keine Käufe gegen den Trend.
            # 3.a.  close > ma20
	        # 4.	vola < 0.03     → Der Markt ist ruhig genug – kein chaotisches Umfeld.
            return "BUY"
        elif (rsi > 70 and macd < macd_sig and close < ma200 and vola > 0.03):
            # SELL-Kriterium:
            # Ein Verkauf wird nur ausgelöst, wenn wirklich alle Alarmsignale rot sind.
	        # 1.	rsi > 70        → Der Markt ist überkauft – Gewinnmitnahme oder Ausstieg sinnvoll.
	        # 2.	macd < macd_sig → Momentum zeigt nach unten.
	        # 3.	close < ma200   → Der Markt ist in einem Abwärtstrend.
	        # 4.	vola > 0.03     → Volatilität ist erhöht – Gefahr für stärkere Abwärtsbewegung.
            return "SELL"
        else:
            # HOLD-Kriterium:
            # Wenn keine der klaren „BUY“ oder „SELL“-Situationen zutrifft, wird einfach gehalten.
            return "HOLD"
    except:
        return "n/v"    
    
    # Diese Art von Kombination findet man in vielen konservativen Handelsmodellen, ETF-Ratgebern oder quantitativen Strategien für Privatanleger – angepasst auf mittel-/langfristige Entscheidungen (nicht Daytrading!).
    # Woher stammt diese Logik?
    # Sie ist eine heuristische Kombination von
    # -	RSI-Leveln (klassisch: 30/70)
	# - MACD-Kreuzungen (Momentumwechsel)
	# - Trendfilter (200-Tage-Linie) aus dem institutionellen Bereich
	# - Volatilitätsfilter (zur Risikosteuerung)

def generate_ampel(row):
    try:
        close = safe_float(row["Close"])
        ma200 = safe_float(row["200_MA"])
        ma20 = safe_float(row["20_MA"])

        if pd.isna([close, ma200, ma20]).any():
            return "grau"
        if close > ma200 and close > ma20:
            return "grün"
        elif close > ma20 and close < ma200:
            return "gelb"  # Zwischenphase: kurzfristig stark, langfristig schwach
        else:
            return "rot"
    except:
        return "grau"

latest = df.iloc[-1]
signal = generate_signal(latest)
ampel = generate_ampel(latest)

print(f"🟢 Heutiges Signal: {signal}, Ampel: {ampel}")

# Chart speichern
today = datetime.now().strftime("%Y-%m-%d")
counter = 1
while os.path.exists(f"{CHART_DIR}/chart_{today}_{counter}.png"):
    counter += 1
chart_path = f"{CHART_DIR}/chart_{today}_{counter}.png"

#plt.figure(figsize=(12,6))
#df["Close"].plot(title="ETF Kursverlauf mit 200-Tage-Linie")
#df["200_MA"].plot()
#plt.legend(["Close", "200 MA"])
#plt.grid(True)
#plt.tight_layout()
#plt.savefig(chart_path)
#plt.close()

#Chart von Version 1.1
plt.figure(figsize=(12,6))
plt.plot(df['Close'], label='Close')
plt.plot(df['200_MA'], label='200-Tage MA', linestyle='--')
plt.title(f'{TICKER} - Chart mit 200 MA')
plt.legend()
plt.grid(True)
plt.tight_layout()
plt.savefig(chart_path)
plt.close()

# Trendverlauf RSI & MACD im Chart anzeigen
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), sharex=True, gridspec_kw={'height_ratios': [3, 1]})

# Kurs + MA
ax1.plot(df.index, df["Close"], label="Close")
ax1.plot(df.index, df["200_MA"], label="200-Tage MA", linestyle="--")
ax1.plot(df.index, df["20_MA"], label="20-Tage MA", linestyle=":", color="orange")
ax1.set_title(f"{TICKER} - Chart mit 200 MA")
ax1.legend()
ax1.grid(True)

# RSI + MACD
ax2.plot(df.index, df["RSI"], label="RSI", color="orange")
ax2.axhline(RSI_BUY_THRESHOLD, color="red", linestyle="--", alpha=0.5)
ax2.plot(df.index, df["MACD"], label="MACD", color="blue")
ax2.plot(df.index, df["MACD_Signal"], label="Signal", color="grey", linestyle="--")
ax2.legend()
ax2.grid(True)

plt.tight_layout()
plt.savefig(chart_path)
plt.close()


# HTML speichern
html_path = f"{HTML_DIR}/report_{today}_{counter}.html"

# 🔢 Werte von heute und gestern
latest_row = df.iloc[-1]
prev_row = df.iloc[-2]

close_today = float(latest_row["Close"].iloc[0]) if isinstance(latest_row["Close"], pd.Series) else float(latest_row["Close"])
close_yesterday = float(prev_row["Close"].iloc[0]) if isinstance(prev_row["Close"], pd.Series) else float(prev_row["Close"])
diff_abs = close_today - close_yesterday
diff_pct = (diff_abs / close_yesterday) * 100 if close_yesterday != 0 else 0

def format_diff(val, is_pct=False):
    color = "#28a745" if val > 0 else "#dc3545" if val < 0 else "#6c757d"
    symbol = "+" if val > 0 else ""
    formatted = f"{symbol}{val:.2f}"
    return f'<span style="color:{color};">{formatted}{"%" if is_pct else ""}</span>'

def format_val(val):
    try:
        if isinstance(val, pd.Series):
            val = val.iloc[0]
        return f"{val:.2f}" if pd.notna(val) else "–"
    except:
        return "–"

def format_rsi(val):
    try:
        val = val.iloc[0] if isinstance(val, pd.Series) else val
        if pd.isna(val): return "–"
        color = "#dc3545" if val < RSI_BUY_THRESHOLD else "#28a745"
        return f'<span style="color:{color};">{val:.2f}</span>'
    except:
        return "–"

def format_macd(macd, signal):
    try:
        macd = macd.iloc[0] if isinstance(macd, pd.Series) else macd
        signal = signal.iloc[0] if isinstance(signal, pd.Series) else signal
        if pd.isna(macd) or pd.isna(signal): return "–"
        color = "#28a745" if macd > signal else "#dc3545"
        return f'<span style="color:{color};">{macd:.2f}</span>'
    except:
        return "–"

def format_volatility(val):
    try:
        val = val.iloc[0] if isinstance(val, pd.Series) else val
        if pd.isna(val): return "–"
        color = "#dc3545" if val > VOLATILITY_THRESHOLD else "#28a745"
        return f'<span style="color:{color};">{val:.4f}</span>'
    except:
        return "–"

def format_close_vs_20ma(close, ma20):
    try:
        close = safe_float(close)
        ma20 = safe_float(ma20)
        if pd.isna(close) or pd.isna(ma20): return "–"
        color = "#28a745" if close > ma20 else "#dc3545"
        return f'<span style="color:{color};">{close:.2f}</span>'
    except:
        return "–"    

# Wenn Schlusskurs über dem 200-Tage-MA liegt → grün, sonst rot.
def format_close_vs_ma(close, ma):
    try:
        close = close.iloc[0] if isinstance(close, pd.Series) else close
        ma = ma.iloc[0] if isinstance(ma, pd.Series) else ma
        if pd.isna(close) or pd.isna(ma): return "–"
        color = "#28a745" if close > ma else "#dc3545"
        return f'<span style="color:{color};">{close:.2f}</span>'
    except:
        return "–"

def safe_float(val):
    try:
        if isinstance(val, pd.Series):
            val = val.iloc[0]
        return float(val)
    except:
        return float("nan")   

def interpret_indicator(indicator, row):
    try:
        if indicator == "RSI":
            val = safe_float(row["RSI"])
            return "🟢 Normal" if val >= RSI_BUY_THRESHOLD else "🔴 Überverkauft"
        elif indicator == "MACD":
            macd = safe_float(row["MACD"])
            macd_sig = safe_float(row["MACD_Signal"])
            return "🟢 Momentum steigt" if macd > macd_sig else "🔴 Momentum sinkt"
        elif indicator == "Volatility":
            vol = safe_float(row["Volatility"])
            return "🟢 Ruhiger Markt" if vol <= VOLATILITY_THRESHOLD else "🔴 Hohe Schwankung"
        elif indicator == "Close":
            close = safe_float(row["Close"])
            ma = safe_float(row["200_MA"])
            return "🟢 Über 200-Tage-Linie" if close > ma else "🔴 Unter 200-Tage-Linie"
        else:
            return "–"
    except:
        return "–"

def interpret_signal(signal):
    mapping = {
        "BUY": "📈 Kaufempfehlung – technische Indikatoren sprechen für einen Einstieg.",
        "SELL": "📉 Verkaufssignal – Indikatoren deuten auf Schwäche oder Korrektur.",
        "HOLD": "⏸️ Neutral – kein klares Signal, Markt bewegt sich seitwärts.",
        "n/v": "❔ Keine Bewertung möglich – unzureichende Datenlage."
    }
    return mapping.get(signal.upper(), "–")

def interpret_close_vs_ma(close, ma, typ="lang"):
    try:
        close = safe_float(close)
        ma = safe_float(ma)
        if pd.isna(close) or pd.isna(ma): return "–"
        if close > ma:
            return "🟢 Kurs über {}fristigem Durchschnitt".format("kurz" if typ=="kurz" else "lang")
        else:
            return "🔴 Kurs unter {}fristigem Durchschnitt".format("kurz" if typ=="kurz" else "lang")
    except:
        return "–"
    

def interpret_ampel(ampel):
    mapping = {
        "grün": "🟢 Aufwärtstrend – Kurs über 200-Tage-Linie.",
        "rot": "🔴 Abwärtstrend – Kurs unter 200-Tage-Linie.",
        "grau": "⚠️ Trend nicht bestimmbar – unzureichende Daten."
    }
    return mapping.get(ampel.lower(), "–")

# 📊 Indikator-Tabelle
# Warum stehen RSI-Werte auf “–”?
# Das bedeutet, dass einer der Werte NaN ist – das passiert z. B., 
# wenn die Datenreihe zu kurz ist oder der RSI noch nicht vollständig 
# berechnet wurde (bei <14 Datenpunkten zu Beginn oder Datenlücken).
indicator_table = f"""
<table border="1" cellspacing="0" cellpadding="5">
    <tr>
        <th>Indikator</th>
        <th>{prev_row.name.strftime('%Y-%m-%d')}</th>
        <th>{latest_row.name.strftime('%Y-%m-%d')}</th>
        <th>Bedeutung</th>
    </tr>
    <tr><td>RSI</td><td>{format_rsi(prev_row['RSI'])}</td><td>{format_rsi(latest_row['RSI'])}</td><td>{interpret_indicator("RSI", latest_row)}</td></tr>
    <tr><td>MACD</td><td>{format_macd(prev_row['MACD'], prev_row['MACD_Signal'])}</td><td>{format_macd(latest_row['MACD'], latest_row['MACD_Signal'])}</td><td>{interpret_indicator("MACD", latest_row)}</td></tr>
    <tr><td>Signal</td><td>{format_val(prev_row['MACD_Signal'])}</td><td>{format_val(latest_row['MACD_Signal'])}</td><td>–</td></tr>
    <tr><td>Volatilität</td><td>{format_volatility(prev_row['Volatility'])}</td><td>{format_volatility(latest_row['Volatility'])}</td><td>{interpret_indicator("Volatility", latest_row)}</td></tr>
    <tr><td>Schlusskurs</td><td>{format_close_vs_ma(prev_row['Close'], prev_row['200_MA'])}</td><td>{format_close_vs_ma(latest_row['Close'], latest_row['200_MA'])}</td><td>{interpret_indicator("Close", latest_row)}</td></tr>
    <tr><td>200-Tage-MA</td><td>{format_val(prev_row['200_MA'])}</td><td>{format_val(latest_row['200_MA'])}</td><td>–</td></tr>
    <tr><td>20-Tage-MA</td><td>{format_val(prev_row['20_MA'])}</td><td>{format_val(latest_row['20_MA'])}</td><td>{interpret_close_vs_ma(latest_row["Close"], latest_row["20_MA"], "kurz")}</td></tr>
</table>
"""

def ampel_html(ampel):
    farben = {
        "grün": "#28a745",  # Bootstrap grün
        "gelb": "#ffc107",  # Bootstrap gelb
        "rot": "#dc3545"    # Bootstrap rot
    }
    farbe = farben.get(ampel.lower(), "#6c757d")  # grau als fallback
    return f'<span style="color:{farbe}; font-weight:bold;">{ampel.capitalize()}</span>'

# 📁 Chart absoluter Pfad für lokale Anzeige
chart_abs_path = os.path.abspath(chart_path)

signal_note = ""
if signal == "n/v":
    signal_note = "<p style='color:#dc3545;'>⚠️ Signal konnte nicht berechnet werden (unzureichende Datenbasis)</p>"

# 📝 HTML-Datei schreiben
with open(html_path, "w", encoding="utf-8") as f:
    f.write(f"""
    <html>
    <head><meta charset="UTF-8"></head>
    <body>
        <h2>ETF Signalbericht für {today}</h2>
        <p><b>Signal:</b> {signal}</p>
        <p><i>{interpret_signal(signal)}</i></p>
        <p><b>Ampel:</b> {ampel_html(ampel)}</p>
        <p><i>{interpret_ampel(ampel)}</i></p>
        <p><b>Aktueller Schlusskurs:</b> {close_today:.2f} EUR</p>
        <b>Veränderung seit gestern:</b> {format_diff(diff_abs)} ({format_diff(diff_pct, is_pct=True)})
        <h3>Indikatorvergleich (gestern vs. heute)</h3>
        {indicator_table}
        <br/>
        <img src="file://{chart_abs_path}" width="800"/>
    </body>
    </html>
    """)

# Content auch in der Mail
email_html_content = f"""
<html>
<head><meta charset="UTF-8"></head>
<body>
    <h2>📩 ETF Signalbericht für {today}</h2>
    <p><b>Signal:</b> {signal}</p>
    <p><i>{interpret_signal(signal)}</i></p>
    <p><b>Ampel:</b> {ampel_html(ampel)}</p>
    <p><i>{interpret_ampel(ampel)}</i></p>
    <p><b>Schlusskurs:</b> {close_today:.2f} EUR<br>
       <b>Veränderung seit gestern:</b> {format_diff(diff_abs)} ({format_diff(diff_pct, is_pct=True)})</p>
    <h3>📊 Indikatorvergleich (heute vs. gestern)</h3>
    {indicator_table}
    <br>
    <p>⚠️ Dies ist keine Anlageberatung. Siehe vollständigen <a href='https://github.com/juerg-schaerer/etf-signalanalyse/blob/main/DISCLAIMER.md'>Disclaimer</a>.</p>
</body>
</html>
"""


# Kopie des aktuellen Reports als "index.html" speichern
index_html_path = os.path.join(HTML_DIR, "index.html")

with open(index_html_path, "w", encoding="utf-8") as f_index:
    f_index.write(f"""
    <html>
    <head><meta charset="UTF-8"></head>
    <body>
        <h2>ETF Signalbericht für {today}</h2>
        <p><b>Signal:</b> {signal}</p>
        <p><b>Ampel:</b> {ampel}</p>
        <h3>Indikatorvergleich (heute vs. gestern)</h3>
        {indicator_table}
        <br/>
        <img src="file://{chart_abs_path}" width="800"/>
    </body>
    </html>
    """)
print(f"📄 index.html aktualisiert unter: {index_html_path}")

# Alte HTML-Dateien löschen
cutoff = datetime.now() - timedelta(days=RETENTION_DAYS)
for file in glob.glob(f"{HTML_DIR}/report_*.html"):
    date_str = file.split("_")[1]
    try:
        file_date = datetime.strptime(date_str, "%Y-%m-%d")
        if file_date < cutoff:
            os.remove(file)
    except Exception:
        continue

# SQLite Setup
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS signals (
            date TEXT PRIMARY KEY,
            signal TEXT,
            ampel TEXT
        )
    ''')
    conn.commit()
    conn.close()

def store_today_signal(date, signal, ampel):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT signal, ampel FROM signals WHERE date = ?", (date,))
    row = c.fetchone()

    signal = str(signal)
    ampel = str(ampel)

    if row is None:
        c.execute("INSERT INTO signals (date, signal, ampel) VALUES (?, ?, ?)", (date, signal, ampel))
        conn.commit()
        conn.close()
        return True
    elif row[0] != signal or row[1] != ampel:
        c.execute("UPDATE signals SET signal = ?, ampel = ? WHERE date = ?", (signal, ampel, date))
        conn.commit()
        conn.close()
        return True
    conn.close()
    return False

init_db()
today_str = datetime.now().strftime("%Y-%m-%d")
changed = store_today_signal(today_str, signal, ampel)

def send_email(subject, body, chart_path):
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = EMAIL_SENDER
    msg["To"] = EMAIL_RECEIVER
    msg.set_content("Dies ist ein HTML-ETF-Report.")
    msg.add_alternative(email_html_content, subtype="html")

    with open(chart_path, "rb") as f:
        file_data = f.read()
        file_name = os.path.basename(chart_path)
    msg.add_attachment(file_data, maintype="image", subtype="png", filename=file_name)

    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as smtp:
        smtp.starttls()
        smtp.login(EMAIL_SENDER, EMAIL_PASSWORD)
        smtp.send_message(msg)

if changed:
    print("📤 Sende E-Mail...")
    send_email(f"ETF Signal Update: {signal} / {ampel}",
               f"Signal: {signal}\nAmpel: {ampel}\nChart siehe Anhang.",
               chart_path)
    print("✅ E-Mail erfolgreich gesendet.")
else:
    print("ℹ️ Keine Änderung – keine E-Mail gesendet.")