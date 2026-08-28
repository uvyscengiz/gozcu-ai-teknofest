"""Giriş yüzeyinin duman testi.

`app.py` artık üç satır: bütün ekran `gozcu.ui.server` içinde. Bu dosya
yalnız GİRİŞ YÜZEYİNİ koruyor — modül temiz import edilebilmeli ve `app.py`
gerçekten onu açmalı. Ekranın kendi mantığı `tests/test_server.py` /
`tests/test_view.py` / `tests/test_session.py` / `tests/test_feed.py`
altında sınanıyor.

Görev 11: Gradio konsolu (`gozcu/ui/console.py`) silindi; kalan testler
`console` yerine `server`a bakıyor. `test_the_console_module_imports_cleanly`
`baslat`ın hâlâ çağrılabilir olduğunu doğruluyor — `app.py` onu import
ediyor ve başka hiçbir test giriş noktasının VARLIĞINI sınamıyor.
`_ensure_server_running`'in mlx-vlm testi buradan KALKTI: aynı iddia
`tests/test_server.py::test_ensure_server_running_explains_missing_mlx_vlm`
içinde birebir duruyordu ve iki kopya bir gün ayrışırdı.
"""


def test_app_imports_and_only_opens_the_console():
    """`app.py` giriş noktası; kendi ekran mantığını taşımıyor."""
    import app

    from gozcu.ui.server import baslat

    assert app.baslat is baslat


def test_gozcu_config_is_importable():
    from gozcu.core import config

    assert config.FRAME_FPS > 0


def test_the_console_module_imports_cleanly():
    from gozcu.ui import server

    assert callable(server.baslat)
    assert server.app is not None
