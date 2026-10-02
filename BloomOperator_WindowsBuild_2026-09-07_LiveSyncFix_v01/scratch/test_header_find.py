import pandas as pd
import io

def read_excel_headers_robust(file_bytes):
    df = pd.read_excel(io.BytesIO(file_bytes), header=None, nrows=30, dtype=str)
    headers = []
    # Collect all unique strings from the first 30 rows
    for idx, row in df.iterrows():
        for val in row:
            if pd.notna(val):
                v_str = str(val).strip()
                if v_str and v_str not in headers and not v_str.startswith("Unnamed"):
                    headers.append(v_str)
    return headers

def parse_mapped_records_robust(file_bytes, mapping):
    df = pd.read_excel(io.BytesIO(file_bytes), header=None, dtype=str)
    
    # Resolve mapping values (strings) to column indices
    col_indices = {}
    for map_key, mapped_string in mapping.items():
        if not mapped_string:
            continue
        # Find which column contains this string
        found_col = None
        for col in df.columns:
            # Check if this string exists anywhere in the column (usually in the first 30 rows)
            # A faster way:
            if mapped_string in df[col].head(30).values:
                found_col = col
                break
        if found_col is not None:
            col_indices[map_key] = found_col
            
    print("Resolved columns:", col_indices)

# Test
df_dummy = pd.DataFrame([
    [None, None, None],
    ["Title", None, None],
    ["Gr.No", "Student Name", "DOB"],
    ["1", "Alice", "2000-01-01"]
])
csv_bytes = io.BytesIO()
df_dummy.to_excel(csv_bytes, index=False, header=False)
csv_bytes = csv_bytes.getvalue()

headers = read_excel_headers_robust(csv_bytes)
print("Headers for dropdown:", headers)

parse_mapped_records_robust(csv_bytes, {"gr": "Gr.No", "name": "Student Name"})

