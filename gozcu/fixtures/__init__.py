"""Kurgusal tesis dünyası — Görev 09.

JSON dosyaları bu paketin **içinde** duruyor; yolu tek bir yerden veriyoruz ki
onları okuyan hiçbir modül (Görev 10'un araçları, Görev 12'nin raporu) dizini
kendi başına tahmin etmesin.
"""

from pathlib import Path

FIXTURE_DIR = Path(__file__).parent

__all__ = ["FIXTURE_DIR"]
