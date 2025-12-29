from flask import Flask, render_template, request, redirect, session, url_for, flash
import sqlite3
from datetime import datetime
import os
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = "super_secure_secret_key_change_in_production"
DB_NAME = "database.db"

# Detect if running on Vercel (or read-only environment)
# Vercel sets keys like VERCEL=1
IS_VERCEL = os.environ.get('VERCEL') == '1'

# File Upload Configuration
if os.environ.get('VERCEL') == '1':
    UPLOAD_FOLDER = '/tmp/uploads/payment_proofs'
else:
    UPLOAD_FOLDER = 'static/uploads/payment_proofs'

if not os.path.exists(UPLOAD_FOLDER):
    try:
        os.makedirs(UPLOAD_FOLDER)
    except OSError:
        pass # Handling read-only? No, if we are in tmp we should be able to make it.

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# ---------- HELPERS ----------
import os
import shutil
try:
    import psycopg2
    import psycopg2.extras
except ImportError:
    pass

class DBWrapper:
    def __init__(self, conn, db_type):
        self.conn = conn
        self.db_type = db_type

    def execute(self, query, params=()):
        if self.db_type == 'sqlite':
            # Convert %s placeholder to ? for SQLite
            query = query.replace('%s', '?')
            return self.conn.execute(query, params)
        else:
            # Postgres uses %s natively
            cursor = self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cursor.execute(query, params)
            return cursor

    def executescript(self, script):
        if self.db_type == 'sqlite':
            return self.conn.executescript(script)
        else:
            cursor = self.conn.cursor()
            cursor.execute(script)
            return cursor

    def commit(self):
        self.conn.commit()

    def close(self):
        self.conn.close()

def get_db():
    database_url = os.environ.get('DATABASE_URL')
    
    if database_url:
        # Use PostgreSQL
        try:
            conn = psycopg2.connect(database_url)
            return DBWrapper(conn, 'postgres')
        except Exception as e:
            # Fallback or Error? If URL is invalid, better to error out visibly or fallback?
            # Let's let it crash but maybe log it?
            # actually better to return the error to the UI if possible, but for now specific crash is better than silent sqlite fallback
            raise e
    else:
        # Use SQLite (Fallback)
        # On Vercel, ROOT is read-only. We must use /tmp
        db_path = DB_NAME
        if IS_VERCEL:
            db_path = "/tmp/database.db"
            # We might need to copy our schema or init it if it doesn't exist
            # But the init route handles that.
            
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        return DBWrapper(conn, 'sqlite')

def format_currency(value):
    return f"₹{value:,.2f}"

app.jinja_env.filters['currency'] = format_currency

def calculate_dynamic_emi(loan_amount, total_months, interest_rate_percent, month_no):
    """
    Calculates EMI using Reducing Balance Method.
    Returns dictionary with details.
    """
    if month_no > total_months:
        return None # Loan should be closed
        
    principal_constant = loan_amount / total_months
    remaining_principal_start = loan_amount - (principal_constant * (month_no - 1))
    
    # Ensure no negative principal
    if remaining_principal_start < 0:
        remaining_principal_start = 0
        
    interest_amount = (remaining_principal_start * interest_rate_percent) / 100
    total_emi = principal_constant + interest_amount
    
    return {
        "month": month_no,
        "principal_component": principal_constant,
        "interest_component": interest_amount,
        "total_emi": total_emi,
        "remaining_principal_start": remaining_principal_start
    }

def login_required(role=None):
    def decorator(f):
        def wrapped(*args, **kwargs):
            if "user_id" not in session:
                return redirect(url_for("login"))
            if role and session.get("role") != role:
                return "❌ Unauthorized Access", 403
            return f(*args, **kwargs)
        wrapped.__name__ = f.__name__
        return wrapped
    return decorator

