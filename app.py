import base64
import io
import re
import uuid
from datetime import datetime

import qrcode
from flask import Flask, flash, redirect, render_template, request, session, url_for
from sqlalchemy.exc import OperationalError
from werkzeug.security import check_password_hash, generate_password_hash

from models import (
    Attendee,
    BudgetItem,
    Event,
    FOOD_OPTIONS,
    NotificationLog,
    Organizer,
    Payment,
    db,
)

# Backward-compatible default credentials
ORGANIZER_USERNAME = 'organizer'
ORGANIZER_PASSWORD_HASH = generate_password_hash('admin123')


def _slugify(value):
    cleaned = re.sub(r'[^a-zA-Z0-9\s-]', '', value or '').strip().lower()
    return re.sub(r'[\s-]+', '-', cleaned)


def _food_summary_for(attendees):
    food_summary = {}
    for attendee in attendees:
        choice = attendee.food_choice
        unit_cost = FOOD_OPTIONS.get(choice, 0)
        if choice not in food_summary:
            food_summary[choice] = {'quantity': 0, 'unit_cost': unit_cost, 'total': 0}
        food_summary[choice]['quantity'] += 1
        food_summary[choice]['total'] += unit_cost
    return food_summary


def _seed_defaults():
    organizer = Organizer.query.filter_by(username=ORGANIZER_USERNAME).first()
    if not organizer:
        organizer = Organizer(username=ORGANIZER_USERNAME, password_hash=ORGANIZER_PASSWORD_HASH)
        db.session.add(organizer)
        db.session.commit()

    if not Event.query.filter_by(organizer_id=organizer.id).first():
        event = Event(
            organizer_id=organizer.id,
            name='Main Event',
            slug='main-event',
            ticket_price=0,
            active=True,
        )
        db.session.add(event)
        db.session.commit()


