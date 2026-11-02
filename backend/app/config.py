"""
Central configuration for the VetGPT backend.
All values are overridable via environment variables (.env file supported).
"""
import os
from dotenv import load_dotenv

load_dotenv()

# --- Paths ---
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KNOWLEDGE_BASE_DIR = os.path.join(BASE_DIR, "data", "knowledge_base")
FAISS_INDEX_DIR = os.path.join(BASE_DIR, "data", "faiss_index")

# --- Embeddings ---
# Multilingual E5 embeddings, as used in the project (sentence-transformers backed)
EMBEDDING_MODEL_NAME = os.getenv("EMBEDDING_MODEL_NAME", "intfloat/multilingual-e5-large")

# --- Retrieval ---
RETRIEVER_TOP_K = int(os.getenv("RETRIEVER_TOP_K", "4"))
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "500"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "80"))

# --- LLM provider ---
# "llama_cpp"  -> runs a local Llama 2 GGUF model file (LLAMA_MODEL_PATH) -- needs 6-8GB+ RAM
# "hf_endpoint" -> calls a HuggingFace Inference Endpoint running Llama 2
# "openai_compatible" -> any OpenAI-compatible chat completions API (Groq, vLLM, Ollama, etc.)
#
# Default is "openai_compatible" pointed at Groq's free API running Llama models --
# this is the easiest path to a working public deployment since it needs no GPU/RAM
# for the model itself. Get a free key at https://console.groq.com and set GROQ_API_KEY.
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openai_compatible")

LLAMA_MODEL_PATH = os.getenv("LLAMA_MODEL_PATH", "./models/llama-2-7b-chat.Q4_K_M.gguf")
LLAMA_N_CTX = int(os.getenv("LLAMA_N_CTX", "4096"))
LLAMA_N_GPU_LAYERS = int(os.getenv("LLAMA_N_GPU_LAYERS", "0"))  # >0 if you have a GPU build

HF_ENDPOINT_URL = os.getenv("HF_ENDPOINT_URL", "")
HF_API_TOKEN = os.getenv("HF_API_TOKEN", "")

# Groq by default (free tier, OpenAI-compatible, hosts Llama models). Swap
# OPENAI_COMPATIBLE_BASE_URL to http://localhost:11434/v1 for local Ollama instead.
OPENAI_COMPATIBLE_BASE_URL = os.getenv("OPENAI_COMPATIBLE_BASE_URL", "https://api.groq.com/openai/v1")
OPENAI_COMPATIBLE_API_KEY = os.getenv("OPENAI_COMPATIBLE_API_KEY", os.getenv("GROQ_API_KEY", "not-needed"))
OPENAI_COMPATIBLE_MODEL = os.getenv("OPENAI_COMPATIBLE_MODEL", "openai/gpt-oss-20b")

# Optional operator secret; when unset, manual reindexing stays disabled.
REINDEX_API_KEY = os.getenv("REINDEX_API_KEY", "")

# --- Generation ---
MAX_NEW_TOKENS = int(os.getenv("MAX_NEW_TOKENS", "512"))
TEMPERATURE = float(os.getenv("TEMPERATURE", "0.3"))

# --- CORS ---
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "*").split(",")
