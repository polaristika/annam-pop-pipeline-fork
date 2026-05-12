import csv
from bson import ObjectId
from pymongo import MongoClient

MONGO_URI          = "mongodb+srv://paulose610_db_user:6kjuVpxUEoU2LhYj@cluster-rkp.vghajqu.mongodb.net/?appName=Cluster-rkp"
DB_NAME            = "ans_source_audit_db"
ANSWERS_COLLECTION = "answers"
QUESTIONS_COLLECTION = "questions"
INPUT_CSV          = "temp_deduped(1).csv"
OUTPUT_CSV         = "temp3.csv"

client        = MongoClient(MONGO_URI)
db            = client[DB_NAME]
answers_col   = db[ANSWERS_COLLECTION]
questions_col = db[QUESTIONS_COLLECTION]

# Cache questions to avoid repeated DB hits for the same questionId
question_cache = {}

def get_question(question_id):
    if question_id in question_cache:
        return question_cache[question_id]
    # Try lookup as ObjectId first, fall back to raw value
    try:
        doc = questions_col.find_one({"_id": ObjectId(str(question_id))}, {"question": 1})
    except Exception:
        doc = questions_col.find_one({"_id": question_id}, {"question": 1})
    text = doc.get("question", "") if doc else ""
    question_cache[question_id] = text
    return text


with open(INPUT_CSV, newline="") as infile, open(OUTPUT_CSV, "w", newline="") as outfile:
    reader  = csv.DictReader(infile)
    fieldnames = ["source_name", "link", "answer_id", "question_id", "question", "answer"]
    writer  = csv.DictWriter(outfile, fieldnames=fieldnames)
    writer.writeheader()

    for row in reader:
        link        = row.get("link", "").strip()
        source_name = row.get("source_name", "")

        if not link:
            continue

        # Find first answer doc that references this link in its sources array
        answer_doc = answers_col.find_one({"sources.source": link})

        if not answer_doc:
            writer.writerow({
                "source_name": source_name,
                "link":        link,
                "answer_id":   "",
                "question_id": "",
                "question":    "",
                "answer":      "",
            })
            continue

        answer_id   = str(answer_doc.get("_id", ""))
        question_id = str(answer_doc.get("questionId", ""))
        answer      = answer_doc.get("answer", "")
        question    = get_question(question_id) if question_id else ""

        writer.writerow({
            "source_name": source_name,
            "link":        link,
            "answer_id":   answer_id,
            "question_id": question_id,
            "question":    question,
            "answer":      answer,
        })
        print(f"[OK] {link[:80]}")

print(f"\nDone. Output written to {OUTPUT_CSV}")
