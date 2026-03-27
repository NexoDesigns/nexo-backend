from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from core.security import get_current_user_id
from core.supabase import get_supabase
from models.project import (
    ProjectCreate,
    ProjectResponse,
    ProjectUpdate,
    RequirementsCreate,
    RequirementsResponse,
)

router = APIRouter(prefix="/projects", tags=["Projects"])


# ── Projects ──────────────────────────────────────────────────────────────────

@router.get("", response_model=list[ProjectResponse])
async def list_projects(
    user_id: str = Depends(get_current_user_id),
    supabase=Depends(get_supabase),
):
    """List all projects ordered by most recently updated."""
    result = (
        supabase.table("projects")
        .select("*")
        .neq("status", "deleted")
        .order("updated_at", desc=True)
        .execute()
    )
    return result.data


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(
    body: ProjectCreate,
    user_id: str = Depends(get_current_user_id),
    supabase=Depends(get_supabase),
):
    """Create a new project."""
    result = (
        supabase.table("projects")
        .insert({
            "name": body.name,
            "client_name": body.client_name,
            "description": body.description,
            "created_by": user_id,
        })
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=500, detail="Failed to create project")
    return result.data[0]


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: UUID,
    user_id: str = Depends(get_current_user_id),
    supabase=Depends(get_supabase),
):
    """Get a single project by ID."""
    result = (
        supabase.table("projects")
        .select("*")
        .eq("id", str(project_id))
        .single()
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Project not found")
    return result.data


@router.put("/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: UUID,
    body: ProjectUpdate,
    user_id: str = Depends(get_current_user_id),
    supabase=Depends(get_supabase),
):
    """Update project metadata. Only provided fields are updated."""
    updates = body.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    # updated_at is managed by Supabase trigger in production;
    # we set it explicitly here for safety.
    from datetime import datetime, timezone
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()

    result = (
        supabase.table("projects")
        .update(updates)
        .eq("id", str(project_id))
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Project not found")
    return result.data[0]


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def archive_project(
    project_id: UUID,
    user_id: str = Depends(get_current_user_id),
    supabase=Depends(get_supabase),
):
    """
    Soft-delete: marks the project as 'archived'.
    Hard deletes are not supported in the MVP.
    """
    result = (
        supabase.table("projects")
        .update({"status": "archived"})
        .eq("id", str(project_id))
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Project not found")


# ── Active runs ───────────────────────────────────────────────────────────────

@router.get("/{project_id}/active-runs")
async def list_active_runs(
    project_id: UUID,
    user_id: str = Depends(get_current_user_id),
    supabase=Depends(get_supabase),
):
    """Return all active runs for a project from project_active_runs."""
    result = (
        supabase.table("project_active_runs")
        .select("*")
        .eq("project_id", str(project_id))
        .execute()
    )
    return result.data


# ── Requirements ──────────────────────────────────────────────────────────────

@router.get("/{project_id}/requirements", response_model=RequirementsResponse | None)
async def get_requirements(
    project_id: UUID,
    user_id: str = Depends(get_current_user_id),
    supabase=Depends(get_supabase),
):
    """Get the requirements for a project. Returns null if none exist yet."""
    result = (
        supabase.table("project_requirements")
        .select("*")
        .eq("project_id", str(project_id))
        .execute()
    )
    if not result.data:
        return None
    return result.data[0]


@router.post(
    "/{project_id}/requirements",
    response_model=RequirementsResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upsert_requirements(
    project_id: UUID,
    body: RequirementsCreate,
    user_id: str = Depends(get_current_user_id),
    supabase=Depends(get_supabase),
):
    """
    Create or replace the requirements for a project.
    If requirements already exist, they are deleted and re-created.
    This keeps the logic simple: requirements are treated as a single
    mutable document per project, not a versioned history.
    """
    # Check project exists
    project_check = (
        supabase.table("projects")
        .select("id")
        .eq("id", str(project_id))
        .single()
        .execute()
    )
    if not project_check.data:
        raise HTTPException(status_code=404, detail="Project not found")

    # Delete existing requirements if any
    supabase.table("project_requirements").delete().eq(
        "project_id", str(project_id)
    ).execute()

    # Insert new requirements
    payload = body.model_dump(exclude_none=True)
    payload["project_id"] = str(project_id)

    result = (
        supabase.table("project_requirements")
        .insert(payload)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=500, detail="Failed to save requirements")
    return result.data[0]