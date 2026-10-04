from typing import Literal

from fastapi import APIRouter, Depends, Query, Request, status

from ..database import get_db
from ..evaluation_service import InternEvaluationService
from ..schemas import InternEvaluationCreate, InternEvaluationUpdate
from ..security import require_role


router = APIRouter(tags=["Intern Evaluations - US19"])


@router.get("/api/mentor/me/evaluations")
def list_mentor_evaluations(
    request: Request,
    internship_profile_id: int | None = Query(default=None, gt=0),
    program_id: int | None = Query(default=None, gt=0),
    evaluation_period: Literal["MIDTERM", "FINAL"] | None = None,
    db=Depends(get_db),
):
    mentor = require_role(request, "Mentor")
    return InternEvaluationService(db).list_for_mentor(
        mentor["ma_nguoi_dung"],
        profile_id=internship_profile_id,
        program_id=program_id,
        evaluation_period=evaluation_period,
    )


@router.get("/api/mentor/me/evaluations/{evaluation_id}")
def get_mentor_evaluation(evaluation_id: int, request: Request, db=Depends(get_db)):
    mentor = require_role(request, "Mentor")
    return InternEvaluationService(db).get_for_mentor(evaluation_id, mentor["ma_nguoi_dung"])


@router.post("/api/mentor/me/evaluations", status_code=status.HTTP_201_CREATED)
def create_mentor_evaluation(data: InternEvaluationCreate, request: Request, db=Depends(get_db)):
    mentor = require_role(request, "Mentor")
    return InternEvaluationService(db).create(mentor["ma_nguoi_dung"], data)


@router.put("/api/mentor/me/evaluations/{evaluation_id}")
def update_mentor_evaluation(
    evaluation_id: int,
    data: InternEvaluationUpdate,
    request: Request,
    db=Depends(get_db),
):
    mentor = require_role(request, "Mentor")
    return InternEvaluationService(db).update(evaluation_id, mentor["ma_nguoi_dung"], data)


@router.get("/api/interns/me/evaluations")
def list_my_evaluations(request: Request, db=Depends(get_db)):
    intern = require_role(request, "ThucTapSinh")
    return InternEvaluationService(db).list_for_intern(intern["ma_nguoi_dung"])


@router.get("/api/interns/me/evaluations/{evaluation_id}")
def get_my_evaluation(evaluation_id: int, request: Request, db=Depends(get_db)):
    intern = require_role(request, "ThucTapSinh")
    return InternEvaluationService(db).get_for_intern(evaluation_id, intern["ma_nguoi_dung"])


@router.get("/api/evaluations")
def list_evaluations_for_hr_admin(
    request: Request,
    internship_profile_id: int | None = Query(default=None, gt=0),
    program_id: int | None = Query(default=None, gt=0),
    evaluation_period: Literal["MIDTERM", "FINAL"] | None = None,
    db=Depends(get_db),
):
    require_role(request, "Admin", "HR")
    return InternEvaluationService(db).list_for_hr_admin(
        profile_id=internship_profile_id,
        program_id=program_id,
        evaluation_period=evaluation_period,
    )


@router.get("/api/evaluations/{evaluation_id}")
def get_evaluation_for_hr_admin(evaluation_id: int, request: Request, db=Depends(get_db)):
    require_role(request, "Admin", "HR")
    return InternEvaluationService(db).get_for_hr_admin(evaluation_id)
