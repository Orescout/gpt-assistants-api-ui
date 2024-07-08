import os
import base64
import re
import json
from fastapi import FastAPI, Request, WebSocket, Form, UploadFile, File
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from dotenv import load_dotenv
import openai

load_dotenv()

app = FastAPI()
templates = Jinja2Templates(directory="templates")

openai_api_key = os.environ.get("OPENAI_API_KEY")
azure_openai_endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT")
azure_openai_key = os.environ.get("AZURE_OPENAI_KEY")

if azure_openai_endpoint and azure_openai_key:
    openai.api_type = "azure"
    openai.api_base = azure_openai_endpoint
    openai.api_key = azure_openai_key
else:
    openai.api_key = openai_api_key

@app.get("/", response_class=HTMLResponse)
async def get_form(request: Request):
    return templates.TemplateResponse("form.html", {"request": request})

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    while True:
        data = await websocket.receive_text()
        response_text = await handle_user_message(data)
        await websocket.send_text(response_text)

async def handle_user_message(message: str) -> str:
    response = openai.Completion.create(
        engine="davinci",
        prompt=message,
        max_tokens=150
    )
    return response.choices[0].text.strip()