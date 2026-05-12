"""
Extract 200 random Q&A pairs from agriai.answers + agriai.questions.
Output: agri_qa_pairs.csv

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
OUTPUT_FILE = os.path.join(os.path.dirname(__file__), "agri_qa_pairs.csv")


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
    db = client["agriai"]

    print(f"Sampling {SAMPLE_SIZE} random answers...")
    answers = list(db["answers"].aggregate([
        {"$sample": {"size": SAMPLE_SIZE}},
        {"$project": {"embedding": 0}},
    ]))
    print(f"  Got {len(answers)} answer docs")

    # Fetch matching questions in one query
    q_ids = [ans["questionId"] for ans in answers if "questionId" in ans]
    q_map = {
        q["_id"]: q
        for q in db["questions"].find(
            {"_id": {"$in": q_ids}},
            {"embedding": 0},
        )
    }
    print(f"  Fetched {len(q_map)} matching question docs")

    rows = []
    for ans in answers:
        row = {f"ans_{k}": serialize(v) for k, v in ans.items()}
        q = q_map.get(ans.get("questionId"))
        if q:
            row.update({f"q_{k}": serialize(v) for k, v in q.items()})
        rows.append(row)

    # Collect ordered fieldnames (answer cols first, then question cols)
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
