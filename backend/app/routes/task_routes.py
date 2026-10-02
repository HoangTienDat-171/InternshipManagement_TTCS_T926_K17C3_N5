import sqlite3
from datetime import date

from fastapi import APIRouter, Depends, Query, Request, Response, status

from ..database import get_db
from ..schemas import InternTaskProgressUpdate, MentorTaskCreate, MentorTaskUpdate, TaskPriority, TaskStatus
from ..security import require_role
from ..task_service import InternshipTaskService


router = APIRouter(tags=["Internship Tasks - US15"])


@router.get("/api/mentor/me/interns")
def list_my_assigned_interns(request: Request, db: sqlite3.Connection = Depends(get_db)):
    mentor = require_role(request, "Mentor")
    return InternshipTaskService(db).list_assigned_interns(mentor["ma_nguoi_dung"])


@router.post("/api/mentor/tasks", status_code=status.HTTP_201_CREATED)
def create_mentor_task(
    data: MentorTaskCreate,
    request: Request,
    db: sqlite3.Connection = Depends(get_db),
):
    mentor = require_role(request, "Mentor")
    return InternshipTaskService(db).create_task(mentor, data)


@router.get("/api/mentor/tasks")
def list_mentor_tasks(
    request: Request,
    internship_profile_id: int | None = Query(default=None, gt=0),
    task_status: TaskStatus | None = Query(default=None, alias="status"),
    priority: TaskPriority | None = None,
    due_date: date | None = None,
    db: sqlite3.Connection = Depends(get_db),
):
    mentor = require_role(request, "Mentor")
    return InternshipTaskService(db).list_mentor_tasks(
        mentor["ma_nguoi_dung"],
        profile_id=internship_profile_id,
        task_status=task_status,
        priority=priority,
        due_date=due_date,
    )


@router.put("/api/mentor/tasks/{task_id}")
def update_mentor_task(
    task_id: int,
    data: MentorTaskUpdate,
    request: Request,
    db: sqlite3.Connection = Depends(get_db),
):
    mentor = require_role(request, "Mentor")
    return InternshipTaskService(db).update_task(task_id, mentor, data)


@router.delete("/api/mentor/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_mentor_task(
    task_id: int,
    request: Request,
    db: sqlite3.Connection = Depends(get_db),
):
    mentor = require_role(request, "Mentor")
    InternshipTaskService(db).delete_task(task_id, mentor)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/api/interns/me/tasks")
def list_my_intern_tasks(request: Request, db: sqlite3.Connection = Depends(get_db)):
    intern = require_role(request, "ThucTapSinh")
    return InternshipTaskService(db).list_intern_tasks(intern["ma_nguoi_dung"])


@router.patch("/api/interns/me/tasks/{task_id}/progress")
def update_my_task_progress(
    task_id: int,
    data: InternTaskProgressUpdate,
    request: Request,
    db: sqlite3.Connection = Depends(get_db),
):
    intern = require_role(request, "ThucTapSinh")
    return InternshipTaskService(db).update_progress(task_id, intern, data)


@router.get("/api/tasks/{task_id}")
def get_task_detail(task_id: int, request: Request, db: sqlite3.Connection = Depends(get_db)):
    actor = require_role(request, "Mentor", "ThucTapSinh")
    return InternshipTaskService(db).get_task(task_id, actor)


@router.get("/api/tasks/{task_id}/progress-history")
def get_task_progress_history(task_id: int, request: Request, db: sqlite3.Connection = Depends(get_db)):
    actor = require_role(request, "Mentor", "ThucTapSinh")
    return InternshipTaskService(db).get_progress_history(task_id, actor)
