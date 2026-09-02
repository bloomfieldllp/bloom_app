import re

with open("services/student_import_service.py", "r") as f:
    content = f.read()

new_parse = """    @staticmethod
    def parse_mapped_records(file_bytes: bytes, mapping: Dict[str, str], school_id: str) -> Dict[str, Any]:
        try:
            # Read first 30 rows to find the header row again
            df_temp = pd.read_excel(io.BytesIO(file_bytes), header=None, nrows=30, dtype=str)
            max_non_null = 0
            header_row_idx = 0
            for idx, row in df_temp.iterrows():
                count = sum(1 for val in row if pd.notna(val) and str(val).strip())
                if count > max_non_null:
                    max_non_null = count
                    header_row_idx = idx
                    
            # Now read the full dataframe using the correct header row
            df = pd.read_excel(io.BytesIO(file_bytes), header=header_row_idx, dtype=str)
        except Exception:
            raise ValueError("Failed to parse Excel data.")
            
        # Clean columns
        df.columns = [str(c).strip() for c in df.columns]
        
        # Drop rows where all mapped columns are NaN
        mapped_cols = [col for col in mapping.values() if col in df.columns]
        df.dropna(subset=mapped_cols, how='all', inplace=True)"""

# We need to replace the start of parse_mapped_records up to df.dropna
content = re.sub(r'    @staticmethod\n    def parse_mapped_records\(file_bytes.*?df\.dropna\(subset=mapped_cols, how=\'all\', inplace=True\)', new_parse, content, flags=re.DOTALL)

with open("services/student_import_service.py", "w") as f:
    f.write(content)
