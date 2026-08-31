# Computing Environment

Fr3d runs on a HP Z440 machine running Debian Linux with an NVIDIA Quadro M4000 GPU. The GPU provides 8 GB of memory for local model inference.

## Software Stack

- Debian Trixie
- NVIDIA driver and CUDA 12.4
- CUDA-enabled llama.cpp inference server
- Qwen3.5 4B model using Q4_K_M GGUF quantization
- Python virtual environment under /opt/fr3d/.venv
- systemd service running under the dedicated fr3d account
- MCP v2 server exposing the Fr3d Knowledge Base tool

The llama.cpp source and model artifacts live under /opt/dev. The deployed Fr3d application and Knowledge Base live under /opt/fr3d.

- [Return to the Knowledge Base](/)
