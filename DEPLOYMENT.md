# Deployment Guide: Group Finance System

This guide explains how to deploy your Flask + SQLite application to a live website safely.

**Recommended Platform:** [PythonAnywhere](https://www.pythonanywhere.com/) (Beginner Friendly) or a **DigitalOcean Droplet** (Advanced).
**Why:** Both support **Persistent Storage**, meaning your `database.db` file will NOT be deleted when the server restarts (which happens on Cloud Run/Vercel).

---

## 🚀 Phase 1: Preparation (Done on your Laptop)

We have already:
1.  Created a `.gitignore` file (so you don't overwrite the live database with your test one).
2.  Added `gunicorn` to `requirements.txt`.
3.  Created a `backup_db.py` script to keep your data safe.

**Action:**
1.  Upload your project code to **GitHub** (create a new repository and push this code).

---

## ☁️ Phase 2: Deploying to PythonAnywhere (Step-by-Step)

This is the easiest path for "11 members, 2 years" stability.

1.  **Sign Up**: Go to [PythonAnywhere.com](https://www.pythonanywhere.com/) and create a beginner account.
2.  **Upload Code**:
    *   Open the "Consoles" tab -> "Bash".
    *   Clone your code: `git clone https://github.com/YOUR_USERNAME/YOUR_REPO_NAME.git`
3.  **Setup Virtual Environment**:
    *   Run: `cd YOUR_REPO_NAME`
    *   Run: `python3 -m venv venv`
    *   Run: `source venv/bin/activate`
    *   Run: `pip install -r requirements.txt`
4.  **Initialize Database**:
    *   Run: `python app.py` (Wait for it to say "Initialized", then press Ctrl+C to stop).
    *   *Note: This creates the `database.db` file on the server.*
5.  **Configure Web App**:
    *   Go to the "Web" tab.
    *   Click **"Add a new web app"**.
    *   Select **Manual Configuration** (NB: Do not select Flask auto-config, manual gives more control).
    *   Select **Python 3.x** (latest).
    *   **Virtualenv section**: Enter the path: `/home/yourusername/YOUR_REPO_NAME/venv`
    *   **WSGI configuration file**: Click the link to edit it. Delete everything and add:
        ```python
        import sys
        import os

        # Add your project directory to the sys.path
        project_home = '/home/yourusername/YOUR_REPO_NAME'
        if project_home not in sys.path:
            sys.path = [project_home] + sys.path

        # Import flask app but need to call it "application" for WSGI to work
        from app import app as application
        ```
6.  **Finish**: Click the **Reload** button at the top of the Web tab. Your site is live!

---

## 🛡️ Phase 3: Safety & Backups (Long-Term Storage)

Since the database is a file, if that file gets corrupted or deleted, you lose data. **You MUST backup.**

### Option A: Manual Backup (Weekly)
1.  Login to PythonAnywhere.
2.  Go to the "Files" tab.
3.  Find `database.db`.
4.  Click download. Save it on your laptop or Google Drive.

### Option B: Automated Backup (Recommended)
We created `backup_db.py`. You can make the server run this every day.

1.  On PythonAnywhere, go to the **Tasks** tab.
2.  Add a new daily task.
3.  Command: `/home/yourusername/YOUR_REPO_NAME/venv/bin/python /home/yourusername/YOUR_REPO_NAME/backup_db.py`
4.  Set the time (e.g., 03:00 AM).

**Result:** The server will create a copy of your database every day in the `backups` folder. If something breaks, you can just restore yesterday's file!

---

## ✅ Summary Checklist
- [ ] Code backed up to GitHub.
- [ ] Deployed to a server with Persistent Storage (VPS or PythonAnywhere).
- [ ] `database.db` initialized on server (not copied from local).
- [ ] Automated Backup Task configured.
- [ ] HTTPS enabled (PythonAnywhere does this button click).
