import os
import shutil
import requests
import json
import gradio as gr
import PyPDF2
import chromadb
import csv
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings

# Constants
API_KEY = os.getenv("togetherai")
BASE_URL = "https://api.together.xyz/v1/chat/completions"
CHUNK_SIZE = 6000  # Maximum words per chunk
TEMP_SUMMARY_FILE = "temp_summaries.txt"
COLLECTIONS_FILE = "collections.csv"

# Function to convert PDF to text
def pdf_to_text(file_path):
    with open(file_path, 'rb') as pdf_file:
        pdf_reader = PyPDF2.PdfReader(pdf_file)
        text = ""
        for page in pdf_reader.pages:
            text += page.extract_text()
    return text

# Function to summarize text using LLM
def summarize_text(text):
    user_prompt = f"""
    You are an expert in legal language and document summarization. Your task is to provide a concise and accurate summary of the given document. 
    Keep the summary concise, ideally in 2000 words, while covering all essential points. Here is the document to summarize:

    {text}
    """

    return call_llm(user_prompt)

# Function to handle file upload, summarization, and saving to ChromaDB
def handle_file_upload(files, collection_name):
    if not collection_name:
        return "Please provide a collection name."

    os.makedirs('uploaded_pdfs', exist_ok=True)
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=CHUNK_SIZE, chunk_overlap=100)
    embeddings = HuggingFaceEmbeddings(model_name="thenlper/gte-small")

    client = chromadb.PersistentClient(path="./db")
    try:
        collection = client.create_collection(name=collection_name)
    except ValueError as e:
        return f"Error creating collection: {str(e)}. Please try a different collection name."

    file_names = []
    with open(TEMP_SUMMARY_FILE, 'w', encoding='utf-8') as temp_file:
        for file in files:
            file_name = os.path.basename(file.name)
            file_names.append(file_name)
            file_path = os.path.join('uploaded_pdfs', file_name)
            shutil.copy(file.name, file_path)
            
            text = pdf_to_text(file_path)
            chunks = text_splitter.split_text(text)
            
            for i, chunk in enumerate(chunks):
                summary = summarize_text(chunk)
                temp_file.write(f"Summary of {file_name} (Part {i+1}):\n{summary}\n\n")

    # Process the temporary file and add to ChromaDB
    with open(TEMP_SUMMARY_FILE, 'r', encoding='utf-8') as temp_file:
        summaries = temp_file.read()
        summary_chunks = text_splitter.split_text(summaries)

        for i, chunk in enumerate(summary_chunks):
            vector = embeddings.embed_query(chunk)
            collection.add(
                embeddings=[vector],
                documents=[chunk],
                ids=[f"summary_{i}"]
            )

    os.remove(TEMP_SUMMARY_FILE)

    # Update collections.csv
    update_collections_csv(collection_name, file_names)

    return "Files uploaded, summarized, and processed successfully."

# Function to update collections.csv
def update_collections_csv(collection_name, file_names):
    file_names_str = ", ".join(file_names)
    with open(COLLECTIONS_FILE, 'a', newline='') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow([collection_name, file_names_str])

# Function to read collections.csv
def read_collections():
    if not os.path.exists(COLLECTIONS_FILE):
        return "No collections found."
    
    with open(COLLECTIONS_FILE, 'r') as csvfile:
        reader = csv.reader(csvfile)
        collections = [f"Collection: {row[0]}\nFiles: {row[1]}\n\n" for row in reader]
    
    return "".join(collections)

# Function to search vector database
def search_vector_database(query, collection_name):
    if not collection_name:
        return "Please provide a collection name."

    embeddings = HuggingFaceEmbeddings(model_name="thenlper/gte-small")
    client = chromadb.PersistentClient(path="./db")
    try:
        collection = client.get_collection(name=collection_name)
    except ValueError as e:
        return f"Error accessing collection: {str(e)}. Make sure the collection name is correct."

    query_vector = embeddings.embed_query(query)
    results = collection.query(query_embeddings=[query_vector], n_results=2, include=["documents"])
    
    return "\n\n".join(results["documents"][0])

