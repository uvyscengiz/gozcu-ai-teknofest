"""Giriş yüzeyinin duman testi.

`app.py` artık üç satır: bütün ekran `gozcu.ui.console` içinde. Bu dosyanın
koruduğu iki cümle taşındı ama değişmedi — modül temiz import edilebilmeli ve
mlx-vlm kurulu değilken **alt süreç açmadan** okunur bir hata vermeli. Ekranın
kendi mantığı `tests/test_console.py` altında sınanıyor.
"""

from unittest.mock import MagicMock, patch

import pytest


def test_app_imports_and_only_opens_the_console():
    """`app.py` giriş noktası; kendi ekran mantığını taşımıyor."""
    import app

    from gozcu.ui.console import baslat

    assert app.baslat is baslat


def test_gozcu_config_is_importable():
    from gozcu import config

    assert config.FRAME_FPS > 0


def test_the_console_module_imports_cleanly():
    from gozcu.ui import console

    assert callable(console.baslat)
    assert callable(console.build)


def test_ensure_server_running_explains_missing_mlx_vlm():
    """mlx-vlm kurulu değilken alt süreç açmadan okunur bir hata verilmeli."""
    from gozcu.ui import console

    client = MagicMock()
    client.models.list.side_effect = Exception("unreachable")

    with (
        patch.object(console, "OpenAI", return_value=client),
        patch("importlib.util.find_spec", return_value=None),
        patch.object(console.subprocess, "Popen") as popen,
        patch.object(console.time, "sleep"),
    ):
        with pytest.raises(RuntimeError, match="mlx-vlm"):
            console._ensure_server_running()

        popen.assert_not_called()
