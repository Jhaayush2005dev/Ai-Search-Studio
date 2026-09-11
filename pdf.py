from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter


loader = PyPDFLoader("documents loaders/a.pdf")

docs = loader.load()


splitter = RecursiveCharacterTextSplitter(
    chunk_size=500,
    chunk_overlap=50
)


chunks = splitter.split_documents(docs)

print(len(chunks))

print(chunks[0].page_content)
print(chunks[1].page_content)