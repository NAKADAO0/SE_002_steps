import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_cli_offline_end_to_end(tmp_path):
    result = subprocess.run([sys.executable, "main.py", "--demo", "--output-dir", str(tmp_path)],
                            cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
                            env=dict(os.environ, PYTHONIOENCODING="utf-8"), timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "completed" in result.stdout
    assert len(list(tmp_path.glob("*/state.json"))) == 1


def test_cli_demo_rejects_custom_requirement(tmp_path):
    result = subprocess.run([sys.executable, "main.py", "--demo", "--requirement", "custom",
                             "--output-dir", str(tmp_path)], cwd=ROOT, capture_output=True)
    assert result.returncode == 1 and not list(tmp_path.iterdir())


def test_web_demo_end_to_end(tmp_path, monkeypatch):
    from streamlit.testing.v1 import AppTest
    from workflow import service
    monkeypatch.setattr(service, "ROOT", tmp_path)
    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30).run()
    assert not app.exception
    next(button for button in app.button if button.label == "运行 Workflow").click().run()
    assert not app.exception
    result = app.session_state["result"]
    assert result.status == "completed" and result.mode == "demo" and result.repairs == 1
    assert len(list(tmp_path.glob("runs/*/state.json"))) == 1
