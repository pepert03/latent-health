"""Entry point for Hugging Face Spaces (Gradio SDK).

The Space runs `python app.py`. We serve the real LatentHealth app (website + model API, FastAPI) on
port 7860; a minimal Gradio block is mounted under /gradio because the SDK expects one.
Locally, use `web/start.ps1` (or the Dockerfile) instead.
"""

import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.join(ROOT, "src"), os.path.join(ROOT, "web")]

import gradio as gr  # noqa: E402
import uvicorn  # noqa: E402

from server.main import app  # noqa: E402

with gr.Blocks(title="LatentHealth") as demo:
    gr.Markdown("LatentHealth runs at the root of this Space: [open the app](/).")

app = gr.mount_gradio_app(app, demo, path="/gradio")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 7860)))
