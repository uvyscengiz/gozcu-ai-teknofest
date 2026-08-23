def test_app_imports_without_mlx_vlm():
    """mlx-vlm opsiyonel oldu; app.py onsuz da import edilebilmeli."""
    import app

    assert hasattr(app, "process_video")


def test_gozcu_config_is_importable():
    from gozcu import config

    assert config.FRAME_FPS > 0
