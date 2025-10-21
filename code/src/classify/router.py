# src/classify/router.py
import pandas as pd

WORKLIST = "worklist.parquet"
HOLD_CSV = "hold_non_en_or_non_digital.csv"


def main():
    df = pd.read_csv("pdf_inventory.csv")

    # Ensure digital_guess exists (backward compatibility)
    if "digital_guess" not in df.columns:
        df["digital_guess"] = df["class"].str.startswith("digital")

    mask_digital = df["digital_guess"] == True  # noqa: E712
    mask_en = df["lang_guess"].fillna("") == "en"

    work = df[mask_digital & mask_en].copy()
    work["route"] = "digital_en"
    work["status"] = work.get("status", "pending")

    hold = df[~(mask_digital & mask_en)].copy()
    hold.to_csv(HOLD_CSV, index=False)

    out_cols = [
        "file_path",
        "md5",
        "route",
        "status",
        "lang_guess",
        "lang_conf",
        "garbled_detected",
    ]
    # Add doc_id for convenience
    work["doc_id"] = work["md5"].str[:12]
    
    # Ensure garbled_detected exists (backward compatibility)
    if "garbled_detected" not in work.columns:
        work["garbled_detected"] = False

    work[out_cols + ["doc_id"]].to_parquet(WORKLIST, index=False)
    print(f"Routed digital_en: {len(work)} (held: {len(hold)})")
    if len(work) == 0:
        print("WARNING: No digital English PDFs routed. Check thresholds or language probe.")


if __name__ == "__main__":
    main()
