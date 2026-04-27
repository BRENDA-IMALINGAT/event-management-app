"""Smoke tests for the EventMgr Flask application."""
import os
import tempfile

import pytest
from app import create_app
from models import db, BudgetItem


@pytest.fixture
def client():
    db_fd, db_path = tempfile.mkstemp(suffix='.db')
    application = create_app({
        'TESTING': True,
        'SQLALCHEMY_DATABASE_URI': f'sqlite:///{db_path}',
    })
    with application.app_context():
        db.create_all()
    yield application.test_client()
    os.close(db_fd)
    os.unlink(db_path)


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
