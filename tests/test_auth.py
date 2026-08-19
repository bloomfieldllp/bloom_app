import pytest
from services.auth_service import AuthService
from config import settings

def test_password_hashing():
    pwd = "my-secure-password"
    hashed = AuthService.hash_password(pwd)
    
    assert pwd != hashed
    assert AuthService.verify_password(pwd, hashed)
    assert not AuthService.verify_password("wrong-password", hashed)

def test_dual_login_options(mock_db):
    # 1. Create a user with both phone and email
    user_with_email_id = AuthService.create_user({
        "name": "User Phone Email",
        "phone": "9876543210",
        "email": "phone_email@test.com",
        "password": "mypassword123",
        "role": "school_admin",
        "school_id": "65cb76e27ad5bcf341999999",
        "status": "active"
    })
    
    # 2. Create a user with phone only (no email)
    user_no_email_id = AuthService.create_user({
        "name": "User Phone Only",
        "phone": "1234567890",
        "email": None,
        "password": "password456",
        "role": "school_admin",
        "school_id": "65cb76e27ad5bcf341999999",
        "status": "active"
    })

    # Test login using phone (user with email)
    assert AuthService.authenticate_user("9876543210", "mypassword123") is not None
    
    # Test login using email (user with email)
    assert AuthService.authenticate_user("phone_email@test.com", "mypassword123") is not None

    # Test login using phone (user with phone only)
    assert AuthService.authenticate_user("1234567890", "password456") is not None

    # Test login using email (user with phone only tries email - should fail)
    assert AuthService.authenticate_user("none_existing@test.com", "password456") is None

def test_login_routes_with_username(client, mock_db):
    AuthService.create_user({
        "name": "School Admin",
        "phone": "9999988888",
        "email": "school@test.com",
        "password": "schoolpassword",
        "role": "school_admin",
        "school_id": "65cb76e27ad5bcf341999999",
        "status": "active"
    })
    
    # Test GET login page contains username label and script
    resp = client.get("/login")
    assert resp.status_code == 200
    assert "Email or Phone Number" in resp.text
    assert "togglePasswordVisibility" in resp.text
    assert "lucide-eye" in resp.text

    # Test POST login using phone number
    resp_phone = client.post("/login", data={"username": "9999988888", "password": "schoolpassword"}, follow_redirects=False)
    assert resp_phone.status_code == 303
    assert resp_phone.headers["Location"] == "/school"

    # Test POST login using email address
    resp_email = client.post("/login", data={"username": "school@test.com", "password": "schoolpassword"}, follow_redirects=False)
    assert resp_email.status_code == 303
    assert resp_email.headers["Location"] == "/school"

def test_role_based_permissions(client, mock_db):
    # Create school admin
    AuthService.create_user({
        "name": "School Admin User",
        "phone": "9990001111",
        "email": "schooladmin@test.com",
        "password": "password123",
        "role": "school_admin",
        "school_id": "65cb76e27ad5bcf341999999",
        "status": "active"
    })
    
    # Create operator
    AuthService.create_user({
        "name": "Operator User",
        "phone": "8880001111",
        "email": "operator@test.com",
        "password": "password123",
        "role": "bloom_operator",
        "school_id": None,
        "status": "active"
    })

    # Create Bloom Admin
    AuthService.create_user({
        "name": "Bloom Admin User",
        "phone": "7770001111",
        "email": "bloomadmin@test.com",
        "password": "password123",
        "role": "bloom_admin",
        "school_id": None,
        "status": "active"
    })

    # 1. School Admin access checks
    client.post("/login", data={"username": "9990001111", "password": "password123"})
    assert client.get("/admin").status_code == 403
    client.get("/logout")

    # 2. Operator access checks
    client.post("/login", data={"username": "8880001111", "password": "password123"})
    assert client.get("/admin").status_code == 403
    client.get("/logout")

    # 3. Bloom Admin access checks
    client.post("/login", data={"username": "7770001111", "password": "password123"})
    assert client.get("/admin").status_code == 200
    client.get("/logout")

def test_phone_normalization_and_email_validation():
    from utils import normalize_phone
    # Test valid phone normalizations
    assert normalize_phone("09876543210") == "9876543210"
    assert normalize_phone("+919876543210") == "9876543210"
    assert normalize_phone("919876543210") == "9876543210"
    assert normalize_phone("9876543210") == "9876543210"
    assert normalize_phone("_") == "_"
    
    # Test invalid phones raise ValueError
    with pytest.raises(ValueError):
        normalize_phone("123")
    with pytest.raises(ValueError):
        normalize_phone("94264079790") # 11 digits

