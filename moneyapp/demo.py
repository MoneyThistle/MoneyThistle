"""Made-up sample data for trying the app out (and for screenshots)."""

import datetime as dt
import random

from . import loans


def load_sample(store):
    if store.accounts():
        return False
    store.set_setting("sample_data", True)   # (Start fresh then needs no typed confirmation)
    rnd = random.Random(7)
    cats = {c["full_name"]: c["id"] for c in store.categories()}
    t = dt.date.today()
    start = (t.replace(day=1) - dt.timedelta(days=95)).replace(day=1)
    first_car = (start - dt.timedelta(days=730)).replace(day=25)
    chk = store.save_account({"name": "Everyday Checking", "type": "Checking", "opening_balance": "2450.00",
                              "opening_date": start.isoformat(), "favorite": True})
    sav = store.save_account({"name": "Rainy Day Savings", "type": "Savings", "opening_balance": "8200.00",
                              "opening_date": start.isoformat()})
    card = store.save_account({"name": "Rewards Card", "type": "Credit Card", "opening_balance": "-312.40",
                               "opening_date": start.isoformat()})
    store.save_account({"name": "Wallet", "type": "Cash", "opening_balance": "80.00",
                        "opening_date": start.isoformat()})
    # A car loan with full terms: 18,000 at 6.9% over 60 months, already 2 years in.
    car = loans.save(store, {"name": "Car Loan", "payee": "Riverbank Auto Finance", "original_amount": "18000",
                             "apr": "6.9", "payments_per_year": 12, "num_payments": 60,
                             "first_payment": first_car.isoformat(), "escrow": "0",
                             "interest_category_id": cats["Loan : Loan Interest"], "pay_from_account_id": chk})
    # Start the sample's history at `start`: owed as of then, next payment the first 25th after it.
    made, nxt_car = loans.payment_dates_until(first_car, 12, start)
    owed = loans.schedule(1800000, 6.9, 12, loans.calc_payment(1800000, 6.9, 12, 60), first_car, 25,
                          limit=made)[-1]["balance"]
    store.db.execute("UPDATE accounts SET opening_balance=?, opening_date=? WHERE id=?",
                     (-owed, start.isoformat(), car))
    store.db.execute("UPDATE bills SET next_date=? WHERE kind='loan' AND loan_account_id=?",
                     (nxt_car.isoformat(), car))
    store.db.commit()
    car_bill = store.q1("SELECT id FROM bills WHERE kind='loan' AND loan_account_id=?", (car,))["id"]

    def tx(acc, d, payee, cat, amount, status="R"):
        if d > t:
            return
        store.save_transaction({"account_id": acc, "date": d.isoformat(), "payee": payee,
                                "category_id": cats.get(cat), "amount": amount,
                                "status": status if d < t - dt.timedelta(days=10) else ""})

    d = start
    while d <= t:
        if d.day in (1, 16):
            tx(chk, d, "Northwind Payroll", "Wages & Salary : Net Pay", 2310.55)
        if d.day == 3:
            tx(chk, d, "Maple Court Apartments", "Bills : Rent", -1450.00)
        if d.day == 9:
            tx(chk, d, "City Power & Light", "Bills : Electricity", -round(rnd.uniform(62, 118), 2))
        if d.day == 12:
            tx(chk, d, "Clearwave Internet", "Bills : Online/Internet Service", -59.99)
        if d.weekday() == 5:
            tx(card, d, rnd.choice(["Fresh Market", "Green Grocer", "Corner Foods"]), "Groceries",
               -round(rnd.uniform(48, 135), 2))
        if d.weekday() == 4:
            tx(card, d, rnd.choice(["Luigi's Trattoria", "Noodle House", "Taco Stand"]), "Dining Out",
               -round(rnd.uniform(18, 64), 2))
        if d.day in (7, 22):
            tx(card, d, "Quick Fuel", "Automobile : Gasoline", -round(rnd.uniform(35, 58), 2))
        if d.day == 17:
            tx(card, d, "Streamly", "Hobbies/Leisure : Movies & Video Rentals", -12.99)
        if d.day == 25 and d <= t:
            store.enter_bill(car_bill)
        d += dt.timedelta(days=1)
    # Monthly transfers and card payments.
    m = start
    while m <= t:
        d20 = m.replace(day=20)
        if d20 <= t:
            store.save_transaction({"account_id": chk, "date": d20.isoformat(), "payee": "Monthly savings",
                                    "amount": -400, "transfer_account_id": sav, "status": "R"})
        d28 = m.replace(day=28)
        if d28 <= t:
            store.save_transaction({"account_id": chk, "date": d28.isoformat(), "payee": "Rewards Card payment",
                                    "amount": -650, "transfer_account_id": card})
        m = (m + dt.timedelta(days=32)).replace(day=1)

    def nxt(day):
        n = t.replace(day=day)
        return n if n >= t else (n.replace(day=1) + dt.timedelta(days=32)).replace(day=day)

    store.save_bill({"kind": "bill", "payee": "Maple Court Apartments", "account_id": chk, "amount": 1450,
                     "frequency": "Monthly", "next_date": nxt(3).isoformat(), "category_id": cats["Bills : Rent"]})
    # The electric bill varies: expect the average of the last 12, starting from 90.
    power = store.save_bill({"kind": "bill", "payee": "City Power & Light", "account_id": chk, "amount": 90,
                             "frequency": "Monthly", "next_date": nxt(9).isoformat(),
                             "category_id": cats["Bills : Electricity"], "amount_mode": "average",
                             "average_count": 12})
    for p in store.transactions(account_id=chk, search="City Power"):
        store.db.execute("INSERT INTO bill_history(bill_id,date,amount,transaction_id) VALUES(?,?,?,?)",
                         (power, p["date"], -p["amount"], p["id"]))
    store.db.commit()
    store.save_bill({"kind": "bill", "payee": "Clearwave Internet", "account_id": chk, "amount": 59.99,
                     "frequency": "Monthly", "next_date": nxt(12).isoformat(),
                     "category_id": cats["Bills : Online/Internet Service"]})

    store.save_bill({"kind": "deposit", "payee": "Northwind Payroll", "account_id": chk, "amount": 2310.55,
                     "frequency": "Twice a month", "next_date": (nxt(16) if 1 < t.day <= 16 else nxt(1)).isoformat(),
                     "category_id": cats["Wages & Salary : Net Pay"]})
    store.save_bill({"kind": "transfer", "payee": "Monthly savings", "account_id": chk, "to_account_id": sav,
                     "amount": 400, "frequency": "Monthly", "next_date": nxt(20).isoformat()})
    store.set_budget([
        {"category_id": cats["Groceries"], "amount": 520},
        {"category_id": cats["Dining Out"], "amount": 180},
        {"category_id": cats["Bills"], "amount": 1650},
        {"category_id": cats["Automobile : Gasoline"], "amount": 110},
        {"category_id": cats["Hobbies/Leisure"], "amount": 60},
        {"category_id": cats["Clothing"], "amount": 75},
        {"category_id": cats["Wages & Salary"], "amount": 4621.10},
    ])
    return True
