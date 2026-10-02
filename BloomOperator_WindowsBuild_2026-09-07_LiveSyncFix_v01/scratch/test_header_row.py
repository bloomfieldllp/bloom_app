import pandas as pd
import io

def get_headers(file_bytes):
    df = pd.read_excel(io.BytesIO(file_bytes), header=None, nrows=30, dtype=str)
    
    max_non_null = 0
    header_row_idx = 0
    
    for idx, row in df.iterrows():
        # count non-null, non-empty strings
        count = sum(1 for val in row if pd.notna(val) and str(val).strip())
        if count > max_non_null:
            max_non_null = count
            header_row_idx = idx
            
    headers = []
    # Now we know the header row, let's return the strings from it
    if max_non_null > 0:
        for val in df.iloc[header_row_idx]:
            if pd.notna(val) and str(val).strip():
                headers.append(str(val).strip())
                
    return headers, header_row_idx

df_dummy = pd.DataFrame([
    [None, None, None],
    ["School Title", None, None],
    [None, None, None],
    ["Gr.No", "Student Name", "DOB"],
    ["1", "Alice", "2000-01-01"],
    ["2", "Bob", "2000-01-02"]
])
csv_bytes = io.BytesIO()
df_dummy.to_excel(csv_bytes, index=False, header=False)
csv_bytes = csv_bytes.getvalue()

headers, idx = get_headers(csv_bytes)
print("Headers:", headers)
print("Row idx:", idx)
