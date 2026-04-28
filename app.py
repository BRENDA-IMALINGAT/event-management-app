from flask import (
    Flask, render_template, request, redirect, url_for,
    session, flash
)
from werkzeug.security import check_password_hash, generate_password_hash
from models import db, Attendee, BudgetItem, Sponsor, SponsorEngagement, FOOD_OPTIONS

# Simple organizer credentials (hashed password for "admin123")
ORGANIZER_USERNAME = 'organizer'
ORGANIZER_PASSWORD_HASH = generate_password_hash('admin123')


def create_app(test_config=None):
    """Application factory – creates and configures a Flask app instance."""
    application = Flask(__name__)
    application.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///event.db'
    application.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    application.config['SECRET_KEY'] = 'change-me-in-production'

    if test_config:
        application.config.update(test_config)

    db.init_app(application)

    # -----------------------------------------------------------------------
    # Attendee Routes
    # -----------------------------------------------------------------------

    @application.route('/')
    def home():
        return redirect(url_for('register'))

    @application.route('/register', methods=['GET', 'POST'])
    def register():
        if request.method == 'POST':
            name = request.form.get('name', '').strip()
            email = request.form.get('email', '').strip()
            phone = request.form.get('phone', '').strip()
            food = request.form.get('food', '').strip()

            if not all([name, email, phone, food]):
                flash('All fields are required.', 'danger')
                return render_template('register.html', food_options=FOOD_OPTIONS)

            if food not in FOOD_OPTIONS:
                flash('Invalid food choice.', 'danger')
                return render_template('register.html', food_options=FOOD_OPTIONS)

            existing = Attendee.query.filter_by(email=email).first()
            if existing:
                flash('An attendee with that email is already registered.', 'warning')
                return render_template('register.html', food_options=FOOD_OPTIONS)

            attendee = Attendee(name=name, email=email, phone=phone, food_choice=food)
            db.session.add(attendee)
            db.session.commit()

            return redirect(url_for('confirmation', attendee_id=attendee.id))

        return render_template('register.html', food_options=FOOD_OPTIONS)

    @application.route('/confirmation/<int:attendee_id>')
    def confirmation(attendee_id):
        attendee = db.get_or_404(Attendee, attendee_id)
        unit_cost = FOOD_OPTIONS.get(attendee.food_choice, 0)
        return render_template('confirmation.html', attendee=attendee, unit_cost=unit_cost)

    # -----------------------------------------------------------------------
    # Organizer Routes
    # -----------------------------------------------------------------------

    @application.route('/login', methods=['GET', 'POST'])
    def login():
        if session.get('organizer'):
            return redirect(url_for('dashboard'))

        if request.method == 'POST':
            username = request.form.get('username', '').strip()
            password = request.form.get('password', '')

            if username == ORGANIZER_USERNAME and check_password_hash(
                ORGANIZER_PASSWORD_HASH, password
            ):
                session['organizer'] = True
                flash('Welcome back!', 'success')
                return redirect(url_for('dashboard'))

            flash('Invalid username or password.', 'danger')

        return render_template('login.html')

    @application.route('/logout')
    def logout():
        session.pop('organizer', None)
        flash('You have been logged out.', 'info')
        return redirect(url_for('login'))

    def _require_organizer():
        """Return a redirect response if the organizer is not logged in, else None."""
        if not session.get('organizer'):
            flash('Please log in to access the dashboard.', 'warning')
            return redirect(url_for('login'))
        return None

    @application.route('/dashboard')
    def dashboard():
        auth = _require_organizer()
        if auth:
            return auth

        attendees = Attendee.query.order_by(Attendee.name).all()

        food_summary = {}
        for attendee in attendees:
            choice = attendee.food_choice
            unit_cost = FOOD_OPTIONS.get(choice, 0)
            if choice not in food_summary:
                food_summary[choice] = {'quantity': 0, 'unit_cost': unit_cost, 'total': 0}
            food_summary[choice]['quantity'] += 1
            food_summary[choice]['total'] += unit_cost

        food_total = sum(v['total'] for v in food_summary.values())

        return render_template(
            'dashboard.html',
            attendees=attendees,
            food_summary=food_summary,
            food_total=food_total,
        )

    @application.route('/budget')
    def budget():
        auth = _require_organizer()
        if auth:
            return auth

        attendees = Attendee.query.all()
        food_summary = {}
        for attendee in attendees:
            choice = attendee.food_choice
            unit_cost = FOOD_OPTIONS.get(choice, 0)
            if choice not in food_summary:
                food_summary[choice] = {'quantity': 0, 'unit_cost': unit_cost, 'total': 0}
            food_summary[choice]['quantity'] += 1
            food_summary[choice]['total'] += unit_cost

        food_total = sum(v['total'] for v in food_summary.values())

        extras = BudgetItem.query.order_by(BudgetItem.name).all()
        extras_total = sum(item.total for item in extras)
        grand_total = food_total + extras_total

        return render_template(
            'budget.html',
            food_summary=food_summary,
            food_total=food_total,
            extras=extras,
            extras_total=extras_total,
            grand_total=grand_total,
        )

    @application.route('/budget/add', methods=['POST'])
    def budget_add():
        auth = _require_organizer()
        if auth:
            return auth

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

        item = BudgetItem(name=name, cost=cost, quantity=quantity)
        db.session.add(item)
        db.session.commit()
        flash(f'"{name}" added to the budget.', 'success')
        return redirect(url_for('budget'))

    @application.route('/budget/delete/<int:item_id>', methods=['POST'])
    def budget_delete(item_id):
        auth = _require_organizer()
        if auth:
            return auth

        item = db.get_or_404(BudgetItem, item_id)
        db.session.delete(item)
        db.session.commit()
        flash(f'"{item.name}" removed from the budget.', 'info')
        return redirect(url_for('budget'))

    @application.route('/sponsors', methods=['GET', 'POST'])
    def sponsors():
        auth = _require_organizer()
        if auth:
            return auth

        if request.method == 'POST':
            name = request.form.get('name', '').strip()
            booth_name = request.form.get('booth_name', '').strip() or None
            active = request.form.get('active') == 'on'

            if not name:
                flash('Sponsor name is required.', 'danger')
                return redirect(url_for('sponsors'))

            sponsor = Sponsor(name=name, booth_name=booth_name, active=active)
            db.session.add(sponsor)
            db.session.commit()
            flash(f'Sponsor "{name}" created.', 'success')
            return redirect(url_for('sponsors'))

        sponsors_list = Sponsor.query.order_by(Sponsor.name.asc()).all()
        return render_template('sponsors.html', sponsors=sponsors_list)

    @application.route('/sponsors/delete/<int:sponsor_id>', methods=['POST'])
    def sponsors_delete(sponsor_id):
        auth = _require_organizer()
        if auth:
            return auth

        sponsor = db.get_or_404(Sponsor, sponsor_id)
        db.session.delete(sponsor)
        db.session.commit()
        flash(f'Sponsor "{sponsor.name}" deleted.', 'info')
        return redirect(url_for('sponsors'))

    @application.route('/sponsors/<int:sponsor_id>/booth-engagement', methods=['POST'])
    def sponsor_booth_engagement(sponsor_id):
        auth = _require_organizer()
        if auth:
            return auth

        sponsor = db.get_or_404(Sponsor, sponsor_id)
        attendee_email = request.form.get('attendee_email', '').strip().lower()
        if not attendee_email:
            flash('Attendee email is required to log booth engagement.', 'danger')
            return redirect(url_for('sponsors'))

        attendee = Attendee.query.filter_by(email=attendee_email).first()
        if not attendee:
            flash('Attendee email not found. Register attendee first.', 'danger')
            return redirect(url_for('sponsors'))

        engagement = SponsorEngagement(
            sponsor_id=sponsor.id,
            attendee_id=attendee.id,
            interaction_type='booth_visit',
            source='organizer_dashboard',
        )
        db.session.add(engagement)
        db.session.commit()
        flash(f'Booth engagement logged for {sponsor.name}.', 'success')
        return redirect(url_for('sponsors'))

    @application.route('/sponsor/scan/<qr_token>', methods=['GET', 'POST'])
    def sponsor_scan(qr_token):
        sponsor = Sponsor.query.filter_by(qr_token=qr_token, active=True).first_or_404()
        attendee = None

        attendee_email = request.args.get('email', '').strip().lower()
        if request.method == 'POST':
            attendee_email = request.form.get('attendee_email', '').strip().lower()
        if attendee_email:
            attendee = Attendee.query.filter_by(email=attendee_email).first()

        engagement = SponsorEngagement(
            sponsor_id=sponsor.id,
            attendee_id=attendee.id if attendee else None,
            interaction_type='qr_scan',
            source='public_qr',
        )
        db.session.add(engagement)
        db.session.commit()

        if attendee_email and not attendee:
            flash('Scan recorded, but attendee email was not found.', 'warning')
        else:
            flash('Thanks for engaging with this sponsor.', 'success')

        return render_template('sponsor_scan.html', sponsor=sponsor, attendee=attendee)

    @application.route('/analytics')
    def analytics():
        auth = _require_organizer()
        if auth:
            return auth

        attendees = Attendee.query.all()
        sponsors_list = Sponsor.query.order_by(Sponsor.name.asc()).all()
        engagements = SponsorEngagement.query.all()

        total_attendees = len(attendees)
        food_summary = {}
        for attendee in attendees:
            choice = attendee.food_choice
            food_summary[choice] = food_summary.get(choice, 0) + 1

        sponsor_rows = {}
        all_unique_attendees = set()
        total_qr_scans = 0
        total_booth_visits = 0

        for sponsor in sponsors_list:
            sponsor_rows[sponsor.id] = {
                'sponsor': sponsor,
                'qr_scans': 0,
                'booth_visits': 0,
                'total_engagements': 0,
                'unique_attendees': set(),
                'scan_url': url_for('sponsor_scan', qr_token=sponsor.qr_token, _external=True),
            }

        for engagement in engagements:
            row = sponsor_rows.get(engagement.sponsor_id)
            if not row:
                continue

            row['total_engagements'] += 1
            if engagement.interaction_type == 'booth_visit':
                row['booth_visits'] += 1
                total_booth_visits += 1
            else:
                row['qr_scans'] += 1
                total_qr_scans += 1

            if engagement.attendee_id:
                row['unique_attendees'].add(engagement.attendee_id)
                all_unique_attendees.add(engagement.attendee_id)

        sponsor_metrics = []
        for sponsor in sponsors_list:
            row = sponsor_rows[sponsor.id]
            sponsor_metrics.append({
                'sponsor': sponsor,
                'qr_scans': row['qr_scans'],
                'booth_visits': row['booth_visits'],
                'total_engagements': row['total_engagements'],
                'unique_attendees': len(row['unique_attendees']),
                'scan_url': row['scan_url'],
            })

        return render_template(
            'analytics.html',
            total_attendees=total_attendees,
            food_summary=food_summary,
            sponsors=sponsors_list,
            total_sponsors=len(sponsors_list),
            total_qr_scans=total_qr_scans,
            total_booth_visits=total_booth_visits,
            total_unique_attendees=len(all_unique_attendees),
            sponsor_metrics=sponsor_metrics,
        )

    return application


# ---------------------------------------------------------------------------
# Module-level app instance (used by flask run / gunicorn / direct execution)
# ---------------------------------------------------------------------------
app = create_app()

if __name__ == '__main__':
    import os as _os
    with app.app_context():
        db.create_all()
    app.run(debug=_os.environ.get('FLASK_DEBUG', '0') == '1')

