import os
import csv
import io
from datetime import datetime, timezone
import click
from dotenv import load_dotenv
load_dotenv()
from flask import Flask, render_template, request, redirect, url_for, flash, abort, Response
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from models import db, User, Company, ClaimPeriod, TravelClaim, PurchaseClaim

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')

# Ensure the data directory exists alongside the app
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
os.makedirs(DATA_DIR, exist_ok=True)

database_url = os.environ.get('DATABASE_URL', f'sqlite:///{os.path.join(DATA_DIR, "reimbursements.db")}')
# Render uses postgres:// but SQLAlchemy needs postgresql://
if database_url.startswith('postgres://'):
    database_url = database_url.replace('postgres://', 'postgresql://', 1)
app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)

login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Please log in to access this page.'
login_manager.login_message_category = 'warning'


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# ---------------------------------------------------------------------------
# CLI Commands
# ---------------------------------------------------------------------------

@app.cli.command('init-db')
def init_db_command():
    """Create all database tables."""
    db.create_all()
    click.echo('Database tables created successfully.')


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def require_admin():
    """Abort with 403 if the current user is not an admin."""
    if not current_user.is_authenticated or not current_user.is_admin:
        abort(403)


def company_scope(query):
    """Apply company_id filter scoped to the current user's company."""
    return query.filter_by(company_id=current_user.company_id)


def _claim_owned_or_admin(claim):
    """Return True if current user owns the claim or is an admin in the same company."""
    if current_user.is_admin and claim.company_id == current_user.company_id:
        return True
    return claim.user_id == current_user.id


# ---------------------------------------------------------------------------
# Error handlers
# ---------------------------------------------------------------------------

@app.errorhandler(403)
def forbidden(e):
    return render_template('errors/403.html'), 403


@app.errorhandler(404)
def not_found(e):
    return render_template('errors/404.html'), 404


# ---------------------------------------------------------------------------
# Landing / index
# ---------------------------------------------------------------------------

@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return render_template('landing.html')


# ---------------------------------------------------------------------------
# Auth routes
# ---------------------------------------------------------------------------

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        if not username or not password:
            flash('Please enter both username and password.', 'error')
            return render_template('login.html')

        user = User.query.filter_by(username=username).first()

        if user and user.check_password(password):
            login_user(user, remember=bool(request.form.get('remember')))
            next_page = request.args.get('next')
            flash(f'Welcome back, {user.full_name or user.username}!', 'success')
            return redirect(next_page or url_for('dashboard'))
        else:
            flash('Invalid username or password.', 'error')

    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        company_name = request.form.get('company_name', '').strip()
        full_name = request.form.get('full_name', '').strip()
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip() or None
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')

        # Validation
        if not company_name or not full_name or not username or not password:
            flash('Company name, full name, username, and password are required.', 'error')
            return render_template('register.html')

        if password != confirm_password:
            flash('Passwords do not match.', 'error')
            return render_template('register.html')

        if User.query.filter_by(username=username).first():
            flash(f'Username "{username}" is already taken.', 'error')
            return render_template('register.html')

        if Company.query.filter_by(name=company_name).first():
            flash(f'A company named "{company_name}" already exists.', 'error')
            return render_template('register.html')

        # Generate a unique slug
        base_slug = Company.generate_slug(company_name)
        slug = base_slug
        counter = 1
        while Company.query.filter_by(slug=slug).first():
            slug = f'{base_slug}-{counter}'
            counter += 1

        company = Company(name=company_name, slug=slug)
        db.session.add(company)
        db.session.flush()  # get company.id before committing

        user = User(
            username=username,
            full_name=full_name,
            email=email,
            role='admin',
            company_id=company.id,
        )
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        login_user(user)
        flash(f'Welcome, {full_name}! Your company "{company_name}" has been created.', 'success')
        return redirect(url_for('dashboard'))

    return render_template('register.html')


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------

