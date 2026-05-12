# src/utils/io.py
import json, os, hashlib, pathlib

def sha256_file(path): 
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for chunk in iter(lambda: f.read(1<<20), b''):
            h.update(chunk)
    return h.hexdigest()

def ensure_dir(p): pathlib.Path(p).mkdir(parents=True, exist_ok=True)

def write_json(obj, path):
    ensure_dir(os.path.dirname(path))
    with open(path,'w',encoding='utf-8') as f: json.dump(obj,f,ensure_ascii=False,indent=2)
