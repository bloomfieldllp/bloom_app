import re

with open("services/student_import_service.py", "r") as f:
    content = f.read()

new_read_headers = """    @staticmethod
    def read_excel_headers(files_data: List[Tuple[bytes, str]]) -> Tuple[List[str], bytes]:
        if not files_data:
            raise ValueError("No file provided.")
        content, filename = files_data[0]
        try:
            df = pd.read_excel(io.BytesIO(content), header=None, nrows=30, dtype=str)
        except Exception:
            raise ValueError("Failed to read Excel file. Please ensure it is a valid .xlsx or .xls file.")
            
        max_non_null = 0
        header_row_idx = 0
        
        for idx, row in df.iterrows():
            count = sum(1 for val in row if pd.notna(val) and str(val).strip())
            if count > max_non_null:
                max_non_null = count
                header_row_idx = idx
                
        headers = []
        if max_non_null > 0:
            for val in df.iloc[header_row_idx]:
                if pd.notna(val) and str(val).strip():
                    headers.append(str(val).strip())
                    
        return headers, content"""

content = re.sub(r'    @staticmethod\n    def read_excel_headers.*?return headers, content', new_read_headers, content, flags=re.DOTALL)

with open("services/student_import_service.py", "w") as f:
    f.write(content)
