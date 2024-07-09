import os
import base64
import re
import json

import streamlit as st
import openai
from openai import AssistantEventHandler
from tools import TOOL_MAP
from typing_extensions import override
from dotenv import load_dotenv
import streamlit_authenticator as stauth
import json

import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
import streamlit.components.v1 as components
from streamlit.components.v1 import html
# import streamlit_cookies_manager as cookies_manager
import uuid
from streamlit_javascript import st_javascript
from streamlit_js_eval import streamlit_js_eval
import os
import json
from dotenv import load_dotenv
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# Load the .env file
load_dotenv()

creds_json = os.getenv('GOOGLE_SHEETS_CREDENTIALS')
creds_dict = json.loads(creds_json)
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client_gs = gspread.authorize(creds)
sheet = client_gs.open("ai_concussion_expert_v1_log").get_worksheet(0)

st.set_page_config(
    page_title="AI Expert",  # Replace with your desired page title
    page_icon="favicon.ico",  # Replace with the path to your favicon
)

def hide_streamlit_elements():
    hide_streamlit_style = """
        <style>
        #MainMenu {visibility: hidden;}
        footer {visibility: hidden;}
        header {visibility: hidden;}
        </style>
    """
    st.markdown(hide_streamlit_style, unsafe_allow_html=True)

hide_streamlit_elements()  # Add this line to hide Streamlit elements
    
def log_interaction(user_id, event_type, data):
    timestamp = datetime.now().isoformat()
    sheet.append_row([timestamp, user_id, event_type, data])
    
def str_to_bool(str_input):
    if not isinstance(str_input, str):
        return False
    return str_input.lower() == "true"

# Load environment variables
openai_api_key = os.environ.get("OPENAI_API_KEY")
instructions = os.environ.get("RUN_INSTRUCTIONS", "")
enabled_file_upload_message = os.environ.get(
    "ENABLED_FILE_UPLOAD_MESSAGE"
    "ENABLED_FILE_UPLOAD_MESSAGE"
)
azure_openai_endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT")
azure_openai_key = os.environ.get("AZURE_OPENAI_KEY")
authentication_required = str_to_bool(os.environ.get("AUTHENTICATION_REQUIRED", False))

# Load authentication configuration
if authentication_required:
    if "credentials" in st.secrets:
        authenticator = stauth.Authenticate(
            st.secrets["credentials"].to_dict(),
            st.secrets["cookie"]["name"],
            st.secrets["cookie"]["key"],
            st.secrets["cookie"]["expiry_days"],
        )
    else:
        authenticator = None  # No authentication should be performed

def get_session_id():
    if 'user_id' not in st.session_state:
        st.session_state.user_id = str(uuid.uuid4())
    return st.session_state.user_id

st.session_state.user_id = get_session_id()
    
client = None
if azure_openai_endpoint and azure_openai_key:
    client = openai.AzureOpenAI(
        api_key=azure_openai_key,
        api_version="2024-05-01-preview",
        azure_endpoint=azure_openai_endpoint,
    )
else:
    client = openai.OpenAI(api_key=openai_api_key)


