"""Giriş yüzeyinin duman testi.

`app.py` artık üç satır: bütün ekran `gozcu.ui.server` içinde. Bu dosyanın
koruduğu iki cümle taşındı ama değişmedi — modül temiz import edilebilmeli ve
mlx-vlm kurulu değilken **alt süreç açmadan** okunur bir hata vermeli. Ekranın
kendi mantığı `tests/test_server.py` / `tests/test_view.py` /
`tests/test_session.py` / `tests/test_feed.py` altında sınanıyor.

Görev 11: Gradio konsolu (`gozcu/ui/console.py`) silindi; bu dosyanın üç
testi de `console` yerine `server`a bakıyor. `test_the_console_module_
imports_cleanly` de `baslat`ın hâlâ çağrılabilir olduğunu doğruluyor —
`app.py` onu import ediyor ve başka hiçbir test giriş noktasının VARLIĞINI
sınamıyor.
"""

from unittest.mock import MagicMock, patch

import pytest


def test_app_imports_and_only_opens_the_console():
    """`app.py` giriş noktası; kendi ekran mantığını taşımıyor."""
    import app

    from gozcu.ui.server import baslat

    assert app.baslat is baslat


def test_gozcu_config_is_importable():
    from gozcu import config

    assert config.FRAME_FPS > 0


def test_the_console_module_imports_cleanly():
    from gozcu.ui import server

    assert callable(server.baslat)
    assert server.app is not None


def test_ensure_server_running_explains_missing_mlx_vlm():
    """mlx-vlm kurulu değilken alt süreç açmadan okunur bir hata verilmeli."""
    from gozcu.ui import server

    client = MagicMock()
    client.models.list.side_effect = Exception("unreachable")

    with (
        patch.object(server, "OpenAI", return_value=client),
        patch("importlib.util.find_spec", return_value=None),
        patch.object(server.subprocess, "Popen") as popen,
        patch.object(server.time, "sleep"),
    ):
        with pytest.raises(RuntimeError, match="mlx-vlm"):
            server._ensure_server_running()

        popen.assert_not_called()
