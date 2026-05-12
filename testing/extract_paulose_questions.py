import csv
import json
import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_PATH = os.path.join(SCRIPT_DIR, "Ajrasakha Testing - GDB (reviewer).csv")
OUTPUT_PATH = os.path.join(SCRIPT_DIR, "output.csv")

results = []

with open(CSV_PATH, newline="", encoding="utf-8") as f:
    reader = csv.DictReader(f)
    for i, row in enumerate(reader):
        if i >= 50:
            break
        if row.get("Tester", "").strip() != "Paulose":
            continue
        q_question = row.get("q_question", "").strip()
        try:
            q_details = json.loads(row.get("q_details", "{}"))
            state = q_details.get("State") or q_details.get("state", "")
        except (json.JSONDecodeError, AttributeError):
            state = ""
        district = q_details.get("District") or q_details.get("district", "")
        if district and district.strip().upper() not in ("FAQ", "UNKNOWN"):
            location = f"{state}, {district}"
        else:
            location = state
        results.append({"question": f"{q_question} for {location}"})

with open(OUTPUT_PATH, "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=["question"])
    writer.writeheader()
    writer.writerows(results)

print(f"Wrote {len(results)} rows to {OUTPUT_PATH}")