@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    if request.method == 'POST':
        full_name = request.form.get('full_name', '').strip()
        email = request.form.get('email', '').strip() or None
        current_password = request.form.get('current_password', '')
        new_password = request.form.get('new_password', '')
        confirm_new_password = request.form.get('confirm_new_password', '')

        if full_name:
            current_user.full_name = full_name
        if email is not None:
            current_user.email = email

        # Password change (only if fields provided)
        if current_password or new_password or confirm_new_password:
            if not current_password:
                flash('Please enter your current password to change it.', 'error')
                return render_template('profile.html')
            if not current_user.check_password(current_password):
                flash('Current password is incorrect.', 'error')
                return render_template('profile.html')
            if not new_password:
                flash('New password cannot be empty.', 'error')
                return render_template('profile.html')
            if new_password != confirm_new_password:
                flash('New passwords do not match.', 'error')
                return render_template('profile.html')
            current_user.set_password(new_password)

        db.session.commit()
        flash('Profile updated successfully.', 'success')
        return redirect(url_for('profile'))

    return render_template('profile.html')


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@app.route('/dashboard')
@login_required
def dashboard():
    status_filter = request.args.get('status', 'all')

    if current_user.is_admin:
        query = (
            ClaimPeriod.query
            .join(User)
            .filter(User.company_id == current_user.company_id)
            .order_by(ClaimPeriod.created_at.desc())
        )
    else:
        query = (
            ClaimPeriod.query
            .filter_by(user_id=current_user.id)
            .order_by(ClaimPeriod.created_at.desc())
        )

    if status_filter in ('pending', 'paid'):
        query = query.filter(ClaimPeriod.status == status_filter)

    claim_periods = query.all()

    # Summary calculations
    if current_user.is_admin:
        all_claims = (
            ClaimPeriod.query
            .join(User)
            .filter(User.company_id == current_user.company_id)
            .all()
        )
    else:
        all_claims = ClaimPeriod.query.filter_by(user_id=current_user.id).all()

    total_claimed = sum(cp.total_amount for cp in all_claims)
    total_paid = sum(cp.total_amount for cp in all_claims if cp.status == 'paid')
    outstanding = total_claimed - total_paid

    return render_template(
        'dashboard.html',
        claim_periods=claim_periods,
        status_filter=status_filter,
        total_claimed=total_claimed,
        total_paid=total_paid,
        outstanding=outstanding,
    )


# ---------------------------------------------------------------------------
# Claim detail
# ---------------------------------------------------------------------------

@app.route('/claims/<int:claim_id>')
@login_required
def claim_detail(claim_id):
    claim = ClaimPeriod.query.get_or_404(claim_id)

    if not _claim_owned_or_admin(claim):
        flash('You do not have permission to view that claim.', 'error')
        return redirect(url_for('dashboard'))

    travel_claims = claim.travel_claims.order_by(TravelClaim.date).all()
    purchase_claims = claim.purchase_claims.order_by(PurchaseClaim.date).all()

    business_purchases = [p for p in purchase_claims if p.category == 'Business']
    personal_purchases = [p for p in purchase_claims if p.category == 'Personal']

    business_total = round(sum(p.price or 0 for p in business_purchases), 2)
    personal_total = round(sum(p.price or 0 for p in personal_purchases), 2)
    travel_total = claim.travel_total
    purchase_total = claim.purchase_total
    grand_total = claim.total_amount

    return render_template(
        'claim_detail.html',
        claim=claim,
        travel_claims=travel_claims,
        business_purchases=business_purchases,
        personal_purchases=personal_purchases,
        business_total=business_total,
        personal_total=personal_total,
        travel_total=travel_total,
        purchase_total=purchase_total,
        grand_total=grand_total,
    )


# ---------------------------------------------------------------------------
# Create claim period
# ---------------------------------------------------------------------------

@app.route('/claims/new', methods=['GET', 'POST'])
@login_required
def claims_new():
    if request.method == 'POST':
        period_name = request.form.get('period_name', '').strip()
        notes = request.form.get('notes', '').strip() or None

        if not period_name:
            flash('Period name is required.', 'error')
            return render_template('claims/new.html')

        claim = ClaimPeriod(
            user_id=current_user.id,
            company_id=current_user.company_id,
            period_name=period_name,
            notes=notes,
            status='pending',
        )
        db.session.add(claim)
        db.session.commit()
        flash(f'Claim period "{period_name}" created.', 'success')
        return redirect(url_for('claim_detail', claim_id=claim.id))

    return render_template('claims/new.html')


# ---------------------------------------------------------------------------
# Delete claim period
# ---------------------------------------------------------------------------

