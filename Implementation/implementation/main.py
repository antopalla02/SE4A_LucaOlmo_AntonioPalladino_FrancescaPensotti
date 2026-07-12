"""Composition root (DD Sec. 2.4.1 / 2.4.2).

This is the single module that knows which concrete matching strategy is
active: it reads the configuration, builds the strategy, and hands the wired
application object to the ASGI server. Nothing below this module imports a
concrete strategy — replacing or adding one is a configuration change here
(R26).

Run with:
    uvicorn main:app --reload
or:
    python main.py
then open http://127.0.0.1:8000/docs
"""

from __future__ import annotations

from app.api.app import create_app
from app.config import Config

config = Config.from_env()
app = create_app(config)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=False)
