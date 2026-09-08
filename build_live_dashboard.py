"""Baut das Live-Dashboard. Aufruf: python build_live_dashboard.py"""
import sys

sys.path.insert(0, ".")

from src.dashboard.live import build

path = build()
print(f"Fertig: {path}  ({path.stat().st_size // 1024} KB)")
print("Doppelklick zum Oeffnen.")
