# src/translate/indictrans_runner.py
import argparse, json, torch
from transformers import AutoTokenizer, AutoModelForSeq2SeqLM
from utils.io import write_json

def load_model(name):
    tok = AutoTokenizer.from_pretrained(name)
    model = AutoModelForSeq2SeqLM.from_pretrained(name, torch_dtype=torch.float16, device_map="auto")
    return tok, model

def batch_translate(texts, tok, model, max_new_tokens=256):
    out=[]
    for i in range(0, len(texts), 16):
        batch = texts[i:i+16]
        enc = tok(batch, return_tensors="pt", padding=True, truncation=True).to(model.device)
        with torch.no_grad():
            gen = model.generate(**enc, max_new_tokens=max_new_tokens)
        out.extend(tok.batch_decode(gen, skip_special_tokens=True))
    return out

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--in_json", required=True, help="JSONL with {'id','text_native'} per line")
    ap.add_argument("--out_json", required=True)
    ap.add_argument("--model", default="ai4bharat/indictrans2-indic-en-1B")
    ap.add_argument("--source_lang", required=False, default=None, help="Source language code (e.g. hi, bn, ta)")
    args = ap.parse_args()

    tok, model = load_model(args.model)
    ids, texts = [], []
    with open(args.in_json, 'r', encoding='utf-8') as f:
        for line in f:
            obj = json.loads(line)
            ids.append(obj["id"]); texts.append(obj["text_native"])
    # If source_lang is provided, prepend language tag to each text
    if args.source_lang:
        texts = [f"<2{args.source_lang}> {t}" for t in texts]
    tr = batch_translate(texts, tok, model)
    rows = [{"id":i, "text_native":t, "text_en":e} for i,t,e in zip(ids,texts,tr)]
    write_json(rows, args.out_json)
    print("translated:", args.out_json, "rows:", len(rows))
