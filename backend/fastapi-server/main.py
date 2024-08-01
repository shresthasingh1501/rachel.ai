from fastapi import FastAPI, File, UploadFile
from pydantic import BaseModel
from typing import List
from gradio_client import Client
import os
import shutil

app = FastAPI()

GRADIO_SERVER_URL = "http://0.0.0.0:7860/"
client = Client(GRADIO_SERVER_URL)

class FileUploadResponse(BaseModel):
    status: str

class SearchRequest(BaseModel):
    query: str
    collection_name: str

class AnswerRequest(BaseModel):
    question: str
    collection_name: str

@app.post("/upload_files", response_model=FileUploadResponse)
async def upload_files(files: List[UploadFile], collection_name: str):
    # Save uploaded files temporarily
    temp_files = []
    for file in files:
        temp_path = f"temp_{file.filename}"
        with open(temp_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        temp_files.append(temp_path)

    # Call Gradio client
    try:
        result = client.predict(temp_files, collection_name, api_name="/handle_file_upload")
        status = "Files uploaded and processed successfully."
    except Exception as e:
        status = f"Error: {str(e)}"
    finally:
        # Clean up temporary files
        for temp_file in temp_files:
            os.remove(temp_file)

    return FileUploadResponse(status=status)

@app.post("/search", response_model=str)
async def search(req: SearchRequest):
    try:
        result = client.predict(req.query, req.collection_name, api_name="/search_vector_database")
        return result
    except Exception as e:
        return f"Error: {str(e)}"

@app.post("/ask_question", response_model=str)
async def ask_question(req: AnswerRequest):
    try:
        result = client.predict(req.question, req.collection_name, api_name="/answer_question")
        return result
    except Exception as e:
        return f"Error: {str(e)}"

@app.get("/collections", response_model=str)
async def get_collections():
    try:
        result = client.predict(api_name="/read_collections")
        return result
    except Exception as e:
        return f"Error: {str(e)}"