class EventHandler(AssistantEventHandler):
    @override
    def on_event(self, event):
        pass

    @override
    def on_text_created(self, text):
        st.session_state.current_message = ""
        with st.chat_message("Assistant"):
            st.session_state.current_markdown = st.empty()

    @override
    def on_text_delta(self, delta, snapshot):
        if snapshot.value:
            text_value = re.sub(
                r"\[(.*?)\]\s*\(\s*(.*?)\s*\)", "Download Link", snapshot.value
            )
            st.session_state.current_message = text_value
            st.session_state.current_markdown.markdown(
                st.session_state.current_message, True
            )

    @override
    def on_text_done(self, text):
        format_text = format_annotation_new(text)
        # format_text = text.value
        st.session_state.current_markdown.markdown(format_text, True)
        st.session_state.chat_log.append({"name": "assistant", "msg": format_text})
        log_interaction(st.session_state.user_id, "response", format_text)
        
    @override
    def on_tool_call_created(self, tool_call):
        if tool_call.type == "code_interpreter":
            st.session_state.current_tool_input = ""
            with st.chat_message("Assistant"):
                st.session_state.current_tool_input_markdown = st.empty()

    @override
    def on_tool_call_delta(self, delta, snapshot):
        if 'current_tool_input_markdown' not in st.session_state:
            with st.chat_message("Assistant"):
                st.session_state.current_tool_input_markdown = st.empty()

        if delta.type == "code_interpreter":
            if delta.code_interpreter.input:
                st.session_state.current_tool_input += delta.code_interpreter.input
                input_code = f"### code interpreter\ninput:\n```python\n{st.session_state.current_tool_input}\n```"
                st.session_state.current_tool_input_markdown.markdown(input_code, True)

            if delta.code_interpreter.outputs:
                for output in delta.code_interpreter.outputs:
                    if output.type == "logs":
                        pass

    @override
    def on_tool_call_done(self, tool_call):
        st.session_state.tool_calls.append(tool_call)
        if tool_call.type == "code_interpreter":
            if tool_call.id in [x.id for x in st.session_state.tool_calls]:
                return
            input_code = f"### code interpreter\ninput:\n```python\n{tool_call.code_interpreter.input}\n```"
            st.session_state.current_tool_input_markdown.markdown(input_code, True)
            st.session_state.chat_log.append({"name": "assistant", "msg": input_code})
            st.session_state.current_tool_input_markdown = None
            for output in tool_call.code_interpreter.outputs:
                if output.type == "logs":
                    output = f"### code interpreter\noutput:\n```\n{output.logs}\n```"
                    with st.chat_message("Assistant"):
                        st.markdown(output, True)
                        st.session_state.chat_log.append(
                            {"name": "assistant", "msg": output}
                        )
        elif (
            tool_call.type == "function"
            and self.current_run.status == "requires_action"
        ):
            with st.chat_message("Assistant"):
                msg = f"### Function Calling: {tool_call.function.name}"
                st.markdown(msg, True)
                st.session_state.chat_log.append({"name": "assistant", "msg": msg})
            tool_calls = self.current_run.required_action.submit_tool_outputs.tool_calls
            tool_outputs = []
            for submit_tool_call in tool_calls:
                tool_function_name = submit_tool_call.function.name
                tool_function_arguments = json.loads(
                    submit_tool_call.function.arguments
                )
                tool_function_output = TOOL_MAP[tool_function_name](
                    **tool_function_arguments
                )
                tool_outputs.append(
                    {
                        "tool_call_id": submit_tool_call.id,
                        "output": tool_function_output,
                    }
                )

            with client.beta.threads.runs.submit_tool_outputs_stream(
                thread_id=st.session_state.thread.id,
                run_id=self.current_run.id,
                tool_outputs=tool_outputs,
                event_handler=EventHandler(),
            ) as stream:
                stream.until_done()


def create_thread(content, file):
    return client.beta.threads.create()


def create_message(thread, content, file):
    attachments = []
    if file is not None:
        attachments.append(
            {"file_id": file.id, "tools": [{"type": "code_interpreter"}, {"type": "file_search"}]}
        )
    client.beta.threads.messages.create(
        thread_id=thread.id, role="user", content=content, attachments=attachments
    )


def create_file_link(file_name, file_id):
    content = client.files.content(file_id)
    content_type = content.response.headers["content-type"]
    b64 = base64.b64encode(content.text.encode(content.encoding)).decode()
    link_tag = f'<a href="data:{content_type};base64,{b64}" download="{file_name}">Download Link</a>'
    return link_tag


# def format_annotation(text):
#     citations = []
#     text_value = text.value
#     for index, annotation in enumerate(text.annotations):
#         text_value = text.value.replace(annotation.text, f" [{index}]")

#         if file_citation := getattr(annotation, "file_citation", None):
#             cited_file = client.files.retrieve(file_citation.file_id)
#             citations.append(
#                 f"[{index}] {file_citation.quote} from {cited_file.filename}"
#             )
#         elif file_path := getattr(annotation, "file_path", None):
#             link_tag = create_file_link(
#                 annotation.text.split("/")[-1],
#                 file_path.file_id,
#             )
#             text_value = re.sub(r"\[(.*?)\]\s*\(\s*(.*?)\s*\)", link_tag, text_value)
#     text_value += "\n\n" + "\n".join(citations)
#     return text_value

