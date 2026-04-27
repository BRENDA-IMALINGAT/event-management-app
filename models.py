from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import uuid

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
    event_id = db.Column(db.Integer, db.ForeignKey('event.id'), nullable=False, index=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    food_choice = db.Column(db.String(50), nullable=False)
    ticket_token = db.Column(db.String(36), nullable=False, unique=True, default=lambda: str(uuid.uuid4()))
    paid = db.Column(db.Boolean, nullable=False, default=False)
    checked_in = db.Column(db.Boolean, nullable=False, default=False)
    checked_in_at = db.Column(db.DateTime, nullable=True)

    __table_args__ = (
        db.UniqueConstraint('event_id', 'email', name='uq_attendee_event_email'),
    )


class BudgetItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey('event.id'), nullable=False, index=True)
    name = db.Column(db.String(100), nullable=False)
    cost = db.Column(db.Float, nullable=False)
    quantity = db.Column(db.Integer, nullable=False, default=1)

    @property
    def total(self):
        return self.cost * self.quantity


class Organizer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), nullable=False, unique=True)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    events = db.relationship('Event', backref='organizer', lazy=True)


class Event(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    organizer_id = db.Column(db.Integer, db.ForeignKey('organizer.id'), nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False)
    slug = db.Column(db.String(140), nullable=False, unique=True)
    ticket_price = db.Column(db.Float, nullable=False, default=0)
    active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    attendees = db.relationship('Attendee', backref='event', lazy=True, cascade='all, delete-orphan')
    budget_items = db.relationship('BudgetItem', backref='event', lazy=True, cascade='all, delete-orphan')


class Payment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    attendee_id = db.Column(db.Integer, db.ForeignKey('attendee.id'), nullable=False, index=True, unique=True)
    amount = db.Column(db.Float, nullable=False)
    provider = db.Column(db.String(40), nullable=False, default='manual')
    status = db.Column(db.String(20), nullable=False, default='pending')
    transaction_ref = db.Column(db.String(100), nullable=True)
    paid_at = db.Column(db.DateTime, nullable=True)

    attendee = db.relationship('Attendee', backref=db.backref('payment', uselist=False))


class NotificationLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey('event.id'), nullable=False, index=True)
    attendee_id = db.Column(db.Integer, db.ForeignKey('attendee.id'), nullable=False, index=True)
    channel = db.Column(db.String(20), nullable=False, default='email')
    message = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), nullable=False, default='sent')
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    event = db.relationship('Event')
    attendee = db.relationship('Attendee')
