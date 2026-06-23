from flask import (
    Blueprint, flash, redirect, render_template,
    request, session, url_for,
)

from app.auth import login_required, roles_required, verify_manager_password
from app.db import get_db
from app.services.activity_service import log as log_activity

bp = Blueprint('sales', __name__, url_prefix='/sales')

PAYMENT_METHODS = [
    ('cash',          'Cash'),
    ('bank_transfer', 'Bank Transfer'),
    ('mobile_money',  'Mobile Money'),
    ('cheque',        'Cheque'),
    ('other',         'Other'),
]


def _sale_with_totals(db, sale_id):
    """Return a sale row augmented with computed amount_paid and balance."""
    row = db.execute(
        """SELECT s.*,
                  p.name  AS product_name,
                  c.name  AS client_name,
                  c.organization AS client_org,
                  COALESCE(
                      (SELECT SUM(py.amount) FROM payments py WHERE py.sale_id = s.id),
                      0
                  ) AS amount_paid
           FROM sales s
           JOIN products p ON p.id = s.product_id
           JOIN clients  c ON c.id = s.client_id
           WHERE s.id = ? AND s.deleted_at IS NULL""",
        [sale_id],
    ).fetchone()
    return row


# ─── List ──────────────────────────────────────────────────────────────

@bp.route('/')
@login_required
@roles_required('super_admin', 'administrator', 'finance_officer', 'marketing_manager')
def list():
    db = get_db()
    q          = request.args.get('q', '').strip()
    product_id = request.args.get('product_id', '')
    client_id  = request.args.get('client_id', '')
    date_from  = request.args.get('date_from', '')
    date_to    = request.args.get('date_to', '')
    page       = max(1, int(request.args.get('page', 1)))
    per_page   = 20

    filters = ['s.deleted_at IS NULL']
    params  = []
    if q:
        filters.append('(c.name LIKE ? OR p.name LIKE ?)')
        params += [f'%{q}%', f'%{q}%']
    if product_id:
        filters.append('s.product_id = ?')
        params.append(product_id)
    if client_id:
        filters.append('s.client_id = ?')
        params.append(client_id)
    if date_from:
        filters.append('s.sale_date >= ?')
        params.append(date_from)
    if date_to:
        filters.append('s.sale_date <= ?')
        params.append(date_to)

    where = ' AND '.join(filters)

    total = db.execute(
        f"""SELECT COUNT(*) FROM sales s
            JOIN clients  c ON c.id = s.client_id
            JOIN products p ON p.id = s.product_id
            WHERE {where}""",
        params,
    ).fetchone()[0]

    sales = db.execute(
        f"""SELECT s.*,
                   c.name  AS client_name,
                   p.name  AS product_name,
                   COALESCE(
                       (SELECT SUM(py.amount) FROM payments py WHERE py.sale_id = s.id),
                       0
                   ) AS amount_paid
            FROM sales s
            JOIN clients  c ON c.id = s.client_id
            JOIN products p ON p.id = s.product_id
            WHERE {where}
            ORDER BY s.sale_date DESC, s.id DESC
            LIMIT ? OFFSET ?""",
        params + [per_page, (page - 1) * per_page],
    ).fetchall()

    # Summary totals for the filtered set (all pages)
    totals = db.execute(
        f"""SELECT
               COALESCE(SUM(s.sale_amount - COALESCE(s.discount,0)), 0) AS total_due,
               COALESCE((
                   SELECT SUM(py.amount)
                   FROM payments py
                   JOIN sales s2 ON s2.id = py.sale_id
                   JOIN clients c2 ON c2.id = s2.client_id
                   JOIN products p2 ON p2.id = s2.product_id
                   WHERE {where.replace('s.', 's2.').replace('c.', 'c2.').replace('p.', 'p2.')}
               ), 0) AS total_paid
            FROM sales s
            JOIN clients  c ON c.id = s.client_id
            JOIN products p ON p.id = s.product_id
            WHERE {where}""",
        params + params,
    ).fetchone()

    products = db.execute(
        "SELECT id, name FROM products WHERE deleted_at IS NULL ORDER BY name"
    ).fetchall()
    clients = db.execute(
        "SELECT id, name FROM clients WHERE deleted_at IS NULL ORDER BY name"
    ).fetchall()

    total_pages = max(1, (total + per_page - 1) // per_page)
    return render_template('sales/list.html',
                           sales=sales, q=q, product_id=product_id,
                           client_id=client_id, date_from=date_from, date_to=date_to,
                           page=page, total_pages=total_pages, total=total,
                           totals=totals, products=products, clients=clients,
                           payment_methods=PAYMENT_METHODS)


# ─── New Sale ─────────────────────────────────────────────────────────────

@bp.route('/new', methods=['GET', 'POST'])
@login_required
@roles_required('super_admin', 'administrator', 'finance_officer', 'marketing_manager')
def new():
    db = get_db()
    products = db.execute(
        "SELECT id, name FROM products WHERE deleted_at IS NULL ORDER BY name"
    ).fetchall()
    clients = db.execute(
        "SELECT id, name FROM clients WHERE deleted_at IS NULL ORDER BY name"
    ).fetchall()

    # Pre-fill client from query param (e.g. from client detail page)
    default_client = request.args.get('client_id', '')

    if request.method == 'POST':
        errors = _validate_sale_form(request.form)
        if errors:
            for e in errors:
                flash(e, 'danger')
            return render_template('sales/form.html',
                                   sale=request.form, products=products,
                                   clients=clients, payment_methods=PAYMENT_METHODS,
                                   action='new')

        sale_amount = int(request.form.get('sale_amount', 0))
        discount    = int(request.form.get('discount', 0) or 0)
        first_payment = int(request.form.get('first_payment', 0) or 0)

        cur = db.execute(
            """INSERT INTO sales
               (product_id, client_id, sale_date, sale_amount, discount,
                payment_method, notes)
               VALUES (?,?,?,?,?,?,?)""",
            [
                request.form['product_id'],
                request.form['client_id'],
                request.form.get('sale_date') or None,
                sale_amount,
                discount,
                request.form['payment_method'],
                request.form.get('notes', '').strip() or None,
            ],
        )
        sale_id = cur.lastrowid

        # Optional first payment recorded immediately
        if first_payment > 0:
            db.execute(
                """INSERT INTO payments
                   (sale_id, amount, payment_date, payment_method, recorded_by)
                   VALUES (?,?,?,?,?)""",
                [
                    sale_id,
                    first_payment,
                    request.form.get('sale_date') or None,
                    request.form['payment_method'],
                    session['user_id'],
                ],
            )
            log_activity('payment_recorded', 'payment', sale_id,
                         details=f'GNF {first_payment:,} (initial payment)')

        db.commit()
        log_activity('sale_created', 'sale', sale_id,
                     details=f'{request.form.get("product_id")} — GNF {sale_amount:,}')
        db.commit()
        flash('Sale recorded successfully.', 'success')
        return redirect(url_for('sales.detail', id=sale_id))

    return render_template('sales/form.html',
                           sale={'client_id': default_client}, products=products,
                           clients=clients, payment_methods=PAYMENT_METHODS,
                           action='new')


# ─── Detail ───────────────────────────────────────────────────────────────

@bp.route('/<int:id>')
@login_required
@roles_required('super_admin', 'administrator', 'finance_officer', 'marketing_manager')
def detail(id):
    db = get_db()
    sale = _sale_with_totals(db, id)
    if sale is None:
        flash('Sale not found.', 'danger')
        return redirect(url_for('sales.list'))

    payments = db.execute(
        """SELECT py.*, u.full_name AS recorded_by_name
           FROM payments py
           JOIN users u ON u.id = py.recorded_by
           WHERE py.sale_id = ?
           ORDER BY py.payment_date, py.id""",
        [id],
    ).fetchall()

    receipts = db.execute(
        'SELECT * FROM receipts WHERE sale_id = ? ORDER BY created_at DESC',
        [id],
    ).fetchall()

    balance = (sale['sale_amount'] - (sale['discount'] or 0)) - sale['amount_paid']
    return render_template('sales/detail.html',
                           sale=sale, payments=payments, receipts=receipts,
                           balance=balance, payment_methods=PAYMENT_METHODS)


# ─── Record Payment ───────────────────────────────────────────────────────────

@bp.route('/<int:id>/payment', methods=['POST'])
@login_required
@roles_required('super_admin', 'administrator', 'finance_officer', 'marketing_manager')
def add_payment(id):
    db = get_db()
    sale = _sale_with_totals(db, id)
    if sale is None:
        flash('Sale not found.', 'danger')
        return redirect(url_for('sales.list'))

    if not verify_manager_password(request.form.get('manager_password', '')):
        flash('Invalid manager password. Payment not recorded.', 'danger')
        return redirect(url_for('sales.detail', id=id))

    amount = int(request.form.get('amount', 0) or 0)
    if amount <= 0:
        flash('Payment amount must be greater than zero.', 'danger')
        return redirect(url_for('sales.detail', id=id))

    db.execute(
        """INSERT INTO payments
           (sale_id, amount, payment_date, payment_method, notes, recorded_by)
           VALUES (?,?,?,?,?,?)""",
        [
            id,
            amount,
            request.form.get('payment_date') or None,
            request.form.get('payment_method', 'cash'),
            request.form.get('notes', '').strip() or None,
            session['user_id'],
        ],
    )
    db.commit()
    log_activity('payment_recorded', 'sale', id,
                 details=f'GNF {amount:,}')
    db.commit()
    flash(f'Payment of {amount:,} GNF recorded.', 'success')
    return redirect(url_for('sales.detail', id=id))


# ─── Delete Sale ────────────────────────────────────────────────────────────

@bp.route('/<int:id>/delete', methods=['POST'])
@login_required
@roles_required('super_admin', 'administrator')
def delete(id):
    db = get_db()
    sale = _sale_with_totals(db, id)
    if sale is None:
        flash('Sale not found.', 'danger')
        return redirect(url_for('sales.list'))

    if not verify_manager_password(request.form.get('manager_password', '')):
        flash('Invalid manager password. Deletion cancelled.', 'danger')
        return redirect(url_for('sales.detail', id=id))

    db.execute('UPDATE sales SET deleted_at = CURRENT_TIMESTAMP WHERE id = ?', [id])
    db.commit()
    log_activity('sale_deleted', 'sale', id,
                 details=f'{sale["product_name"]} — {sale["client_name"]}')
    db.commit()
    flash('Sale deleted.', 'success')
    return redirect(url_for('sales.list'))


# ─── Revenue Reports ──────────────────────────────────────────────────────────

@bp.route('/reports')
@login_required
@roles_required('super_admin', 'administrator', 'finance_officer')
def reports():
    db = get_db()

    # Monthly revenue (payments in last 12 months)
    monthly = db.execute(
        """SELECT strftime('%Y-%m', py.payment_date) AS month,
                  SUM(py.amount) AS revenue
           FROM payments py
           JOIN sales s ON s.id = py.sale_id
           WHERE s.deleted_at IS NULL
             AND py.payment_date >= date('now', '-11 months')
           GROUP BY month
           ORDER BY month""",
    ).fetchall()

    # Per-product revenue
    by_product = db.execute(
        """SELECT p.name,
                  COALESCE(SUM(py.amount), 0) AS revenue,
                  COUNT(DISTINCT s.id) AS sale_count
           FROM products p
           LEFT JOIN sales s ON s.product_id = p.id AND s.deleted_at IS NULL
           LEFT JOIN payments py ON py.sale_id = s.id
           WHERE p.deleted_at IS NULL
           GROUP BY p.id
           ORDER BY revenue DESC
           LIMIT 10""",
    ).fetchall()

    # Outstanding by client
    outstanding = db.execute(
        """SELECT c.name AS client_name,
                  SUM(s.sale_amount - COALESCE(s.discount,0)) AS total_due,
                  COALESCE(SUM(py.amount), 0) AS total_paid
           FROM clients c
           JOIN sales s ON s.client_id = c.id AND s.deleted_at IS NULL
           LEFT JOIN payments py ON py.sale_id = s.id
           WHERE c.deleted_at IS NULL
           GROUP BY c.id
           HAVING total_due > total_paid
           ORDER BY (total_due - total_paid) DESC
           LIMIT 20""",
    ).fetchall()

    return render_template('sales/reports.html',
                           monthly=monthly, by_product=by_product,
                           outstanding=outstanding)


# ─── Validation helpers ─────────────────────────────────────────────────────────

def _validate_sale_form(form):
    errors = []
    if not form.get('product_id'):
        errors.append('Please select a product.')
    if not form.get('client_id'):
        errors.append('Please select a client.')
    try:
        amt = int(form.get('sale_amount', 0))
        if amt <= 0:
            errors.append('Sale amount must be greater than zero.')
    except ValueError:
        errors.append('Sale amount must be a whole number.')
    try:
        disc = int(form.get('discount', 0) or 0)
        amt  = int(form.get('sale_amount', 0) or 0)
        if disc < 0:
            errors.append('Discount cannot be negative.')
        if disc > amt:
            errors.append('Discount cannot exceed the sale amount.')
    except ValueError:
        errors.append('Discount must be a whole number.')
    if form.get('payment_method') not in [m[0] for m in PAYMENT_METHODS]:
        errors.append('Please select a valid payment method.')
    return errors
