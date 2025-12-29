PRAGMA foreign_keys = ON;

CREATE TABLE members (
    member_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    username TEXT UNIQUE NOT NULL,
    password TEXT NOT NULL,
    role TEXT CHECK(role IN ('admin','member')) NOT NULL,
    status TEXT DEFAULT 'active', -- active, inactive
    join_date TEXT
);

CREATE TABLE fund (
    id INTEGER PRIMARY KEY,
    total_balance INTEGER DEFAULT 0
);

CREATE TABLE loans (
    loan_id INTEGER PRIMARY KEY AUTOINCREMENT,
    member_id INTEGER,
    amount INTEGER,
    interest_rate_percent INTEGER DEFAULT 1,
    interest_per_month INTEGER, -- Calculated as (amount * rate) / 100
    total_months INTEGER,
    status TEXT DEFAULT 'pending', -- pending, approved, rejected, paid
    repayment_status TEXT DEFAULT 'open', -- open, closed
    request_time TEXT,
    approved_time TEXT,
    closed_time TEXT,
    emi_amount INTEGER, -- Monthly EMI = principal_portion + interest_portion
    principal_portion INTEGER, -- Principal part of EMI
    interest_portion INTEGER, -- Interest part of EMI
    remaining_balance INTEGER, -- Remaining principal to be paid
    FOREIGN KEY(member_id) REFERENCES members(member_id)
);

CREATE TABLE interest_payments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    loan_id INTEGER,
    month_no INTEGER, -- 1, 2, 3... relative to loan start
    amount INTEGER,
    status TEXT DEFAULT 'pending', -- pending, paid
    paid_date TEXT,
    FOREIGN KEY(loan_id) REFERENCES loans(loan_id)
);

CREATE TABLE monthly_contributions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    member_id INTEGER,
    month INTEGER,
    year INTEGER,
    amount INTEGER DEFAULT 200,
    status TEXT DEFAULT 'pending', -- pending, paid
    paid_date TEXT,
    FOREIGN KEY(member_id) REFERENCES members(member_id)
);

CREATE TABLE payment_proofs (
    proof_id INTEGER PRIMARY KEY AUTOINCREMENT,
    proof_type TEXT DEFAULT 'emi', -- 'emi' or 'contribution'
    loan_id INTEGER,
    member_id INTEGER,
    month_no INTEGER, -- Installment number for EMI
    month INTEGER, -- Month (1-12) for Savings
    year INTEGER, -- Year for Savings
    amount INTEGER,
    screenshot_path TEXT,
    status TEXT DEFAULT 'pending', -- pending, approved, rejected
    submission_date TEXT,
    review_date TEXT,
    admin_notes TEXT,
    FOREIGN KEY(member_id) REFERENCES members(member_id)
);

CREATE TABLE messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    member_id INTEGER,
    content TEXT NOT NULL,
    timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(member_id) REFERENCES members(member_id)
);
