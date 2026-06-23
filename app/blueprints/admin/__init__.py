import shutil
from datetime import datetime
from pathlib import Path

from flask import (
    Blueprint, flash, redirect, render_template,
    request, url_for, current_app,
)
from werkzeug.security import generate_password_hash

from app.auth import login_required, roles_required
from app.db import get_db
from app.services.activity_service import log as log_activity

bp = Blueprint('admin', __name__, url_prefix='/admin')

ROLES = [
    ('super_admin',       'Super Admin'),
    ('administrator',     'Administrator'),
    ('finance_officer',   'Finance Officer'),
    ('technical_officer', 'Technical Officer'),
    ('marketing_manager', 'Marketing Manager'),
]


@bp.route('/users')
@login_required
@roles_required('super_admin')
def users():
    db   = get_db()
    page = max(1, int(request.args.get('page', 1)))
    per_page = 30
    total = db.execute("SELECT COUNT(*) FROM users WHERE deleted_at IS NULL").fetchone()[0]
    all_users = db.execute(
        "SELECT * FROM users WHERE deleted_at IS NULL ORDER BY created_at DESC LIMIT ? OFFSET ?",
        [per_page, (page - 1) * per_page],
    ).fetchall()
    total_pages = max(1, (total + per_page - 1) // per_page)
    return render_template('admin/users.html', users=all_users,
                           roles=ROLES, page=page, total_pages=total_pages)


@bp.route('/users/new', methods=['POST'])
@login_required
@roles_required('super_admin')
def new_user():
    db = get_db()
    name    = request.form.get('full_name', '').strip()
    email   = request.form.get('email', '').strip().lower()
    role    = request.form.get('role', '')
    pw      = request.form.get('password', '')
    mgr_pw  = request.form.get('manager_password', '')

    errors = []
    if not name:            errors.append('Full name is required.')
    if not email:           errors.append('Email is required.')
    if not role:            errors.append('Role is required.')
    if len(pw) < 8:         errors.append('Password must be at least 8 characters.')
    if len(mgr_pw) < 6:     errors.append('Manager password must be at least 6 characters.')

    if not errors:
        exists = db.execute('SELECT id FROM users WHERE email = ?', [email]).fetchone()
        if exists:
            errors.append(f'Email {email} is already registered.')

    if errors:
        for e in errors:
            flash(e, 'danger')
        return redirect(url_for('admin.users'))

    db.execute(
        """INSERT INTO users (full_name, email, password_hash, manager_password_hash, role)
           VALUES (?,?,?,?,?)""",
        [name, email,
         generate_password_hash(pw),
         generate_password_hash(mgr_pw),
         role],
    )
    db.commit()
    log_activity('user_created', 'user', details=f'{name} ({role})')
    db.commit()
    flash(f'Account created for {name}.', 'success')
    return redirect(url_for('admin.users'))


@bp.route('/users/<int:id>/toggle-status', methods=['POST'])
@login_required
@roles_required('super_admin')
def toggle_status(id):
    db   = get_db()
    user = db.execute('SELECT * FROM users WHERE id = ?', [id]).fetchone()
    if user is None:
        flash('User not found.', 'danger')
        return redirect(url_for('admin.users'))
    new_status = 'inactive' if user['status'] == 'active' else 'active'
    db.execute('UPDATE users SET status = ? WHERE id = ?', [new_status, id])
    db.commit()
    log_activity('user_status_changed', 'user', id, details=new_status)
    db.commit()
    flash(f'{user["full_name"]} set to {new_status}.', 'success')
    return redirect(url_for('admin.users'))


@bp.route('/users/<int:id>/reset-password', methods=['POST'])
@login_required
@roles_required('super_admin')
def reset_password(id):
    db   = get_db()
    user = db.execute('SELECT * FROM users WHERE id = ?', [id]).fetchone()
    if user is None:
        flash('User not found.', 'danger')
        return redirect(url_for('admin.users'))

    new_pw = request.form.get('new_password', '')
    if len(new_pw) < 8:
        flash('New password must be at least 8 characters.', 'danger')
        return redirect(url_for('admin.users'))

    db.execute('UPDATE users SET password_hash = ? WHERE id = ?',
               [generate_password_hash(new_pw), id])
    db.commit()
    log_activity('user_password_reset', 'user', id,
                 details=user['full_name'])
    db.commit()
    flash(f'Password reset for {user["full_name"]}.', 'success')
    return redirect(url_for('admin.users'))


@bp.route('/settings')
@login_required
@roles_required('super_admin')
def settings():
    db = get_db()
    audit = db.execute(
        """SELECT al.*, u.full_name
           FROM activity_log al
           LEFT JOIN users u ON u.id = al.user_id
           ORDER BY al.created_at DESC
           LIMIT 50""",
    ).fetchall()
    return render_template('admin/settings.html', audit=audit)


@bp.route('/backup', methods=['POST'])
@login_required
@roles_required('super_admin')
def backup():
    db_path      = Path(current_app.config['DATABASE'])
    backup_dir   = Path(current_app.config['BACKUPS_FOLDER'])
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp        = datetime.now().strftime('%Y%m%d_%H%M%S')
    dest         = backup_dir / f'tcc_{stamp}.db'
    shutil.copy2(db_path, dest)
    # Keep last 7 backups
    backups = sorted(backup_dir.glob('tcc_*.db'))
    for old in backups[:-7]:
        old.unlink(missing_ok=True)
    log_activity('manual_backup', details=str(dest.name))
    get_db().commit()
    flash(f'Backup created: {dest.name}', 'success')
    return redirect(url_for('admin.settings'))
