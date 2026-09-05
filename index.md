---
title: The Fr3d Project
author_profile: true
layout: single
---

![Fr3d Logo](/pages/images/fr3d.png)

# The Fr3D Project

At the center of this project is **Fr3d**, a locally run LLM based on the Qwen3.5 model.

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
