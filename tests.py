"""Smoke tests for the EventMgr Flask application."""

import pytest
from app import create_app
from models import db, Attendee, BudgetItem, Sponsor, SponsorEngagement


@pytest.fixture
def client():
    application = create_app({
        'TESTING': True,
        'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:',
    })
    with application.app_context():
        db.create_all()
    yield application.test_client()
    with application.app_context():
        db.session.remove()
        db.drop_all()


# ---------------------------------------------------------------------------
# Public attendee routes
# ---------------------------------------------------------------------------

def test_home_redirects_to_register(client):
    r = client.get('/', follow_redirects=False)
    assert r.status_code == 302
    assert '/register' in r.headers['Location']


def test_register_get(client):
    r = client.get('/register')
    assert r.status_code == 200
    assert b'Attendee Registration' in r.data


def test_register_post_valid(client):
    r = client.post('/register', data={
        'name': 'Jane Akello',
        'email': 'jane@example.com',
        'phone': '+256700000000',
        'food': 'Pilau',
    }, follow_redirects=True)
    assert r.status_code == 200
    assert b'Registered' in r.data


def test_register_duplicate_email(client):
    data = {'name': 'User A', 'email': 'dup@test.com',
            'phone': '+256700000001', 'food': 'Chapati'}
    client.post('/register', data=data)
    r = client.post('/register', data=data)
    assert r.status_code == 200
    assert b'already registered' in r.data


def test_register_missing_name(client):
    r = client.post('/register', data={
        'name': '', 'email': 'x@test.com',
        'phone': '+256700000002', 'food': 'Pilau',
    })
    assert r.status_code == 200
    assert b'required' in r.data


def test_register_invalid_food(client):
    r = client.post('/register', data={
        'name': 'User B', 'email': 'b@test.com',
        'phone': '+256700000003', 'food': 'InvalidFood',
    })
    assert r.status_code == 200
    assert b'Invalid food' in r.data


# ---------------------------------------------------------------------------
# Organizer login / logout
# ---------------------------------------------------------------------------

def test_login_get(client):
    r = client.get('/login')
    assert r.status_code == 200
    assert b'Organizer Login' in r.data


def test_login_invalid_credentials(client):
    r = client.post('/login', data={'username': 'wrong', 'password': 'bad'})
    assert r.status_code == 200
    assert b'Invalid' in r.data


def test_login_valid(client):
    r = client.post('/login', data={'username': 'organizer', 'password': 'admin123'},
                    follow_redirects=True)
    assert r.status_code == 200
    assert b'Dashboard' in r.data


def test_logout(client):
    client.post('/login', data={'username': 'organizer', 'password': 'admin123'})
    r = client.get('/logout', follow_redirects=True)
    assert r.status_code == 200


# ---------------------------------------------------------------------------
# Dashboard (auth required)
# ---------------------------------------------------------------------------

def test_dashboard_requires_login(client):
    r = client.get('/dashboard', follow_redirects=True)
    assert b'Login' in r.data or b'log in' in r.data.lower()


def test_dashboard_accessible_when_logged_in(client):
    client.post('/login', data={'username': 'organizer', 'password': 'admin123'})
    r = client.get('/dashboard')
    assert r.status_code == 200
    assert b'Dashboard' in r.data


# ---------------------------------------------------------------------------
# Budget (auth required)
# ---------------------------------------------------------------------------

def test_budget_requires_login(client):
    r = client.get('/budget', follow_redirects=True)
    assert b'Login' in r.data or b'log in' in r.data.lower()


def test_budget_add_item(client):
    client.post('/login', data={'username': 'organizer', 'password': 'admin123'})
    r = client.post('/budget/add', data={
        'name': 'Tents', 'cost': '100000', 'quantity': '2',
    }, follow_redirects=True)
    assert r.status_code == 200
    assert b'Tents' in r.data


def test_budget_add_invalid_cost(client):
    client.post('/login', data={'username': 'organizer', 'password': 'admin123'})
    r = client.post('/budget/add', data={
        'name': 'Chairs', 'cost': '-500', 'quantity': '10',
    }, follow_redirects=True)
    assert r.status_code == 200
    assert b'positive' in r.data


def test_budget_delete_item(client):
    client.post('/login', data={'username': 'organizer', 'password': 'admin123'})
    client.post('/budget/add', data={'name': 'T-Shirts', 'cost': '15000', 'quantity': '5'})
    with client.application.app_context():
        item = BudgetItem.query.filter_by(name='T-Shirts').first()
        item_id = item.id
    r = client.post(f'/budget/delete/{item_id}', follow_redirects=True)
    assert r.status_code == 200


def test_sponsor_roi_flow(client):
    client.post('/login', data={'username': 'organizer', 'password': 'admin123'})
    client.post('/register', data={
        'name': 'ROI User',
        'email': 'roi@test.com',
        'phone': '+256700001234',
        'food': 'Pilau',
    }, follow_redirects=True)

    create = client.post('/sponsors', data={
        'name': 'Acme Telecom',
        'booth_name': 'Hall A',
        'active': 'on',
    }, follow_redirects=True)
    assert create.status_code == 200
    assert b'Acme Telecom' in create.data

    with client.application.app_context():
        sponsor = Sponsor.query.filter_by(name='Acme Telecom').first()
        assert sponsor is not None
        qr_token = sponsor.qr_token

    scan = client.get(f'/sponsor/scan/{qr_token}?email=roi@test.com', follow_redirects=True)
    assert scan.status_code == 200
    assert b'Engagement Recorded' in scan.data

    booth = client.post(
        f'/sponsors/{sponsor.id}/booth-engagement',
        data={'attendee_email': 'roi@test.com'},
        follow_redirects=True,
    )
    assert booth.status_code == 200

    analytics = client.get('/analytics')
    assert analytics.status_code == 200
    assert b'Analytics Dashboard' in analytics.data
    assert b'Acme Telecom' in analytics.data
    assert b'Unique attendees engaged with sponsors' in analytics.data

    with client.application.app_context():
        attendee = Attendee.query.filter_by(email='roi@test.com').first()
        assert attendee is not None
        qr_scans = SponsorEngagement.query.filter_by(
            sponsor_id=sponsor.id,
            interaction_type='qr_scan',
            attendee_id=attendee.id,
        ).count()
        booth_visits = SponsorEngagement.query.filter_by(
            sponsor_id=sponsor.id,
            interaction_type='booth_visit',
            attendee_id=attendee.id,
        ).count()
        assert qr_scans == 1
        assert booth_visits == 1
