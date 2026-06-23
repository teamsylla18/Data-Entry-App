"""
Authentication blueprint + shared helpers.

Provides:
  - Blueprint 'auth'  (/auth/login, /auth/logout)
  - login_required       decorator
  - roles_required        decorator factory
  - verify_manager_password(password) -> bool
  - get_current_user()   -> dict | None
"""
import functools

from flask import (
    Blueprint, flash, g, redirect, render_template,
    request, session, url_for,
)
from werkzeug.security import check_password_hash

from app.db import get_db

bp = Blueprint('auth', __name__, url_prefix='/auth')


# ---------------------------------------------------------------------------
# Route helpers
# ---------------------------------------------------------------------------

def _load_logged_in_user():
    user_id = session.get('user_id')
    if user_id is None:
        g.user = None
    else:
        g.user = get_db().execute(
            'SELECT * FROM users WHERE id = ? AND deleted_at IS NULL',
            [user_id],
        ).fetchone()


def get_current_user():
    return g.get('user')


# ---------------------------------------------------------------------------
# Decorators
# ---------------------------------------------------------------------------

def login_required(view):
    @functools.wraps(view)
    def wrapped(**kwargs):
        if session.get('user_id') is None:
            flash('Please log in to continue.', 'warning')
            return redirect(url_for('auth.login', next=request.path))
        return view(**kwargs)
    return wrapped


def roles_required(*roles):
    """Usage:  @roles_required('super_admin', 'administrator')"""
    def decorator(view):
        @functools.wraps(view)
        def wrapped(**kwargs):
            if session.get('user_id') is None:
                flash('Please log in to continue.', 'warning')
                return redirect(url_for('auth.login'))
            if session.get('user_role') not in roles:
                flash('You do not have permission to access that page.', 'danger')
                return redirect(url_for('dashboard.index'))
            return view(**kwargs)
        return wrapped
    return decorator


def verify_manager_password(password: str) -> bool:
    """Re-verify the current user's manager password for sensitive actions."""
    uid = session.get('user_id')
    if not uid or not password:
        return False
    row = get_db().execute(
        'SELECT manager_password_hash FROM users WHERE id = ?', [uid]
    ).fetchone()
    if row is None:
        return False
    return check_password_hash(row['manager_password_hash'], password)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@bp.before_app_request
def load_logged_in_user():
    _load_logged_in_user()


@bp.route('/login', methods=['GET', 'POST'])
def login():
    if session.get('user_id'):
        return redirect(url_for('dashboard.index'))

    error = None
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        db = get_db()

        user = db.execute(
            "SELECT * FROM users WHERE email = ? AND deleted_at IS NULL",
            [email],
        ).fetchone()

        if user is None or not check_password_hash(user['password_hash'], password):
            error = 'Invalid email or password.'
            _log(db, None, 'login_failed', details=f'email={email}')
        elif user['status'] != 'active':
            error = 'Your account has been deactivated. Contact the administrator.'
        else:
            session.clear()
            session.permanent = True
            session['user_id'] = user['id']
            session['user_role'] = user['role']
            session['user_name'] = user['full_name']
            _log(db, user['id'], 'login')
            db.commit()
            next_url = request.args.get('next') or url_for('dashboard.index')
            return redirect(next_url)

    return render_template('auth/login.html', error=error)


@bp.route('/logout', methods=['POST'])
def logout():
    db = get_db()
    _log(db, session.get('user_id'), 'logout')
    db.commit()
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('auth.login'))


# ---------------------------------------------------------------------------
# Internal helper
# ---------------------------------------------------------------------------

def _log(db, user_id, action, details=None):
    db.execute(
        'INSERT INTO activity_log (user_id, action, ip_address, details) VALUES (?,?,?,?)',
        [user_id, action, request.remote_addr, details],
    )
