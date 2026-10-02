# Bloom — Google Drive & Google Sheets Integration Setup Guide

This document provides a comprehensive, step-by-step setup and operational guide for the **Bloom School ID Card Verification, Editing & Correction System** integration with Google Drive and Google Sheets.

---

## A. Google Cloud Project Setup

### 1. Create or Select a Project
1. Navigate to the [Google Cloud Console](https://console.cloud.google.com/).
2. In the top project dropdown, click **New Project**.
3. Name your project (e.g., `bloom-id-card-production` or `bloom-id-card-dev`).
4. Click **Create** and ensure the newly created project is selected in the project dropdown.

### 2. Enable Required APIs
Bloom uses only the minimal set of APIs required for Drive file operations and Sheets synchronization.

1. In the Google Cloud Console, open the navigation menu (`☰`) and go to **APIs & Services > Library**.
2. Search for and enable the following APIs:
   - **Google Drive API** (`drive.googleapis.com`):
     - *Why required*: Used by Bloom to traverse school/class folders, fetch ID card JPG previews, physically move cards marked for correction into `Correction Needed/{Class}/`, and store replacement photo uploads in `Correction Needed/{Class}/replacements/`.
   - **Google Sheets API** (`sheets.googleapis.com`):
     - *Why required*: Used by Bloom to maintain real-time correction logs, create school-specific spreadsheets, write header rows, and append/update correction entries dynamically.

> **Note**: Do *not* enable unnecessary APIs (such as Google Picker API or Gmail API) to adhere to the principle of least privilege.

---

## B. Authentication Method

### Why Service Account Authentication is Used
Bloom utilizes **Google Service Account** authentication:
1. **Server-to-Server Workflows**: ID card indexing, image streaming, file moves, and spreadsheet synchronization happen autonomously in backend background tasks without requiring end-user OAuth login prompts from school staff.
2. **Deterministic Ownership & Permissions**: Files and folders reside in an organization-owned master Google Drive directory (`ID Card Photos/`). The Service Account is granted granular `Editor` access solely to that specific folder hierarchy.
3. **Multi-School Isolation**: Authentication is handled entirely server-side. School administrators never receive OAuth tokens or direct cloud credentials; all requests are authenticated through Bloom's session-based role system (`school_admin` and `bloom_admin`).

---

## C. Service Account Setup & Key Management

### 1. Create the Service Account
1. In the Google Cloud Console, navigate to **IAM & Admin > Service Accounts**.
2. Click **+ Create Service Account**.
3. Fill in the details:
   - **Service account name**: `bloom-drive-sync`
   - **Service account ID**: `bloom-drive-sync`
   - **Description**: `Backend service account for Bloom ID Card Drive & Sheets integration`
4. Click **Create and Continue**.
5. Granting project-level roles is **NOT** required because permissions will be granted directly on the target Google Drive folder. Click **Continue**, then **Done**.
6. Note down the **Service Account Email** (e.g., `bloom-drive-sync@bloom-id-card-production.iam.gserviceaccount.com`).

### 2. Generate and Download JSON Key
1. In the Service Accounts list, click on the newly created service account.
2. Go to the **Keys** tab.
3. Click **Add Key > Create new key**.
4. Select **JSON** format and click **Create**.
5. The private key JSON file will be downloaded to your computer.

### 3. Secure Storage of Credentials
> ⚠️ **CRITICAL SECURITY RULES**:
> - **NEVER** commit service account JSON files to Git repositories.
> - **NEVER** expose service account private keys to client-side code / frontend browsers.
> - Store the JSON file outside the workspace root or in a secured secrets directory ignored by Git (e.g., `~/.bloom/credentials/google-service-account.json`).

---

## D. Drive Folder Permissions & Master Folder

### 1. Create the Master Folder
1. In your organization's Google Drive (or administrator Google Drive), create a top-level master folder:
   ```text
   ID Card Photos/
   ```

### 2. Share with the Service Account
1. Right-click on the `ID Card Photos/` folder and select **Share**.
2. Paste the **Service Account Email** (`bloom-drive-sync@...iam.gserviceaccount.com`).
3. Set the role to **Editor** (allows creating subfolders, moving files into `Correction Needed`, and updating spreadsheets).
4. Uncheck *Notify people* and click **Share**.

---

## E. Initial Drive Folder Structure

Bloom expects or automatically manages the following folder hierarchy inside `ID Card Photos/`:

```text
ID Card Photos/
│
├── Greenfield Public School/
│   ├── Grade 10-A/
│   │   ├── STU001.jpg            <-- Complete generated ID-card JPG
│   │   ├── STU002.jpg
│   │   └── Grade_10A.xlsx        <-- Optional source student roster
│   │
│   ├── Grade 10-B/
│   │   ├── STU101.jpg
│   │   └── STU102.jpg
│   │
│   └── Correction Needed/
│       ├── Grade 10-A/
│       │   ├── STU002.jpg        <-- Moved automatically when corrected
│       │   └── replacements/
│       │       └── STU002_photo_20261003_120000.jpg
│       │
│       └── Grade 10-B/
│           └── ...
│
└── St. Mary's Academy/
    ├── Class 5-A/
    └── Correction Needed/
```

### Folder Discovery and Auto-Creation
- **Class Folders**: Offline Photoshop artists upload generated card JPGs into `ID Card Photos/{School}/{Class}/`.
- **Correction Folders**: When a school marks an ID card for correction, Bloom **automatically and idempotently** creates `ID Card Photos/{School}/Correction Needed/{Class}/` and moves the original JPG there.

---

## F. School & Class Drive Mapping

### 1. Deterministic Filename Matching
Bloom bridges student roster records with generated ID card images using **case-insensitive filename stem matching**:

```text
Student Roster Record: File Name = "STU001.PNG"
               ↓
Stem Extraction: "STU001"
               ↓
Drive Search in Class Folder: "stu001.jpg" / "STU001.JPG"
               ↓
Matched: ID Card Photo preview loaded
```

### 2. Drive Folder ID Caching
Bloom records Google Drive Folder IDs in the database/metadata cache during initial folder indexing (`/admin/schools/{school_id}/id-cards/index-drive`):
- `drive_folder_id`: Master folder ID for the school.
- `class_folder_ids`: Dictionary mapping class names to Google Drive folder IDs.
- `correction_folder_id`: Google Drive folder ID for `Correction Needed/`.

---

## G. Google Sheets Setup & Real-time Sync

### 1. Automated Sheet Lifecycle
- When the first correction is submitted for a school, Bloom automatically creates a dedicated Google Sheet named:
  ```text
  {School Name} — ID Card Corrections
  ```
- The spreadsheet ID is stored in the school configuration (`correction_sheet_id`).
- All subsequent corrections from any class are upserted into this centralized spreadsheet in real time.

### 2. Sheet Column Structure
Bloom writes the following dynamic columns based on the school's configured fields:

| Column | Description | Example |
| :--- | :--- | :--- |
| **Correction ID** | Unique UUID of the correction record | `c48f29ab-76f9-4d22` |
| **Class** | Class/division name | `Grade 10-A` |
| **File Name** | Image filename stem / identifier | `STU001` |
| **Student Name** | Corrected or original student name | `Aarav Sharma` |
| **GR Number** | General Register Number | `GR-10492` |
| **Standard** | Standard / Grade | `10-A` |
| **Phone Number** | Contact number | `+91 98765 43210` |
| **Address** | Residential address | `42 Park Avenue, Mumbai` |
| **Date of Birth** | DOB in YYYY-MM-DD format | `2008-05-14` |
| *[Custom Fields]* | Any admin-configured custom fields | `Bus Route: Route 4` |
| **Photo Wrong** | Boolean flag indicating incorrect photo | `YES` / `NO` |
| **Replacement Photo** | Filename of uploaded replacement photo | `STU001_photo_20261003.jpg` |
| **Correction Timestamp** | Timestamp in IST (YYYY-MM-DD HH:MM:SS) | `2026-10-03 14:30:00` |
| **Status** | Verification status | `CORRECTION_NEEDED` |

---

## H. Configuration & Environment Variables

Configure the following environment variables in your `.env` file or production deployment configuration:

| Variable | Required | Description | Example |
| :--- | :--- | :--- | :--- |
| `GOOGLE_CREDENTIALS_PATH` | Optional | Absolute path to the Service Account JSON key file. | `/etc/bloom/secrets/google-sa.json` |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | Optional | Raw JSON string containing service account credentials (useful for cloud secret managers). | `{"type": "service_account", ...}` |
| `GOOGLE_DRIVE_MASTER_FOLDER_ID` | Optional | Google Drive folder ID of the master `ID Card Photos/` folder. | `1A2b3C4d5E6f7G8h9I0j` |
| `BLOOM_DRIVE_LOCAL_ROOT` | Optional | Local file system root directory used as a seamless fallback during offline development. | `/Users/dhruv/arrent/bloom/id_card_photos` |

---

## I. Local Development vs Production Guide

### Mode 1: Local Development (Filesystem Mock / Fallback)
For offline development or UI testing without Google Cloud credentials:
1. Create a local folder structure:
   ```bash
   mkdir -p ./data/id_card_photos/"Demo School"/"Class 10A"
   cp sample.jpg ./data/id_card_photos/"Demo School"/"Class 10A"/STU001.jpg
   ```
2. Set `BLOOM_DRIVE_LOCAL_ROOT=./data/id_card_photos` in `.env`.
3. Bloom's `GoogleDriveService` automatically operates in local fallback mode, simulating Google Drive moves and storage.

### Mode 2: Full Google Cloud Integration
1. Place your downloaded service account JSON at `~/.bloom/google-sa.json`.
2. Add to `.env`:
   ```bash
   GOOGLE_CREDENTIALS_PATH=/Users/username/.bloom/google-sa.json
   GOOGLE_DRIVE_MASTER_FOLDER_ID=your_master_folder_id_here
   ```
3. Restart the Bloom application.

---

## J. Verification & Diagnostics

Run the automated integration test suite to verify Google Drive and Sheets service operations:

```bash
# Run all ID card verification tests
pytest tests/test_id_card_verification.py tests/test_id_card_routes.py -v
```

To verify Google Drive indexing on a live school:
1. Log in to Bloom Admin at `/admin/login`.
2. Navigate to **ID Cards > Schools > [Select School] > Overview**.
3. Click **Sync Google Drive**.
4. Verify that class folders and student card counts are detected and listed.

---

## K. Common Failure Modes & Troubleshooting

| Issue / Symptom | Root Cause | Solution |
| :--- | :--- | :--- |
| `404 File Not Found` when moving JPG | Target JPG does not exist in class folder or was already moved. | The system handles moves idempotently. Check if the card is already in `Correction Needed/{Class}/`. |
| `403 Access Denied` on Google Drive API | Service account email is not added as **Editor** to `ID Card Photos/`. | Share the master folder with `service-account@project.iam.gserviceaccount.com` as Editor. |
| Student image preview not loading | Filename mismatch between Excel roster and Drive JPG. | Ensure the filename stem matches (e.g. `ABC123.png` in roster and `ABC123.jpg` on Drive). |
| Excel export encoding error | Special unicode characters in HTTP header filename. | Bloom automatically formats export filenames with ASCII hyphens (`-`). |

---

## L. Security Checklist

- [x] Service Account credentials are kept outside the source repository.
- [x] No service account keys are exposed to the frontend or school portal.
- [x] Google Drive permissions are restricted to the `ID Card Photos/` folder only.
- [x] Multi-school isolation is enforced at the database and route authorization layer.
- [x] School editing permissions are strictly locked when the correction window closes.
