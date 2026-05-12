"""
Extract 200 random docs from golden_db.agri_qa (no embedding field).
Output: golden_agri_qa.csv

Deps: pymongo python-dotenv
"""
import os
import csv
import json
from datetime import datetime
from bson import ObjectId
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".envurgent"))

MONGO_URI = os.environ["MONGO_URI"]
SAMPLE_SIZE = 200
OUTPUT_FILE = os.path.join(os.path.dirname(__file__), "golden_agri_qa.csv")


def serialize(val):
    if isinstance(val, ObjectId):
        return str(val)
    if isinstance(val, datetime):
        return val.isoformat()
    if isinstance(val, (dict, list)):
        return json.dumps(val, default=str)
    return val


def main():
    client = MongoClient(MONGO_URI)
    db = client["golden_db"]

    print(f"Sampling {SAMPLE_SIZE} random docs from golden_db.agri_qa...")
    docs = list(db["agri_qa"].aggregate([
        {"$sample": {"size": SAMPLE_SIZE}},
        {"$project": {"embedding": 0}},
    ]))
    print(f"  Got {len(docs)} docs")

    rows = []
    for doc in docs:
        row = {}
        for k, v in doc.items():
            if k == "metadata" and isinstance(v, dict):
                for mk, mv in v.items():
                    row[f"metadata_{mk}"] = serialize(mv)
            else:
                row[k] = serialize(v)
        rows.append(row)

    seen, fieldnames = set(), []
    for row in rows:
        for k in row:
            if k not in seen:
                fieldnames.append(k)
                seen.add(k)

    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    print(f"Saved {len(rows)} rows → {OUTPUT_FILE}")
    client.close()


if __name__ == "__main__":
    main()