def format_annotation(text):
    citations = []
    text_value = text.value
    for index, annotation in enumerate(text.annotations):
        text_value = text.value.replace(annotation.text, f" [{index}]")

        if file_citation := getattr(annotation, "file_citation", None):
            cited_file = client.files.retrieve(file_citation.file_id)
            quote = getattr(file_citation, "quote", "")
            citations.append(
                f"[{index}] {quote} from {cited_file.filename}"
            )
        elif file_path := getattr(annotation, "file_path", None):
            link_tag = create_file_link(
                annotation.text.split("/")[-1],
                file_path.file_id,
            )
            text_value = re.sub(r"\[(.*?)\]\s*\(\s*(.*?)\s*\)", link_tag, text_value)
    text_value += "\n\n" + "\n".join(citations)
    return text_value

def format_annotation_new(text):
    text_value = text.value
    for index, annotation in enumerate(text.annotations):
        if file_citation := getattr(annotation, "file_citation", None):
            cited_file = client.files.retrieve(file_citation.file_id)
            file_url = cited_file.filename.split('.txt')[0].replace('_', '/')
            citation_text = f" [[{index + 1}]({file_url})]"
        elif file_path := getattr(annotation, "file_path", None):
            file_url = annotation.text.split('.txt')[0].replace('_', '/')
            citation_text = f" [[{index + 1}]({file_url})]"
        text_value = text_value.replace(annotation.text, citation_text)
    return text_value


def run_stream(user_input, file, selected_assistant_id):
    if "thread" not in st.session_state:
        st.session_state.thread = create_thread(user_input, file)
    create_message(st.session_state.thread, user_input, file)
    with client.beta.threads.runs.stream(
        thread_id=st.session_state.thread.id,
        assistant_id=selected_assistant_id,
        event_handler=EventHandler(),
    ) as stream:
        stream.until_done()


def handle_uploaded_file(uploaded_file):
    file = client.files.create(file=uploaded_file, purpose="assistants")
    return file


def render_chat():
    for chat in st.session_state.chat_log:
        with st.chat_message(chat["name"]):
            st.markdown(chat["msg"], True)


if "tool_call" not in st.session_state:
    st.session_state.tool_calls = []

if "chat_log" not in st.session_state:
    st.session_state.chat_log = []

if "in_progress" not in st.session_state:
    st.session_state.in_progress = False

if "query_processed" not in st.session_state:
    st.session_state.query_processed = False

if "first_question_asked" not in st.session_state:
    st.session_state.first_question_asked = False

if "query_processed" not in st.session_state:
    st.session_state.query_processed = False
    

def disable_form():
    st.session_state.in_progress = True


def login():
    if st.session_state["authentication_status"] is False:
        st.error("Username/password is incorrect")
    elif st.session_state["authentication_status"] is None:
        st.warning("Please enter your username and password")


def reset_chat():
    st.session_state.chat_log = []
    st.session_state.in_progress = False


