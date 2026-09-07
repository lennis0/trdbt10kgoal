# Einrichtung auf einem neuen Rechner

## Windows

```
cd %USERPROFILE%\Desktop\Prrsönliches\TradingBot
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Ab jetzt bei JEDER neuen Terminal-Sitzung zuerst:

```
.venv\Scripts\activate
```

Vorne in der Zeile steht dann `(.venv)`. Fehlt das, benutzt du das System-Python
und bekommst wieder `ModuleNotFoundError`.

## Linux / macOS

```
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Pruefen, ob es geht

```
python -m src.paper.runner --status
```

## Warum ein venv und nicht einfach `pip install pandas`?

Ein venv ist ein eigener Python-Ordner nur fuer dieses Projekt. Zwei Vorteile:
Projekte mit unterschiedlichen Paketversionen kommen sich nicht in die Quere,
und du kannst alles wegwerfen, indem du `.venv` loeschst. Systemweit installierte
Pakete bekommt man dagegen nie wieder sauber los. Ist Standard in jedem
Python-Projekt - der Ordner ist in `.gitignore`.

## Befehle

```
python -m src.paper.runner            ein Durchlauf
python -m src.paper.runner --loop     dauerhaft laufen lassen
python -m src.paper.runner --status   Stand anzeigen
python build_dashboards.py            Dashboards neu bauen
```
