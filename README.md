# Reimburse

Multi-company reimbursement tracking for teams. Employees can submit claims, admins can review them, and each company is isolated from every other company.

## Local

```bash
pip install -r requirements.txt
python import_data.py
python app.py
```

The app runs on `http://localhost:8080`.

## Vercel

This project runs on Vercel's Flask runtime using the root [`app.py`](app.py) entrypoint.

Required environment variables:

- `SECRET_KEY`: a long random string for Flask sessions
- `DATABASE_URL`: PostgreSQL connection string for production

Recommended database:

1. Create a Vercel project from this repo.
2. In the Vercel dashboard, add Postgres from the Storage tab.
3. Vercel will inject the database environment variables.
4. Set `DATABASE_URL` in the project to the Postgres connection string you want Flask/SQLAlchemy to use.
5. Set `SECRET_KEY`.
6. Deploy.

If `DATABASE_URL` is missing on Vercel, the app falls back to `/tmp/reimbursements.db`. That is only for previews or smoke testing because it is not persistent.

## Deploy CLI

```bash
vercel
vercel --prod
```
