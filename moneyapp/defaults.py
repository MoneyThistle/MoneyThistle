"""Starting lists for a new money file.

Taken from the original program's resource tables (see MECHANICS.md):
category names, which ones are tax related, which ones start in the budget,
account types and how often bills can repeat.
"""

# Each entry: (name, tax_related, in_budget, [(sub_name, tax_related, in_budget), ...])
# "+" in the original table = added to the default budget, "*" = tax related.
INCOME_CATEGORIES = [
    ("Investment Income", True, True, [
        ("Dividends", True, False),
        ("Interest", True, False),
        ("Capital Gains", True, False),
        ("Tax-Exempt Interest", True, False),
    ]),
    ("Other Income", True, True, [
        ("Child Support Received", False, False),
        ("Gifts Received", False, False),
        ("Loan Principal Received", False, False),
        ("Lotteries", True, False),
        ("State & Local Tax Refund", True, False),
        ("Unemployment Compensation", True, False),
        ("Employee Stock Option", True, False),
    ]),
    ("Retirement Income", True, True, [
        ("IRA Distributions", True, False),
        ("Pensions & Annuities", True, False),
        ("Social Security Benefits", True, False),
    ]),
    ("Wages & Salary", True, True, [
        ("Bonus", True, True),
        ("Commission", True, True),
        ("Employer Matching", False, False),
        ("Gross Pay", True, True),
        ("Net Pay", False, False),
        ("Overtime", True, True),
    ]),
]

EXPENSE_CATEGORIES = [
    ("Automobile", False, False, [
        ("Gasoline", False, True),
        ("Maintenance", False, True),
        ("Car Payment", False, False),
    ]),
    ("Bills", False, True, [
        ("Cable/Satellite Television", False, True),
        ("Cell Phone", False, False),
        ("Cellular", False, True),
        ("Electricity", False, True),
        ("Garbage & Recycle", False, True),
        ("Health Club", False, False),
        ("Homeowner's Dues", False, False),
        ("Membership Fees", False, False),
        ("Mortgage Payment", False, True),
        ("Natural Gas/Oil", False, True),
        ("Newspaper", False, False),
        ("Online/Internet Service", False, False),
        ("Other Loan Payment", False, False),
        ("Rent", False, False),
        ("Student Loan Payment", False, False),
        ("Telephone", False, True),
        ("Water & Sewer", False, True),
    ]),
    ("Bank Charges", False, False, [
        ("Interest Paid", False, False),
        ("Service Charge", False, True),
    ]),
    ("Cash Withdrawal", False, True, []),
    ("Charitable Donations", True, True, []),
    ("Childcare", True, True, []),
    ("Children/Toys", False, False, [
        ("Child Support", False, False),
        ("Daycare", False, False),
    ]),
    ("Clothing", False, True, []),
    ("Credit Card Payments/Transfers", False, False, []),
    ("Dining Out", False, True, []),
    ("Education", False, False, [
        ("Books", False, False),
        ("Fees", False, False),
        ("Tuition", False, False),
    ]),
    ("Entertainment", False, False, []),
    ("Fees", False, False, []),
    ("Food", False, True, []),
    ("Gifts", False, False, []),
    ("Groceries", False, True, []),
    ("Healthcare", True, True, [
        ("Dental", True, True),
        ("Eyecare", True, True),
        ("Hospital", True, False),
        ("Physician", True, True),
        ("Prescriptions", True, False),
    ]),
    ("Hobbies/Leisure", False, True, [
        ("Books & Magazines", False, True),
        ("Cultural Events", False, False),
        ("Entertaining", False, False),
        ("Movies & Video Rentals", False, True),
        ("Sporting Events", False, False),
        ("Sporting Goods", False, False),
        ("Tapes & CDs", False, False),
        ("Toys & Games", False, False),
    ]),
    ("Home Improvement", False, False, []),
    ("Household", False, False, [
        ("Furnishings", False, False),
        ("House Cleaning", False, False),
        ("Yard Service", False, False),
    ]),
    ("Insurance", False, False, [
        ("Automobile", False, True),
        ("Health", True, False),
        ("Homeowner's/Renter's", False, True),
        ("Life", False, False),
    ]),
    ("Job Expense", False, False, [
        ("Non-Reimbursed", True, False),
        ("Reimbursed", False, False),
    ]),
    ("Loan", False, False, [
        ("Loan Interest", False, False),
        ("Mortgage Interest", True, False),
        ("Student Loan Interest", True, False),
    ]),
    ("Miscellaneous", False, False, []),
    ("Mortgage/Rent", False, False, []),
    ("Personal Care", False, False, []),
    ("Pet Care", False, False, [
        ("Food", False, False),
        ("Supplies", False, False),
        ("Veterinarian", False, False),
    ]),
    ("Phone/Wireless", False, False, []),
    ("Services/Memberships", False, False, []),
    ("Taxes", True, False, [
        ("Federal Income Tax", True, False),
        ("Federal Income Tax-Previous Year", True, False),
        ("Local Income Tax", True, False),
        ("Medicare Tax", True, True),
        ("Other Taxes", True, True),
        ("Real Estate Taxes", True, False),
        ("Sales Tax", True, False),
        ("Social Security Tax", True, True),
        ("State Income Tax", True, True),
        ("State/Provincial", True, False),
    ]),
    ("Travel/Vacation", False, True, [
        ("Lodging", False, False),
        ("Travel", False, False),
    ]),
    ("Utilities", False, False, []),
    ("Alimony", True, False, []),
]

# Categories added after the first release, for what paystubs commonly take out. New files
# start with them; files made before get each group once (Store._add_new_categories, one
# setting per group). Kept apart so the translation catalog's numbering of the starting
# categories stays as it was. Each group: (its setting, main category, (tax, budget) when the
# main category is new itself else None, subcategories).
ADDED_CATEGORIES = [
    ("categories_v2", "Insurance", None, [
        ("Accident", False, False),
        ("Dental", True, False),
        ("Disability", False, False),
        ("Legal Plan", False, False),
        ("Vision", True, False),
    ]),
    # Money a paycheck puts aside for later, for people who don't keep the account it goes to
    # (a 401(k), an HSA) in MoneyThistle; those who do send it to that account instead.
    ("categories_v3", "Savings & Investments", (False, False), [
        ("Retirement Plan", False, False),
        ("HSA/FSA", False, False),
    ]),
]
for _v, _parent, _new, _subs in ADDED_CATEGORIES:
    if _new:
        EXPENSE_CATEGORIES.append((_parent, _new[0], _new[1], list(_subs)))
    else:
        next(c for c in EXPENSE_CATEGORIES if c[0] == _parent)[3].extend(_subs)
ADDED_FULL_NAMES = ({f"{p} : {s[0]}" for _v, p, _n, subs in ADDED_CATEGORIES for s in subs} |
                    {p for _v, p, n, _s in ADDED_CATEGORIES if n})

# The original keeps a special category for money that is neither income nor
# spending; reports leave it out.
NOT_AN_EXPENSE = "Not an Expense"

ACCOUNT_TYPES = [
    "Checking", "Savings", "Credit Card", "Line of Credit", "Cash",
    "Investment", "Retirement", "Asset", "Liability", "Loan", "Other",
]

# Account types whose balance counts against net worth.
LIABILITY_TYPES = {"Credit Card", "Line of Credit", "Liability", "Loan"}

FREQUENCIES = [
    "Daily", "Weekly", "Every other week", "Twice a month", "Every four weeks",
    "Monthly", "Every other month", "Every three months", "Twice a year",
    "Yearly", "Every other year", "Only once",
]
