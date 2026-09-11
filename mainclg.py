import os
import sys
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, scrolledtext
from dotenv import load_dotenv

from langchain_mistralai import ChatMistralAI, MistralAIEmbeddings
from langchain_community.document_loaders import PyPDFLoader, TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter

from langchain_community.vectorstores import Chroma 
from langchain_core.messages import HumanMessage

load_dotenv()
api_key = os.getenv("MISTRAL_API_KEY")
if not api_key:
    root = tk.Tk()
    root.withdraw()
    messagebox.showerror("Error", "MISTRAL_API_KEY not found in .env")
    sys.exit(1)

model = ChatMistralAI(model="mistral-small-2506", api_key=api_key)
embeddings = MistralAIEmbeddings(model="mistral-embed", api_key=api_key)

try:
    test_vector = embeddings.embed_query("This is a test for Mistral embeddings.")
    print("--- Embedding Engine Online ---")
    print("Vector length:", len(test_vector))
    print("First 5 values:", test_vector[:5])
    print("--------------------------------")
except Exception as e:
    print(f"Warning: Preliminary embedding test failed: {e}")

root_path = Path(__file__).resolve().parent
docs_folder = root_path / "documents loaders"

pdf_path = docs_folder / "a.pdf"
notes_path = docs_folder / "notes.txt"

if not pdf_path.exists() and not notes_path.exists():
    root = tk.Tk()
    root.withdraw()
    messagebox.showerror(
        "Error", 
        f"Could not find any source documents in:\n{docs_folder}\n\nPlease verify 'a.pdf' or 'notes.txt' exists."
    )
    sys.exit(1)

all_raw_docs = []
loaded_files_status = []

try:
    if pdf_path.exists():
        pdf_loader = PyPDFLoader(str(pdf_path))
        all_raw_docs.extend(pdf_loader.load())
        loaded_files_status.append(f"{pdf_path.name}")
        
    if notes_path.exists():
        txt_loader = TextLoader(str(notes_path), encoding="utf-8")
        all_raw_docs.extend(txt_loader.load())
        loaded_files_status.append(f"{notes_path.name}")

    if not all_raw_docs:
        raise RuntimeError("The source documents appear to be completely empty.")

    text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
    doc_chunks = text_splitter.split_documents(all_raw_docs)
    
    vector_store = Chroma.from_documents(
        documents=doc_chunks,
        embedding=embeddings,
        persist_directory="./chroma_db"
    )
    print("\nVector Database Created Successfully!")
    print("Database saved in './chroma_db'")

except Exception as e:
    root = tk.Tk()
    root.withdraw()
    messagebox.showerror("Initialization Error", f"Failed to ingest documents:\n{str(e)}")
    sys.exit(1)



