import os
from flask import Flask
from flask_wtf.csrf import CSRFProtect

csrf = CSRFProtect()


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)

    # ── Config ───────────────────────────────────────────────────────────────
    from app.config import Config
    app.config.from_object(Config)
    if test_config is not None:
        app.config.update(test_config)

    # Ensure run-time directories exist
    for key in ('RECEIPTS_FOLDER', 'BACKUPS_FOLDER', 'UPLOAD_FOLDER'):
        os.makedirs(app.config[key], exist_ok=True)

    # ── Extensions ───────────────────────────────────────────────────────────
    csrf.init_app(app)

    from app.db import init_app as db_init_app, init_db, get_db
    db_init_app(app)

    # Auto-initialise schema on first boot (idempotent CREATE IF NOT EXISTS)
    with app.app_context():
        from pathlib import Path
        db_path = Path(app.config['DATABASE'])
        if not db_path.exists() or db_path.stat().st_size == 0:
            init_db(app)
        else:
            # Still run to pick up any new tables added in schema.sql
            init_db(app)

    # ── Jinja helpers ────────────────────────────────────────────────────────
    from app.utils.helpers import register_helpers
    register_helpers(app)

    # ── Blueprints ───────────────────────────────────────────────────────────
    from app.auth import bp as auth_bp
    app.register_blueprint(auth_bp)

    from app.blueprints.dashboard import bp as dashboard_bp
    app.register_blueprint(dashboard_bp)

    from app.blueprints.products import bp as products_bp
    app.register_blueprint(products_bp)

    from app.blueprints.clients import bp as clients_bp
    app.register_blueprint(clients_bp)

    from app.blueprints.sales import bp as sales_bp
    app.register_blueprint(sales_bp)

    from app.blueprints.receipts import bp as receipts_bp
    app.register_blueprint(receipts_bp)

    from app.blueprints.admin import bp as admin_bp
    app.register_blueprint(admin_bp)

    # ── Root redirect ────────────────────────────────────────────────────────
    from flask import redirect, url_for
    @app.route('/')
    def index():
        return redirect(url_for('dashboard.index'))

    return app
