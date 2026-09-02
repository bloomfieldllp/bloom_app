import pandas as pd
import io

def get_possible_headers(df):
    possible = []
    # Check original columns
    for col in df.columns:
        c_str = str(col).strip()
        if c_str and not c_str.startswith("Unnamed"):
            if c_str not in possible:
                possible.append(c_str)
                
    # Check first 50 rows for strings
    for idx, row in df.head(50).iterrows():
        for val in row:
            if pd.notna(val):
                v_str = str(val).strip()
                if v_str and not v_str.startswith("Unnamed") and len(v_str) < 50:
                    if v_str not in possible:
                        possible.append(v_str)
    return possible

# Create a dummy excel with 5 blank rows, then title, then headers
df_dummy = pd.DataFrame([
    [None, None, None],
    [None, None, None],
    ["Title", None, None],
    ["GR Number", "Student Name", "DOB"],
    ["1", "Alice", "2000-01-01"]
])
print(get_possible_headers(df_dummy))
