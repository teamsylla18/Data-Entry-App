import os

from flask import (
    Blueprint, abort, flash, redirect, render_template,
    request, send_file, url_for,
)

from app.auth import login_required, roles_required
from app.db import get_db
from app.services import receipt_service
from app.services.activity_service import log as log_activity

bp = Blueprint('receipts', __name__, url_prefix='/receipts')


@bp.route('/')
@login_required
@roles_required('super_admin', 'administrator', 'finance_officer')
def list():
    db      = get_db()
    q       = request.args.get('q', '').strip()
    page    = max(1, int(request.args.get('page', 1)))
    per_page = 20

    filters = ['1=1']
    params  = []
    if q:
        filters.append('(r.receipt_number LIKE ? OR c.name LIKE ?)')
        params += [f'%{q}%', f'%{q}%']

    where = ' AND '.join(filters)
    total = db.execute(
        f"""SELECT COUNT(*) FROM receipts r
            JOIN sales s ON s.id = r.sale_id
            JOIN clients c ON c.id = s.client_id
            WHERE {where}""",
        params,
    ).fetchone()[0]

    receipts = db.execute(
        f"""SELECT r.*,
                   c.name AS client_name,
                   p.name AS product_name
            FROM receipts r
            JOIN sales s   ON s.id = r.sale_id
            JOIN clients c ON c.id = s.client_id
            JOIN products p ON p.id = s.product_id
            WHERE {where}
            ORDER BY r.created_at DESC
            LIMIT ? OFFSET ?""",
        params + [per_page, (page - 1) * per_page],
    ).fetchall()

    total_pages = max(1, (total + per_page - 1) // per_page)
    return render_template('receipts/list.html', receipts=receipts, q=q,
                           page=page, total_pages=total_pages, total=total)


@bp.route('/generate/<int:sale_id>', methods=['GET', 'POST'])
@login_required
@roles_required('super_admin', 'administrator', 'finance_officer')
def generate(sale_id):
    db = get_db()

    sale = db.execute(
        """SELECT s.*,
                  c.name AS client_name,
                  p.name AS product_name
           FROM sales s
           JOIN clients  c ON c.id = s.client_id
           JOIN products p ON p.id = s.product_id
           WHERE s.id = ? AND s.deleted_at IS NULL""",
        [sale_id],
    ).fetchone()
    if sale is None:
        flash('Sale not found.', 'danger')
        return redirect(url_for('sales.list'))

    payments = db.execute(
        'SELECT * FROM payments WHERE sale_id = ? ORDER BY payment_date, id',
        [sale_id],
    ).fetchall()
    amount_paid = sum(p['amount'] for p in payments)

    if request.method == 'POST':
        receipt_amount = int(request.form.get('amount', amount_paid) or amount_paid)
        if receipt_amount <= 0:
            flash('Receipt amount must be greater than zero.', 'danger')
            return redirect(url_for('receipts.generate', sale_id=sale_id))

        receipt_number = receipt_service.next_receipt_number(db)
        qr_payload = (
            f'TCC/{receipt_number}/{sale["client_name"]}/'
            f'{sale["product_name"]}/{receipt_amount}'
        )

        # Generate PDF
        client_row  = db.execute('SELECT * FROM clients WHERE id = ?', [sale['client_id']]).fetchone()
        product_row = db.execute('SELECT * FROM products WHERE id = ?', [sale['product_id']]).fetchone()

        # Build a receipt-like dict for the PDF service
        temp_receipt = {
            'receipt_number': receipt_number,
            'issue_date': request.form.get('issue_date') or None,
            'qr_payload': qr_payload,
        }
        try:
            pdf_filename = receipt_service.generate_pdf(
                temp_receipt, sale, client_row, product_row, payments
            )
        except Exception as e:
            flash(f'PDF generation failed: {e}', 'danger')
            pdf_filename = None

        cur = db.execute(
            """INSERT INTO receipts
               (receipt_number, sale_id, issue_date, amount, qr_payload, pdf_path)
               VALUES (?,?,?,?,?,?)""",
            [
                receipt_number,
                sale_id,
                request.form.get('issue_date') or None,
                receipt_amount,
                qr_payload,
                pdf_filename,
            ],
        )
        db.commit()
        log_activity('receipt_generated', 'receipt', cur.lastrowid,
                     details=receipt_number)
        db.commit()
        flash(f'Receipt {receipt_number} generated.', 'success')
        return redirect(url_for('receipts.view', id=cur.lastrowid))

    return render_template('receipts/generate.html', sale=sale,
                           amount_paid=amount_paid, payments=payments)


@bp.route('/<int:id>')
@login_required
@roles_required('super_admin', 'administrator', 'finance_officer')
def view(id):
    db = get_db()
    receipt = db.execute(
        """SELECT r.*,
                  c.name  AS client_name,
                  c.organization AS client_org,
                  c.phone AS client_phone,
                  p.name  AS product_name,
                  p.category AS product_category,
                  s.sale_amount, s.discount, s.payment_method,
                  s.client_id, s.product_id
           FROM receipts r
           JOIN sales    s ON s.id = r.sale_id
           JOIN clients  c ON c.id = s.client_id
           JOIN products p ON p.id = s.product_id
           WHERE r.id = ?""",
        [id],
    ).fetchone()
    if receipt is None:
        flash('Receipt not found.', 'danger')
        return redirect(url_for('receipts.list'))

    payments = db.execute(
        'SELECT * FROM payments WHERE sale_id = ? ORDER BY payment_date',
        [receipt['sale_id']],
    ).fetchall()
    amount_paid = sum(p['amount'] for p in payments)
    balance = (receipt['sale_amount'] - (receipt['discount'] or 0)) - amount_paid

    return render_template('receipts/view.html', receipt=receipt,
                           payments=payments, amount_paid=amount_paid,
                           balance=balance)


@bp.route('/<int:id>/pdf')
@login_required
@roles_required('super_admin', 'administrator', 'finance_officer')
def download_pdf(id):
    db = get_db()
    receipt = db.execute(
        'SELECT * FROM receipts WHERE id = ?', [id]
    ).fetchone()
    if receipt is None:
        abort(404)
    if not receipt['pdf_path']:
        flash('PDF not available for this receipt.', 'warning')
        return redirect(url_for('receipts.view', id=id))

    pdf_dir  = __import__('flask').current_app.config['RECEIPTS_FOLDER']
    pdf_path = os.path.join(pdf_dir, receipt['pdf_path'])
    if not os.path.exists(pdf_path):
        flash('PDF file not found on server.', 'danger')
        return redirect(url_for('receipts.view', id=id))

    return send_file(pdf_path, as_attachment=True,
                     download_name=f"{receipt['receipt_number']}.pdf",
                     mimetype='application/pdf')
