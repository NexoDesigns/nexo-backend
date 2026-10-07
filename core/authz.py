"""
Project access control — the single place that answers "may this user open
this project?".

Today it answers "yes, if they are authenticated", which is exactly what the
rest of the API enforces: routers/projects.py list_projects returns every
project to every authenticated user, and projects.created_by is written on
creation but never read. Nexo is, in effect, a shared workspace.

This module exists so that stays true in ONE place. Two callers depend on it:

  * routers/runs.py create_editor_link — mints the scoped token the
    architecture-editor uses to read and write a run's diagram.
  * the subdomain auth gate in nexo-frontend (src/app/api/auth/gate), which
    decides whether to let a browser load editor.nexodesign.ai at all.

They must agree. If the page gate were stricter than the token endpoint,
anyone refused at the door could mint a token for the same project and walk
in with it; if it were looser, the door would be decoration. Keeping the
predicate here means the day a real permission model lands (a
project_members table, or the engineer/admin role that already exists in the
data model and gates nothing), both close together.

In the future this will be changed when the backend and supabase is changed into a SaaS,
with organizations, users and role based access.
"""

from fastapi import HTTPException, status


def assert_can_access_project(user_id: str, project_id: str, supabase) -> None:
    """Raise unless ``user_id`` may act on ``project_id``.

    The project must exist. Beyond that, any authenticated user qualifies —
    see the module docstring for why, and for what to change here when
    per-project permissions arrive.
    """
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    project = (
        supabase.table("projects")
        .select("id")
        .eq("id", project_id)
        .execute()
    )
    if not project.data:
        raise HTTPException(status_code=404, detail="Project not found")

    # Per-project authorization goes here. Deliberately absent: enforcing
    # created_by today would be STRICTER than the dashboard, locking a
    # colleague out of the editor for a project they can otherwise open and
    # run. See docs/nexo-architecture-overview.md, known issue #3.
