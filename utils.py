import re

def normalize_phone(phone_input: str) -> str:
    """
    Normalizes a phone number by removing any leading '0', '91', or '+91'
    and returning a clean 10-digit string.
    Preserves the underscore '_' sentinel exactly.
    Raises ValueError if the number is not a valid 10-digit string.
    """
    if not phone_input:
        raise ValueError("Phone number is mandatory.")
        
    cleaned = phone_input.strip()
    if cleaned == "_":
        return "_"
        
    # Strip all non-digit characters
    digits = re.sub(r"\D", "", cleaned)
    
    # If starts with '91' and is at least 11 digits long, strip the '91'
    if digits.startswith("91") and len(digits) >= 11:
        digits = digits[2:]
        
    # Strip any leading zeros
    while digits.startswith("0"):
        digits = digits[1:]
        
    # Verify it is exactly 10 digits
    if len(digits) != 10:
        raise ValueError("Phone number must be a valid 10-digit number.")
        
    return digits


import sys
import os
from fastapi.templating import Jinja2Templates

def get_resource_path(relative_path: str) -> str:
    if getattr(sys, 'frozen', False):
        bundle_dir = getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
        path1 = os.path.join(bundle_dir, relative_path)
        if os.path.exists(path1):
            return path1
        path2 = os.path.join(bundle_dir, "_internal", relative_path)
        if os.path.exists(path2):
            return path2
        return path1
    # Development mode: resolve relative to utils.py location
    base_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_dir, relative_path)

def get_templates() -> Jinja2Templates:
    return Jinja2Templates(directory=get_resource_path("templates"))
