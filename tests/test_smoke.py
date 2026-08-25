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


def test_annotate_all_frames_matches_the_shipped_event_shape(tmp_path):
    """`app.py` Görev 17'nin `EventSummary(time, event)` şekline uymalı.

    Testler yeşilken arayüz düğmesinin çalışmaması bu depoda tekrar tekrar
    çıkan arıza; bu yüzden render yolu şemaya karşı sınanıyor.
    """
    import app
    from gozcu.models import EventSummary, PipelineOutput

    out = PipelineOutput(summary="ö", risk="Yüksek",
                         events=[EventSummary(time="00:15", event="İstif aracı devrildi")])
    thumbnails, details = app._annotate_all_frames(out, tmp_path)
    assert thumbnails == []                      # tmp_path'te kare yok
    assert details == ["**00:15** — İstif aracı devrildi"]
