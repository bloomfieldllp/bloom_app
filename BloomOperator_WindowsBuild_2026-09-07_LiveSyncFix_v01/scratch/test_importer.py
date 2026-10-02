import pandas as pd
import io
from services.student_import_service import StudentImportService

def create_excel(blocks):
    df = pd.concat(blocks, ignore_index=True)
    out = io.BytesIO()
    df.to_excel(out, index=False, header=False)
    return out.getvalue()

# TEST 1: Normal single block
t1 = pd.DataFrame([
    ["GR", "Name", "Date of Birth", "Address"],
    ["100", "John", "2010-01-01", "123 Main"],
    ["101", "Jane", "2010-02-02", "456 Elm"]
])

# TEST 2: Header at row 6
t2_blank = pd.DataFrame([["", "", "", ""]] * 5)
t2 = pd.concat([t2_blank, t1])

# TEST 4: Three blocks in one sheet
t4_block2 = pd.DataFrame([
    ["", "", "", ""],
    ["Class 2", "", "", ""],
    ["", "", "", ""],
    ["Name", "GR", "Date of Birth", "Address"],
    ["Bob", "102", "2011-01-01", "789 Pine"]
])
t4 = pd.concat([t2, t4_block2])

# TEST 7: Custom field PAN Number
t7 = pd.DataFrame([
    ["GR", "Name", "Date of Birth", "Address", "PAN Number"],
    ["103", "Alice", "2012-01-01", "321 Oak", "ABCDE1234F"]
])

tests = {
    "TEST 1": create_excel([t1]),
    "TEST 2": create_excel([t2]),
    "TEST 4": create_excel([t4]),
    "TEST 7": create_excel([t7])
}

for name, f_bytes in tests.items():
    print(f"--- {name} ---")
    files_data = [(f_bytes, "test.xlsx")]
    try:
        report = StudentImportService.intelligent_parse_records(files_data, "mock_school_id")
        print(f"Blocks detected: {report['blocks_detected']}")
        print(f"Custom fields: {report['new_custom_fields']}")
        print(f"Valid records: {len(report['valid_records'])}")
        for r in report['valid_records']:
            print(f"  {r['gr']} | {r['name']} | Custom: {r['custom_fields']}")
    except Exception as e:
        print(f"Error: {e}")

