"""Gözcü — operatör konsolunun giriş noktası.

Bütün ekran `gozcu/ui/server.py` içinde. Bu dosya yalnız onu açıyor:
1. Aşama PoC'sinin kare galerisi ve `process_video`'su kaldırıldı — konsolun
   gösterdiği şey artık kare değil, videonun kendi saatinde alınan kararlar.
2. Gradio konsolu (`gozcu/ui/console.py`) Görev 21'de emekliye ayrıldı;
   ekran artık FastAPI + SSE + bağımlılıksız HTML/CSS/JS.
"""

from gozcu.ui.server import baslat

if __name__ == "__main__":
    baslat()
