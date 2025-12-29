import requests

BASE_URL = "http://127.0.0.1:5000"

def login_admin():
    session = requests.Session()
    login_data = {
        "username": "admin",
        "password": "admin123"
    }
    response = session.post(f"{BASE_URL}/", data=login_data)
    if "Dashboard" in response.text or response.status_code == 200:
        print("✅ Admin Logged In")
        return session
    else:
        print("❌ Admin Login Failed")
        return None

def test_status_update(session):
    # 1. Test Pay
    print("\nTesting Payment Status Update (Pay)...")
    pay_data = {
        "member_id": 1, # Assuming member 1 exists
        "month": 12,
        "year": 2024,
        "action": "pay"
    }
    
    # We expect a redirect to contribution_tracking
    response = session.post(f"{BASE_URL}/update_contribution_status", data=pay_data, allow_redirects=True)
    
    if response.status_code == 200 and "Yearly Matrix" in response.text:
         print("✅ Payment Request Processed (Redirected to Tracking)")
    else:
         print(f"❌ Payment Request Failed: Status {response.status_code}")

    # 2. Test Unpay
    print("\nTesting Payment Status Update (Unpay)...")
    unpay_data = {
        "member_id": 1,
        "month": 12,
        "year": 2024,
        "action": "unpay"
    }
    
    response = session.post(f"{BASE_URL}/update_contribution_status", data=unpay_data, allow_redirects=True)
    
    if response.status_code == 200 and "Yearly Matrix" in response.text:
         print("✅ Unpayment Request Processed (Redirected to Tracking)")
    else:
         print(f"❌ Unpayment Request Failed: Status {response.status_code}")

if __name__ == "__main__":
    try:
        session = login_admin()
        if session:
            test_status_update(session)
    except Exception as e:
        print(f"❌ Connection Error: {e}")
        print("Make sure the Flask server is running in another terminal!")
