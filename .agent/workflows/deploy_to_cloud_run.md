---
description: Deploy Flask App to Google Cloud Run
---

# Deploy to Google Cloud Run

This guide works for deploying your wrapper Flask application to Google Cloud Run, which is the recommended "serverless" way to host Python apps on Google Cloud.

## Prerequisites

1.  **Google Cloud Project**: You must have a created project in Google Cloud Console.
2.  **Billing Enabled**: Billing must be enabled (Cloud Run has a generous free tier).
3.  **gcloud CLI**: Installed and logged in (`gcloud auth login`).

## Steps

1.  **Initialize gcloud** (if not done):
    ```powershell
    gcloud init
    ```

2.  **Enable Services** (Run once):
    ```powershell
    gcloud services enable cloudbuild.googleapis.com run.googleapis.com
    ```

3.  **Deploy**:
    Run the following command. replace `PROJECT_ID` with your actual project ID (e.g., `my-finance-app-123`).
    ```powershell
    gcloud run deploy finance-app --source . --project PROJECT_ID --allow-unauthenticated --region us-central1
    ```
    *(Note: Follow the prompts. It might ask to create an Artifact Registry repository, say "y".)*

4.  **Verify**:
    The command will output a **Service URL** (e.g., `https://finance-app-xyz-uc.a.run.app`). Click it to view your live app.

## Important Note on Database
Your app is already configured to use the **Firestore** database of the project you deploy to.
*   The `serviceAccountKey.json` is **NOT** uploaded (it is ignored).
*   Instead, Cloud Run uses its own identity. Ensure the "Default Compute Service Account" has **Editor** or **Firestore User** role in IAM settings of your project.

## (Optional) Custom Domain
To map this to a custom domain (like `myapp.com`) or a Firebase subdomain:
1.  Go to **Firebase Console** > **Hosting**.
2.  Click **Get Started**.
3.  Run `firebase init hosting` locally (select "Use existing project").
    *   Public directory: `static` (doesn't matter much for rewrites).
    *   Single page app: No.
4.  Edit `firebase.json` to add a rewrite:
    ```json
    "rewrites": [ { "source": "**", "run": { "serviceId": "finance-app", "region": "us-central1" } } ]
    ```
5.  Run `firebase deploy`.
