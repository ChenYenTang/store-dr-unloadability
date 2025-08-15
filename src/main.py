
import gradio as gr
from fastapi import FastAPI
from src.api.routes import app as api_app
from src.ui.gradio_app import build_demo

# Build Gradio UI
demo = build_demo()

# Mount on FastAPI at /ui
app: FastAPI = api_app
app = gr.mount_gradio_app(app, demo, path="/")
