from langchain_community.document_loaders import DirectoryLoader, PyPDFLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS
import logging
import os # Impor os untuk menghapus folder lama

# Konfigurasi logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- PERUBAHAN 1: Path utama sekarang menunjuk ke folder 'knowledge_base' ---
KNOWLEDGE_BASE_PATH = "knowledge_base"
# --- PERUBAHAN 2: Nama file indeks yang baru dan lebih umum ---
FAISS_INDEX_PATH = "faiss_index_all_subjects" 

def create_vector_store():
    """
    Membaca semua dokumen (.txt dan .pdf) dari SEMUA subfolder di dalam KNOWLEDGE_BASE_PATH,
    lalu membuat dan menyimpan satu FAISS Vector Store gabungan.
    """
    try:
        # 1. Muat dokumen .txt dari semua subfolder
        logging.info(f"Memuat dokumen .txt dari: {KNOWLEDGE_BASE_PATH} dan semua subfoldernya")
        txt_loader = DirectoryLoader(KNOWLEDGE_BASE_PATH, glob="**/*.txt")
        txt_documents = txt_loader.load()

        # 2. Muat dokumen .pdf dari semua subfolder
        logging.info(f"Memuat dokumen .pdf dari: {KNOWLEDGE_BASE_PATH} dan semua subfoldernya")
        pdf_loader = DirectoryLoader(KNOWLEDGE_BASE_PATH, glob="**/*.pdf", loader_cls=PyPDFLoader)
        pdf_documents = pdf_loader.load()
        
        # 3. Gabungkan semua dokumen
        documents = txt_documents + pdf_documents
        
        if not documents:
            logging.warning(f"Tidak ada dokumen (.txt atau .pdf) yang ditemukan di dalam '{KNOWLEDGE_BASE_PATH}'. Pastikan file ada di dalam subfolder.")
            return

        # 4. Bagi dokumen menjadi chunks
        logging.info("Membagi dokumen menjadi chunks...")
        text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=100)
        docs = text_splitter.split_documents(documents)

        # 5. Inisialisasi model embedding
        logging.info("Menginisialisasi model embedding...")
        embeddings = HuggingFaceEmbeddings(model_name='all-MiniLM-L6-v2')

        # 6. Buat Vector Store FAISS
        logging.info("Membuat FAISS vector store...")
        db = FAISS.from_documents(docs, embeddings)

        # 7. Simpan file indeks ke disk
        db.save_local(FAISS_INDEX_PATH)
        logging.info(f"Vector store gabungan berhasil dibuat dan disimpan di: {FAISS_INDEX_PATH}")

    except Exception as e:
        logging.error(f"Terjadi error saat membuat vector store: {e}")

if __name__ == "__main__":
    create_vector_store()