import csv
from pymongo import MongoClient

MONGO_URI         = "mongodb+srv://paulose610_db_user:6kjuVpxUEoU2LhYj@cluster-rkp.vghajqu.mongodb.net/?appName=Cluster-rkp"
DB_NAME           = "ans_source_audit_db"
COLLECTION        = "answers"
UNIQUE_COLLECTION = "unique_links"
OUTPUT_CSV        = "temp.csv"

client      = MongoClient(MONGO_URI)
db          = client[DB_NAME]
answers_col = db[COLLECTION]
unique_col  = db[UNIQUE_COLLECTION]

print("Loading flagged unique_links into memory...")
flagged_links = {doc["source"] for doc in unique_col.find({"flag": True}, {"source": 1})}
print(f"Loaded {len(flagged_links)} flagged entries from unique_links.")

rows = []
seen = set()

print("Scanning answers collection...")
for mongo_doc in answers_col.find({}):
    for source_obj in mongo_doc.get("sources", []):
        link        = source_obj.get("source", "").strip()
        source_name = source_obj.get("source_name", "")
        if not link or link in seen or link not in flagged_links:
            continue
        rows.append({"source_name": source_name, "link": link})
        seen.add(link)

with open(OUTPUT_CSV, "w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=["source_name", "link"])
    writer.writeheader()
    writer.writerows(rows)

print(f"Done. {len(rows)} flagged links → {OUTPUT_CSV}")
