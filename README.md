pip install -r requirements.txt
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124
winget install "FFmpeg (Essentials Build)"

千问所需依赖
pip install qwen-vl-utils>=0.0.4 

如果出现gbk编码错误，使用
python -X utf8 main_rag.py
解决