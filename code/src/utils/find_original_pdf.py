import pandas as pd

# Load the worklist
worklist = pd.read_parquet('worklist.parquet')

doc_id = '42a2234c2652'
# Find the row where md5 starts with doc_id
doc_row = worklist[worklist['md5'].str.startswith(doc_id)]
if not doc_row.empty:
    print('Original PDF path:', doc_row.iloc[0]['file_path'])
else:
    print('No matching document found for doc_id:', doc_id)
