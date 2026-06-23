from flask import Blueprint, render_template, session

from app.auth import login_required
from app.db import get_db
from app.services.activity_service import recent as recent_activity

bp = Blueprint('dashboard', __name__)


@bp.route('/dashboard')
@login_required
def index():
    db = get_db()
    role = session.get('user_role', '')

    # ── Stat card queries ──────────────────────────────────────────────────
    stats = {}

    stats['total_products'] = db.execute(
        "SELECT COUNT(*) FROM products WHERE deleted_at IS NULL"
    ).fetchone()[0]

    stats['active_clients'] = db.execute(
        "SELECT COUNT(*) FROM clients WHERE deleted_at IS NULL"
    ).fetchone()[0]

    # Total revenue = sum of all payments on non-deleted sales
    stats['total_revenue'] = db.execute(
        """SELECT COALESCE(SUM(p.amount),0)
           FROM payments p
           JOIN sales s ON s.id = p.sale_id
           WHERE s.deleted_at IS NULL"""
    ).fetchone()[0]

    # Outstanding balances = SUM(sale_amount - discount) - total payments
    row = db.execute(
        """SELECT
               COALESCE(SUM(s.sale_amount - s.discount), 0) AS total_due,
               COALESCE((
                   SELECT SUM(p2.amount)
                   FROM payments p2
                   JOIN sales s2 ON s2.id = p2.sale_id
                   WHERE s2.deleted_at IS NULL
               ), 0) AS total_paid
           FROM sales s
           WHERE s.deleted_at IS NULL"""
    ).fetchone()
    stats['outstanding'] = max(0, (row['total_due'] or 0) - (row['total_paid'] or 0))

    stats['total_sales'] = db.execute(
        "SELECT COUNT(*) FROM sales WHERE deleted_at IS NULL"
    ).fetchone()[0]

    stats['total_receipts'] = db.execute(
        "SELECT COUNT(*) FROM receipts"
    ).fetchone()[0]

    # ── Recent activity feed ────────────────────────────────────────────
    activity = recent_activity(15)

    return render_template('dashboard/index.html',
                           stats=stats, activity=activity, role=role)
