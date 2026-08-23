import pytest
from unittest.mock import MagicMock, patch


def test_app_imports():
    """app.py sorunsuz import edilmeli; modül seviyesindeki import yüzeyi temiz kalmalı."""
    import app

    assert hasattr(app, "process_video")


def test_gozcu_config_is_importable():
    from gozcu import config

    assert config.FRAME_FPS > 0


def test_ensure_server_running_explains_missing_mlx_vlm():
    """mlx-vlm kurulu değilken alt süreç açmadan okunur bir hata verilmeli."""
    import app

    mock_client = MagicMock()
    mock_client.models.list.side_effect = Exception("unreachable")

    with (
        patch("app.OpenAI", return_value=mock_client),
        patch("importlib.util.find_spec", return_value=None),
        patch("app.subprocess.Popen") as mock_popen,
        patch("app.time.sleep"),
    ):
        with pytest.raises(RuntimeError, match="mlx-vlm"):
            app._ensure_server_running()

        mock_popen.assert_not_called()
