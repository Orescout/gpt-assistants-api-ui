import os
import base64
import re
import json

from fastapi import FastAPI, Request, UploadFile, Form, File
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from openai import OpenAI, AzureOpenAI
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()
templates = Jinja2Templates(directory="templates")

# Load environment variables
openai_api_key = os.environ.get("OPENAI_API_KEY")
azure_openai_endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT")
azure_openai_key = os.environ.get("AZURE_OPENAI_KEY")

if azure_openai_endpoint and azure_openai_key:
    client = AzureOpenAI(api_key=azure_openai_key, azure_endpoint=azure_openai_endpoint)
else:
    client = OpenAI(api_key=openai_api_key)

class EventHandler:
    def on_event(self, event):
        pass

    def on_text_created(self, text):
        pass

    def on_text_delta(self, delta, snapshot):
        pass

    def on_text_done(self, text):
        pass

    def on_tool_call_created(self, tool_call):
        pass

    def on_tool_call_delta(self, delta, snapshot):
        pass

    def on_tool_call_done(self, tool_call):
        pass

def format_annotation(text):
    citations = []
    text_value = text.value
    for index, annotation in enumerate(text.annotations):
        text_value = text.value.replace(annotation.text, f" [{index}]")

        if file_citation := getattr(annotation, "file_citation", None):
            cited_file = client.files.retrieve(file_citation.file_id)
            citations.append(f"[{index}] {file_citation.quote} from {cited_file.filename}")
        elif file_path := getattr(annotation, "file_path", None):
            link_tag = create_file_link(annotation.text.split("/")[-1], file_path.file_id)
            text_value = re.sub(r"\[(.*?)\]\s*\(\s*(.*?)\s*\)", link_tag, text_value)
    text_value += "\n\n" + "\n".join(citations)
    return text_value

def create_file_link(file_name, file_id):
    content = client.files.content(file_id)
    content_type = content.response.headers["content-type"]
    b64 = base64.b64encode(content.text.encode(content.encoding)).decode()
    link_tag = f'<a href="data:{content_type};base64,{b64}" download="{file_name}">Download Link</a>'
    return link_tag

@app.get("/", response_class=HTMLResponse)
async def get_form(request: Request):
    return templates.TemplateResponse("form.html", {"request": request})

@app.post("/submit")
async def handle_form(request: Request, user_input: str = Form(...), file: UploadFile = File(None)):
    # Handle file upload and processing
    if file:
        file_content = await file.read()
        file_obj = client.files.create(file=file_content, purpose="assistants")
    else:
        file_obj = None
    
    # Handle user input
    thread = create_thread(user_input, file_obj)
    create_message(thread, user_input, file_obj)
    
    # Process and format response
    response_text = "Response from OpenAI will be here"
    
    return templates.TemplateResponse("result.html", {"request": request, "response": response_text})

def create_thread(content, file):
    return client.beta.threads.create()

def create_message(thread, content, file):
    attachments = []
    if file is not None:
        attachments.append({"file_id": file.id, "tools": [{"type": "code_interpreter"}, {"type": "file_search"}]})
    client.beta.threads.messages.create(thread_id=thread.id, role="user", content=content, attachments=attachments)