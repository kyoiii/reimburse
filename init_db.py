from app import app, ensure_database_initialized

with app.app_context():
    ensure_database_initialized(force=True)
    print("Database tables created.")
