import pandas as pd
import io
import sys
import unittest.mock as mock

# Mock get_db
mock_db = mock.MagicMock()
def mock_get_db():
    return mock_db

import database
database.get_db = mock_get_db

from services.student_import_service import StudentImportService

def create_excel(blocks):
    df = pd.concat(blocks, ignore_index=True)
    out = io.BytesIO()
    df.to_excel(out, index=False, header=False)
    return out.getvalue()

t1 = pd.DataFrame([["GR", "Name", "Date of Birth", "Address"], ["100", "John", "2010-01-01", "123 Main"], ["101", "Jane", "2010-02-02", "456 Elm"]])
t2_blank = pd.DataFrame([["", "", "", ""]] * 5)
t2 = pd.concat([t2_blank, t1])
t4_block2 = pd.DataFrame([["", "", "", ""], ["Class 2", "", "", ""], ["", "", "", ""], ["Name", "GR", "Date of Birth", "Address"], ["Bob", "102", "2011-01-01", "789 Pine"]])
t4 = pd.concat([t2, t4_block2])
t7 = pd.DataFrame([["GR", "Name", "Date of Birth", "Address", "PAN Number"], ["103", "Alice", "2012-01-01", "321 Oak", "ABCDE1234F"]])

tests = {"TEST 1": create_excel([t1]), "TEST 2": create_excel([t2]), "TEST 4": create_excel([t4]), "TEST 7": create_excel([t7])}

for name, f_bytes in tests.items():
    print(f"--- {name} ---")
    report = StudentImportService.intelligent_parse_records([(f_bytes, "test.xlsx")], "mock_school_id")
    print(f"Blocks detected: {report['blocks_detected']}")
    print(f"Custom fields: {report['new_custom_fields']}")
    print(f"Valid records: {len(report['valid_records'])}")
    for r in report['valid_records']:
        print(f"  {r['gr']} | {r['name']} | Custom: {r['custom_fields']}")

