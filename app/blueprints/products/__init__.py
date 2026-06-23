from flask import (
    Blueprint, flash, redirect, render_template,
    request, url_for,
)

from app.auth import login_required, roles_required, verify_manager_password
from app.db import get_db
from app.services.activity_service import log as log_activity

bp = Blueprint('products', __name__, url_prefix='/products')

CATEGORIES = [
    ('school_management', 'School Management'),
    ('library',           'Library System'),
    ('website',           'Website'),
    ('mobile_app',        'Mobile Application'),
    ('desktop_app',       'Desktop Application'),
    ('api',               'API'),
    ('custom_software',   'Custom Software'),
    ('other',             'Other'),
]
STATUSES = [
    ('active',     'Active'),
    ('inactive',   'Inactive'),
    ('deprecated', 'Deprecated'),
]


# ─── Helpers ──────────────────────────────────────────────────────────────

def _get_product_or_404(db, product_id):
    p = db.execute(
        'SELECT * FROM products WHERE id = ? AND deleted_at IS NULL',
        [product_id],
    ).fetchone()
    if p is None:
        return None
    return p


# ─── List ───────────────────────────────────────────────────────────────

@bp.route('/')
@login_required
@roles_required('super_admin', 'administrator', 'technical_officer')
def list():
    db = get_db()
    q        = request.args.get('q', '').strip()
    category = request.args.get('category', '')
    status   = request.args.get('status', '')
    page     = max(1, int(request.args.get('page', 1)))
    per_page = 20

    filters = ['p.deleted_at IS NULL']
    params  = []
    if q:
        filters.append('p.name LIKE ?')
        params.append(f'%{q}%')
    if category:
        filters.append('p.category = ?')
        params.append(category)
    if status:
        filters.append('p.status = ?')
        params.append(status)

    where = ' AND '.join(filters)

    total = db.execute(
        f'SELECT COUNT(*) FROM products p WHERE {where}', params
    ).fetchone()[0]

    products = db.execute(
        f"""SELECT p.*,
                   (SELECT COUNT(*) FROM sales s
                    WHERE s.product_id = p.id AND s.deleted_at IS NULL) AS sale_count
            FROM products p
            WHERE {where}
            ORDER BY p.created_at DESC
            LIMIT ? OFFSET ?""",
        params + [per_page, (page - 1) * per_page],
    ).fetchall()

    total_pages = max(1, (total + per_page - 1) // per_page)
    return render_template('products/list.html',
                           products=products, q=q, category=category,
                           status=status, page=page, total_pages=total_pages,
                           total=total, categories=CATEGORIES, statuses=STATUSES)


# ─── New / Create ─────────────────────────────────────────────────────────────

@bp.route('/new', methods=['GET', 'POST'])
@login_required
@roles_required('super_admin', 'administrator', 'technical_officer')
def new():
    if request.method == 'POST':
        errors = _validate_form(request.form)
        if errors:
            for e in errors:
                flash(e, 'danger')
            return render_template('products/form.html',
                                   product=request.form, categories=CATEGORIES,
                                   statuses=STATUSES, action='new')

        db = get_db()
        cur = db.execute(
            """INSERT INTO products
               (name, category, description, date_created, launch_date,
                current_version, status, tech_stack, license_number, support_contact)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            _form_values(request.form),
        )
        db.commit()
        log_activity('product_created', 'product', cur.lastrowid,
                     details=request.form.get('name'))
        db.commit()
        flash(f'Product "{request.form["name"]}" created.', 'success')
        return redirect(url_for('products.detail', id=cur.lastrowid))

    return render_template('products/form.html',
                           product={}, categories=CATEGORIES,
                           statuses=STATUSES, action='new')


# ─── Detail ───────────────────────────────────────────────────────────────

@bp.route('/<int:id>')
@login_required
@roles_required('super_admin', 'administrator', 'technical_officer')
def detail(id):
    db = get_db()
    product = _get_product_or_404(db, id)
    if product is None:
        flash('Product not found.', 'danger')
        return redirect(url_for('products.list'))

    versions = db.execute(
        """SELECT * FROM product_versions WHERE product_id = ?
           ORDER BY release_date DESC, id DESC""",
        [id],
    ).fetchall()

    sales = db.execute(
        """SELECT s.*,
                  c.name AS client_name,
                  COALESCE((SELECT SUM(p.amount) FROM payments p WHERE p.sale_id = s.id), 0) AS amount_paid
           FROM sales s
           JOIN clients c ON c.id = s.client_id
           WHERE s.product_id = ? AND s.deleted_at IS NULL
           ORDER BY s.sale_date DESC
           LIMIT 20""",
        [id],
    ).fetchall()

    return render_template('products/detail.html',
                           product=product, versions=versions, sales=sales)


# ─── Edit ───────────────────────────────────────────────────────────────

@bp.route('/<int:id>/edit', methods=['GET', 'POST'])
@login_required
@roles_required('super_admin', 'administrator', 'technical_officer')
def edit(id):
    db = get_db()
    product = _get_product_or_404(db, id)
    if product is None:
        flash('Product not found.', 'danger')
        return redirect(url_for('products.list'))

    if request.method == 'POST':
        errors = _validate_form(request.form)
        if errors:
            for e in errors:
                flash(e, 'danger')
            return render_template('products/form.html',
                                   product=request.form, categories=CATEGORIES,
                                   statuses=STATUSES, action='edit', id=id)

        db.execute(
            """UPDATE products
               SET name=?, category=?, description=?, date_created=?,
                   launch_date=?, current_version=?, status=?,
                   tech_stack=?, license_number=?, support_contact=?
               WHERE id = ?""",
            _form_values(request.form) + [id],
        )
        db.commit()
        log_activity('product_updated', 'product', id,
                     details=request.form.get('name'))
        db.commit()
        flash('Product updated.', 'success')
        return redirect(url_for('products.detail', id=id))

    return render_template('products/form.html',
                           product=product, categories=CATEGORIES,
                           statuses=STATUSES, action='edit', id=id)


# ─── Delete ───────────────────────────────────────────────────────────────

@bp.route('/<int:id>/delete', methods=['POST'])
@login_required
@roles_required('super_admin', 'administrator')
def delete(id):
    db = get_db()
    product = _get_product_or_404(db, id)
    if product is None:
        flash('Product not found.', 'danger')
        return redirect(url_for('products.list'))

    if not verify_manager_password(request.form.get('manager_password', '')):
        flash('Invalid manager password. Deletion cancelled.', 'danger')
        return redirect(url_for('products.detail', id=id))

    db.execute(
        'UPDATE products SET deleted_at = CURRENT_TIMESTAMP WHERE id = ?', [id]
    )
    db.commit()
    log_activity('product_deleted', 'product', id, details=product['name'])
    db.commit()
    flash(f'Product "{product["name"]}" deleted.', 'success')
    return redirect(url_for('products.list'))


# ─── Add version ─────────────────────────────────────────────────────────────

@bp.route('/<int:id>/versions/add', methods=['POST'])
@login_required
@roles_required('super_admin', 'administrator', 'technical_officer')
def add_version(id):
    db = get_db()
    product = _get_product_or_404(db, id)
    if product is None:
        flash('Product not found.', 'danger')
        return redirect(url_for('products.list'))

    version_number = request.form.get('version_number', '').strip()
    if not version_number:
        flash('Version number is required.', 'danger')
        return redirect(url_for('products.detail', id=id) + '#versions')

    db.execute(
        """INSERT INTO product_versions
           (product_id, version_number, release_date, changelog,
            bug_fixes, new_features, developer_notes)
           VALUES (?,?,?,?,?,?,?)""",
        [
            id,
            version_number,
            request.form.get('release_date') or None,
            request.form.get('changelog', '').strip() or None,
            request.form.get('bug_fixes', '').strip() or None,
            request.form.get('new_features', '').strip() or None,
            request.form.get('developer_notes', '').strip() or None,
        ],
    )
    # Keep products.current_version in sync
    db.execute(
        'UPDATE products SET current_version = ? WHERE id = ?',
        [version_number, id],
    )
    db.commit()
    log_activity('version_added', 'product', id,
                 details=f'v{version_number}')
    db.commit()
    flash(f'Version {version_number} added.', 'success')
    return redirect(url_for('products.detail', id=id) + '?tab=versions')


# ─── Internal helpers ──────────────────────────────────────────────────────────

def _validate_form(form):
    errors = []
    if not form.get('name', '').strip():
        errors.append('Product name is required.')
    if form.get('category') not in [c[0] for c in CATEGORIES]:
        errors.append('Please select a valid category.')
    return errors


def _form_values(form):
    return [
        form.get('name', '').strip(),
        form.get('category', ''),
        form.get('description', '').strip() or None,
        form.get('date_created') or None,
        form.get('launch_date') or None,
        form.get('current_version', '').strip() or None,
        form.get('status', 'active'),
        form.get('tech_stack', '').strip() or None,
        form.get('license_number', '').strip() or None,
        form.get('support_contact', '').strip() or None,
    ]
