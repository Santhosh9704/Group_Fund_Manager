-- PostgreSQL Schema

CREATE TABLE members (
    member_id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    username TEXT UNIQUE NOT NULL,
    password TEXT NOT NULL,
    role TEXT CHECK(role IN ('admin','member')) NOT NULL,
    status TEXT DEFAULT 'active', -- active, inactive
    join_date TIMESTAMP
);

CREATE TABLE fund (
    id SERIAL PRIMARY KEY,
    total_balance INTEGER DEFAULT 0
);

CREATE TABLE loans (
    loan_id SERIAL PRIMARY KEY,
    member_id INTEGER REFERENCES members(member_id),
    amount INTEGER,
    interest_rate_percent INTEGER DEFAULT 1,
    interest_per_month INTEGER, -- Calculated as (amount * rate) / 100
    total_months INTEGER,
    status TEXT DEFAULT 'pending', -- pending, approved, rejected, paid
    repayment_status TEXT DEFAULT 'open', -- open, closed
    request_time TIMESTAMP,
    approved_time TIMESTAMP,
    closed_time TIMESTAMP,
    emi_amount INTEGER, -- Monthly EMI = principal_portion + interest_portion
    principal_portion INTEGER, -- Principal part of EMI
    interest_portion INTEGER, -- Interest part of EMI
    remaining_balance INTEGER -- Remaining principal to be paid
);

CREATE TABLE interest_payments (
    id SERIAL PRIMARY KEY,
    loan_id INTEGER REFERENCES loans(loan_id),
    month_no INTEGER, -- 1, 2, 3... relative to loan start
    amount INTEGER,
    status TEXT DEFAULT 'pending', -- pending, paid
    paid_date TIMESTAMP
);

CREATE TABLE monthly_contributions (
    id SERIAL PRIMARY KEY,
    member_id INTEGER REFERENCES members(member_id),
    month INTEGER,
    year INTEGER,
    amount INTEGER DEFAULT 200,
    status TEXT DEFAULT 'pending', -- pending, paid
    paid_date TIMESTAMP
);

CREATE TABLE payment_proofs (
    proof_id SERIAL PRIMARY KEY,
    proof_type TEXT DEFAULT 'emi', -- 'emi' or 'contribution'
    loan_id INTEGER REFERENCES loans(loan_id),
    member_id INTEGER REFERENCES members(member_id),
    month_no INTEGER, -- Installment number for EMI
    month INTEGER, -- Month (1-12) for Savings
    year INTEGER, -- Year for Savings
    amount INTEGER,
    screenshot_path TEXT,
    status TEXT DEFAULT 'pending', -- pending, approved, rejected
    submission_date TIMESTAMP,
    review_date TIMESTAMP,
    admin_notes TEXT
);

CREATE TABLE messages (
    id SERIAL PRIMARY KEY,
    member_id INTEGER REFERENCES members(member_id),
    content TEXT NOT NULL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