def load_chat_screen(assistant_id, assistant_title):
    if enabled_file_upload_message:
        uploaded_file = st.sidebar.file_uploader(
            enabled_file_upload_message,
            type=[
                "txt",
                "pdf",
                "png",
                "jpg",
                "jpeg",
                "csv",
                "json",
                "geojson",
                "xlsx",
                "xls",
            ],
            disabled=st.session_state.in_progress,
        )
    else:
        uploaded_file = None

    st.title(assistant_title if assistant_title else "")
    st.markdown("Looking for super-trustworthy answers to your concussion question?")
    st.markdown("Our AI has studied the vast peer-reviewed literature on concussions and can answer anything. We link everything back to evidence-based research. Ask away!")

    # Log when the user opens the chat
    log_interaction(st.session_state.user_id, "session_started", "___")
    
    user_msg = st.chat_input(
        "What's your question?", on_submit=disable_form, disabled=st.session_state.in_progress
    )
        
    if user_msg:
        render_chat()
        with st.chat_message("user"):
            st.markdown(user_msg, True)
        st.session_state.chat_log.append({"name": "user", "msg": user_msg})
        log_interaction(st.session_state.user_id, "query", user_msg)  

        file = None
        if uploaded_file is not None:
            file = handle_uploaded_file(uploaded_file)
        run_stream(user_msg, file, assistant_id)
        st.session_state.in_progress = False
        st.session_state.tool_call = None
        st.session_state.first_question_asked = True  # Set the state variable
        st.rerun()
        
    render_chat()
    
    # Conditionally display the markdown
    # if st.session_state.first_question_asked:
    #     user_id = st.session_state.get("user_id", "")
    #     st.markdown(f"""
    #         <div style='text-align: left; color: grey'>
    #             <a href="https://www.neuromendhealth.com/expert-answer?user_id={user_id}" >Get next-hour answer from our clinicians</a>
    #             <br>
    #             <a href="https://www.neuromendhealth.com/filters?user_id={user_id}" >Book a next-day appointment with a specialist</a>
    #         </div>
    #         """, unsafe_allow_html=True)

def main():
    
    # Check if multi-agent settings are defined
    multi_agents = os.environ.get("OPENAI_ASSISTANTS", None)
    single_agent_id = os.environ.get("ASSISTANT_ID", None)
    single_agent_title = os.environ.get("ASSISTANT_TITLE", "Assistants API UI")
        
    # Check for query parameters
    query_params = st.query_params
    user_query = query_params.query if "query" in query_params else ""

    if (
        authentication_required
        and "credentials" in st.secrets
        and authenticator is not None
    ):
        authenticator.login()
        if not st.session_state["authentication_status"]:
            login()
            return
        else:
            authenticator.logout(location="sidebar")

    # if multi_agents:
    #     assistants_json = json.loads(multi_agents)
    #     assistants_object = {f'{obj["title"]}': obj for obj in assistants_json}
    #     selected_assistant = st.sidebar.selectbox(
    #         "Select an assistant profile?",
    #         list(assistants_object.keys()),
    #         index=None,
    #         placeholder="Select an assistant profile...",
    #         on_change=reset_chat,  # Call the reset function on change
    #     )
    #     if selected_assistant:
    #         load_chat_screen(
    #             assistants_object[selected_assistant]["id"],
    #             assistants_object[selected_assistant]["title"],
    #         )
    # elif single_agent_id:
    #     load_chat_screen(single_agent_id, single_agent_title)
    # else:
    #     st.error("No assistant configurations defined in environment variables.")
    
    load_chat_screen(single_agent_id, single_agent_title)
    
    # Automatically send the user query as the first message
    if user_query and not st.session_state.query_processed:
        st.session_state.chat_log.append({"name": "user", "msg": user_query})
        log_interaction(st.session_state.user_id, "query", user_query)
        render_chat()
        
        file = None
        run_stream(user_query, file, single_agent_id)
        st.session_state.in_progress = False
        st.session_state.tool_call = None
        st.session_state.query_processed = True
        # st.rerun()
    
    if st.session_state.first_question_asked or st.session_state.query_processed:
        user_id = st.session_state.get("user_id", "")
        st.markdown(f"""
            <div style='text-align: left; color: grey'>
                <a href="https://www.neuromendhealth.com/expert-answer?user_id={user_id}" >Get next-hour answer from our clinicians</a>
                <br>
                <a href="https://www.neuromendhealth.com/filters?user_id={user_id}" >Book a next-day appointment with a specialist</a>
            </div>
            """, unsafe_allow_html=True)
        
    # # Automatically send the user query as the first message
    # if user_query and not st.session_state.query_processed:
    #     st.session_state.chat_log.append({"name": "user", "msg": user_query}) 
    #     render_chat()
        
    #     file = None
    #     run_stream(user_query, file, single_agent_id)
    #     st.session_state.in_progress = False
    #     st.session_state.tool_call = None
    #     st.session_state.query_processed = True


if __name__ == "__main__":
    main()
