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
