import csv
import os

# Extract only garbled files from unprocessed_pdfs.csv
input_csv = os.path.abspath(os.path.join(os.path.dirname(__file__), '../unprocessed_pdfs.csv'))
output_csv = os.path.abspath(os.path.join(os.path.dirname(__file__), '../garbled_pdfs.csv'))

with open(input_csv, newline='', encoding='utf-8') as infile, open(output_csv, 'w', newline='', encoding='utf-8') as outfile:
    reader = csv.DictReader(infile)
    writer = csv.DictWriter(outfile, fieldnames=reader.fieldnames)
    writer.writeheader()
    
    count = 0
    for row in reader:
        if row['garbled_detected'].strip().lower() == 'true':
            writer.writerow(row)
            count += 1
    
    print(f"Extracted {count} garbled files to {output_csv}")
