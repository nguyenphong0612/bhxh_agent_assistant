import os
import sys
from streamlit.web import cli as stcli


def main():
    # Support both source run and PyInstaller bundle run.
    base_dir = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    app_path = os.path.join(base_dir, "app.py")

    sys.argv = [
        "streamlit",
        "run",
        app_path,
        "--server.headless=true",
        "--browser.gatherUsageStats=false",
        "--server.address=127.0.0.1",
        "--server.port=8501",
    ]
    raise SystemExit(stcli.main())


if __name__ == "__main__":
    main()