def create_app(test_config=None):
    application = Flask(__name__)
    application.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///event.db'
    application.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    application.config['SECRET_KEY'] = 'change-me-in-production'

    if test_config:
        application.config.update(test_config)

    db.init_app(application)

    @application.before_request
    def _ensure_baseline_data():
        try:
            _seed_defaults()
        except OperationalError:
            # Supports first boot when tables have not been created yet.
            pass

    def _current_organizer():
        organizer_id = session.get('organizer_id')
        if organizer_id:
            return db.session.get(Organizer, organizer_id)
        if session.get('organizer'):
            return Organizer.query.filter_by(username=ORGANIZER_USERNAME).first()
        return None

    def _require_organizer():
        organizer = _current_organizer()
        if not organizer:
            flash('Please log in to access organizer pages.', 'warning')
            return None, redirect(url_for('login'))
        return organizer, None

    def _get_selected_event(organizer):
        selected_id = session.get('selected_event_id')
        if selected_id:
            event = Event.query.filter_by(id=selected_id, organizer_id=organizer.id).first()
            if event:
                return event
        event = Event.query.filter_by(organizer_id=organizer.id).order_by(Event.created_at.asc()).first()
        if event:
            session['selected_event_id'] = event.id
        return event

    def _qr_data_uri(content):
        qr_img = qrcode.make(content)
        buf = io.BytesIO()
        qr_img.save(buf, format='PNG')
        encoded = base64.b64encode(buf.getvalue()).decode('utf-8')
        return f'data:image/png;base64,{encoded}'

    @application.route('/')
    def home():
        return redirect(url_for('register'))

    @application.route('/signup', methods=['GET', 'POST'])
    def signup():
        if request.method == 'POST':
            username = request.form.get('username', '').strip()
            password = request.form.get('password', '')

            if not username or not password:
                flash('Username and password are required.', 'danger')
                return render_template('signup.html')
            if Organizer.query.filter_by(username=username).first():
                flash('Username already exists.', 'warning')
                return render_template('signup.html')

            organizer = Organizer(username=username, password_hash=generate_password_hash(password))
            db.session.add(organizer)
            db.session.commit()

            default_slug = _slugify(f'{username}-event') or f'event-{organizer.id}'
            candidate = default_slug
            i = 1
            while Event.query.filter_by(slug=candidate).first():
                i += 1
                candidate = f'{default_slug}-{i}'
            db.session.add(Event(organizer_id=organizer.id, name=f"{username}'s Event", slug=candidate))
            db.session.commit()

            flash('Organizer account created. Please log in.', 'success')
            return redirect(url_for('login'))

        return render_template('signup.html')

    @application.route('/login', methods=['GET', 'POST'])
    def login():
        if _current_organizer():
            return redirect(url_for('dashboard'))

        if request.method == 'POST':
            username = request.form.get('username', '').strip()
            password = request.form.get('password', '')

            organizer = Organizer.query.filter_by(username=username).first()
            if organizer and check_password_hash(organizer.password_hash, password):
                session['organizer_id'] = organizer.id
                session['organizer'] = True
                _get_selected_event(organizer)
                flash('Welcome back!', 'success')
                return redirect(url_for('dashboard'))

            if username == ORGANIZER_USERNAME and check_password_hash(ORGANIZER_PASSWORD_HASH, password):
                fallback_org = Organizer.query.filter_by(username=ORGANIZER_USERNAME).first()
                if not fallback_org:
                    fallback_org = Organizer(
                        username=ORGANIZER_USERNAME,
                        password_hash=ORGANIZER_PASSWORD_HASH,
                    )
                    db.session.add(fallback_org)
                    db.session.commit()
                if not Event.query.filter_by(organizer_id=fallback_org.id).first():
                    db.session.add(
                        Event(
                            organizer_id=fallback_org.id,
                            name='Main Event',
                            slug='main-event',
                            ticket_price=0,
                            active=True,
                        )
                    )
                    db.session.commit()
                if fallback_org:
                    session['organizer_id'] = fallback_org.id
                session['organizer'] = True
                if fallback_org:
                    _get_selected_event(fallback_org)
                flash('Welcome back!', 'success')
                return redirect(url_for('dashboard'))

            flash('Invalid username or password.', 'danger')

        return render_template('login.html')

    @application.route('/logout')
    def logout():
        session.pop('organizer', None)
        session.pop('organizer_id', None)
        session.pop('selected_event_id', None)
        flash('You have been logged out.', 'info')
        return redirect(url_for('login'))

    @application.route('/events', methods=['GET', 'POST'])
    def events():
        organizer, auth_redirect = _require_organizer()
        if auth_redirect:
            return auth_redirect

        if request.method == 'POST':
            name = request.form.get('name', '').strip()
            ticket_price_raw = request.form.get('ticket_price', '').strip()
            active = request.form.get('active') == 'on'
            if not name:
                flash('Event name is required.', 'danger')
                return redirect(url_for('events'))
            try:
                ticket_price = float(ticket_price_raw)
                if ticket_price < 0:
                    raise ValueError
            except ValueError:
                flash('Ticket price must be zero or a positive number.', 'danger')
                return redirect(url_for('events'))

            base_slug = _slugify(name) or f'event-{uuid.uuid4().hex[:8]}'
            candidate = base_slug
            i = 1
            while Event.query.filter_by(slug=candidate).first():
                i += 1
                candidate = f'{base_slug}-{i}'

            event = Event(
                organizer_id=organizer.id,
                name=name,
                slug=candidate,
                ticket_price=ticket_price,
                active=active,
            )
            db.session.add(event)
            db.session.commit()
            session['selected_event_id'] = event.id
            flash('Event created and selected.', 'success')
            return redirect(url_for('events'))

        events_list = Event.query.filter_by(organizer_id=organizer.id).order_by(Event.created_at.desc()).all()
        selected_event = _get_selected_event(organizer)
        return render_template('events.html', events=events_list, selected_event=selected_event)

    @application.route('/events/select/<int:event_id>')
    def select_event(event_id):
        organizer, auth_redirect = _require_organizer()
        if auth_redirect:
            return auth_redirect
        event = Event.query.filter_by(id=event_id, organizer_id=organizer.id).first_or_404()
        session['selected_event_id'] = event.id
        flash(f'Selected event: {event.name}', 'info')
        return redirect(url_for('dashboard'))

    @application.route('/register', methods=['GET', 'POST'])
    def register():
        all_active_events = Event.query.filter_by(active=True).order_by(Event.created_at.desc()).all()
        if not all_active_events:
            flash('No active events are available yet.', 'warning')
            return render_template('register.html', food_options=FOOD_OPTIONS, events=[], selected_event=None)

        event_id = request.args.get('event_id', type=int)
        if request.method == 'POST':
            event_id = request.form.get('event_id', type=int)
        selected_event = db.session.get(Event, event_id) if event_id else all_active_events[0]
        if not selected_event or not selected_event.active:
            selected_event = all_active_events[0]

        if request.method == 'POST':
            name = request.form.get('name', '').strip()
            email = request.form.get('email', '').strip()
            phone = request.form.get('phone', '').strip()
            food = request.form.get('food', '').strip()

            if not all([name, email, phone, food]):
                flash('All fields are required.', 'danger')
                return render_template(
                    'register.html',
                    food_options=FOOD_OPTIONS,
                    events=all_active_events,
                    selected_event=selected_event,
                )

            if food not in FOOD_OPTIONS:
                flash('Invalid food choice.', 'danger')
                return render_template(
                    'register.html',
                    food_options=FOOD_OPTIONS,
                    events=all_active_events,
                    selected_event=selected_event,
                )

            existing = Attendee.query.filter_by(event_id=selected_event.id, email=email).first()
            if existing:
                flash('An attendee with that email is already registered for this event.', 'warning')
                return render_template(
                    'register.html',
                    food_options=FOOD_OPTIONS,
                    events=all_active_events,
                    selected_event=selected_event,
                )

            attendee = Attendee(
                event_id=selected_event.id,
                name=name,
                email=email,
                phone=phone,
                food_choice=food,
            )
            db.session.add(attendee)
            db.session.flush()

            payment_amount = float(selected_event.ticket_price or 0)
            payment = Payment(
                attendee_id=attendee.id,
                amount=payment_amount,
                provider='manual',
                status='paid' if payment_amount == 0 else 'pending',
                paid_at=datetime.utcnow() if payment_amount == 0 else None,
            )
            attendee.paid = payment_amount == 0
            db.session.add(payment)
            db.session.commit()

            return redirect(url_for('confirmation', attendee_id=attendee.id))

        return render_template(
            'register.html',
            food_options=FOOD_OPTIONS,
            events=all_active_events,
            selected_event=selected_event,
        )

    @application.route('/confirmation/<int:attendee_id>')
    def confirmation(attendee_id):
        attendee = db.get_or_404(Attendee, attendee_id)
        unit_cost = FOOD_OPTIONS.get(attendee.food_choice, 0)
        checkin_url = url_for('check_in', token=attendee.ticket_token, _external=True)
        qr_data_uri = _qr_data_uri(checkin_url)
        return render_template(
            'confirmation.html',
            attendee=attendee,
            unit_cost=unit_cost,
            checkin_url=checkin_url,
            qr_data_uri=qr_data_uri,
        )

    @application.route('/payment/<int:attendee_id>', methods=['GET', 'POST'])
    def payment(attendee_id):
        attendee = db.get_or_404(Attendee, attendee_id)
        payment_record = attendee.payment
        if not payment_record:
            flash('Payment record missing for attendee.', 'danger')
            return redirect(url_for('confirmation', attendee_id=attendee.id))

        if request.method == 'POST':
            if payment_record.status == 'paid':
                flash('Ticket is already paid.', 'info')
                return redirect(url_for('confirmation', attendee_id=attendee.id))

            provider = request.form.get('provider', 'manual').strip() or 'manual'
            payment_record.status = 'paid'
            payment_record.provider = provider
            payment_record.transaction_ref = f'TXN-{uuid.uuid4().hex[:10].upper()}'
            payment_record.paid_at = datetime.utcnow()
            attendee.paid = True
            db.session.commit()

            flash('Payment successful. Your ticket is now active.', 'success')
            return redirect(url_for('confirmation', attendee_id=attendee.id))

        return render_template('payment.html', attendee=attendee, payment=payment_record)

    @application.route('/check-in/<token>')
    def check_in(token):
        attendee = Attendee.query.filter_by(ticket_token=token).first_or_404()
        if not attendee.paid:
            flash('Ticket is not paid yet. Check-in denied.', 'danger')
            return render_template('checkin_result.html', attendee=attendee, checked_in=False)
        if attendee.checked_in:
            flash('Attendee already checked in.', 'info')
            return render_template('checkin_result.html', attendee=attendee, checked_in=True)

        attendee.checked_in = True
        attendee.checked_in_at = datetime.utcnow()
        db.session.commit()
        flash('Check-in successful.', 'success')
        return render_template('checkin_result.html', attendee=attendee, checked_in=True)

    @application.route('/dashboard')
    def dashboard():
        organizer, auth_redirect = _require_organizer()
        if auth_redirect:
            return auth_redirect
        event = _get_selected_event(organizer)
        if not event:
            flash('Create an event first to use the dashboard.', 'warning')
            return redirect(url_for('events'))

        attendees = Attendee.query.filter_by(event_id=event.id).order_by(Attendee.name).all()
        food_summary = _food_summary_for(attendees)
        food_total = sum(v['total'] for v in food_summary.values())
        paid_count = sum(1 for a in attendees if a.paid)
        checked_in_count = sum(1 for a in attendees if a.checked_in)

        return render_template(
            'dashboard.html',
            event=event,
            attendees=attendees,
            food_summary=food_summary,
            food_total=food_total,
            paid_count=paid_count,
            checked_in_count=checked_in_count,
        )

    @application.route('/budget')
    def budget():
        organizer, auth_redirect = _require_organizer()
        if auth_redirect:
            return auth_redirect
        event = _get_selected_event(organizer)
        if not event:
            flash('Create an event first to manage budget.', 'warning')
            return redirect(url_for('events'))

        attendees = Attendee.query.filter_by(event_id=event.id).all()
        food_summary = _food_summary_for(attendees)
        food_total = sum(v['total'] for v in food_summary.values())

        extras = BudgetItem.query.filter_by(event_id=event.id).order_by(BudgetItem.name).all()
        extras_total = sum(item.total for item in extras)
        grand_total = food_total + extras_total

        return render_template(
            'budget.html',
            event=event,
            food_summary=food_summary,
            food_total=food_total,
            extras=extras,
            extras_total=extras_total,
            grand_total=grand_total,
        )

    @application.route('/budget/add', methods=['POST'])
    def budget_add():
        organizer, auth_redirect = _require_organizer()
        if auth_redirect:
            return auth_redirect
        event = _get_selected_event(organizer)
        if not event:
            flash('Select or create an event first.', 'warning')
            return redirect(url_for('events'))

        name = request.form.get('name', '').strip()
        cost = request.form.get('cost', '').strip()
        quantity = request.form.get('quantity', '').strip()

        if not all([name, cost, quantity]):
            flash('All fields are required to add a budget item.', 'danger')
            return redirect(url_for('budget'))

        try:
            cost = float(cost)
            quantity = int(quantity)
            if cost <= 0 or quantity <= 0:
                raise ValueError
        except ValueError:
            flash('Cost and quantity must be positive numbers.', 'danger')
            return redirect(url_for('budget'))

        item = BudgetItem(event_id=event.id, name=name, cost=cost, quantity=quantity)
        db.session.add(item)
        db.session.commit()
        flash(f'"{name}" added to the budget.', 'success')
        return redirect(url_for('budget'))

    @application.route('/budget/delete/<int:item_id>', methods=['POST'])
    def budget_delete(item_id):
        organizer, auth_redirect = _require_organizer()
        if auth_redirect:
            return auth_redirect
        event = _get_selected_event(organizer)
        if not event:
            flash('Select or create an event first.', 'warning')
            return redirect(url_for('events'))

        item = BudgetItem.query.filter_by(id=item_id, event_id=event.id).first_or_404()
        db.session.delete(item)
        db.session.commit()
        flash(f'"{item.name}" removed from the budget.', 'info')
        return redirect(url_for('budget'))

    @application.route('/notifications/send', methods=['POST'])
    def notifications_send():
        organizer, auth_redirect = _require_organizer()
        if auth_redirect:
            return auth_redirect
        event = _get_selected_event(organizer)
        if not event:
            flash('Select or create an event first.', 'warning')
            return redirect(url_for('events'))

        message = request.form.get('message', '').strip()
        channel = request.form.get('channel', 'email').strip() or 'email'
        if not message:
            flash('Notification message is required.', 'danger')
            return redirect(url_for('dashboard'))

        attendees = Attendee.query.filter_by(event_id=event.id).all()
        for attendee in attendees:
            db.session.add(
                NotificationLog(
                    event_id=event.id,
                    attendee_id=attendee.id,
                    channel=channel,
                    message=message,
                    status='sent',
                )
            )
        db.session.commit()
        flash(f'Notification sent to {len(attendees)} attendees via {channel}.', 'success')
        return redirect(url_for('dashboard'))

    @application.route('/analytics')
    def analytics():
        organizer, auth_redirect = _require_organizer()
        if auth_redirect:
            return auth_redirect
        event = _get_selected_event(organizer)
        if not event:
            flash('Create an event first to view analytics.', 'warning')
            return redirect(url_for('events'))

        attendees = Attendee.query.filter_by(event_id=event.id).all()
        total_attendees = len(attendees)
        paid_attendees = sum(1 for a in attendees if a.paid)
        checked_in_attendees = sum(1 for a in attendees if a.checked_in)
        revenue = sum((a.payment.amount if a.payment and a.payment.status == 'paid' else 0) for a in attendees)
        notification_count = NotificationLog.query.filter_by(event_id=event.id).count()

        conversion_rate = (paid_attendees / total_attendees * 100) if total_attendees else 0
        attendance_rate = (checked_in_attendees / total_attendees * 100) if total_attendees else 0

        return render_template(
            'analytics.html',
            event=event,
            total_attendees=total_attendees,
            paid_attendees=paid_attendees,
            checked_in_attendees=checked_in_attendees,
            revenue=revenue,
            notification_count=notification_count,
            conversion_rate=conversion_rate,
            attendance_rate=attendance_rate,
        )

    return application


app = create_app()

if __name__ == '__main__':
    import os as _os

    with app.app_context():
        db.create_all()
        _seed_defaults()
    app.run(debug=_os.environ.get('FLASK_DEBUG', '0') == '1')