# ---------- INITIALIZATION ----------
@app.route("/init")
def init_db():
    try:
        db = get_db()
        
        # SQLite: prevent overwrite
        # If in /tmp, it might be empty on new boot, so we should allow init
        if db.db_type == 'sqlite' and not IS_VERCEL and os.path.exists(DB_NAME):
            return "⚠️ Database already exists. Initialization skipped to prevent data loss. Delete 'database.db' manually if you want to reset."
        
        # Select Schema
        schema_file = "schema.sql" if db.db_type == 'sqlite' else "schema_postgres.sql"
        
        if not os.path.exists(schema_file):
            return f"❌ Schema file {schema_file} not found.", 404

        with open(schema_file, "r") as f:
            db.executescript(f.read())
        
        # Initial fund balance
        db.execute("INSERT INTO fund (total_balance) VALUES (20000)")
        
        # Create Admin
        db.execute("""
            INSERT INTO members (name, username, password, role, join_date)
            VALUES (%s, %s, %s, 'admin', %s)
        """, ("Super Admin", "admin", "admin123", datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        
        db.commit()
        db.close()
        return "✅ System Initialized! Admin: admin/admin123"
    except Exception as e:
        return f"❌ Error: {str(e)}"

# ---------- AUTH ROUTES ----------
@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        
        db = get_db()
        user = db.execute("SELECT * FROM members WHERE username=?", (username,)).fetchone()
        db.close()
        
        if user and user["password"] == password:
            session["user_id"] = user["member_id"]
            session["role"] = user["role"]
            session["name"] = user["name"]
            return redirect(url_for("dashboard"))
        else:
            return render_template("login.html", error="Invalid credentials")
            
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

# ---------- DASHBOARD ----------
@app.route("/dashboard")
@login_required()
def dashboard():
    db = get_db()
    
    # Common Data - DYNAMIC CALCULATION
    total_collections = db.execute("SELECT SUM(amount) FROM monthly_contributions WHERE status='paid'").fetchone()[0] or 0
    
    # 1. Cash Inflow from Loans (Total EMI paid) - For Fund Balance
    total_repayments_received = db.execute("SELECT SUM(amount) FROM interest_payments WHERE status='paid'").fetchone()[0] or 0
    
    # 2. Real Interest Profit - For "Interest Earned" Card
    # We must calculate the interest component for every single paid installment
    paid_installments = db.execute("""
        SELECT ip.month_no, l.amount, l.total_months, l.interest_rate_percent, l.principal_portion
        FROM interest_payments ip
        JOIN loans l ON ip.loan_id = l.loan_id
        WHERE ip.status='paid'
    """).fetchall()
    
    real_interest_earned = 0
    for p in paid_installments:
        principal_constant = p["principal_portion"]
        # Principal outstanding at the start of that month
        remaining_principal = p["amount"] - (principal_constant * (p["month_no"] - 1))
        
        if remaining_principal < 0: remaining_principal = 0
        
        interest_component = (remaining_principal * p["interest_rate_percent"]) / 100
        real_interest_earned += interest_component

        
    # 3. Total Pending Loan Balance (Outstanding Principal)
    # Get all active loans and sum their current remaining balance
    active_loans_data = db.execute("""
        SELECT l.loan_id, l.amount, l.principal_portion
        FROM loans l
        WHERE l.status='approved' AND l.repayment_status='open'
    """).fetchall()
    
    total_pending_principal = 0
    for loan in active_loans_data:
        months_paid = db.execute("SELECT COUNT(*) FROM interest_payments WHERE loan_id=? AND status='paid'", (loan["loan_id"],)).fetchone()[0]
        current_balance = loan["amount"] - (loan["principal_portion"] * months_paid)
        if current_balance < 0: current_balance = 0
        total_pending_principal += current_balance

    total_loans_issued = db.execute("SELECT SUM(amount) FROM loans WHERE status='approved' OR status='paid'").fetchone()[0] or 0
    
    # Starting Fund + All Inflow - All Outflow
    fund = 20000 + total_collections + total_repayments_received - total_loans_issued
    
    if session["role"] == "admin":
        # New Stats (Calculated above for balance, now reused)
        # total_collections = ...
        # total_loans_issued = ...
        # total_interest = ...
        
        active_loans_count = db.execute("SELECT COUNT(*) FROM loans WHERE status='approved' AND repayment_status='open'").fetchone()[0]
        closed_loans_count = db.execute("SELECT COUNT(*) FROM loans WHERE repayment_status='closed'").fetchone()[0]
        
        # Pending Contributions for CURRENT MONTH
        current_month = datetime.now().month
        current_year = datetime.now().year
        total_members = db.execute("SELECT COUNT(*) FROM members WHERE role='member'").fetchone()[0]
        paid_members_this_month = db.execute("SELECT COUNT(DISTINCT member_id) FROM monthly_contributions WHERE month=? AND year=? AND status='paid'", (current_month, current_year)).fetchone()[0]
        pending_contributions_count = total_members - paid_members_this_month

        members = db.execute("SELECT * FROM members WHERE role='member'").fetchall()
        loans = db.execute("""
            SELECT l.*, m.name 
            FROM loans l 
            JOIN members m ON l.member_id = m.member_id 
            ORDER BY l.request_time DESC
        """).fetchall()
        
        contributions = db.execute("""
            SELECT c.*, m.name 
            FROM monthly_contributions c 
            JOIN members m ON c.member_id = m.member_id
            ORDER BY c.year DESC, c.month DESC
        """).fetchall()
        
        db.close()
        return render_template("dashboard_admin.html", 
                             balance=fund, 
                             total_collections=total_collections,
                             total_loans_issued=total_loans_issued,
                             total_interest=real_interest_earned,
                             total_pending_principal=total_pending_principal,
                             active_loans_count=active_loans_count,
                             closed_loans_count=closed_loans_count,
                             pending_contributions_count=pending_contributions_count,
                             members=members, 
                             loans=loans, 
                             contributions=contributions)
    else:
        # Member View
        my_loans_raw = db.execute("SELECT * FROM loans WHERE member_id=? ORDER BY request_time DESC", (session["user_id"],)).fetchall()
        my_contributions = db.execute("SELECT * FROM monthly_contributions WHERE member_id=? ORDER BY year DESC, month DESC", (session["user_id"],)).fetchall()
        
        # Personal Stats
        my_total_savings = db.execute("SELECT SUM(amount) FROM monthly_contributions WHERE member_id=? AND status='paid'", (session["user_id"],)).fetchone()[0] or 0
        my_active_loans_amount = db.execute("SELECT SUM(amount) FROM loans WHERE member_id=? AND status='approved' AND repayment_status='open'", (session["user_id"],)).fetchone()[0] or 0

        # Process My Loans for Dynamic EMI
        my_loans = []
        for loan in my_loans_raw:
            loan_dict = dict(loan)
            if loan["status"] == 'approved' and loan["repayment_status"] == 'open':
                # Calculate next month
                paid_months = db.execute("SELECT COUNT(*) FROM interest_payments WHERE loan_id=? AND status='paid'", (loan["loan_id"],)).fetchone()[0]
                next_month = paid_months + 1
                
                emi_calc = calculate_dynamic_emi(loan["amount"], loan["total_months"], loan["interest_rate_percent"], next_month)
                if emi_calc:
                    loan_dict["next_emi_amount"] = emi_calc["total_emi"]
                    loan_dict["next_payment_month"] = next_month
                else:
                    loan_dict["next_emi_amount"] = 0
            else:
                loan_dict["next_emi_amount"] = 0
                
            my_loans.append(loan_dict)

        # Automated Alerts (Triggered on the 10th of every month)
        alerts = []
        # For testing purposes, we can comment out the day check or use a specific day
        # if datetime.now().day == 10: 
        # But to strictly follow requirement "on every 10 of month":
        if datetime.now().day == 10: 
            # 1. Monthly Contribution Alert
            current_month = datetime.now().month
            current_year = datetime.now().year
            has_paid_contribution = db.execute("""
                SELECT 1 FROM monthly_contributions 
                WHERE member_id=%s AND month=%s AND year=%s AND status='paid'
            """, (session["user_id"], current_month, current_year)).fetchone()
            
            if not has_paid_contribution:
                alerts.append({
                    "type": "warning",
                    "title": "Payment Reminder",
                    "message": f"Today is the 10th! Please pay your monthly contribution for {datetime.now().strftime('%B')}."
                })
                
            # 2. Pending Loan Balance Alert
            if my_active_loans_amount > 0:
                 # Calculate exact pending principal for my active loans
                my_active_loans_details = db.execute("""
                    SELECT loan_id, amount, principal_portion 
                    FROM loans 
                    WHERE member_id=%s AND status='approved' AND repayment_status='open'
                """, (session["user_id"],)).fetchall()
                
                my_total_pending = 0
                for l in my_active_loans_details:
                     months_paid = db.execute("SELECT COUNT(*) FROM interest_payments WHERE loan_id=? AND status='paid'", (l["loan_id"],)).fetchone()[0]
                     current_balance = l["amount"] - (l["principal_portion"] * months_paid)
                     if current_balance < 0: current_balance = 0
                     my_total_pending += current_balance
                
                alerts.append({
                    "type": "info",
                    "title": "Loan Status",
                    "message": f"You have a total pending loan principal of ₹{my_total_pending:,.2f}."
                })

        db.close()
        return render_template("dashboard_member.html", 
                             balance=fund, 
                             my_total_savings=my_total_savings,
                             alerts=alerts,
                             my_active_loans_amount=my_active_loans_amount,
                             loans=my_loans, 
                             contributions=my_contributions,
                             user_name=session["name"])

# ---------- ADMIN CORE ACTIONS ----------

@app.route("/add_member", methods=["POST"])
@login_required("admin")
def add_member():
    name = request.form["name"]
    username = request.form["username"]
    password = request.form["password"]
    
    db = get_db()
    try:
        db.execute("""
            INSERT INTO members (name, username, password, role, join_date)
            VALUES (%s, %s, %s, 'member', %s)
        """, (name, username, password, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        db.commit()
    except sqlite3.IntegrityError:
        pass # Handle duplicate username if needed
    finally:
        db.close()
    
    return redirect(url_for("dashboard"))

@app.route("/update_contribution_status", methods=["POST"])
@login_required("admin")
def update_contribution_status():
    member_id = request.form["member_id"]
    month = int(request.form["month"])
    year = int(request.form["year"])
    action = request.form.get("action", "pay") # pay or unpaid
    amount = 200 # Fixed amount
    
    db = get_db()
    
    # Check if exists
    exists = db.execute("""
        SELECT id, status FROM monthly_contributions 
        WHERE member_id=%s AND month=%s AND year=%s
    """, (member_id, month, year)).fetchone()
    
    if action == "pay":
        if not exists:
            # Insert as Paid
            db.execute("""
                INSERT INTO monthly_contributions (member_id, month, year, amount, status, paid_date)
                VALUES (%s, %s, %s, %s, 'paid', %s)
            """, (member_id, month, year, amount, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        elif exists["status"] == 'pending':
            # Update to Paid
            db.execute("""
                UPDATE monthly_contributions 
                SET status='paid', paid_date=%s 
                WHERE id=%s
            """, (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), exists["id"]))
            
    elif action == "unpay":
        if exists:
            # If it exists, we can either set to pending or delete it.
            # Setting to pending acts as "unpaid".
            db.execute("""
                UPDATE monthly_contributions 
                SET status='pending', paid_date=NULL
                WHERE id=%s
            """, (exists["id"],))
            
    db.commit()
    db.close()
    
    # Redirect back to the tracking page with the same year filter
    return redirect(url_for("contribution_tracking", year=year))

@app.route("/approve_loan/<int:loan_id>")
@login_required("admin")
def approve_loan(loan_id):
    db = get_db()
    loan = db.execute("SELECT * FROM loans WHERE loan_id=?", (loan_id,)).fetchone()
    
    if loan and loan["status"] == "pending":
        amount = loan["amount"]
        
        # 1. Update Loan Status
        db.execute("""
            UPDATE loans 
            SET status='approved', repayment_status='open', approved_time=%s 
            WHERE loan_id=%s
        """, (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), loan_id))
        
        db.commit()
        
    db.close()
    return redirect(url_for("admin_loans"))

@app.route("/reject_loan/<int:loan_id>")
@login_required("admin")
def reject_loan(loan_id):
    db = get_db()
    db.execute("UPDATE loans SET status='rejected' WHERE loan_id=?", (loan_id,))
    db.commit()
    db.close()
    return redirect(url_for("admin_loans"))

@app.route("/update_interest", methods=["POST"])
@login_required("admin")
def update_interest():
    loan_id = request.form["loan_id"]
    month_no = request.form["month_no"]
    # Amount passed from form is now the Full EMI
    amount = int(float(request.form["amount"])) 
    
    db = get_db()
    
    # Fetch Loan Details to get segments
    loan = db.execute("SELECT * FROM loans WHERE loan_id=?", (loan_id,)).fetchone()
    
    if loan:
        principal_part = loan["principal_portion"]
        
        # 1. Record EMI Payment
        db.execute("""
            INSERT INTO interest_payments (loan_id, month_no, amount, status, paid_date)
            VALUES (%s, %s, %s, 'paid', %s)
        """, (loan_id, month_no, amount, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        
    db.commit()
    db.close()
    return redirect(url_for("admin_loans"))

@app.route("/loan_tracking")
@login_required()
def loan_tracking():
    db = get_db()
    
    
    # Fetch Loans with Dynamic Interest & Balance Stats
    loans_raw = db.execute("""
        SELECT l.*, m.name,
               (SELECT COUNT(*) FROM interest_payments ip WHERE ip.loan_id = l.loan_id AND ip.status='paid') as months_paid,
               COALESCE((SELECT SUM(amount) FROM interest_payments ip WHERE ip.loan_id = l.loan_id AND ip.status='paid'), 0) as total_interest_paid,
               (l.amount - (COALESCE((SELECT COUNT(*) FROM interest_payments ip WHERE ip.loan_id = l.loan_id AND ip.status='paid'), 0) * l.principal_portion)) as dynamic_remaining_balance
        FROM loans l
        JOIN members m ON l.member_id = m.member_id
        WHERE l.status = 'approved'
        ORDER BY l.repayment_status DESC, l.approved_time DESC
    """).fetchall()
    
    loans = []
    for loan in loans_raw:
        loan_dict = dict(loan)
        
        if loan["repayment_status"] == 'open':
            # Calculate what the EMI *should* be for the NEXT month of this loan
            # For tracking board, we want to show the current applicable EMI
            next_month = loan["months_paid"] + 1
            emi_calc = calculate_dynamic_emi(loan["amount"], loan["total_months"], loan["interest_rate_percent"], next_month)
            
            if emi_calc:
                loan_dict["current_emi_amount"] = emi_calc["total_emi"]
                loan_dict["current_interest_portion"] = emi_calc["interest_component"]
            else:
                # Fallback if calculation fails (e.g. loan finished)
                loan_dict["current_emi_amount"] = loan["emi_amount"] 
                loan_dict["current_interest_portion"] = loan["interest_portion"]
        else:
             # Closed loans - show 0 or last paid? sticking to 0 for active liabilities
             loan_dict["current_emi_amount"] = 0
             loan_dict["current_interest_portion"] = 0
             
        loans.append(loan_dict)
    
    db.close()
    return render_template("loan_tracking.html", loans=loans)

@app.route("/admin/loans")
@login_required("admin")
def admin_loans():
    db = get_db()
    
    # Stats
    pending_count = db.execute("SELECT COUNT(*) FROM loans WHERE status='pending'").fetchone()[0]
    total_active_principal = db.execute("SELECT SUM(amount) FROM loans WHERE status='approved' AND repayment_status='open'").fetchone()[0] or 0
    
    current_month = datetime.now().strftime("%Y-%m")
    interest_collected_month = db.execute("SELECT SUM(amount) FROM interest_payments WHERE paid_date LIKE ? AND status='paid'", (f"{current_month}%",)).fetchone()[0] or 0

    # Lists
    pending_loans = db.execute("""
        SELECT l.*, m.name 
        FROM loans l 
        JOIN members m ON l.member_id = m.member_id 
        WHERE l.status='pending'
        ORDER BY l.request_time ASC
    """).fetchall()
    
    active_loans_raw = db.execute("""
        SELECT l.*, m.name,
               (SELECT COUNT(*) FROM interest_payments ip WHERE ip.loan_id = l.loan_id AND ip.status='paid') + 1 as next_payment_month
        FROM loans l 
        JOIN members m ON l.member_id = m.member_id 
        WHERE l.status='approved' AND l.repayment_status='open'
        ORDER BY l.approved_time DESC
    """).fetchall()
    
    # Process Active Loans to calc Dynamic Next EMI
    active_loans = []
    for loan in active_loans_raw:
        loan_dict = dict(loan) # Convert to mutable dict
        next_month = loan["next_payment_month"]
        emi_calc = calculate_dynamic_emi(loan["amount"], loan["total_months"], loan["interest_rate_percent"], next_month)
        
        if emi_calc:
            loan_dict["next_emi_amount"] = emi_calc["total_emi"]
        else:
            loan_dict["next_emi_amount"] = 0 # Should be closed
            
        active_loans.append(loan_dict)
    
    db.close()
    return render_template("admin_loans.html",
                         pending_count=pending_count,
                         total_active_principal=total_active_principal,
                         interest_collected_month=interest_collected_month,
                         pending_loans=pending_loans,
                         active_loans=active_loans)

# ---------- MEMBER ACTIONS ----------
@app.route("/request_loan", methods=["GET", "POST"])
@login_required("member")
def request_loan():
    if request.method == "POST":
        amount = int(request.form["amount"])
        months = int(request.form["months"])
        interest_rate = 1 # 1% per month
        
        # EMI Calculations
        interest_portion = int((amount * interest_rate) / 100)
        principal_portion = int(amount / months)
        emi_amount = principal_portion + interest_portion
        
        db = get_db()
        db.execute("""
            INSERT INTO loans (member_id, amount, interest_rate_percent, interest_per_month, total_months, 
                             status, repayment_status, request_time,
                             emi_amount, principal_portion, interest_portion, remaining_balance)
            VALUES (%s, %s, %s, %s, %s, 'pending', 'open', %s, %s, %s, %s, %s)
        """, (session["user_id"], amount, interest_rate, interest_portion, months, 
              datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
              emi_amount, principal_portion, interest_portion, amount))
        db.commit()
        db.close()
        return redirect(url_for("dashboard"))
        
    return render_template("request_loan.html", user_name=session["name"])

# ---------- PAYMENT PROOF SUBMISSION ----------
@app.route("/submit_payment_proof", methods=["GET", "POST"])
@login_required("member")
def submit_payment_proof():
    db = get_db()
    
    if request.method == "POST":
        proof_type = request.form.get("proof_type", "emi")
        
        if proof_type == "emi":
            loan_id = request.form.get("loan_id")
            month_no = request.form.get("month_no")
            amount = request.form.get("amount_emi")
            
            # Simple validation
            if not loan_id or not amount:
                db.close()
                flash("❌ Missing EMI details")
                return redirect(url_for("submit_payment_proof"))
                
            amount = int(float(amount))
            month_no = int(month_no) if month_no else 1
            month = datetime.now().month
            year = datetime.now().year
        else:
            loan_id = None
            month_no = None
            amount = 200 # Fixed amount for savings
            month = request.form.get("month", datetime.now().month)
            year = request.form.get("year", datetime.now().year)
            month = int(month)
            year = int(year)
        
        # Handle file upload
        if 'screenshot' not in request.files:
            db.close()
            return redirect(url_for("submit_payment_proof"))
        
        file = request.files['screenshot']
        if file.filename == '':
            db.close()
            return redirect(url_for("submit_payment_proof"))
        
        if file and allowed_file(file.filename):
            # Create unique filename
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = secure_filename(f"{session['user_id']}_{proof_type}_{timestamp}_{file.filename}")
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            
            # Save to database
            db.execute("""
                INSERT INTO payment_proofs (proof_type, loan_id, member_id, month_no, month, year, amount, screenshot_path, status, submission_date)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'pending', %s)
            """, (proof_type, loan_id, session["user_id"], month_no, month, year, amount, filepath.replace('\\', '/'), datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
            db.commit()
            db.close()
            flash("✅ Proof submitted successfully! Waiting for admin approval.")
            return redirect(url_for("dashboard"))
    
    # GET request - show form
    active_loans_raw = db.execute("""
        SELECT l.*, 
               (SELECT COUNT(*) FROM interest_payments ip WHERE ip.loan_id = l.loan_id AND ip.status='paid') + 1 as next_payment_month
        FROM loans l
        WHERE l.member_id = %s AND l.status = 'approved' AND l.repayment_status = 'open'
    """, (session["user_id"],)).fetchall()
    
    active_loans = []
    for loan in active_loans_raw:
        loan_dict = dict(loan)
        next_month = loan["next_payment_month"]
        emi_calc = calculate_dynamic_emi(loan["amount"], loan["total_months"], loan["interest_rate_percent"], next_month)
        
        if emi_calc:
            loan_dict["next_emi_amount"] = emi_calc["total_emi"]
        else:
            loan_dict["next_emi_amount"] = 0
            
        active_loans.append(loan_dict)
    
    db.close()
    return render_template("submit_payment_proof.html", loans=active_loans, user_name=session["name"])

@app.route("/admin/payment_proofs")
@login_required("admin")
def admin_payment_proofs():
    db = get_db()
    
    pending_proofs = db.execute("""
        SELECT pp.*, m.name, l.amount as loan_amount, l.emi_amount
        FROM payment_proofs pp
        JOIN members m ON pp.member_id = m.member_id
        LEFT JOIN loans l ON pp.loan_id = l.loan_id
        WHERE pp.status = 'pending'
        ORDER BY pp.submission_date DESC
    """).fetchall()
    
    db.close()
    return render_template("admin_payment_proofs.html", pending_proofs=pending_proofs)

@app.route("/contribution_tracking")
@login_required("admin")
def contribution_tracking():
    # Only Year is needed now, Month picker is removed
    year = int(request.args.get("year", datetime.now().year))
    
    db = get_db()
    
    # Get all members
    members = db.execute("SELECT member_id, name FROM members WHERE role='member' ORDER BY name").fetchall()
    
    # Get contributions for the ENTIRE year
    contributions = db.execute("""
        SELECT member_id, month, amount, status, paid_date 
        FROM monthly_contributions 
        WHERE year=%s
    """, (year,)).fetchall()
    
    # Create a dictionary: member_id -> { month_no: status_info }
    # Structure: { 1: { 1: 'paid', 2: 'unpaid'... } }
    contrib_map = {}
    for c in contributions:
        if c["member_id"] not in contrib_map:
            contrib_map[c["member_id"]] = {}
        contrib_map[c["member_id"]][c["month"]] = {
            "status": c["status"],
            "amount": c["amount"],
            "paid_date": c["paid_date"]
        }
    
    tracking_data = []
    for m in members:
        member_row = {
            "member_id": m["member_id"],
            "name": m["name"],
            "months": {}
        }
        
        # Populate for all 12 months
        for month in range(1, 13):
            # Check if we have data for this month
            if m["member_id"] in contrib_map and month in contrib_map[m["member_id"]]:
                data = contrib_map[m["member_id"]][month]
                member_row["months"][month] = data
            else:
                # Default to Unpaid
                member_row["months"][month] = {
                    "status": "Unpaid",
                    "amount": 0,
                    "paid_date": None
                }
                
        tracking_data.append(member_row)
        
    db.close()
    
    return render_template("contribution_tracking.html", 
                         members=tracking_data, 
                         selected_year=year)

@app.route("/approve_payment_proof/<int:proof_id>")
@login_required("admin")
def approve_payment_proof(proof_id):
    db = get_db()
    
    # Get proof details
    proof = db.execute("SELECT * FROM payment_proofs WHERE proof_id=?", (proof_id,)).fetchone()
    
    if proof and proof["status"] == "pending":
        proof_type = proof["proof_type"]
        member_id = proof["member_id"]
        amount = proof["amount"]
        
        if proof_type == "emi":
            loan_id = proof["loan_id"]
            month_no = proof["month_no"]
            
            # Get loan details
            loan = db.execute("SELECT * FROM loans WHERE loan_id=?", (loan_id,)).fetchone()
            
            if loan:
                principal_part = loan["principal_portion"]
                
                # 1. Record EMI Payment
                db.execute("""
                    INSERT INTO interest_payments (loan_id, month_no, amount, status, paid_date)
                    VALUES (%s, %s, %s, 'paid', %s)
                """, (loan_id, month_no, amount, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        
        elif proof_type == "contribution":
            month = proof["month"]
            year = proof["year"]
            
            # 1. Record Contribution
            # Check if exists
            exists = db.execute("""
                SELECT id, status FROM monthly_contributions 
                WHERE member_id=%s AND month=%s AND year=%s
            """, (member_id, month, year)).fetchone()
            
            if not exists:
                db.execute("""
                    INSERT INTO monthly_contributions (member_id, month, year, amount, status, paid_date)
                    VALUES (%s, %s, %s, %s, 'paid', %s)
                """, (member_id, month, year, amount, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
            
            elif exists["status"] == 'pending':
                # Update existing pending record
                db.execute("""
                    UPDATE monthly_contributions 
                    SET status='paid', paid_date=%s 
                    WHERE id=%s
                """, (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), exists["id"]))
        
        # Finally update proof status
        db.execute("""
            UPDATE payment_proofs 
            SET status='approved', review_date=%s 
            WHERE proof_id=%s
        """, (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), proof_id))
        
        db.commit()
    
    db.close()
    return redirect(url_for("admin_payment_proofs"))

@app.route("/reject_payment_proof/<int:proof_id>", methods=["POST"])
@login_required("admin")
def reject_payment_proof(proof_id):
    db = get_db()
    admin_notes = request.form.get("admin_notes", "")
    
    db.execute("""
        UPDATE payment_proofs 
        SET status='rejected', review_date=%s, admin_notes=%s 
        WHERE proof_id=%s
    """, (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), admin_notes, proof_id))
    
    db.commit()
    db.close()
    return redirect(url_for("admin_payment_proofs"))



# ---------- ADMIN TRANSACTION MANAGEMENT ----------

@app.route("/admin/manage_payments")
@login_required("admin")
def admin_manage_payments():
    db = get_db()
    
    # Fetch Contributions
    contributions = db.execute("""
        SELECT c.*, m.name 
        FROM monthly_contributions c 
        JOIN members m ON c.member_id = m.member_id 
        ORDER BY c.year DESC, c.month DESC
    """).fetchall()
    
    # Fetch Interest Payments
    interest_payments = db.execute("""
        SELECT ip.*, m.name, l.amount as loan_amount
        FROM interest_payments ip 
        JOIN loans l ON ip.loan_id = l.loan_id
        JOIN members m ON l.member_id = m.member_id
        ORDER BY ip.paid_date DESC
    """).fetchall()
    
    db.close()
    return render_template("admin_manage_payments.html", 
                         contributions=contributions, 
                         interest_payments=interest_payments)

@app.route("/admin/delete_contribution/<int:id>", methods=["POST"])
@login_required("admin")
def delete_contribution(id):
    db = get_db()
    db.execute("DELETE FROM monthly_contributions WHERE id=?", (id,))
    db.commit()
    db.close()
    flash("✅ Contribution deleted successfully.")
    return redirect(url_for("admin_manage_payments"))

@app.route("/admin/delete_interest/<int:id>", methods=["POST"])
@login_required("admin")
def delete_interest(id):
    db = get_db()
    db.execute("DELETE FROM interest_payments WHERE id=?", (id,))
    db.commit()
    db.close()
    flash("✅ Payment deleted successfully.")
    return redirect(url_for("admin_manage_payments"))

import pandas as pd
import io
from flask import send_file

@app.route("/admin/export_transactions")
@login_required("admin")
def export_transactions():
    db = get_db()
    
    # 1. Fetch Contributions
    contributions = db.execute("""
        SELECT m.name as Member, c.month, c.year, c.amount, c.status, c.paid_date 
        FROM monthly_contributions c 
        JOIN members m ON c.member_id = m.member_id 
        ORDER BY c.year DESC, c.month DESC
    """).fetchall()
    
    # 2. Fetch Loan Payments
    loan_payments = db.execute("""
        SELECT m.name as Member, l.loan_id, ip.month_no, ip.amount, ip.status, ip.paid_date
        FROM interest_payments ip 
        JOIN loans l ON ip.loan_id = l.loan_id
        JOIN members m ON l.member_id = m.member_id
        ORDER BY ip.paid_date DESC
    """).fetchall()
    
    # 3. Fetch Loans Issued
    loans_issued = db.execute("""
        SELECT m.name as Member, l.loan_id, l.amount, l.interest_rate_percent, 
               l.total_months, l.status, l.repayment_status, 
               l.request_time, l.approved_time, l.closed_time
        FROM loans l
        JOIN members m ON l.member_id = m.member_id
        ORDER BY l.request_time DESC
    """).fetchall()
    
    db.close()
    
    # Convert to DataFrames
    df_contrib = pd.DataFrame([dict(row) for row in contributions])
    df_loans = pd.DataFrame([dict(row) for row in loan_payments])
    df_loans_issued = pd.DataFrame([dict(row) for row in loans_issued])
    
    # Create Excel in Memory
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        if not df_contrib.empty:
            df_contrib.to_excel(writer, sheet_name='Contributions', index=False)
        else:
            pd.DataFrame({"Message": ["No Data"]}).to_excel(writer, sheet_name='Contributions', index=False)
            
        if not df_loans.empty:
            df_loans.to_excel(writer, sheet_name='Loan Payments', index=False)
        else:
            pd.DataFrame({"Message": ["No Data"]}).to_excel(writer, sheet_name='Loan Payments', index=False)
            
        if not df_loans_issued.empty:
            df_loans_issued.to_excel(writer, sheet_name='Loans Issued', index=False)
        else:
            pd.DataFrame({"Message": ["No Data"]}).to_excel(writer, sheet_name='Loans Issued', index=False)
            
    output.seek(0)
    
    filename = f"Transactions_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return send_file(output, as_attachment=True, download_name=filename, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


# ---------- CHAT ----------
@app.route("/chat")
@login_required()
def chat():
    db = get_db()
    messages = db.execute("""
        SELECT m.content, m.timestamp, u.name, u.member_id 
        FROM messages m
        JOIN members u ON m.member_id = u.member_id
        ORDER BY m.timestamp ASC
    """).fetchall()
    db.close()
    return render_template("chat.html", messages=messages, user_id=session["user_id"], user_name=session["name"])

@app.route("/send_message", methods=["POST"])
@login_required()
def send_message():
    content = request.form.get("content")
    if content:
        db = get_db()
        db.execute("INSERT INTO messages (member_id, content) VALUES (?, ?)", (session["user_id"], content))
        db.commit()
        db.close()
    return redirect(url_for("chat"))


# ---------- AUTO-INIT CHECK ----------
def check_and_init_db():
    if not os.path.exists(DB_NAME):
        print("⚠️ Database not found. Initializing...")
        with app.app_context():
            init_db()
    else:
        # Check if tables exist
        try:
            conn = sqlite3.connect(DB_NAME)
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='members'")
            if not cursor.fetchone():
                print("⚠️ Tables missing. Initializing...")
                with app.app_context():
                    init_db()
            conn.close()
        except Exception as e:
            print(f"⚠️ Database check failed: {e}. Re-initializing...")
            with app.app_context():
                init_db()

if __name__ == "__main__":
    check_and_init_db()
    app.run(debug=True)
