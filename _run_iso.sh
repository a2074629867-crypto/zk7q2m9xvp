#!/bin/bash
export PATH="/e/tool/oopz:$PATH"
export NLTK_DATA=G:/nltk_data
export HF_HOME="C:/Users/86178/.cache/huggingface"
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
export version=v5turbo
unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY
cd /g/_setup
G:/Python310/python.exe -u /g/_setup/gsv5_iso_test.py
