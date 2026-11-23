@echo off
cd /d G:\GPT-SoVITS
set PATH=E:\tool\oopz;%PATH%
set NLTK_DATA=G:\nltk_data
set HF_HOME=G:\hf_cache
set HF_ENDPOINT=https://hf-mirror.com
set PYTHONUNBUFFERED=1
G:\Python310\python.exe -u G:\_setup\run_train.py prep s2 s1 > G:\_setup\train_master.log 2>&1
