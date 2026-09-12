---
title: Driver Setup
author_profile: true
layout: single
---

![Akbar]({{ '/pages/images/akbar.png' | relative_url }})

## Introduction

This page documents how to install the NVIDIA driver and CUDA toolkit on Debian
Trixie, then build llama.cpp with CUDA support.

## Check that the GPU is detected

```sh
# lspci | grep -i nvidia
02:00.0 VGA compatible controller: NVIDIA Corporation GM204GL [Quadro M4000] (rev a1)
```

## Enable the contrib and non-free repositories

```sh
# cat /etc/apt/sources.list
deb http://deb.debian.org/debian/ trixie main contrib non-free non-free-firmware
deb-src http://deb.debian.org/debian/ trixie main contrib non-free non-free-firmware

deb http://security.debian.org/debian-security trixie-security main contrib non-free non-free-firmware
deb-src http://security.debian.org/debian-security trixie-security main contrib non-free non-free-firmware

deb http://deb.debian.org/debian/ trixie-updates main contrib non-free non-free-firmware
deb-src http://deb.debian.org/debian/ trixie-updates main contrib non-free non-free-firmware
```

## Install the build tools

Install the packages needed for the NVIDIA kernel module, CUDA, and llama.cpp:

```sh
apt update
apt install build-essential linux-headers-amd64 cmake libssl-dev python3.13-venv git-lfs python3-dev
```

## Install the NVIDIA driver

```sh
apt install nvidia-driver
```

**You will have to reboot because of a kernel module conflict.**

## Install the CUDA toolkit

```sh
apt install nvidia-cuda-dev nvidia-cuda-toolkit
```

## Confirm the driver

```sh
# nvidia-smi
Sat Aug 29 15:53:59 2026       
+-----------------------------------------------------------------------------------------+
| NVIDIA-SMI 550.163.01             Driver Version: 550.163.01     CUDA Version: 12.4     |
|-----------------------------------------+------------------------+----------------------+
| GPU  Name                 Persistence-M | Bus-Id          Disp.A | Volatile Uncorr. ECC |
| Fan  Temp   Perf          Pwr:Usage/Cap |           Memory-Usage | GPU-Util  Compute M. |
|                                         |                        |               MIG M. |
|=========================================+========================+======================|
|   0  Quadro M4000                   Off |   00000000:02:00.0 Off |                  N/A |
| 62%   49C    P0             38W /  120W |       0MiB /   8192MiB |      0%      Default |
|                                         |                        |                  N/A |
+-----------------------------------------+------------------------+----------------------+
                                                                                         
+-----------------------------------------------------------------------------------------+
| Processes:                                                                              |
|  GPU   GI   CI        PID   Type   Process name                              GPU Memory |
|        ID   ID                                                               Usage      |
|=========================================================================================|
|  No running processes found                                                             |
+-----------------------------------------------------------------------------------------+
```

## Confirm the toolkit

```sh
nvcc --version
nvcc: NVIDIA (R) Cuda compiler driver
Copyright (c) 2005-2024 NVIDIA Corporation
Built on Thu_Mar_28_02:18:24_PDT_2024
Cuda compilation tools, release 12.4, V12.4.131
Build cuda_12.4.r12.4/compiler.34097967_0
```

## Download llama.cpp

```sh
git clone https://github.com/ggml-org/llama.cpp
```

## Build llama.cpp with CUDA support

```sh
cd llama.cpp
cmake -B build -DCMAKE_BUILD_TYPE=Release -DGGML_CUDA=ON
cmake --build build --config Release -j 11
cmake --install build --prefix /opt/prod/llama.cpp-0.4.0
```
