# # config.py

# # Backend: we now use Ollama instead of HF or llama_cpp
# MODEL_BACKEND = "ollama"

# # OLLAMA models (these names must match ollama pull <model>)
# OLLAMA_MODELS = {
#     "mistral": "mistral"
# }

# # Generation defaults
# MAX_NEW_TOKENS = 512
# TEMPERATURE = 0.0
# TOP_P = 0.95

# # Chunking
# WORDS_PER_CHUNK = 900
# OVERLAP_WORDS = 150

# # Output dir for JSON results
# OUTPUT_DIR = "outputs"


# Backend: switched from local Ollama to Mistral Cloud
MODEL_BACKEND = "mistral_cloud"

# Model name for Mistral API
OLLAMA_MODELS = {
    "mistral": "open-mistral-7b"
}

# Keep your chunking settings as they are
WORDS_PER_CHUNK = 900
OVERLAP_WORDS = 150