@app.route('/claims/<int:claim_id>/delete', methods=['POST'])
@login_required
def claims_delete(claim_id):
    claim = ClaimPeriod.query.get_or_404(claim_id)

    if not _claim_owned_or_admin(claim):
        flash('You do not have permission to delete that claim.', 'error')
        return redirect(url_for('dashboard'))

    period_name = claim.period_name
    db.session.delete(claim)  # cascades to travel/purchase claims
    db.session.commit()
    flash(f'Claim period "{period_name}" has been deleted.', 'success')
    return redirect(url_for('dashboard'))


# ---------------------------------------------------------------------------
# Travel claims
# ---------------------------------------------------------------------------

@app.route('/claims/<int:claim_id>/travel/add', methods=['POST'])
@login_required
def travel_add(claim_id):
    claim = ClaimPeriod.query.get_or_404(claim_id)

    if not _claim_owned_or_admin(claim):
        flash('You do not have permission to modify that claim.', 'error')
        return redirect(url_for('dashboard'))

    date_str = request.form.get('date', '').strip()
    origin = request.form.get('origin', '').strip()
    destination = request.form.get('destination', '').strip()
    purpose = request.form.get('purpose', '').strip()
    trip_type = request.form.get('trip_type', '').strip()

    try:
        toll_cost = float(request.form.get('toll_cost', 0) or 0)
    except ValueError:
        toll_cost = 0.0

    try:
        distance_km = float(request.form.get('distance_km', 0) or 0)
    except ValueError:
        distance_km = 0.0

    # Parse date
    travel_date = None
    if date_str:
        try:
            travel_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            flash('Invalid date format. Use YYYY-MM-DD.', 'error')
            return redirect(url_for('claim_detail', claim_id=claim_id))

    # Calculate mileage cost using company rate
    company = claim.company
    rate = (company.mileage_rate if company and company.mileage_rate is not None else 0.88)
    mileage_cost = round(distance_km * rate, 2)

    travel = TravelClaim(
        claim_period_id=claim.id,
        date=travel_date,
        origin=origin,
        destination=destination,
        purpose=purpose,
        trip_type=trip_type,
        toll_cost=toll_cost,
        distance_km=distance_km,
        mileage_cost=mileage_cost,
    )
    db.session.add(travel)
    db.session.commit()
    flash('Travel claim added.', 'success')
    return redirect(url_for('claim_detail', claim_id=claim_id))


@app.route('/claims/<int:claim_id>/travel/<int:travel_id>/delete', methods=['POST'])
@login_required
def travel_delete(claim_id, travel_id):
    claim = ClaimPeriod.query.get_or_404(claim_id)
    travel = TravelClaim.query.get_or_404(travel_id)

    if travel.claim_period_id != claim.id:
        abort(404)

    if not _claim_owned_or_admin(claim):
        flash('You do not have permission to modify that claim.', 'error')
        return redirect(url_for('dashboard'))

    db.session.delete(travel)
    db.session.commit()
    flash('Travel claim removed.', 'success')
    return redirect(url_for('claim_detail', claim_id=claim_id))


# ---------------------------------------------------------------------------
# Purchase claims
# ---------------------------------------------------------------------------

@app.route('/claims/<int:claim_id>/purchase/add', methods=['POST'])
@login_required
def purchase_add(claim_id):
    claim = ClaimPeriod.query.get_or_404(claim_id)

    if not _claim_owned_or_admin(claim):
        flash('You do not have permission to modify that claim.', 'error')
        return redirect(url_for('dashboard'))

    date_str = request.form.get('date', '').strip()
    item = request.form.get('item', '').strip()
    purchased_from = request.form.get('purchased_from', '').strip()
    purpose = request.form.get('purpose', '').strip()
    category = request.form.get('category', 'Business')
    has_receipt = bool(request.form.get('has_receipt'))

    if category not in ('Business', 'Personal'):
        category = 'Business'

    try:
        price = float(request.form.get('price', 0) or 0)
    except ValueError:
        price = 0.0

    purchase_date = None
    if date_str:
        try:
            purchase_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            flash('Invalid date format. Use YYYY-MM-DD.', 'error')
            return redirect(url_for('claim_detail', claim_id=claim_id))

    purchase = PurchaseClaim(
        claim_period_id=claim.id,
        date=purchase_date,
        item=item,
        purchased_from=purchased_from,
        purpose=purpose,
        price=price,
        has_receipt=has_receipt,
        category=category,
    )
    db.session.add(purchase)
    db.session.commit()
    flash('Purchase claim added.', 'success')
    return redirect(url_for('claim_detail', claim_id=claim_id))


