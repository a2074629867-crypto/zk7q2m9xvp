import os
from huggingface_hub import snapshot_download
p = snapshot_download(
    'openai/whisper-small.en',
    allow_patterns=['*.json','*.txt','*.model','model.safetensors','pytorch_model.bin'],
)
print('OK', p, flush=True)
