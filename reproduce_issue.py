
from app import app, get_db, init_db, approve_payment_proof
from datetime import datetime

def reproduce():
    # 1. Initialize DB to clean state
    print("--- Initializing DB ---")
    with app.app_context():
        init_db()
        db = get_db()
        
        # 2. Add a member
        print("--- Adding Member John ---")
        db.execute("INSERT INTO members (name, username, password, role, join_date) VALUES ('John', 'john', 'john123', 'member', ?)", (datetime.now().strftime("%Y-%m-%d %H:%M:%S"),))
        john_id = db.execute("SELECT member_id FROM members WHERE username='john'").fetchone()[0]
        db.commit()
        
        # 3. Simulate Member with a 'Pending' contribution ALREADY EXISTING
        print("--- Inserting Pending Contribution for 12/2025 ---")
        db.execute("""
            INSERT INTO monthly_contributions (member_id, month, year, amount, status, paid_date)
            VALUES (?, 12, 2025, 200, 'pending', NULL)
        """, (john_id,))
        db.commit()
        
        # 4. Simulate Member submitting proof for Dec 2025
        print(f"--- Member {john_id} Submitting Proof for 12/2025 ---")
        # Creating a dummy file path
        screenshot_path = "static/uploads/payment_proofs/dummy.png"
        
        db.execute("""
            INSERT INTO payment_proofs (proof_type, member_id, month, year, amount, screenshot_path, status, submission_date)
            VALUES ('contribution', ?, 12, 2025, 200, ?, 'pending', ?)
        """, (john_id, screenshot_path, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        proof_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
        db.commit()
        print(f"Proof ID: {proof_id}")
        
        # 5. Check 'Before' state
        fund_before = db.execute("SELECT total_balance FROM fund WHERE id=1").fetchone()[0]
        contrib = db.execute("SELECT status FROM monthly_contributions WHERE member_id=? AND month=12 AND year=2025", (john_id,)).fetchone()
        
        print(f"Fund Balance Before: {fund_before}")
        print(f"Contribution Status Before: {contrib['status']}")
        
        # 6. Admin Approves (Call the ACTUAL route function)
        print("--- Admin Approving Proof (Calling app.py logic) ---")
        
        # We need a request context, but since approve_payment_proof redirects, we might just want to Invoke the logic?
        # Note: calling the route function directly will return a redirect response.
        # But the side effects (DB updates) should happen.
        # We need to mock session if the route uses it (it checks @login_required).
        # However, we can bypass the route decorator if we just copy the logic... OR we can hack session.
        # EASIER: Just use test_client to hit the endpoint.
        
    with app.test_client() as client:
        with client.session_transaction() as sess:
            sess['user_id'] = 1 # Admin ID (from init_db)
            sess['role'] = 'admin'
            sess['name'] = 'Super Admin'
            
        print("--- Sending Request /approve_payment_proof/" + str(proof_id))
        response = client.get(f'/approve_payment_proof/{proof_id}', follow_redirects=True)
        print(f"Response Status: {response.status_code}")
        
    with app.app_context():
        db = get_db()
        # 7. Check 'After' state
        fund_after = db.execute("SELECT total_balance FROM fund WHERE id=1").fetchone()[0]
        contrib = db.execute("SELECT status FROM monthly_contributions WHERE member_id=? AND month=12 AND year=2025", (john_id,)).fetchone()
        
        print(f"Fund Balance After: {fund_after}")
        print(f"Contribution Status After: {contrib['status']}")
        
        if fund_after > fund_before and contrib['status'] == 'paid':
            print("✅ SUCCESS: Contribution updated correctly.")
        else:
            print("❌ FAILURE: Contribution NOT updated.")

if __name__ == "__main__":
    reproduce()