@app.route('/claims/<int:claim_id>/purchase/<int:purchase_id>/delete', methods=['POST'])
@login_required
def purchase_delete(claim_id, purchase_id):
    claim = ClaimPeriod.query.get_or_404(claim_id)
    purchase = PurchaseClaim.query.get_or_404(purchase_id)

    if purchase.claim_period_id != claim.id:
        abort(404)

    if not _claim_owned_or_admin(claim):
        flash('You do not have permission to modify that claim.', 'error')
        return redirect(url_for('dashboard'))

    db.session.delete(purchase)
    db.session.commit()
    flash('Purchase claim removed.', 'success')
    return redirect(url_for('claim_detail', claim_id=claim_id))


# ---------------------------------------------------------------------------
# Export CSV
# ---------------------------------------------------------------------------

@app.route('/claims/<int:claim_id>/export.csv')
@login_required
def claims_export_csv(claim_id):
    claim = ClaimPeriod.query.get_or_404(claim_id)

    if not _claim_owned_or_admin(claim):
        flash('You do not have permission to export that claim.', 'error')
        return redirect(url_for('dashboard'))

    travel_claims = claim.travel_claims.order_by(TravelClaim.date).all()
    purchase_claims = claim.purchase_claims.order_by(PurchaseClaim.date).all()

    output = io.StringIO()
    writer = csv.writer(output)

    # Header
    writer.writerow(['Type', 'Date', 'Description', 'From/Item', 'To/Store',
                     'Purpose', 'Amount', 'Category', 'Receipt'])

    for tc in travel_claims:
        amount = round((tc.mileage_cost or 0) + (tc.toll_cost or 0), 2)
        writer.writerow([
            'Travel',
            tc.date.isoformat() if tc.date else '',
            tc.trip_type or '',
            tc.origin or '',
            tc.destination or '',
            tc.purpose or '',
            f'{amount:.2f}',
            '',
            '',
        ])

    for pc in purchase_claims:
        writer.writerow([
            'Purchase',
            pc.date.isoformat() if pc.date else '',
            pc.item or '',
            pc.item or '',
            pc.purchased_from or '',
            pc.purpose or '',
            f'{pc.price:.2f}' if pc.price is not None else '0.00',
            pc.category or '',
            'Yes' if pc.has_receipt else 'No',
        ])

    csv_data = output.getvalue()
    output.close()

    username = claim.user.username if claim.user else 'unknown'
    safe_period = claim.period_name.replace(' ', '_').replace('/', '-')
    filename = f'claim_{safe_period}_{username}.csv'

    return Response(
        csv_data,
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename="{filename}"'},
    )


# ---------------------------------------------------------------------------
# Admin: update claim status
# ---------------------------------------------------------------------------

@app.route('/admin/claims/<int:claim_id>/status', methods=['POST'])
@login_required
def update_claim_status(claim_id):
    require_admin()
    claim = ClaimPeriod.query.get_or_404(claim_id)

    # Company isolation: admin can only update claims from their company
    if claim.company_id != current_user.company_id:
        abort(403)

    new_status = request.form.get('status')
    if new_status in ('pending', 'paid'):
        claim.status = new_status
        if new_status == 'paid' and not claim.paid_at:
            claim.paid_at = datetime.now(timezone.utc)
        elif new_status == 'pending':
            claim.paid_at = None
        db.session.commit()
        flash(f'Claim "{claim.period_name}" marked as {new_status}.', 'success')
    else:
        flash('Invalid status value.', 'error')

    next_page = request.form.get('next') or url_for('dashboard')
    return redirect(next_page)


# ---------------------------------------------------------------------------
# Admin: company settings
# ---------------------------------------------------------------------------

