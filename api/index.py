"""Vercel serverless entrypoint. Vercel auto-detects any ASGI `app` object
exported from a file under /api and deploys it as a Python serverless
function; vercel.json rewrites every /api/* request to this function, and
the FastAPI app's own routes (already prefixed with /api/...) take it from
there. See DEPLOY.md for the full setup.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.main import app  # noqa: E402
