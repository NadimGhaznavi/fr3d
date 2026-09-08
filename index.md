---
title: The Fr3d Project
author_profile: true
layout: single
---

![Architecture](/pages/images/architecture.png)

# The Fr3D Project

This project is about tuning the parameters and hyperparameters of an AI Snake Game configuration using a custom agent back by a small 4B LLM.

# Components

- Qwen3.5 4B LLM running locally with `llama-server`
- LLM watchdog service
- The Fr3d agent service
- A Fr3d report service
- MariaDB for data persistence

# Development Style

- Only the data and behavior that slice actually needs.
- No fallback parsing, silent defaults, repair prompts, or retries for contract violations.
- Validate at the boundary; if the contract is broken, raise a clear error and fix the cause.
- Keep the code lean and clean

# Links

Qwen3.5 is an Open Source model created by the Alibaba group out of China.

- [Qwen Homepage](https://qwen.ai/home)
- [Qwen on ReadTheDocs](https://qwen.readthedocs.io/en/latest/)
- [Qwen 3.5 on Hugging Face](https://huggingface.co/collections/Qwen/qwen35)