class DarkDocumentQAApp:
    def __init__(self, window):
        self.window = window
        self.window.title("Universal Document Knowledge Assistant (Chroma DB)")
        self.window.geometry("700x600")
        self.window.minsize(550, 450)

        self.bg_dark = "#1e1e24"       
        self.bg_card = "#2a2a32"       
        self.fg_light = "#f5f5f7"      
        self.fg_muted = "#a0a0b2"      
        self.accent_green = "#4ade80"  
        self.accent_blue = "#3b82f6"   
        self.bg_input = "#141417"      
        
        self.window.configure(bg=self.bg_dark)

        main_frame = tk.Frame(window, bg=self.bg_dark, padx=20, pady=20)
        main_frame.pack(fill=tk.BOTH, expand=True)

        top_bar = tk.Frame(main_frame, bg=self.bg_card, bd=0, padx=12, pady=10)
        top_bar.pack(fill=tk.X, pady=(0, 15))

        files_joined = ", ".join(loaded_files_status)
        status_text = f"● Active Knowledge Base: [ {files_joined} ]  |  Chroma Index Chunks: {len(doc_chunks)}"
        
        self.status_label = tk.Label(
            top_bar, 
            text=status_text, 
            fg=self.accent_green, 
            bg=self.bg_card,
            font=("Consolas", 10, "bold"),
            anchor="w"
        )
        self.status_label.pack(fill=tk.X)

        self.lbl_question = tk.Label(
            main_frame, 
            text="Query Assistant:", 
            fg=self.fg_light, 
            bg=self.bg_dark, 
            font=("Arial", 12, "bold")
        )
        self.lbl_question.pack(anchor="w", pady=(0, 5))

        self.entry_question = tk.Entry(
            main_frame, 
            font=("Arial", 11), 
            bg=self.bg_input, 
            fg=self.fg_light,
            insertbackground=self.fg_light,  
            bd=1, 
            relief=tk.FLAT,
            highlightbackground="#3a3a42",
            highlightthickness=1
        )
        self.entry_question.pack(fill=tk.X, ipady=8, pady=(0, 12))
        self.entry_question.bind("<Return>", lambda event: self.ask_question()) 
        self.entry_question.focus()

        self.btn_submit = tk.Button(
            main_frame, 
            text="Search & Synthesize", 
            command=self.ask_question, 
            bg=self.accent_blue, 
            fg="white", 
            activebackground="#2563eb",
            activeforeground="white",
            font=("Arial", 10, "bold"),
            bd=0,
            cursor="hand2",
            padx=15,
            pady=6
        )
        self.btn_submit.pack(anchor="e", pady=(0, 15))

        self.lbl_answer = tk.Label(
            main_frame, 
            text="Generated Synthesis:", 
            fg=self.fg_light, 
            bg=self.bg_dark, 
            font=("Arial", 11, "bold")
        )
        self.lbl_answer.pack(anchor="w", pady=(0, 5))

        self.txt_answer = scrolledtext.ScrolledText(
            main_frame, 
            font=("Segoe UI", 11), 
            bg=self.bg_input, 
            fg="#e2e8f0",
            insertbackground=self.fg_light,
            bd=0, 
            highlightthickness=1,
            highlightbackground="#2d2d36",
            wrap=tk.WORD
        )
        self.txt_answer.pack(fill=tk.BOTH, expand=True)
        self.txt_answer.config(state=tk.DISABLED) 

    def ask_question(self):
        question = self.entry_question.get().strip()
        
        if not question:
            messagebox.showwarning("System Alert", "Input field cannot be empty. Please state a query.")
            return

        self.txt_answer.config(state=tk.NORMAL)
        self.txt_answer.delete("1.0", tk.END)
        self.txt_answer.insert(tk.END, "⚡ Searching Chroma vectors & invoking Mistral AI clusters...")
        self.txt_answer.config(state=tk.DISABLED)
        self.window.update_idletasks()

        try:
            relevant_docs = vector_store.similarity_search(question, k=5)
            context_text = "\n\n".join([f"--- Context Source ({doc.metadata.get('source','')}): ---\n{doc.page_content}" for doc in relevant_docs])

            prompt = f"""
Answer the user's question clearly using only the provided pieces of retrieved context from the text and/or PDF documents. 
If the text does not contain enough data to supply a sound response, explain nicely that the information is unavailable.

Retrieved Document Context:
{context_text}

Question: {question}
"""
            message = HumanMessage(content=prompt)

            response = model.invoke([message])
            
            self.txt_answer.config(state=tk.NORMAL)
            self.txt_answer.delete("1.0", tk.END)
            self.txt_answer.insert(tk.END, response.content)
            self.txt_answer.config(state=tk.DISABLED)
            
        except Exception as e:
            messagebox.showerror("API Operations Error", f"An anomaly occurred:\n{str(e)}")
            self.txt_answer.config(state=tk.NORMAL)
            self.txt_answer.delete("1.0", tk.END)
            self.txt_answer.config(state=tk.DISABLED)


if __name__ == "__main__":
    app_window = tk.Tk()
    app = DarkDocumentQAApp(app_window)
    app_window.mainloop()