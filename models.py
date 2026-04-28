from datetime import datetime
import uuid

from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

# Food options with unit costs in UGX
FOOD_OPTIONS = {
    'Pilau': 3000,
    'Chapati': 500,
    'Matoke': 2500,
    'Nyama Choma': 5000,
}


class Attendee(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), nullable=False, unique=True)
    phone = db.Column(db.String(20), nullable=False)
    food_choice = db.Column(db.String(50), nullable=False)


class BudgetItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    cost = db.Column(db.Float, nullable=False)
    quantity = db.Column(db.Integer, nullable=False, default=1)

    @property
    def total(self):
        return self.cost * self.quantity


class Sponsor(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    booth_name = db.Column(db.String(120), nullable=True)
    qr_token = db.Column(db.String(36), nullable=False, unique=True, default=lambda: str(uuid.uuid4()))
    active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    engagements = db.relationship('SponsorEngagement', backref='sponsor', lazy=True, cascade='all, delete-orphan')


class SponsorEngagement(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sponsor_id = db.Column(db.Integer, db.ForeignKey('sponsor.id'), nullable=False, index=True)
    attendee_id = db.Column(db.Integer, db.ForeignKey('attendee.id'), nullable=True, index=True)
    interaction_type = db.Column(db.String(20), nullable=False, default='qr_scan')
    source = db.Column(db.String(30), nullable=False, default='qr')
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    attendee = db.relationship('Attendee', backref=db.backref('sponsor_engagements', lazy=True))