# Function to call LLM
def call_llm(prompt):
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }

    data = {
        "model": "meta-llama/Meta-Llama-3.1-405B-Instruct-Turbo",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7,
        "top_p": 0.7,
        "top_k": 50,
        "repetition_penalty": 1,
        "stop": ["\"\""],
        "stream": False
    }

    response = requests.post(BASE_URL, headers=headers, data=json.dumps(data))
    response.raise_for_status()
    return response.json()['choices'][0]['message']['content']

# Function to answer questions using Rachel.AI
def answer_question(question, collection_name):
    context = search_vector_database(question, collection_name)
    
    prompt = f"""
    You are a paralegal AI assistant. Your role is to assist with legal inquiries by providing clear and concise answers based on the provided question and legal context. Always maintain a highly professional tone, ensuring that your responses are well-reasoned and legally accurate.
    Question: {question}
    Legal Context: {context}
    Please provide a detailed response considering the above information. also when answering the question make sure to inform the user which filename you are using (filename is often given in the context)
    """
    
    return call_llm(prompt)

# Gradio interface
def gradio_interface():
    with gr.Blocks(theme='gl198976/The-Rounded') as interface:
        gr.Markdown("# rachel.ai backend")

        gr.Markdown("""
        ### Warning
        If you encounter an error when uploading files, try changing the collection name and upload again.
        Each collection name must be unique.
        """)
        
        with gr.Tab("Document Upload and Search"):
            with gr.Row():
                with gr.Column():
                    collection_name_input = gr.Textbox(label="Collection Name", placeholder="Enter a unique name for this collection")
                    file_upload = gr.Files(file_types=[".pdf"], label="Upload PDFs")
                    upload_btn = gr.Button("Upload, Summarize, and Process Files")
                    upload_status = gr.Textbox(label="Upload Status", interactive=False)
                with gr.Column():
                    search_query_input = gr.Textbox(label="Search Query")
                    search_collection_name = gr.Textbox(label="Collection Name for Search", placeholder="Enter the collection name to search")
                    search_output = gr.Textbox(label="Search Results", lines=10)
                    search_btn = gr.Button("Search")
            
            api_details = gr.Markdown("""
                ### API Endpoint Details
                - **URL:** http://0.0.0.0:7860/search_vector_database
                - **Method:** POST
                - **Example Usage:**
                
                ```python
                from gradio_client import Client

                client = Client("http://0.0.0.0:7860/")
                result = client.predict(
                    "search query",  # str in 'Search Query' Textbox component
                    "name of collection given in ui",  # str in 'Collection Name' Textbox component
                    api_name="/search_vector_database"
                )
                print(result)
                ```
            """)

        with gr.Tab("Rachel.AI"):
            question_input = gr.Textbox(label="Ask a question")
            rachel_collection_name = gr.Textbox(label="Collection Name", placeholder="Enter the collection name to search")
            answer_output = gr.Textbox(label="Answer", lines=10)
            ask_btn = gr.Button("Ask Rachel.AI")
            
            rachel_api_details = gr.Markdown("""
                ### API Endpoint Details for Rachel.AI
                - **URL:** http://0.0.0.0:7860/answer_question
                - **Method:** POST
                - **Example Usage:**
                
                ```python
                from gradio_client import Client

                client = Client("http://0.0.0.0:7860/")
                result = client.predict(
                    "question",  # str in 'Ask a question' Textbox component
                    "collection_name",  # str in 'Collection Name' Textbox component
                    api_name="/answer_question"
                )
                print(result)
                ```
            """)

        with gr.Tab("Collections"):
            collections_output = gr.Textbox(label="Collections and Files", lines=20)
            refresh_btn = gr.Button("Refresh Collections")

        upload_btn.click(handle_file_upload, inputs=[file_upload, collection_name_input], outputs=[upload_status])
        search_btn.click(search_vector_database, inputs=[search_query_input, search_collection_name], outputs=[search_output])
        ask_btn.click(answer_question, inputs=[question_input, rachel_collection_name], outputs=[answer_output])
        refresh_btn.click(read_collections, inputs=[], outputs=[collections_output])

    interface.launch(server_name="0.0.0.0", server_port=7860)

if __name__ == "__main__":
    gradio_interface()