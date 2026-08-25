"""Gözcü — operatör konsolunun giriş noktası.

Bütün ekran `gozcu/ui/console.py` içinde. Bu dosya yalnız onu açıyor:
1. Aşama PoC'sinin kare galerisi ve `process_video`'su kaldırıldı — konsolun
   gösterdiği şey artık kare değil, videonun kendi saatinde alınan kararlar.
"""

from gozcu.ui.console import baslat

if __name__ == "__main__":
    baslat()
