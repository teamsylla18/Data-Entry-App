"""
Centralised activity/audit logging.
All writes go to activity_log; no second table needed.
"""
from flask import request, session
from app.db import get_db


def log(action: str, entity_type: str = None, entity_id: int = None,
        details: str = None):
    """Insert one audit row.  Commits immediately if called outside a
    route that will commit anyway; callers inside a route should let
    the route commit."""
    db = get_db()
    db.execute(
        """INSERT INTO activity_log
               (user_id, action, entity_type, entity_id, ip_address, details)
           VALUES (?, ?, ?, ?, ?, ?)""",
        [
            session.get('user_id'),
            action,
            entity_type,
            entity_id,
            request.remote_addr,
            details,
        ],
    )


def recent(limit: int = 15):
    """Return the most recent activity_log rows for the dashboard feed."""
    db = get_db()
    return db.execute(
        """SELECT al.*, u.full_name
           FROM activity_log al
           LEFT JOIN users u ON u.id = al.user_id
           ORDER BY al.created_at DESC
           LIMIT ?""",
        [limit],
    ).fetchall()
