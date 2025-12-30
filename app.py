import sqlite3
import pandas as pd
from flask import Flask, render_template, request, redirect, session, url_for, g, flash
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, date
import os
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = "super_secret_key"
DATABASE = 'database.db'

# File Upload Configuration
UPLOAD_FOLDER = 'static/uploads/payment_proofs'
if not os.path.exists(UPLOAD_FOLDER):
    try:
        os.makedirs(UPLOAD_FOLDER)
    except OSError:
        pass

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

def init_db():
    with app.app_context():
        db = get_db()
        with open('schema.sql', mode='r') as f:
            db.cursor().executescript(f.read())
        db.commit()
    print("Initialized the database.")

def format_currency(value):
    return f"₹{value:,.2f}"

app.jinja_env.filters['currency'] = format_currency

# --- LOGIC HELPERS ---

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

# --- ROUTES ---

@app.route("/")
def index():
    return redirect(url_for("login"))

@app.route("/init")
def init():
    init_db()
    # Create Admin if not exists
    db = get_db()
    cur = db.cursor()
    try:
        cur.execute("INSERT INTO members (name, username, password, role, join_date) VALUES (?, ?, ?, ?, ?)",
                    ("Super Admin", "admin", "admin123", "admin", datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        # Initialize Fund
        cur.execute("INSERT INTO fund (id, total_balance) VALUES (1, 20000)")
        db.commit()
        return "Database initialized. Admin user created (admin/admin123)."
    except sqlite3.IntegrityError:
        return "Database already initialized."

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        
        db = get_db()
        user = db.execute("SELECT * FROM members WHERE username = ?", (username,)).fetchone()
        
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


@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        return redirect(url_for("login"))
    
    db = get_db()
    
    # Global Stats
    fund_row = db.execute("SELECT total_balance FROM fund WHERE id = 1").fetchone()
    starting_fund = fund_row['total_balance'] if fund_row else 0
    
    total_collections = db.execute("SELECT SUM(amount) FROM monthly_contributions WHERE status = 'paid'").fetchone()[0] or 0
    total_repayments_received = db.execute("SELECT SUM(amount) FROM interest_payments WHERE status = 'paid'").fetchone()[0] or 0
    total_loans_issued = db.execute("SELECT SUM(amount) FROM loans WHERE status IN ('approved', 'paid')").fetchone()[0] or 0
    
    fund = starting_fund + total_collections + total_repayments_received - total_loans_issued
    
    # Real Interest Logic (re-calculating from raw payments for accuracy)
    # Using SQL join for efficiency
    real_interest_earned_query = """
        SELECT 
            p.amount as payment_amount, 
            p.month_no,
            l.amount as loan_amount,
            l.total_months,
            l.principal_portion,
            l.interest_rate_percent
        FROM interest_payments p
        JOIN loans l ON p.loan_id = l.loan_id
        WHERE p.status = 'paid'
    """
    payments = db.execute(real_interest_earned_query).fetchall()
    
    real_interest_earned = 0
    for p in payments:
        principal_constant = p['principal_portion']
        month_no = p['month_no']
        loan_amt = p['loan_amount']
        
        remaining_principal = loan_amt - (principal_constant * (month_no - 1))
        if remaining_principal < 0: remaining_principal = 0
        
        interest_component = (remaining_principal * p['interest_rate_percent']) / 100
        real_interest_earned += interest_component

    # Pending Principal
    active_loans_query = "SELECT * FROM loans WHERE status = 'approved' AND repayment_status='open'"
    active_loans = db.execute(active_loans_query).fetchall()
    
    total_pending_principal = 0
    for loan in active_loans:
        paid_months = db.execute("SELECT COUNT(*) FROM interest_payments WHERE loan_id = ? AND status = 'paid'", (loan['loan_id'],)).fetchone()[0]
        current_balance = loan['amount'] - (loan['principal_portion'] * paid_months)
        if current_balance < 0: current_balance = 0
        total_pending_principal += current_balance

    if session["role"] == "admin":
        active_loans_count = len(active_loans)
        closed_loans_count = db.execute("SELECT COUNT(*) FROM loans WHERE repayment_status='closed'").fetchone()[0]
        
        # Pending Contributions
        current_month = datetime.now().month
        current_year = datetime.now().year
        total_members_count = db.execute("SELECT COUNT(*) FROM members WHERE role='member'").fetchone()[0]
        paid_members_this_month = db.execute("SELECT COUNT(*) FROM monthly_contributions WHERE month=? AND year=? AND status='paid'", (current_month, current_year)).fetchone()[0]
        pending_contributions_count = total_members_count - paid_members_this_month
        if pending_contributions_count < 0: pending_contributions_count = 0
        
        # Tables Data
        loans = db.execute("SELECT l.*, m.name FROM loans l JOIN members m ON l.member_id = m.member_id ORDER BY request_time DESC").fetchall()
        contributions = db.execute("SELECT c.*, m.name FROM monthly_contributions c JOIN members m ON c.member_id = m.member_id ORDER BY year DESC, month DESC").fetchall()
        
        return render_template("dashboard_admin.html", 
                             balance=fund, 
                             total_collections=total_collections,
                             total_loans_issued=total_loans_issued,
                             total_interest=real_interest_earned,
                             total_pending_principal=total_pending_principal,
                             active_loans_count=active_loans_count,
                             closed_loans_count=closed_loans_count,
                             pending_contributions_count=pending_contributions_count,
                             members=db.execute("SELECT * FROM members WHERE role='member'").fetchall(), 
                             loans=loans, 
                             contributions=contributions)
    else:
        user_id = session["user_id"]
        
        my_loans = db.execute("SELECT * FROM loans WHERE member_id = ?", (user_id,)).fetchall()
        my_contributions = db.execute("SELECT * FROM monthly_contributions WHERE member_id = ? ORDER BY year DESC, month DESC", (user_id,)).fetchall()
        
        my_total_savings = sum(c['amount'] for c in my_contributions if c['status'] == 'paid')
        my_active_loans_amount = sum(l['amount'] for l in my_loans if l['status'] == 'approved' and l['repayment_status'] == 'open')
        
        # Loan Display Logic
        loans_display = []
        for loan in my_loans:
            loan_dict = dict(loan)
            if loan["status"] == 'approved' and loan["repayment_status"] == 'open':
                paid_months = db.execute("SELECT COUNT(*) FROM interest_payments WHERE loan_id=? AND status='paid'", (loan['loan_id'],)).fetchone()[0]
                next_month = paid_months + 1
                
                emi_calc = calculate_dynamic_emi(loan["amount"], loan["total_months"], loan["interest_rate_percent"], next_month)
                if emi_calc:
                    loan_dict["next_emi_amount"] = emi_calc["total_emi"]
                    loan_dict["next_payment_month"] = next_month
                else:
                    loan_dict["next_emi_amount"] = 0
            else:
                loan_dict["next_emi_amount"] = 0
            loans_display.append(loan_dict)
            
        return render_template("dashboard_member.html", 
                             balance=fund, 
                             my_total_savings=my_total_savings,
                             alerts=[], # Can be added back if needed
                             my_active_loans_amount=my_active_loans_amount,
                             loans=loans_display, 
                             contributions=my_contributions,
                             user_name=session["name"])


@app.route("/admin/update_fund_balance", methods=["POST"])
def update_fund_balance():
    if session.get("role") != "admin": return redirect(url_for("login"))
    try:
        amount = float(request.form.get("amount", 0))
        db = get_db()
        db.execute("UPDATE fund SET total_balance = ? WHERE id = 1", (amount,))
        db.commit()
    except Exception as e:
        print(e)
    return redirect(url_for("dashboard"))

@app.route("/add_member", methods=["POST"])
def add_member():
    if session.get("role") != "admin": return redirect(url_for("login"))
    
    name = request.form["name"]
    username = request.form["username"]
    password = request.form["password"]
    
    db = get_db()
    try:
        db.execute("INSERT INTO members (name, username, password, role, join_date) VALUES (?, ?, ?, ?, ?)",
                   (name, username, password, 'member', datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        db.commit()
    except:
        pass # Duplicate user?
        
    return redirect(url_for("dashboard"))

@app.route("/update_contribution_status", methods=["POST"])
def update_contribution_status():
    if session.get("role") != "admin": return redirect(url_for("login"))
    
    member_id = request.form["member_id"]
    month = int(request.form["month"])
    year = int(request.form["year"])
    action = request.form.get("action", "pay")
    amount = 200
    
    db = get_db()
    
    existing = db.execute("SELECT id, status FROM monthly_contributions WHERE member_id=? AND month=? AND year=?", 
                          (member_id, month, year)).fetchone()
                          
    if action == "pay":
        if not existing:
             db.execute("INSERT INTO monthly_contributions (member_id, month, year, amount, status, paid_date) VALUES (?,?,?,?,?,?)",
                        (member_id, month, year, amount, 'paid', datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        elif existing['status'] == 'pending':
             db.execute("UPDATE monthly_contributions SET status='paid', paid_date=? WHERE id=?", 
                        (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), existing['id']))
    elif action == "unpay":
         if existing:
             db.execute("UPDATE monthly_contributions SET status='pending', paid_date=NULL WHERE id=?", 
                        (existing['id'],))
                         
    db.commit()
    return redirect(url_for("contribution_tracking", year=year))

@app.route("/request_loan", methods=["GET", "POST"])
def request_loan():
    if "user_id" not in session: return redirect(url_for("login"))
    
    if request.method == "POST":
        amount = int(request.form["amount"])
        months = int(request.form["months"])
        interest_rate = 1 
        
        interest_portion = int((amount * interest_rate) / 100)
        principal_portion = int(amount / months)
        emi_amount = principal_portion + interest_portion
        
        db = get_db()
        db.execute("""INSERT INTO loans (member_id, amount, interest_rate_percent, interest_per_month, total_months, 
                                      status, repayment_status, request_time, emi_amount, principal_portion, interest_portion, remaining_balance)
                      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                   (session["user_id"], amount, interest_rate, interest_portion, months, 'pending', 'open', 
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"), emi_amount, principal_portion, interest_portion, amount))
        db.commit()
        return redirect(url_for("dashboard"))
        
    return render_template("request_loan.html", user_name=session["name"])

@app.route("/admin/loans")
def admin_loans():
    if session.get("role") != "admin": return redirect(url_for("login"))
    db = get_db()
    
    pending_loans = db.execute("SELECT l.*, m.name FROM loans l JOIN members m ON l.member_id = m.member_id WHERE l.status='pending' ORDER BY request_time").fetchall()
    
    active_loans_raw = db.execute("SELECT l.*, m.name FROM loans l JOIN members m ON l.member_id = m.member_id WHERE l.status='approved' AND l.repayment_status='open' ORDER BY approved_time DESC").fetchall()
    
    active_loans = []
    total_active_principal = 0
    
    for loan in active_loans_raw:
        l_dict = dict(loan)
        total_active_principal += loan['amount']
        
        paid_count = db.execute("SELECT COUNT(*) FROM interest_payments WHERE loan_id=? AND status='paid'", (loan['loan_id'],)).fetchone()[0]
        next_month = paid_count + 1
        l_dict['next_payment_month'] = next_month
        
        emi_calc = calculate_dynamic_emi(loan["amount"], loan["total_months"], loan["interest_rate_percent"], next_month)
        if emi_calc:
            l_dict["next_emi_amount"] = emi_calc["total_emi"]
        else:
            l_dict["next_emi_amount"] = 0
            
        active_loans.append(l_dict)
        
    interest_collected_month = 0 
    # Skipping exact month calc for brevity, can be re-added
    
    return render_template("admin_loans.html",
                         pending_count=len(pending_loans),
                         total_active_principal=total_active_principal,
                         interest_collected_month=interest_collected_month,
                         pending_loans=pending_loans,
                         active_loans=active_loans)

@app.route("/approve_loan/<int:loan_id>")
def approve_loan(loan_id):
    if session.get("role") != "admin": return redirect(url_for("login"))
    db = get_db()
    db.execute("UPDATE loans SET status='approved', repayment_status='open', approved_time=? WHERE loan_id=?", 
               (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), loan_id))
    db.commit()
    return redirect(url_for("admin_loans"))

@app.route("/reject_loan/<int:loan_id>")
def reject_loan(loan_id):
    if session.get("role") != "admin": return redirect(url_for("login"))
    db = get_db()
    db.execute("UPDATE loans SET status='rejected' WHERE loan_id=?", (loan_id,))
    db.commit()
    return redirect(url_for("admin_loans"))

@app.route("/update_interest", methods=["POST"])
def update_interest():
    if session.get("role") != "admin": return redirect(url_for("login"))
    
    loan_id = request.form["loan_id"]
    month_no = request.form["month_no"]
    amount = request.form["amount"]
    
    db = get_db()
    db.execute("INSERT INTO interest_payments (loan_id, month_no, amount, status, paid_date) VALUES (?, ?, ?, ?, ?)",
               (loan_id, month_no, amount, 'paid', datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    db.commit()
    
    return redirect(url_for("admin_loans"))

@app.route("/loan_tracking")
def loan_tracking():
    if "user_id" not in session: return redirect(url_for("login"))
    db = get_db()
    
    loans = db.execute("SELECT l.*, m.name FROM loans l JOIN members m ON l.member_id = m.member_id WHERE l.status='approved' ORDER BY l.repayment_status DESC, l.approved_time DESC").fetchall()
    
    loans_display = []
    for loan in loans:
        l_dict = dict(loan)
        
        paid_count = db.execute("SELECT COUNT(*) FROM interest_payments WHERE loan_id=? AND status='paid'", (loan['loan_id'],)).fetchone()[0]
        l_dict['months_paid'] = paid_count
        
        current_balance = loan["amount"] - (loan["principal_portion"] * paid_count)
        if current_balance < 0: current_balance = 0
        l_dict['dynamic_remaining_balance'] = current_balance
        
        if loan["repayment_status"] == 'open':
            next_month = paid_count + 1
            emi_calc = calculate_dynamic_emi(loan["amount"], loan["total_months"], loan["interest_rate_percent"], next_month)
            if emi_calc:
                l_dict["current_emi_amount"] = emi_calc["total_emi"]
                l_dict["current_interest_portion"] = emi_calc["interest_component"]
            else:
                l_dict["current_emi_amount"] = 0
                l_dict["current_interest_portion"] = 0
        else:
             l_dict["current_emi_amount"] = 0
             l_dict["current_interest_portion"] = 0
             
        loans_display.append(l_dict)
        
    return render_template("loan_tracking.html", loans=loans_display)

@app.route("/contribution_tracking")
def contribution_tracking():
    if session.get("role") != "admin": return redirect(url_for("login"))
    year = int(request.args.get("year", datetime.now().year))
    
    db = get_db()
    members = db.execute("SELECT * FROM members WHERE role='member'").fetchall()
    
    contributions = db.execute("SELECT * FROM monthly_contributions WHERE year=?", (year,)).fetchall()
    
    # Transform for matrix
    # Format: {member_id: {month: status}}
    status_map = {}
    for c in contributions:
        if c['member_id'] not in status_map: status_map[c['member_id']] = {}
        status_map[c['member_id']][c['month']] = c['status']
        
    tracking_data = []
    for m in members:
        row = {'id': m['member_id'], 'name': m['name'], 'status_by_month': {}}
        for month in range(1, 13):
            status = status_map.get(m['member_id'], {}).get(month, 'pending')
            row['status_by_month'][month] = status
        tracking_data.append(row)
        
    return render_template("contribution_tracking.html", 
                         tracking_data=tracking_data, 
                         selected_year=year,
                         current_year=datetime.now().year)

@app.route("/submit_payment_proof", methods=["GET", "POST"])
def submit_payment_proof():
    if "user_id" not in session: return redirect(url_for("login"))
    db = get_db()
    
    if request.method == "POST":
        proof_type = request.form.get("proof_type", "emi")
        
        if proof_type == "emi":
            loan_id = request.form.get("loan_id")
            month_no = request.form.get("month_no")
            amount = request.form.get("amount_emi")
        else:
            loan_id = None
            month_no = None
            amount = 200
            
        file = request.files['screenshot']
        if file and allowed_file(file.filename):
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = secure_filename(f"{session['user_id']}_{proof_type}_{timestamp}_{file.filename}")
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            
            db.execute("""INSERT INTO payment_proofs (proof_type, loan_id, member_id, month_no, amount, screenshot_path, status, submission_date) 
                          VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                       (proof_type, loan_id, session["user_id"], month_no, amount, filepath, 'pending', datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
            db.commit()
            flash("Proof submitted successfully!")
            return redirect(url_for("dashboard"))
            
    # GET
    active_loans = db.execute("SELECT * FROM loans WHERE member_id=? AND status='approved' AND repayment_status='open'", (session['user_id'],)).fetchall()
    loans_display = []
    for loan in active_loans:
        l = dict(loan)
        paid_count = db.execute("SELECT COUNT(*) FROM interest_payments WHERE loan_id=? AND status='paid'", (loan['loan_id'],)).fetchone()[0]
        next = paid_count + 1
        emi = calculate_dynamic_emi(loan['amount'], loan['total_months'], loan['interest_rate_percent'], next)
        l['next_emi_amount'] = emi['total_emi'] if emi else 0
        loans_display.append(l)

    return render_template("submit_payment_proof.html", loans=loans_display, user_name=session["name"])

@app.route("/admin/payment_proofs")
def admin_payment_proofs():
    if session.get("role") != "admin": return redirect(url_for("login"))
    db = get_db()
    
    proofs = db.execute("""SELECT p.*, m.name, l.amount as loan_amount 
                           FROM payment_proofs p 
                           JOIN members m ON p.member_id = m.member_id 
                           LEFT JOIN loans l ON p.loan_id = l.loan_id 
                           WHERE p.status='pending' ORDER BY submission_date DESC""").fetchall()
                           
    return render_template("admin_payment_proofs.html", pending_proofs=proofs)

# ---------- CHAT ----------
@app.route("/chat")
def chat():
    if "user_id" not in session: return redirect(url_for("login"))
    db = get_db()
    
    messages = db.execute("SELECT m.*, u.name FROM messages m JOIN members u ON m.member_id = u.member_id ORDER BY m.timestamp").fetchall()
    
    return render_template("chat.html", messages=messages, user_id=session["user_id"], user_name=session["name"])

@app.route("/send_message", methods=["POST"])
def send_message():
    if "user_id" not in session: return redirect(url_for("login"))
    
    content = request.form.get("content")
    if content:
        db = get_db()
        db.execute("INSERT INTO messages (member_id, content, timestamp) VALUES (?, ?, ?)",
                   (session["user_id"], content, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        db.commit()
    return redirect(url_for("chat"))

# ---------- EXPORT TRANSACTIONS ----------
import io
from flask import send_file

@app.route("/admin/export_transactions")
def export_transactions():
    if session.get("role") != "admin": return redirect(url_for("login"))
    
    db = get_db()
    
    # 1. Contributions
    contributions = db.execute("""SELECT m.name as Member, c.month as Month, c.year as Year, c.amount as Amount, 
                                  c.status as Status, c.paid_date as 'Paid Date'
                                  FROM monthly_contributions c 
                                  JOIN members m ON c.member_id = m.member_id
                                  ORDER BY c.year DESC, c.month DESC""").fetchall()
                                  
    # 2. Loan Payments
    loan_payments = db.execute("""SELECT m.name as Member, p.loan_id as 'Loan ID', p.month_no as 'Month No', 
                                  p.amount as Amount, p.status as Status, p.paid_date as 'Paid Date'
                                  FROM interest_payments p 
                                  JOIN loans l ON p.loan_id = l.loan_id
                                  JOIN members m ON l.member_id = m.member_id
                                  ORDER BY p.paid_date DESC""").fetchall()
                                  
    # 3. Loans Issued
    loans_issued = db.execute("""SELECT m.name as Member, l.loan_id as 'Loan ID', l.amount as Amount, 
                                 l.interest_rate_percent as 'Interest Rate', l.total_months as 'Total Months', 
                                 l.status as Status, l.repayment_status as 'Repayment Status', 
                                 l.request_time as 'Request Time', l.approved_time as 'Approved Time', 
                                 l.closed_time as 'Closed Time'
                                 FROM loans l 
                                 JOIN members m ON l.member_id = m.member_id
                                 ORDER BY l.request_time DESC""").fetchall()
                                 
    # Convert to DataFrames
    # Use list comprehension to convert sqlite3.Row to dict
    df_contrib = pd.DataFrame([dict(row) for row in contributions])
    df_loans = pd.DataFrame([dict(row) for row in loan_payments])
    df_loans_issued = pd.DataFrame([dict(row) for row in loans_issued])
    
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

@app.route("/admin/manage_payments")
def admin_manage_payments():
    if session.get("role") != "admin": return redirect(url_for("login"))
    db = get_db()
    
    contributions = db.execute("SELECT c.*, m.name FROM monthly_contributions c JOIN members m ON c.member_id = m.member_id ORDER BY year DESC, month DESC").fetchall()
    
    interest_payments = db.execute("SELECT p.*, m.name, l.amount as loan_amount FROM interest_payments p JOIN loans l ON p.loan_id = l.loan_id JOIN members m ON l.member_id = m.member_id ORDER BY paid_date DESC").fetchall()
    
    return render_template("admin_manage_payments.html", 
                         contributions=contributions, 
                         interest_payments=interest_payments)

@app.route("/admin/delete_contribution/<int:id>", methods=["POST"])
def delete_contribution(id):
    if session.get("role") != "admin": return redirect(url_for("login"))
    db = get_db()
    db.execute("DELETE FROM monthly_contributions WHERE id=?", (id,))
    db.commit()
    flash("✅ Contribution deleted successfully.")
    return redirect(url_for("admin_manage_payments"))

@app.route("/admin/delete_interest/<int:id>", methods=["POST"])
def delete_interest(id):
    if session.get("role") != "admin": return redirect(url_for("login"))
    db = get_db()
    db.execute("DELETE FROM interest_payments WHERE id=?", (id,))
    db.commit()
    flash("✅ Payment deleted successfully.")
    return redirect(url_for("admin_manage_payments"))

@app.route("/admin/approve_payment_proof/<int:proof_id>")
def approve_payment_proof(proof_id):
    if session.get("role") != "admin": return redirect(url_for("login"))
    db = get_db()
    proof = db.execute("SELECT * FROM payment_proofs WHERE proof_id=?", (proof_id,)).fetchone()
    
    if proof and proof['status'] == 'pending':
        if proof['proof_type'] == 'emi':
            # Add to interest payments
            db.execute("INSERT INTO interest_payments (loan_id, month_no, amount, status, paid_date) VALUES (?,?,?,?,?)",
                       (proof['loan_id'], proof['month_no'], proof['amount'], 'paid', datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        elif proof['proof_type'] == 'contribution':
            # Update/Insert contribution
             existing = db.execute("SELECT id FROM monthly_contributions WHERE member_id=? AND month=? AND year=?",
                                   (proof['member_id'], proof['month'], proof['year'])).fetchone()
             if existing:
                 db.execute("UPDATE monthly_contributions SET status='paid', paid_date=? WHERE id=?",
                            (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), existing['id']))
             else:
                 db.execute("INSERT INTO monthly_contributions (member_id, month, year, amount, status, paid_date) VALUES (?,?,?,?,?,?)",
                            (proof['member_id'], proof['month'], proof['year'], proof['amount'], 'paid', datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        
        db.execute("UPDATE payment_proofs SET status='approved', review_date=? WHERE proof_id=?", 
                   (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), proof_id))
        db.commit()
        
    return redirect(url_for("admin_payment_proofs"))

@app.route("/admin/reject_payment_proof/<int:proof_id>", methods=["POST"])
def reject_payment_proof(proof_id):
    if session.get("role") != "admin": return redirect(url_for("login"))
    admin_notes = request.form.get("admin_notes", "")
    
    db = get_db()
    db.execute("UPDATE payment_proofs SET status='rejected', review_date=?, admin_notes=? WHERE proof_id=?", 
               (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), admin_notes, proof_id))
    db.commit()
    return redirect(url_for("admin_payment_proofs"))

if __name__ == "__main__":
    app.run(debug=True)
