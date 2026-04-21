# src/qc/qc_report.py
import json, argparse, statistics
from pathlib import Path
from utils.io import write_json

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--doc_id", required=True)
    args = ap.parse_args()

    p = Path("artifacts")/args.doc_id/"doc.json"
    data = json.load(open(p,'r',encoding='utf-8'))
    confs = [b.get("confidence",1.0) for b in data["blocks"]]
    report = dict(
        doc_id=args.doc_id,
        n_blocks=len(confs),
        avg_conf=sum(confs)/max(1,len(confs)),
        min_conf=min(confs) if confs else 1.0
    )
    write_json(report, Path("artifacts")/args.doc_id/"qc.json")
    print("QC:", report)
