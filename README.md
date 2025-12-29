# Finance Management System

A comprehensive web-based application designed to manage group finances, loans, and monthly contributions. This system provides transparency and efficiency for managing shared funds, tracking loans with dynamic EMI calculations, and facilitating member communication.

## 🚀 Features

### 👤 User & Role Management
- **Secure Authentication**: Login system with role-based access (Admin vs. Member).
- **Member Profiles**: Admins can add new members to the group.

### 💰 Contribution Management
- **Monthly Tracking**: Track monthly contributions from all members.
- **Status Updates**: Admins can mark contributions as Paid or Pending.
- **Automated Calculations**: Updates the total fund balance automatically.

### 🏦 Loan Management
- **Loan Requests**: Members can request loans directly via their dashboard.
- **Approval Workflow**: Admins can review, approve, or reject loan requests.
- **Dynamic EMI Calculation**: Uses the **Reducing Balance Method** to calculate EMIs fairly.
- **Loan Tracking**: detailed tracking of remaining balance, total interest paid, and progress.

### 🧾 Payment Proofs & Transparency
- **Proof Submission**: Members can upload screenshots/receipts for EMI or contribution payments.
- **Verification System**: Admins review and approve payment proofs.
- **Data Integrity**: Financial records are only updated upon verification.

### 💬 Communication
- **Group Chat**: Built-in chat feature for members to discuss, transparently integrated into the dashboard.

### 📊 Reporting & Analytics
- **Dashboard**: Visual summaries of Total Funds, Loans Issued, Active Loans, and Interest Earned.
- **Excel Export**: Admins can download full transaction histories and loan details for offline analysis.

## 🛠️ Tech Stack

- **Backend**: Python (Flask)
- **Database**: SQLite (Lightweight, file-based storage)
- **Frontend**: HTML5, CSS3, JavaScript (Jinja2 Templates)
- **Data Handling**: Pandas, OpenPyXL (For Excel generation)

## ⚙️ Installation & Setup

### Prerequisites
- Python 3.8 or higher installed.

### Steps

1.  **Clone the Repository** (or download the source code):
    ```bash
    git clone <repository-url>
    cd "NEW PROJECT FOR FINANCE"
    ```

2.  **Create a Virtual Environment** (Recommended):
    ```bash
    python -m venv .venv
    # Windows
    .venv\Scripts\activate
    # Mac/Linux
    source .venv/bin/activate
    ```

3.  **Install Dependencies**:
    ```bash
    pip install -r requirements.txt
    ```

4.  **Database Initialization**:
    The application checks for the database on the first run. If it doesn't exist, it will auto-initialize `database.db` with the schema and a default admin user.

## 🚀 Usage

1.  **Run the Application**:
    ```bash
    python app.py
    ```

2.  **Access the Dashboard**:
    Open your browser and navigate to: `http://127.0.0.1:5000`

3.  **Login with Default Admin Credentials**:
    *   **Username**: `admin`
    *   **Password**: `admin123`

    > **Note:** Please change the admin password or create a new admin account after the first login for security.

## 📂 Project Structure

```text
NEW PROJECT FOR FINANCE/
├── app.py                  # Main application entry point and logic
├── schema.sql              # Database schema definition
├── requirements.txt        # Python dependencies
├── database.db             # SQLite database (created on first run)
├── static/                 # CSS, JS, images, and uploads
├── templates/              # HTML templates
└── ...
```

## 🤝 Contributing
1. Fork the repository.
2. Create a feature branch (`git checkout -b feature-name`).
3. Commit your changes.
4. Push to the branch.
5. Open a Pull Request.
