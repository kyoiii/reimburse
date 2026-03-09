# Reimbursement Management Web App — Build Spec

## Overview
A multi-user, multi-company reimbursement management web app.
- Admins can view ALL users' reimbursements
- Regular users can only view THEIR OWN reimbursements
- Clean, intuitive, modern UI

## Tech Stack
- **Backend**: Python Flask + SQLite (single file DB at `data/reimbursements.db`)
- **Frontend**: Jinja2 templates + Tailwind CSS (CDN) + vanilla JS
- **Auth**: Flask-Login with session-based auth, bcrypt for passwords
- **Excel import**: openpyxl

## Project Structure
```
reimbursement/
├── app.py                  # Main Flask app, routes, auth
├── models.py               # SQLAlchemy models
├── import_data.py          # Excel importer script
├── requirements.txt
├── templates/
│   ├── base.html           # Base template with nav
│   ├── login.html
│   ├── dashboard.html      # Main view
│   ├── claim_detail.html   # Individual claim detail
│   └── admin/
│       ├── users.html      # Admin: manage users
│       └── overview.html   # Admin: all claims overview
├── static/
│   └── style.css           # Minimal custom CSS
├── data/
│   └── reimbursements.db   # SQLite DB (auto-created)
├── "Theresa Reimbursement_To 19 May 2025.xlsx"
└── "Tony Claim_To 16 Dec 2025.xlsx"
```

## Database Models

### Company
- id, name, created_at

### User
- id, username, password_hash, role (admin/user), company_id, full_name, created_at

### ClaimPeriod
- id, user_id, company_id, period_name (e.g. "July 2022"), status (pending/paid), created_at

### TravelClaim
- id, claim_period_id, date, origin, destination, purpose, trip_type, toll_cost, distance_km, mileage_cost

### PurchaseClaim
- id, claim_period_id, date, item, purchased_from, purpose, price, has_receipt, category (Business/Personal)

## Seeded Data (from Excel files)
Import both Excel files to populate the database:

### From "Theresa Reimbursement_To 19 May 2025.xlsx"
- User: theresa / password123 (role: user)
- Full name: Theresa Xu (Tongdu Xu)
- Company: Tivoli International (Aust) Pty Ltd
- Two sheets: "To 18 Sep 2025" and "To 18 May 2025 Paid"

### From "Tony Claim_To 16 Dec 2025.xlsx"
- User: tony / password123 (role: user)
- Full name: Tony
- Company: Tivoli International (Aust) Pty Ltd
- Multiple sheets: July-Paid, August-Paid, September-Paid, Nov, Oct, Nov 24 - Apr 2025-Paid, May 2025-23 June 2025-Paid, 24 June 2025-13 Oct 2025_Paid, 14 Oct 2025-18 Dec 2025

### Admin account
- username: admin / password: admin123 (role: admin)
- Company: Tivoli International (Aust) Pty Ltd

## Excel Parsing Notes

### Theresa's file structure (per sheet):
- Row 1: Company name
- Row 3: "Part 1: Vehicle travel claims..."
- Row 5: Employee name in col C
- Row 8: Headers: Date, From, To, Purpose, Type of Trip, Toll Cost, Distance (km), Mileage Cost
- Row 9 onwards: travel claim rows until "Sub total" row
- Row 27: "Part 2: Claims for purchased items..."
- Row 30: Headers: Date, Purchased From, Items, Purpose, Price, Receipt
- Row 31 onwards: purchase rows until summary rows
- Sheet name contains "Paid" = status is "paid", otherwise "pending"

### Tony's file structure (per sheet):
- Similar structure to Theresa
- Row 8: Date, Origin, Destination, Purpose, Type of Trip, Toll Cost, Distance (km)
- Row 18: Date, Item(s), Purchased From, Purpose, Price, Receipt
- Sheet name contains "Paid" = status is "paid"

## Routes
- GET /                    → redirect to /dashboard or /login
- GET /login               → login form
- POST /login              → authenticate
- GET /logout              → logout
- GET /dashboard           → show claims (admin: all users; user: own only)
- GET /claims/<id>         → claim period detail (travel + purchases)
- GET /admin/users         → admin only: manage users
- POST /admin/users/add    → admin only: add user
- GET /admin/overview      → admin: summary stats per user

## UI Design
- Use Tailwind CSS via CDN for styling
- Clean white background, subtle shadows
- Color scheme: indigo/violet for primary actions
- Dashboard shows cards/table of claim periods with:
  - Period name, employee (admin only), total amount, status badge (paid=green, pending=yellow)
  - Click to view detail
- Detail page shows:
  - Part 1: Travel claims table (date, from, to, purpose, distance, cost)
  - Part 2: Purchases table (date, item, from, purpose, price, receipt)
  - Summary totals
- Admin overview: table of all users with total claimed, total paid, outstanding
- Responsive, mobile-friendly

## Running the App
```bash
pip install -r requirements.txt
python import_data.py    # Import Excel data (run once)
python app.py            # Start on http://localhost:5000
```

## Security
- Passwords hashed with bcrypt
- Non-admin users are redirected if they try to access other users' data
- Flash messages for errors/success
