import re
from datetime import datetime, timezone
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
import bcrypt

db = SQLAlchemy()


class Company(db.Model):
    __tablename__ = 'companies'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False, unique=True)
    mileage_rate = db.Column(db.Float, default=0.88)
    slug = db.Column(db.String(100), unique=True, nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    users = db.relationship('User', back_populates='company', lazy='dynamic')
    claim_periods = db.relationship('ClaimPeriod', back_populates='company', lazy='dynamic')

    @staticmethod
    def generate_slug(name: str) -> str:
        """Lowercase the name and replace spaces/special chars with hyphens."""
        slug = name.lower()
        slug = re.sub(r'[^a-z0-9]+', '-', slug)
        slug = slug.strip('-')
        return slug

    def __repr__(self):
        return f'<Company {self.name}>'


class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), nullable=False, unique=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='user')  # 'admin' or 'user'
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=True)
    full_name = db.Column(db.String(150), nullable=True)
    email = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    company = db.relationship('Company', back_populates='users')
    claim_periods = db.relationship('ClaimPeriod', back_populates='user', lazy='dynamic')

    def set_password(self, password: str) -> None:
        """Hash and store the password using bcrypt."""
        password_bytes = password.encode('utf-8')
        salt = bcrypt.gensalt()
        self.password_hash = bcrypt.hashpw(password_bytes, salt).decode('utf-8')

    def check_password(self, password: str) -> bool:
        """Verify a plaintext password against the stored hash."""
        try:
            return bcrypt.checkpw(
                password.encode('utf-8'),
                self.password_hash.encode('utf-8')
            )
        except Exception:
            return False

    @property
    def is_admin(self) -> bool:
        return self.role == 'admin'

    def __repr__(self):
        return f'<User {self.username} ({self.role})>'


class ClaimPeriod(db.Model):
    __tablename__ = 'claim_periods'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False)
    period_name = db.Column(db.String(100), nullable=False)
    status = db.Column(db.String(20), nullable=False, default='pending')  # 'pending' or 'paid'
    notes = db.Column(db.Text, nullable=True)
    submitted_at = db.Column(db.DateTime, nullable=True)
    paid_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    user = db.relationship('User', back_populates='claim_periods')
    company = db.relationship('Company', back_populates='claim_periods')
    travel_claims = db.relationship('TravelClaim', back_populates='claim_period',
                                    cascade='all, delete-orphan', lazy='dynamic')
    purchase_claims = db.relationship('PurchaseClaim', back_populates='claim_period',
                                      cascade='all, delete-orphan', lazy='dynamic')

    @property
    def total_amount(self) -> float:
        """Sum of all travel mileage + toll costs and all purchase prices."""
        travel_total = sum(
            (tc.mileage_cost or 0) + (tc.toll_cost or 0)
            for tc in self.travel_claims
        )
        purchase_total = sum(
            (pc.price or 0)
            for pc in self.purchase_claims
        )
        return round(travel_total + purchase_total, 2)

    @property
    def travel_total(self) -> float:
        return round(sum(
            (tc.mileage_cost or 0) + (tc.toll_cost or 0)
            for tc in self.travel_claims
        ), 2)

    @property
    def purchase_total(self) -> float:
        return round(sum((pc.price or 0) for pc in self.purchase_claims), 2)

    def __repr__(self):
        return f'<ClaimPeriod {self.period_name} [{self.status}]>'


class TravelClaim(db.Model):
    __tablename__ = 'travel_claims'

    id = db.Column(db.Integer, primary_key=True)
    claim_period_id = db.Column(db.Integer, db.ForeignKey('claim_periods.id'), nullable=False)
    date = db.Column(db.Date, nullable=True)
    origin = db.Column(db.String(255), nullable=True)
    destination = db.Column(db.String(255), nullable=True)
    purpose = db.Column(db.String(500), nullable=True)
    trip_type = db.Column(db.String(100), nullable=True)
    toll_cost = db.Column(db.Float, nullable=True, default=0.0)
    distance_km = db.Column(db.Float, nullable=True, default=0.0)
    mileage_cost = db.Column(db.Float, nullable=True, default=0.0)

    claim_period = db.relationship('ClaimPeriod', back_populates='travel_claims')

    def __repr__(self):
        return f'<TravelClaim {self.date}: {self.origin} → {self.destination}>'


class PurchaseClaim(db.Model):
    __tablename__ = 'purchase_claims'

    id = db.Column(db.Integer, primary_key=True)
    claim_period_id = db.Column(db.Integer, db.ForeignKey('claim_periods.id'), nullable=False)
    date = db.Column(db.Date, nullable=True)
    item = db.Column(db.String(500), nullable=True)
    purchased_from = db.Column(db.String(255), nullable=True)
    purpose = db.Column(db.String(500), nullable=True)
    price = db.Column(db.Float, nullable=True, default=0.0)
    has_receipt = db.Column(db.Boolean, nullable=True, default=False)
    category = db.Column(db.String(50), nullable=True, default='Business')  # 'Business' or 'Personal'

    claim_period = db.relationship('ClaimPeriod', back_populates='purchase_claims')

    def __repr__(self):
        return f'<PurchaseClaim {self.date}: {self.item} ${self.price}>'
