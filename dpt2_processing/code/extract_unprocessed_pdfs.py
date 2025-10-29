import csv

# Input and output file paths
import os
input_csv = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../pdf_inventory.csv'))
output_csv = os.path.abspath(os.path.join(os.path.dirname(__file__), '../unprocessed_pdfs.csv'))

with open(input_csv, newline='', encoding='utf-8') as infile, open(output_csv, 'w', newline='', encoding='utf-8') as outfile:
    reader = csv.DictReader(infile)
    writer = csv.DictWriter(outfile, fieldnames=reader.fieldnames)
    writer.writeheader()
    for row in reader:
        if row['status'].strip().lower() == 'pending':
            writer.writerow(row)
