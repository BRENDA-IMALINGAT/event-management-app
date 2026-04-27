from flask import (
    Flask, render_template, request, redirect, url_for,
    session, flash
)
from werkzeug.security import check_password_hash, generate_password_hash
from models import db, Attendee, BudgetItem, FOOD_OPTIONS

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