@app.route('/admin/company', methods=['GET', 'POST'])
@login_required
def admin_company():
    require_admin()
    company = Company.query.get_or_404(current_user.company_id)

    if request.method == 'POST':
        company_name = request.form.get('company_name', '').strip()
        mileage_rate_str = request.form.get('mileage_rate', '').strip()

        if company_name and company_name != company.name:
            # Check uniqueness
            existing = Company.query.filter_by(name=company_name).first()
            if existing and existing.id != company.id:
                flash(f'Company name "{company_name}" is already taken.', 'error')
                return render_template('admin/company.html', company=company)
            company.name = company_name
            company.slug = Company.generate_slug(company_name)

        if mileage_rate_str:
            try:
                company.mileage_rate = float(mileage_rate_str)
            except ValueError:
                flash('Invalid mileage rate. Please enter a number.', 'error')
                return render_template('admin/company.html', company=company)

        db.session.commit()
        flash('Company settings saved.', 'success')
        return redirect(url_for('admin_company'))

    return render_template('admin/company.html', company=company)


# ---------------------------------------------------------------------------
# Admin: users
# ---------------------------------------------------------------------------

@app.route('/admin/users')
@login_required
def admin_users():
    require_admin()

    users = User.query.filter_by(company_id=current_user.company_id).order_by(User.created_at).all()
    companies = Company.query.order_by(Company.name).all()

    user_stats = []
    for u in users:
        claims = ClaimPeriod.query.filter_by(user_id=u.id).all()
        total = sum(c.total_amount for c in claims)
        paid = sum(c.total_amount for c in claims if c.status == 'paid')
        user_stats.append({
            'user': u,
            'claim_count': len(claims),
            'total': total,
            'paid': paid,
            'outstanding': total - paid,
        })

    return render_template('admin/users.html', user_stats=user_stats, companies=companies)


@app.route('/admin/users/add', methods=['POST'])
@login_required
def admin_users_add():
    require_admin()

    username = request.form.get('username', '').strip()
    full_name = request.form.get('full_name', '').strip()
    email = request.form.get('email', '').strip() or None
    password = request.form.get('password', '')
    role = request.form.get('role', 'user')

    if not username or not password:
        flash('Username and password are required.', 'error')
        return redirect(url_for('admin_users'))

    if role not in ('admin', 'user'):
        flash('Invalid role specified.', 'error')
        return redirect(url_for('admin_users'))

    if User.query.filter_by(username=username).first():
        flash(f'Username "{username}" is already taken.', 'error')
        return redirect(url_for('admin_users'))

    new_user = User(
        username=username,
        full_name=full_name or username,
        email=email,
        role=role,
        company_id=current_user.company_id,  # always scoped to current admin's company
    )
    new_user.set_password(password)

    db.session.add(new_user)
    db.session.commit()
    flash(f'User "{username}" created successfully.', 'success')
    return redirect(url_for('admin_users'))


@app.route('/admin/users/<int:user_id>/delete', methods=['POST'])
@login_required
def admin_users_delete(user_id):
    require_admin()

    user = User.query.get_or_404(user_id)

    # Company isolation: admin can only delete users in their own company
    if user.company_id != current_user.company_id:
        abort(403)

    if user.id == current_user.id:
        flash('You cannot delete your own account.', 'error')
        return redirect(url_for('admin_users'))

    ClaimPeriod.query.filter_by(user_id=user.id).delete()
    db.session.delete(user)
    db.session.commit()
    flash(f'User "{user.username}" and all their claims have been deleted.', 'success')
    return redirect(url_for('admin_users'))


# ---------------------------------------------------------------------------
# Admin: overview
# ---------------------------------------------------------------------------

@app.route('/admin/overview')
@login_required
def admin_overview():
    require_admin()

    users = (
        User.query
        .filter_by(role='user', company_id=current_user.company_id)
        .order_by(User.full_name)
        .all()
    )

    overview = []
    for u in users:
        claims = ClaimPeriod.query.filter_by(user_id=u.id).order_by(ClaimPeriod.created_at).all()
        total = sum(c.total_amount for c in claims)
        paid = sum(c.total_amount for c in claims if c.status == 'paid')
        overview.append({
            'user': u,
            'claims': claims,
            'total': total,
            'paid': paid,
            'outstanding': total - paid,
            'claim_count': len(claims),
            'pending_count': sum(1 for c in claims if c.status == 'pending'),
        })

    grand_total = sum(o['total'] for o in overview)
    grand_paid = sum(o['paid'] for o in overview)
    grand_outstanding = grand_total - grand_paid

    return render_template(
        'admin/overview.html',
        overview=overview,
        grand_total=grand_total,
        grand_paid=grand_paid,
        grand_outstanding=grand_outstanding,
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(debug=os.environ.get('FLASK_ENV') != 'production', host='0.0.0.0', port=port)
