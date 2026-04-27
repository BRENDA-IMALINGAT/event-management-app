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
