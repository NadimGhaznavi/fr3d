---
title: Model Setup
author_profile: true
layout: single
---

![Akbar]({{ '/pages/images/akbar.png' | relative_url }})

## Create a virtual environment

```sh
python3 -m venv venv
. venv/bin/activate
```

## Install the Python requirements

From within the virtual environment, install the llama.cpp conversion-script
requirements:

```sh
cd /opt/dev/llama.cpp
pip install -r requirements.txt
```

## Download the model

```sh
git lfs install
cd /opt/dev
git clone --depth 1 https://huggingface.co/Qwen/Qwen3.5-4B
```

The download is approximately 18 GB and may take a while. Verify the checkout:

```sh
# cd Qwen3.5-4B
# git status
On branch main
Your branch is up to date with 'origin/main'.

nothing to commit, working tree clean

$ git lfs ls-files
26a93f066e * model.safetensors-00001-of-00002.safetensors
cb544bd9bf * model.safetensors-00002-of-00002.safetensors
5f9e4d4901 * tokenizer.json

$ git rev-parse HEAD
851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a
```

## Convert the model to GGUF

```sh
cd /opt/dev/llama.cpp
mkdir -p /opt/dev/models/intermediate /opt/dev/models/quantized

python convert_hf_to_gguf.py \
    /opt/dev/Qwen3.5-4B \
    --outfile /opt/dev/models/intermediate/Qwen3.5-4B-BF16.gguf \
    --outtype bf16

...
INFO:hf-to-gguf:Model successfully exported to /opt/dev/models/intermediate/Qwen3.5-4B-BF16.gguf
```

## Quantize the model

```sh
./build/bin/llama-quantize \
    /opt/dev/models/intermediate/Qwen3.5-4B-BF16.gguf \
    /opt/dev/models/quantized/Qwen3.5-4B-Q4_K_M.gguf \
    Q4_K_M
```
