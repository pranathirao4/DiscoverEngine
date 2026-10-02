"""Streamlit Community Cloud entry point. The app itself lives in app/streamlit_app.py."""

from pathlib import Path
import runpy

runpy.run_path(str(Path(__file__).resolve().parent / "app" / "streamlit_app.py"), run_name="__main__")
