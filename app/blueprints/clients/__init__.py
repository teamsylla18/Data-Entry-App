from flask import (
    Blueprint, flash, redirect, render_template,
    request, url_for,
)

from app.auth import login_required, roles_required, verify_manager_password
from app.db import get_db
from app.services.activity_service import log as log_activity

bp = Blueprint('clients', __name__, url_prefix='/clients')


def _get_client_or_404(db, client_id):
    return db.execute(
        'SELECT * FROM clients WHERE id = ? AND deleted_at IS NULL',
        [client_id],
    ).fetchone()


@bp.route('/')
@login_required
@roles_required('super_admin', 'administrator', 'finance_officer', 'marketing_manager')
def list():
    db  = get_db()
    q   = request.args.get('q', '').strip()
    page = max(1, int(request.args.get('page', 1)))
    per_page = 20

    filters = ['c.deleted_at IS NULL']
    params  = []
    if q:
        filters.append('(c.name LIKE ? OR c.organization LIKE ? OR c.email LIKE ?)')
        params += [f'%{q}%', f'%{q}%', f'%{q}%']

    where = ' AND '.join(filters)
    total = db.execute(f'SELECT COUNT(*) FROM clients c WHERE {where}', params).fetchone()[0]

    clients = db.execute(
        f"""SELECT c.*,
                   (SELECT COUNT(*) FROM sales s WHERE s.client_id = c.id AND s.deleted_at IS NULL) AS sale_count,
                   COALESCE((
                       SELECT SUM(p.amount)
                       FROM payments p JOIN sales s ON s.id = p.sale_id
                       WHERE s.client_id = c.id AND s.deleted_at IS NULL
                   ), 0) AS total_paid
            FROM clients c
            WHERE {where}
            ORDER BY c.created_at DESC
            LIMIT ? OFFSET ?""",
        params + [per_page, (page - 1) * per_page],
    ).fetchall()

    total_pages = max(1, (total + per_page - 1) // per_page)
    return render_template('clients/list.html', clients=clients, q=q,
                           page=page, total_pages=total_pages, total=total)


@bp.route('/new', methods=['GET', 'POST'])
@login_required
@roles_required('super_admin', 'administrator', 'finance_officer', 'marketing_manager')
def new():
    if request.method == 'POST':
        errors = _validate_form(request.form)
        if errors:
            for e in errors:
                flash(e, 'danger')
            return render_template('clients/form.html', client=request.form, action='new')

        db = get_db()
        cur = db.execute(
            """INSERT INTO clients
               (name, organization, phone, email, country, address,
                date_registered, contract_info, notes)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            _form_values(request.form),
        )
        db.commit()
        log_activity('client_created', 'client', cur.lastrowid,
                     details=request.form.get('name'))
        db.commit()
        flash(f'Client "{request.form["name"]}" added.', 'success')
        return redirect(url_for('clients.detail', id=cur.lastrowid))

    return render_template('clients/form.html', client={}, action='new')


@bp.route('/<int:id>')
@login_required
@roles_required('super_admin', 'administrator', 'finance_officer', 'marketing_manager')
def detail(id):
    db = get_db()
    client = _get_client_or_404(db, id)
    if client is None:
        flash('Client not found.', 'danger')
        return redirect(url_for('clients.list'))

    sales = db.execute(
        """SELECT s.*,
                  pr.name AS product_name,
                  COALESCE((SELECT SUM(p.amount) FROM payments p WHERE p.sale_id = s.id), 0) AS amount_paid
           FROM sales s
           JOIN products pr ON pr.id = s.product_id
           WHERE s.client_id = ? AND s.deleted_at IS NULL
           ORDER BY s.sale_date DESC""",
        [id],
    ).fetchall()

    receipts = db.execute(
        """SELECT r.*
           FROM receipts r
           JOIN sales s ON s.id = r.sale_id
           WHERE s.client_id = ?
           ORDER BY r.created_at DESC
           LIMIT 20""",
        [id],
    ).fetchall()

    # Totals
    total_due  = sum((s['sale_amount'] - (s['discount'] or 0)) for s in sales)
    total_paid = sum(s['amount_paid'] for s in sales)
    outstanding = max(0, total_due - total_paid)

    return render_template('clients/detail.html',
                           client=client, sales=sales, receipts=receipts,
                           total_due=total_due, total_paid=total_paid,
                           outstanding=outstanding)


@bp.route('/<int:id>/edit', methods=['GET', 'POST'])
@login_required
@roles_required('super_admin', 'administrator', 'finance_officer', 'marketing_manager')
def edit(id):
    db = get_db()
    client = _get_client_or_404(db, id)
    if client is None:
        flash('Client not found.', 'danger')
        return redirect(url_for('clients.list'))

    if request.method == 'POST':
        errors = _validate_form(request.form)
        if errors:
            for e in errors:
                flash(e, 'danger')
            return render_template('clients/form.html', client=request.form,
                                   action='edit', id=id)

        db.execute(
            """UPDATE clients
               SET name=?, organization=?, phone=?, email=?, country=?,
                   address=?, date_registered=?, contract_info=?, notes=?
               WHERE id = ?""",
            _form_values(request.form) + [id],
        )
        db.commit()
        log_activity('client_updated', 'client', id,
                     details=request.form.get('name'))
        db.commit()
        flash('Client updated.', 'success')
        return redirect(url_for('clients.detail', id=id))

    return render_template('clients/form.html', client=client,
                           action='edit', id=id)


@bp.route('/<int:id>/delete', methods=['POST'])
@login_required
@roles_required('super_admin', 'administrator')
def delete(id):
    db = get_db()
    client = _get_client_or_404(db, id)
    if client is None:
        flash('Client not found.', 'danger')
        return redirect(url_for('clients.list'))

    if not verify_manager_password(request.form.get('manager_password', '')):
        flash('Invalid manager password. Deletion cancelled.', 'danger')
        return redirect(url_for('clients.detail', id=id))

    db.execute('UPDATE clients SET deleted_at = CURRENT_TIMESTAMP WHERE id = ?', [id])
    db.commit()
    log_activity('client_deleted', 'client', id, details=client['name'])
    db.commit()
    flash(f'Client "{client["name"]}" deleted.', 'success')
    return redirect(url_for('clients.list'))


def _validate_form(form):
    errors = []
    if not form.get('name', '').strip():
        errors.append('Client name is required.')
    return errors


def _form_values(form):
    return [
        form.get('name', '').strip(),
        form.get('organization', '').strip() or None,
        form.get('phone', '').strip() or None,
        form.get('email', '').strip() or None,
        form.get('country', '').strip() or None,
        form.get('address', '').strip() or None,
        form.get('date_registered') or None,
        form.get('contract_info', '').strip() or None,
        form.get('notes', '').strip() or None,
    ]
