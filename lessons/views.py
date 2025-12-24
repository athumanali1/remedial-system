"""lessons/views.py"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth import logout
from django.contrib.admin.views.decorators import staff_member_required
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
from django.conf import settings

from django.db import models, IntegrityError
from django.db.models import Sum, F, Count, ExpressionWrapper, FloatField
from decimal import Decimal, InvalidOperation
import os

from .models import (
    Teacher,
    Timetable,
    LessonRecord,
    Week,
    ClassGroup,
    Subject,
    Student,
    StudentPayment,
    NormalLessonSlot,
    NormalLessonAttendance,
)


TERM_FEE = 1500

def home(request):
    return render(request, "lessons/home.html")


def debug_load_timetables(request):
    return JsonResponse({
        "timetables": [
            {"id": 1, "text": "Dummy Timetable A"},
            {"id": 2, "text": "Dummy Timetable B"},
            {"id": 3, "text": "Dummy Timetable C"},
        ]
    })


def simple_password_reset(request):
    """Simple password reset info page linked from the login screen."""
    return render(request, "lessons/simple_password_reset.html")


def simple_logout(request):
    """Log the user out and redirect to the login page.

    This view accepts both GET and POST so that existing logout links
    (which typically issue a GET) work without raising Method Not Allowed.
    """

    logout(request)
    return redirect("login")


# ---------- Remedial admin stats (admin dashboard) ----------

@staff_member_required
def remedial_stats(request):
    """Aggregate remedial stats by *logical* lessons, not raw rows.

    A logical remedial lesson is defined as a unique combination of:
    (teacher, day, start_time, end_time, subject) within a given week.

    This ensures joint remedial classes (multiple Timetable rows for the
    same teacher/subject/time but different classes) are only counted
    **once** for both attendance and payment, similar in spirit to the
    normal deputy stats view.
    """

    selected_week = request.GET.get("week")
    selected_teacher = request.GET.get("teacher")

    # Base queryset: filtered LessonRecords
    lessons = LessonRecord.objects.select_related("timetable", "timetable__subject_fk", "timetable__teacher")
    if selected_week:
        lessons = lessons.filter(week_id=selected_week)
    if selected_teacher:
        lessons = lessons.filter(created_by_id=selected_teacher)

    # Group by logical remedial lesson key
    # key = (teacher_id, day, start_time, end_time, subject_id)
    logical_map = {}

    def status_rank(val: str) -> int:
        v = (val or "").strip().lower()
        if v == "attended":
            return 3
        if v == "not attended":
            return 2
        if v == "pending":
            return 1
        return 0

    def payment_rank(val: str) -> int:
        v = (val or "").strip().lower()
        if v == "paid":
            return 2
        if v == "unpaid":
            return 1
        return 0

    for rec in lessons:
        tt = rec.timetable
        if not tt:
            continue

        key = (
            tt.teacher_id,
            tt.day,
            tt.start_time,
            tt.end_time,
            tt.subject_fk_id,
        )

        agg = logical_map.get(key)
        if agg is None:
            agg = {
                "teacher_id": tt.teacher_id,
                "status": None,
                "payment_status": None,
                "paid_amount": 0,
                "unpaid_amount": 0,
            }
            logical_map[key] = agg

        # Merge attendance status with priority
        new_status = (rec.status or "Pending").strip()
        if agg["status"] is None or status_rank(new_status) > status_rank(agg["status"]):
            agg["status"] = new_status

        # Merge payment_status with simple priority Paid > Unpaid > None
        new_pay = (rec.payment_status or "").strip()
        if new_pay:
            if agg["payment_status"] is None or payment_rank(new_pay) > payment_rank(agg["payment_status"]):
                agg["payment_status"] = new_pay

        # Always add amounts per row; grouping only affects counting, not sums
        amount = rec.amount or 0
        if (rec.payment_status or "").strip().lower() == "paid":
            agg["paid_amount"] += amount
        elif (rec.payment_status or "").strip().lower() == "unpaid":
            agg["unpaid_amount"] += amount

    # Global totals based on logical lessons
    total = len(logical_map)
    attended = 0
    not_attended = 0
    pending = 0
    paid = 0
    unpaid = 0
    total_paid_amount = 0
    total_unpaid_amount = 0

    for agg in logical_map.values():
        st = (agg["status"] or "Pending").strip().lower()
        if st == "attended":
            attended += 1
        elif st == "not attended":
            not_attended += 1
        else:
            pending += 1

        pay = (agg["payment_status"] or "").strip().lower()
        if pay == "paid":
            paid += 1
        elif pay == "unpaid":
            unpaid += 1

        total_paid_amount += agg["paid_amount"]
        total_unpaid_amount += agg["unpaid_amount"]

    # Per-teacher aggregation from logical lessons
    per_teacher_counters = {}
    for agg in logical_map.values():
        tid = agg["teacher_id"]
        if tid is None:
            continue
        c = per_teacher_counters.setdefault(
            tid,
            {
                "total": 0,
                "attended": 0,
                "not_attended": 0,
                "pending": 0,
                "paid": 0,
                "unpaid": 0,
                "paid_amount": 0,
                "unpaid_amount": 0,
            },
        )

        c["total"] += 1

        st = (agg["status"] or "Pending").strip().lower()
        if st == "attended":
            c["attended"] += 1
        elif st == "not attended":
            c["not_attended"] += 1
        else:
            c["pending"] += 1

        pay = (agg["payment_status"] or "").strip().lower()
        if pay == "paid":
            c["paid"] += 1
        elif pay == "unpaid":
            c["unpaid"] += 1

        c["paid_amount"] += agg["paid_amount"]
        c["unpaid_amount"] += agg["unpaid_amount"]

    # Resolve teachers in bulk
    all_teachers = Teacher.objects.all()
    teachers_by_id = {t.id: t for t in all_teachers}

    per_teacher_list = []
    for tid, c in per_teacher_counters.items():
        teacher = teachers_by_id.get(tid)
        total_l = c["total"] or 0

        def pct(x: int) -> float:
            return round(100 * x / total_l, 1) if total_l else 0

        per_teacher_list.append(
            {
                "teacher": teacher,
                "total": total_l,
                "attended": c["attended"],
                "not_attended": c["not_attended"],
                "pending": c["pending"],
                "paid": c["paid"],
                "unpaid": c["unpaid"],
                "paid_amount": c["paid_amount"],
                "unpaid_amount": c["unpaid_amount"],
                "attended_pct": pct(c["attended"]),
                "not_attended_pct": pct(c["not_attended"]),
                "pending_pct": pct(c["pending"]),
            }
        )

    weeks = Week.objects.all()
    teachers = Teacher.objects.all()

    context = {
        "weeks": weeks,
        "teachers": teachers,
        "selected_week": int(selected_week) if selected_week else None,
        "selected_teacher": int(selected_teacher) if selected_teacher else None,
        "total": total,
        "attended": attended,
        "not_attended": not_attended,
        "pending": pending,
        "paid": paid,
        "unpaid": unpaid,
        "total_paid_amount": total_paid_amount,
        "total_unpaid_amount": total_unpaid_amount,
        "per_teacher_list": per_teacher_list,
    }

    return render(request, "lessons/admin_remedial_stats.html", context)


@staff_member_required
def deputy_normal_stats(request):
    """Normal-classes overview used by the Deputy dashboard.

    Uses the same aggregation logic as remedial_stats but renders the
    admin_normal_stats.html template expected by the existing deputy
    normal stats UI.
    """

    from datetime import datetime

    selected_week = request.GET.get("week")
    selected_teacher = request.GET.get("teacher")
    normal_selected_day = request.GET.get("normal_day")
    normal_selected_date = request.GET.get("normal_date")

    attendances = NormalLessonAttendance.objects.select_related("slot__teacher", "slot__subject_fk")

    if selected_week:
        try:
            week_obj = Week.objects.get(id=selected_week)
            attendances = attendances.filter(date__range=(week_obj.start_date, week_obj.end_date))
        except Week.DoesNotExist:
            week_obj = None
    else:
        week_obj = None

    if selected_teacher:
        attendances = attendances.filter(slot__teacher_id=selected_teacher)

    if normal_selected_day:
        attendances = attendances.filter(slot__day=normal_selected_day)

    if normal_selected_date:
        try:
            parsed_date = datetime.strptime(normal_selected_date, "%Y-%m-%d").date()
            attendances = attendances.filter(date=parsed_date)
        except ValueError:
            pass

    # --- Collapse joint classes so each logical lesson (teacher+day+time+subject)
    # counts once, even if there are multiple attendance rows (one per class).
    logical_map = {}
    for att in attendances:
        slot = att.slot
        key = (
            slot.teacher_id,
            slot.day,
            slot.start_time,
            slot.end_time,
            slot.subject_fk_id,
        )
        logical_map[key] = att.status or "Pending"

    total = len(logical_map)
    attended = sum(1 for s in logical_map.values() if str(s).lower() == "attended".lower())
    not_attended = sum(1 for s in logical_map.values() if str(s).lower() == "not attended".lower())
    pending = sum(1 for s in logical_map.values() if str(s).lower() == "pending".lower())

    # Per-teacher breakdown based on logical lessons
    per_teacher_counters = {}
    for (teacher_id, _day, _st, _et, _subj_id), status in logical_map.items():
        if teacher_id not in per_teacher_counters:
            per_teacher_counters[teacher_id] = {"total": 0, "Attended": 0, "Not Attended": 0, "Pending": 0}
        c = per_teacher_counters[teacher_id]
        c["total"] += 1
        if str(status).lower() == "attended".lower():
            c["Attended"] += 1
        elif str(status).lower() == "not attended".lower():
            c["Not Attended"] += 1
        else:
            c["Pending"] += 1

    # Resolve Teacher objects in bulk for efficiency
    all_teachers = Teacher.objects.all()
    teachers_by_id = {t.id: t for t in all_teachers}

    per_teacher_list = []
    for teacher_id, counts in per_teacher_counters.items():
        teacher = teachers_by_id.get(teacher_id)
        total_l = counts["total"]

        def pct(x: int) -> float:
            return round(100 * x / total_l, 1) if total_l else 0

        per_teacher_list.append(
            {
                "teacher": teacher,
                "total": total_l,
                "attended": counts["Attended"],
                "not_attended": counts["Not Attended"],
                "pending": counts["Pending"],
                "attended_pct": pct(counts["Attended"]),
                "not_attended_pct": pct(counts["Not Attended"]),
                "pending_pct": pct(counts["Pending"]),
            }
        )

    weeks = Week.objects.all()
    teachers = Teacher.objects.all()

    context = {
        "weeks": weeks,
        "teachers": teachers,
        "selected_week": int(selected_week) if selected_week else None,
        "selected_teacher": int(selected_teacher) if selected_teacher else None,
        "normal_selected_day": normal_selected_day,
        "normal_selected_date": normal_selected_date,
        "total": total,
        "attended": attended,
        "not_attended": not_attended,
        "pending": pending,
        "attended_pct": round(100 * attended / total, 1) if total else 0,
        "not_attended_pct": round(100 * not_attended / total, 1) if total else 0,
        "pending_pct": round(100 * pending / total, 1) if total else 0,
        "per_teacher_list": per_teacher_list,
    }

    return render(request, "lessons/admin_normal_stats.html", context)


@staff_member_required
def remedial_teacher_details(request, teacher_id):
    """Detail view for a single teacher's remedial LessonRecords.

    Used from the remedial_stats "View" link. Shows remedial lessons
    only and allows bulk updating of status and payment_status.
    """

    teacher = get_object_or_404(Teacher, id=teacher_id)
    week_id = request.GET.get("week")

    # Base queryset: all LessonRecords created by this teacher
    lessons = LessonRecord.objects.filter(created_by=teacher)
    if week_id:
        lessons = lessons.filter(week_id=week_id)

    # Handle bulk update POST (status / payment_status)
    if request.method == "POST":
        record_ids = request.POST.getlist("record_ids")
        new_status = request.POST.get("status") or None
        new_payment = request.POST.get("payment_status") or None

        if record_ids and (new_status or new_payment):
            qs = lessons.filter(id__in=record_ids)
            for rec in qs:
                if new_status:
                    rec.status = new_status
                if new_payment:
                    rec.payment_status = new_payment
                rec.save()

        # After applying changes, redirect to GET to avoid reposting
        return redirect(
            f"{request.path}?week={week_id or ''}"
        )

    # Aggregates for header summary
    total = lessons.count()
    attended = lessons.filter(status__iexact="Attended").count()
    not_attended = lessons.filter(status__iexact="Not Attended").count()
    pending = lessons.filter(status__iexact="Pending").count()

    # Build row structures expected by admin_remedial_teacher_details.html
    rows = []
    lessons = lessons.select_related("timetable", "week").prefetch_related("timetable__class_groups")
    for rec in lessons:
        tt = rec.timetable
        class_names = ", ".join(c.name for c in tt.class_groups.all()) if tt else ""
        row = {
            "record_ids": [rec.id],
            "week": rec.week,
            "day_code": tt.day if tt else "",
            "start": tt.start_time if tt else None,
            "end": tt.end_time if tt else None,
            "class_label": class_names,
            "subject_name": tt.subject_fk.name if tt and tt.subject_fk else "",
            "status": rec.status,
            "payment_status": rec.payment_status,
            "amount": rec.amount,
        }
        rows.append(row)

    weeks = Week.objects.all()

    context = {
        "teacher": teacher,
        "weeks": weeks,
        "selected_week": week_id,
        "rows": rows,
        "total": total,
        "attended": attended,
        "not_attended": not_attended,
        "pending": pending,
    }
    return render(request, "lessons/admin_remedial_teacher_details.html", context)


@staff_member_required
def normal_teacher_details(request, teacher_id):
    """Detail view for a single teacher's normal lessons (deputy side).

    Uses NormalLessonAttendance and the admin_normal_teacher_details
    template. This is separate from remedial_teacher_details so that
    normal and remedial flows remain independent.
    """

    from datetime import datetime

    teacher = get_object_or_404(Teacher, id=teacher_id)

    # Week may come through as a string like "None"; normalise to int or None
    raw_week = request.GET.get("week")
    try:
        week_id = int(raw_week) if raw_week and str(raw_week).isdigit() else None
    except (TypeError, ValueError):
        week_id = None
    normal_selected_day = request.GET.get("normal_day")
    normal_selected_date = request.GET.get("normal_date")

    # Handle inline status change POST from the template
    if request.method == "POST":
        slot_ids = request.POST.getlist("slot_ids")
        new_status = request.POST.get("status")
        # Keep current filters when redirecting back
        normal_selected_day = request.POST.get("normal_day") or None
        normal_selected_date = request.POST.get("normal_date") or None
        raw_week = request.POST.get("week") or raw_week

        if slot_ids and new_status:
            qs = NormalLessonAttendance.objects.filter(slot_id__in=slot_ids, slot__teacher=teacher)

            if week_id is not None:
                try:
                    week_obj = Week.objects.get(id=week_id)
                    qs = qs.filter(date__range=(week_obj.start_date, week_obj.end_date))
                except Week.DoesNotExist:
                    pass

            if normal_selected_day:
                qs = qs.filter(slot__day=normal_selected_day)

            if normal_selected_date:
                try:
                    parsed_date = datetime.strptime(normal_selected_date, "%Y-%m-%d").date()
                    qs = qs.filter(date=parsed_date)
                except ValueError:
                    pass

            qs.update(status=new_status)

        # Redirect to GET to avoid resubmission
        redirect_url = f"{request.path}?"
        params = []
        if raw_week:
            params.append(f"week={raw_week}")
        if normal_selected_day:
            params.append(f"normal_day={normal_selected_day}")
        if normal_selected_date:
            params.append(f"normal_date={normal_selected_date}")
        redirect_url += "&".join(params)
        return redirect(redirect_url)

    attendances = NormalLessonAttendance.objects.select_related("slot", "slot__class_group", "slot__subject_fk").filter(
        slot__teacher=teacher
    )

    if week_id is not None:
        try:
            week_obj = Week.objects.get(id=week_id)
            attendances = attendances.filter(date__range=(week_obj.start_date, week_obj.end_date))
        except Week.DoesNotExist:
            week_obj = None
    else:
        week_obj = None

    if normal_selected_day:
        attendances = attendances.filter(slot__day=normal_selected_day)

    if normal_selected_date:
        try:
            parsed_date = datetime.strptime(normal_selected_date, "%Y-%m-%d").date()
            attendances = attendances.filter(date=parsed_date)
        except ValueError:
            pass

    # Build rows per logical lesson (day, start, end, subject), collapsing
    # joint classes so they appear as a single row.
    rows_map = {}
    for att in attendances:
        slot = att.slot
        key = (
            slot.day,
            slot.start_time,
            slot.end_time,
            slot.subject_fk.name if slot.subject_fk else "",
        )

        if key not in rows_map:
            # Generalise the class label e.g. "Form 2 West" -> "Form 2"
            base_label = slot.class_group.name
            parts = base_label.split()
            if len(parts) >= 2:
                base_label = " ".join(parts[:2])

            rows_map[key] = {
                "day": slot.day,
                "start": slot.start_time,
                "end": slot.end_time,
                "class_label": base_label,
                "subject_name": slot.subject_fk.name if slot.subject_fk else "",
                "status": att.status,
                "slot_ids": [slot.id],
            }
        else:
            rows_map[key]["slot_ids"].append(slot.id)

    rows = list(rows_map.values())

    # Aggregates based on logical rows, not raw attendance records
    total = len(rows)
    attended = sum(1 for r in rows if str(r["status"]).lower() == "attended".lower())
    not_attended = sum(1 for r in rows if str(r["status"]).lower() == "not attended".lower())
    pending = sum(1 for r in rows if str(r["status"]).lower() == "pending".lower())

    weeks = Week.objects.all()

    context = {
        "teacher": teacher,
        "weeks": weeks,
        "selected_week": int(week_id) if week_id else None,
        "normal_selected_day": normal_selected_day,
        "normal_selected_date": normal_selected_date,
        "rows": rows,
        "total": total,
        "attended": attended,
        "not_attended": not_attended,
        "pending": pending,
    }

    return render(request, "lessons/admin_normal_teacher_details.html", context)


@login_required
def teacher_normal_stats(request):
    """Normal lessons statistics view for the logged-in teacher.

    This mirrors `normal_teacher_details` but infers the teacher from the
    current user instead of taking a teacher_id, and is intended for the
    teacher-facing dashboard. It reuses the same
    admin_normal_teacher_details.html template so normal/remedial flows
    stay consistent.
    """

    from datetime import datetime

    try:
        teacher = Teacher.objects.get(user=request.user)
    except Teacher.DoesNotExist:
        # If the user is staff/superuser but not a Teacher, send them to the admin.
        if request.user.is_staff or request.user.is_superuser:
            return redirect("/admin/")

        # Otherwise send non-teacher users back to the public home page.
        return redirect("website:home")

    raw_week = request.GET.get("week")
    try:
        week_id = int(raw_week) if raw_week and str(raw_week).isdigit() else None
    except (TypeError, ValueError):
        week_id = None
    normal_selected_day = request.GET.get("normal_day")
    normal_selected_date = request.GET.get("normal_date")

    # Handle inline status change POST from the template (teacher-facing)
    if request.method == "POST":
        slot_ids = request.POST.getlist("slot_ids")
        new_status = request.POST.get("status")
        normal_selected_day = request.POST.get("normal_day") or None
        normal_selected_date = request.POST.get("normal_date") or None
        raw_week = request.POST.get("week") or raw_week

        if slot_ids and new_status:
            qs = NormalLessonAttendance.objects.filter(slot_id__in=slot_ids, slot__teacher=teacher)

            if week_id is not None:
                try:
                    week_obj = Week.objects.get(id=week_id)
                    qs = qs.filter(date__range=(week_obj.start_date, week_obj.end_date))
                except Week.DoesNotExist:
                    pass

            if normal_selected_day:
                qs = qs.filter(slot__day=normal_selected_day)

            if normal_selected_date:
                try:
                    parsed_date = datetime.strptime(normal_selected_date, "%Y-%m-%d").date()
                    qs = qs.filter(date=parsed_date)
                except ValueError:
                    pass

            qs.update(status=new_status)

        redirect_url = f"{request.path}?"
        params = []
        if raw_week:
            params.append(f"week={raw_week}")
        if normal_selected_day:
            params.append(f"normal_day={normal_selected_day}")
        if normal_selected_date:
            params.append(f"normal_date={normal_selected_date}")
        redirect_url += "&".join(params)
        return redirect(redirect_url)

    attendances = NormalLessonAttendance.objects.select_related(
        "slot", "slot__class_group", "slot__subject_fk"
    ).filter(slot__teacher=teacher)

    if week_id is not None:
        try:
            week_obj = Week.objects.get(id=week_id)
            attendances = attendances.filter(date__range=(week_obj.start_date, week_obj.end_date))
        except Week.DoesNotExist:
            week_obj = None
    else:
        week_obj = None

    if normal_selected_day:
        attendances = attendances.filter(slot__day=normal_selected_day)

    if normal_selected_date:
        try:
            parsed_date = datetime.strptime(normal_selected_date, "%Y-%m-%d").date()
            attendances = attendances.filter(date=parsed_date)
        except ValueError:
            pass

    # Group into logical lessons (day, start, end, subject), collapsing
    # joint classes to a single row, and generalise class label.
    rows_map = {}
    for att in attendances:
        slot = att.slot
        key = (
            slot.day,
            slot.start_time,
            slot.end_time,
            slot.subject_fk.name if slot.subject_fk else "",
        )

        if key not in rows_map:
            base_label = slot.class_group.name
            parts = base_label.split()
            if len(parts) >= 2:
                base_label = " ".join(parts[:2])

            rows_map[key] = {
                "day": slot.day,
                "start": slot.start_time,
                "end": slot.end_time,
                "class_label": base_label,
                "subject_name": slot.subject_fk.name if slot.subject_fk else "",
                "status": att.status,
                "slot_ids": [slot.id],
            }
        else:
            rows_map[key]["slot_ids"].append(slot.id)

    rows = list(rows_map.values())

    # Aggregates based on logical rows
    total = len(rows)
    attended = sum(1 for r in rows if str(r["status"]).lower() == "attended".lower())
    not_attended = sum(1 for r in rows if str(r["status"]).lower() == "not attended".lower())
    pending = sum(1 for r in rows if str(r["status"]).lower() == "pending".lower())

    weeks = Week.objects.all()

    context = {
        "teacher": teacher,
        "weeks": weeks,
        "selected_week": week_id,
        "normal_selected_day": normal_selected_day,
        "normal_selected_date": normal_selected_date,
        "rows": rows,
        "total": total,
        "attended": attended,
        "not_attended": not_attended,
        "pending": pending,
    }

    return render(request, "lessons/admin_normal_teacher_details.html", context)


def debug_load_timetables(request):
    return JsonResponse({
        "timetables": [
            {"id": 1, "text": "Dummy Timetable A"},
            {"id": 2, "text": "Dummy Timetable B"},
            {"id": 3, "text": "Dummy Timetable C"},
        ]
    })


# ---------- AJAX: timetables by teacher + week (used in admin JS) ----------

@login_required
def get_timetables(request):
    teacher_id = request.GET.get("teacher")
    week_id = request.GET.get("week")

    qs = Timetable.objects.none()
    if teacher_id:
        qs = Timetable.objects.filter(teacher_id=teacher_id)
        if week_id:
            used_ids = LessonRecord.objects.filter(
                week_id=week_id,
                timetable__in=qs
            ).values_list("timetable_id", flat=True)
            qs = qs.exclude(id__in=used_ids)

    data = [
        {
            "id": t.id,
            "display": f"{t.subject} - {t.day} {t.start_time.strftime('%H:%M')} "
                       f"({', '.join(c.name for c in t.class_groups.all())})"
        }
        for t in qs
    ]
    return JsonResponse({"timetables": data})

# ---------- Teacher dashboard ----------
@login_required
def teacher_dashboard(request):
    try:
        teacher = Teacher.objects.get(user=request.user)
    except Teacher.DoesNotExist:
        # If the user is staff/superuser but not a Teacher, send them to the admin.
        if request.user.is_staff or request.user.is_superuser:
            return redirect('/admin/')

        # Otherwise send non-teacher users back to the public home page.
        return redirect('website:home')

    context = {"teacher": teacher}
    

    # Filters from GET parameters
    selected_week = request.GET.get("week")
    selected_class = request.GET.get("class_group")
    selected_subject = request.GET.get("subject")

    # Base queryset for lessons of this teacher
    lessons = LessonRecord.objects.filter(timetable__teacher=teacher)

    if selected_week:
        lessons = lessons.filter(week_id=selected_week)
    if selected_class:
        lessons = lessons.filter(timetable__class_groups__id=selected_class)
    if selected_subject:
        lessons = lessons.filter(timetable__subject__id=selected_subject)

    # Statistics
    total_lessons = lessons.count()
    attended = lessons.filter(status__iexact="Attended").count()
    not_attended = lessons.filter(status__iexact="Not Attended").count()
    pending = lessons.filter(status__iexact="Pending").count()

    paid = lessons.filter(payment_status__iexact="Paid").count()
    unpaid = lessons.filter(payment_status__iexact="Unpaid").count()

    total_paid_amount = lessons.filter(payment_status__iexact="Paid").aggregate(
        Sum("amount")
    )["amount__sum"] or 0

    total_unpaid_amount = lessons.filter(payment_status__iexact="Unpaid").aggregate(
        Sum("amount")
    )["amount__sum"] or 0

    # Lists for filters
    weeks = Week.objects.all()
    classes = ClassGroup.objects.all()
    subjects = Subject.objects.all()
    timetables = Timetable.objects.filter(teacher=teacher)
    other_teachers = Teacher.objects.exclude(id=teacher.id)

    context = {
        "teacher": teacher,
        "lessons": lessons,
        "weeks": weeks,
        "classes": classes,
        "subjects": subjects,
        "timetables": timetables,
        "other_teachers": other_teachers,
        "selected_week": selected_week,
        "selected_class": selected_class,
        "selected_subject": selected_subject,
        "total_lessons": total_lessons,
        "attended": attended,
        "not_attended": not_attended,
        "pending": pending,
        "paid": paid,
        "unpaid": unpaid,
        "total_paid_amount": total_paid_amount,
        "total_unpaid_amount": total_unpaid_amount,
    }

    return render(request, "lessons/teacher_dashboard.html", context)

# ---------- Update profile picture ----------
@login_required
def update_profile_picture(request):
    teacher = get_object_or_404(Teacher, user=request.user)
    if request.method == "POST":
        if request.FILES.get('profile_picture'):
            if teacher.profile_picture:
                old_path = os.path.join(settings.MEDIA_ROOT, teacher.profile_picture.name)
                if os.path.exists(old_path):
                    os.remove(old_path)
            teacher.profile_picture = request.FILES['profile_picture']
            teacher.save()
        elif 'delete_picture' in request.POST:
            if teacher.profile_picture:
                old_path = os.path.join(settings.MEDIA_ROOT, teacher.profile_picture.name)
                if os.path.exists(old_path):
                    os.remove(old_path)
            teacher.profile_picture = None
            teacher.save()
    return redirect('teacher_dashboard')


# ---------- Mark attended (teacher) ----------
@login_required
def mark_attended(request, lesson_id):
    lesson = get_object_or_404(LessonRecord, id=lesson_id)
    teacher = get_object_or_404(Teacher, user=request.user)
    if lesson.timetable.teacher != teacher and lesson.swapped_with != teacher:
        return JsonResponse({'error': 'Not allowed'}, status=403)
    lesson.status = "Pending"
    lesson.created_by = teacher
    lesson.save()
    return redirect("teacher_dashboard")


# ---------- Teacher add lesson ----------
from .forms import TeacherLessonForm

@login_required
def add_lesson_teacher(request):
    teacher = get_object_or_404(Teacher, user=request.user)
    if request.method == "POST":
        form = TeacherLessonForm(request.POST, teacher=teacher)
        if form.is_valid():
            lesson = form.save(commit=False)
            lesson.created_by = teacher
            lesson.status = "Pending"
            lesson.payment_status = "Unpaid"
            # ❌ remove lesson.amount = 0
            exists = LessonRecord.objects.filter(
                timetable=lesson.timetable, week=lesson.week
            ).exists()
            if exists:
                form.add_error(None, "This lesson has already been scheduled for this week.")
                return render(request, "lessons/add_lesson_teacher.html", {"form": form})
            lesson.save()
            return redirect("teacher_dashboard")
    else:
        form = TeacherLessonForm(teacher=teacher)
    return render(request, "lessons/add_lesson_teacher.html", {"form": form})



# ---------- Teacher AJAX to list own timetables ----------
@login_required
def ajax_teacher_subjects(request):
    teacher = get_object_or_404(Teacher, user=request.user)
    timetables = Timetable.objects.filter(teacher=teacher)
    subjects = [
        {
            'id': t.id,
            'subject': t.subject,
            'class_groups': ', '.join([c.name for c in t.class_groups.all()])
        }
        for t in timetables
    ]
    return JsonResponse({'subjects': subjects})


"""Normal and remedial timetable tools."""


def _fixed_timetable_structure():
    """Return fixed days and lesson slots for Mon–Fri.

    All lessons are 40 minutes with the following structure per day:

    - Lesson 1: 08:00–08:40
    - Lesson 2: 08:40–09:20
    - Break 1: 20 minutes (09:20–09:40)
    - Lesson 3: 09:40–10:20
    - Lesson 4: 10:20–11:00
    - Break 2: 10 minutes (11:00–11:10)
    - Lesson 5: 11:10–11:50
    - Lesson 6: 11:50–12:30
    - Lunch: 12:30–14:20
    - Lesson 7: 14:20–15:00
    - Lesson 8: 15:00–15:40
    - Lesson 9: 15:40–16:20
    """

    from datetime import time

    days = ["Mon", "Tue", "Wed", "Thu", "Fri"]
    slots = [
        (time(8, 0), time(8, 40)),
        (time(8, 40), time(9, 20)),
        (time(9, 40), time(10, 20)),
        (time(10, 20), time(11, 0)),
        (time(11, 10), time(11, 50)),
        (time(11, 50), time(12, 30)),
        (time(14, 20), time(15, 0)),
        (time(15, 0), time(15, 40)),
        (time(15, 40), time(16, 20)),
    ]
    return days, slots


def _fixed_remedial_structure():
    """Return fixed remedial days and time slots.

    Structure (you provided):

    - Monday–Friday:
      * 16:30–17:30 (4:30pm–5:30pm)
      * 19:00–20:00 (7:00pm–8:00pm)
      * 13:30–14:20 (1:30pm–2:20pm)

    - Saturday:
      * 07:00–08:00
      * 08:00–09:00
      * 09:00–10:00
    """

    from datetime import time

    days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
    slots = [
        (time(16, 30), time(17, 30)),  # evening 1 (Mon–Fri)
        (time(19, 0), time(20, 0)),    # evening 2 (Mon–Fri)
        (time(13, 30), time(14, 20)),  # lunchtime (Mon–Fri)
        (time(7, 0), time(8, 0)),      # Saturday morning 1
        (time(8, 0), time(9, 0)),      # Saturday morning 2
        (time(9, 0), time(10, 0)),     # Saturday morning 3
    ]

    return days, slots


@staff_member_required
def timetable_builder(request):
    """Timetable Builder (Mon–Fri) using a fixed daily structure.

    Uses the Timetable model, one row per (subject, teacher, day, time
    range, class_group). Multiple rows with the same subject/teacher and
    time but different classes naturally represent joint classes; rows
    with different teachers at the same time are parallels.
    """

    from datetime import time

    class_groups_all = ClassGroup.objects.all()
    days, slots = _fixed_timetable_structure()

    # ----- Parse selected classes from GET or POST -----
    if request.method == "POST":
        selected_ids = request.POST.getlist("selected_classes")
    else:
        selected_ids = request.GET.getlist("classes")

    try:
        selected_class_ids = [int(cid) for cid in selected_ids if cid]
    except ValueError:
        selected_class_ids = []

    if selected_class_ids:
        class_groups = ClassGroup.objects.filter(id__in=selected_class_ids)
    else:
        class_groups = ClassGroup.objects.none()

    # ----- Build subject/teacher pairs for the dropdowns -----
    subjects = Subject.objects.all()
    teachers = Teacher.objects.all()
    pairs = []
    for subj in subjects:
        for teacher in teachers:
            pairs.append(
                {
                    "subject_id": subj.id,
                    "teacher_id": teacher.id,
                    "label": f"{subj.name} — {teacher}",
                    "key": f"{subj.id}-{teacher.id}",
                }
            )

    error_message = None

    # ----- Handle save / clear actions -----
    if request.method == "POST" and selected_class_ids:
        action = request.POST.get("action")

        if action == "clear":
            # Remove all timetable entries for the selected classes
            for cg in class_groups:
                Timetable.objects.filter(
                    class_groups=cg,
                    day__in=days,
                    start_time__in=[st for (st, _et) in slots],
                ).delete()
        elif action == "save":
            # ----- Pre-validate that any multi-class blocks are valid joint classes
            # and that a teacher is never assigned two different subjects at the
            # same time slot (even if both are joint subjects). -----
            from collections import defaultdict as _dd
            from .models import JointSubject as _JointSubject, JointClassGroupSet as _JointClassGroupSet

            # Map logical block -> set of class_ids chosen in this POST
            # key = (teacher_id, day, start_time, end_time, subject_id)
            block_classes: dict[tuple, set[int]] = _dd(set)

            # Map per time slot -> set of subject_ids used there
            # key = (teacher_id, day, start_time, end_time)
            block_subjects: dict[tuple, set[int]] = _dd(set)

            for cg in class_groups:
                for day in days:
                    for (st, et) in slots:
                        st_key = st.strftime("%H%M")
                        et_key = et.strftime("%H%M")

                        for idx in (1, 2, 3):
                            field_name = f"cell_{cg.id}_{day}_{st_key}_{et_key}_{idx}"
                            val = request.POST.get(field_name, "").strip()
                            if not val:
                                continue

                            try:
                                subj_id_str, teacher_id_str = val.split("-", 1)
                                subj_id = int(subj_id_str)
                                teacher_id = int(teacher_id_str)
                            except (ValueError, TypeError):
                                error_message = "Invalid subject/teacher selection received."
                                continue

                            k = (teacher_id, day, st, et, subj_id)
                            block_classes[k].add(cg.id)

                            tkey = (teacher_id, day, st, et)
                            block_subjects[tkey].add(subj_id)

            if not error_message:
                # First, ensure no teacher has two different subjects at the same time
                for (_teacher_id, _day, _st, _et), subj_ids in block_subjects.items():
                    if len(subj_ids) > 1:
                        error_message = (
                            "A teacher cannot be assigned different subjects in the same "
                            "time slot. Adjust the timetable so each teacher has only one "
                            "subject per slot."
                        )
                        break

            if not error_message:
                # Build joint subject / joint class-group configuration
                joint_subject_ids = set(
                    _JointSubject.objects.filter(active=True).values_list("subject_id", flat=True)
                )

                class_to_tag: dict[int, str] = {}
                for group_set in _JointClassGroupSet.objects.filter(active=True).prefetch_related("class_groups"):
                    ids = [c.id for c in group_set.class_groups.all()]
                    for cid in ids:
                        class_to_tag[cid] = group_set.name

                # Validate each logical block
                for (teacher_id, day, st, et, subj_id), class_ids in block_classes.items():
                    if len(class_ids) <= 1:
                        continue  # only one class, always allowed

                    # Must be a joint subject
                    if subj_id not in joint_subject_ids:
                        error_message = (
                            "Cannot assign this teacher to multiple classes at the same time "
                            "unless the subject is configured as a joint subject."
                        )
                        break

                    # All classes must share the same joint-group tag
                    tags = {class_to_tag.get(cid) for cid in class_ids}
                    if len(tags) != 1 or None in tags:
                        error_message = (
                            "These classes are not configured as a single joint class group for this "
                            "subject and time. Please configure a JointClassGroupSet or select fewer "
                            "classes."
                        )
                        break

            if error_message:
                # Do not modify the timetable if validation failed
                pass
            else:
                # First clear existing rows for those classes and slots to
                # avoid duplicates, then recreate from submitted cells.
                for cg in class_groups:
                    Timetable.objects.filter(
                        class_groups=cg,
                        day__in=days,
                        start_time__in=[st for (st, _et) in slots],
                    ).delete()

                # Track which combinations we've already created to avoid
                # duplicate rows when the same option is selected twice.
                created_keys = set()

                for cg in class_groups:
                    for day in days:
                        for (st, et) in slots:
                            st_key = st.strftime("%H%M")
                            et_key = et.strftime("%H%M")

                            for idx in (1, 2, 3):
                                field_name = f"cell_{cg.id}_{day}_{st_key}_{et_key}_{idx}"
                                val = request.POST.get(field_name, "").strip()
                                if not val:
                                    continue

                                try:
                                    subj_id_str, teacher_id_str = val.split("-", 1)
                                    subj_id = int(subj_id_str)
                                    teacher_id = int(teacher_id_str)
                                except (ValueError, TypeError):
                                    error_message = "Invalid subject/teacher selection received."
                                    continue

                                key = (cg.id, day, st, et, subj_id, teacher_id)
                                if key in created_keys:
                                    continue
                                created_keys.add(key)

                                tt = Timetable.objects.create(
                                    subject_fk_id=subj_id,
                                    teacher_id=teacher_id,
                                    day=day,
                                    start_time=st,
                                    end_time=et,
                                )
                                tt.class_groups.add(cg)
        else:
            # Unknown or missing action – keep error minimal
            error_message = "Unknown action; timetable was not saved."

    # ----- Build current selection map for the template -----
    current = {}
    if selected_class_ids:
        tts = (
            Timetable.objects.filter(
                class_groups__in=class_groups,
                day__in=days,
                start_time__in=[st for (st, _et) in slots],
            )
            .select_related("subject_fk", "teacher")
            .prefetch_related("class_groups")
        )

        for tt in tts:
            subj_id = tt.subject_fk_id if tt.subject_fk_id else None
            teacher_id = tt.teacher_id
            if not subj_id or not teacher_id:
                continue

            value = f"{subj_id}-{teacher_id}"

            for cg in tt.class_groups.all():
                if cg.id not in selected_class_ids:
                    continue
                st_key = tt.start_time.strftime("%H%M")
                et_key = tt.end_time.strftime("%H%M")

                base = f"{cg.id}_{tt.day}_{st_key}_{et_key}"

                # Place into the first free slot 1..3 in a stable way
                placed = False
                for idx in (1, 2, 3):
                    key = f"{base}_{idx}"
                    if key not in current:
                        current[key] = value
                        placed = True
                        break
                if not placed:
                    # If all three are already used, we ignore extras.
                    continue

    # ----- Joint class configuration for auto-copy in the builder -----
    from collections import defaultdict
    from .models import JointSubject, JointClassGroupSet

    # Joint subjects come from JointSubject entries marked active.
    joint_subject_ids = list(
        JointSubject.objects.filter(active=True).values_list("subject_id", flat=True)
    )

    joint_class_group_tags = {}
    joint_group_members = {}

    # Build maps from JointClassGroupSet so admins can configure which
    # class groups move together in joint lessons.
    members_by_tag: dict[str, list[int]] = defaultdict(list)
    for group_set in JointClassGroupSet.objects.filter(active=True).prefetch_related("class_groups"):
        ids = [cg.id for cg in group_set.class_groups.all()]
        if len(ids) < 2:
            continue
        members_by_tag[group_set.name] = ids

    for tag, ids in members_by_tag.items():
        joint_group_members[tag] = ids
        for cid in ids:
            joint_class_group_tags[cid] = tag

    context = {
        "error_message": error_message,
        "class_groups_all": class_groups_all,
        "selected_class_ids": selected_class_ids,
        "days": days,
        "slots": slots,
        "class_groups": class_groups,
        "pairs": pairs,
        "current": current,
        "joint_subject_ids": joint_subject_ids,
        "joint_class_group_tags": joint_class_group_tags,
        "joint_group_members": joint_group_members,
    }

    return render(request, "lessons/timetable_builder.html", context)


@staff_member_required
def timetable_master(request):
    """Master Timetable view based on the fixed daily structure."""

    days, slots = _fixed_timetable_structure()
    class_groups = ClassGroup.objects.all()

    # Build a grid keyed by "classId_day_HHMM_HHMM" mapping to a list of
    # Timetable rows (to support parallels/joints display).
    tts = (
        Timetable.objects.filter(
            day__in=days,
            start_time__in=[st for (st, _et) in slots],
        )
        .select_related("subject_fk", "teacher")
        .prefetch_related("class_groups")
    )

    grid = {}
    for tt in tts:
        st_key = tt.start_time.strftime("%H%M")
        et_key = tt.end_time.strftime("%H%M")
        for cg in tt.class_groups.all():
            key = f"{cg.id}_{tt.day}_{st_key}_{et_key}"
            grid.setdefault(key, []).append(tt)

    context = {
        "days": days,
        "slots": slots,
        "class_groups": class_groups,
        "grid": grid,
    }
    return render(request, "lessons/timetable_master.html", context)


@staff_member_required
def generate_week_lessons(request):
    """Generate normal lesson attendance for a selected Week.

    For each Timetable row (normal timetable) we now create **one**
    NormalLessonAttendance per week (weekly lesson), not one per day in
    the date range. The attendance `date` is set to the Week's
    `start_date` as the canonical date for that week.

    Behaviour is idempotent: running this multiple times for the same
    week will not duplicate slots or attendance records.
    """

    weeks = Week.objects.all()
    selected_week = None
    created_att = None

    if request.method == "POST":
        week_id = request.POST.get("week")
        if week_id:
            try:
                selected_week = Week.objects.get(id=week_id)
            except Week.DoesNotExist:
                selected_week = None

        if selected_week is not None:
            week_date = selected_week.start_date

            created_count = 0

            # Use the fixed normal timetable structure so we only pick
            # true normal lesson rows (Mon–Fri, normal school times),
            # not remedial entries that also live in Timetable.
            days, slots = _fixed_timetable_structure()
            normal_start_times = [st for (st, _et) in slots]

            tts = (
                Timetable.objects.filter(day__in=days, start_time__in=normal_start_times)
                .select_related("teacher", "subject_fk")
                .prefetch_related("class_groups")
            )

            for tt in tts:
                first_slot = None
                for cg in tt.class_groups.all():
                    # Ensure a NormalLessonSlot exists for this
                    # class/teacher/subject/day/time.
                    slot, _ = NormalLessonSlot.objects.get_or_create(
                        day=tt.day,
                        start_time=tt.start_time,
                        end_time=tt.end_time,
                        class_group=cg,
                        subject_fk=tt.subject_fk,
                        teacher=tt.teacher,
                    )
                    if first_slot is None:
                        first_slot = slot

                # Ensure a single NormalLessonAttendance exists for this
                # logical teaching block (teacher/day/start/end/subject)
                # and week, represented by week_date. We tie it to the
                # first slot created above so combined classes still
                # count as ONE lesson.
                if first_slot is not None:
                    att, created = NormalLessonAttendance.objects.get_or_create(
                        slot=first_slot,
                        date=week_date,
                        defaults={"status": "Pending"},
                    )
                    if created:
                        created_count += 1

            created_att = created_count
        else:
            created_att = 0

    context = {
        "weeks": weeks,
        "selected_week": selected_week,
        "created_att": created_att,
    }
    return render(request, "lessons/generate_week_lessons.html", context)


@login_required
def teacher_normal_timetable(request):
    """Display the logged-in teacher's normal timetable as a grid.

    Uses NormalLessonSlot rows (generated from the master Timetable via
    generate_week_lessons) and the same fixed Mon–Fri lesson slots as
    the timetable builder. This is a read-only timetable view for
    teachers.
    """

    from datetime import time

    teacher = get_object_or_404(Teacher, user=request.user)

    selected_week_id = request.GET.get("week")
    weeks = Week.objects.all()
    try:
        selected_week = Week.objects.get(id=selected_week_id) if selected_week_id else None
    except Week.DoesNotExist:
        selected_week = None

    days, slots = _fixed_timetable_structure()

    # Fetch all normal slots for this teacher within the fixed structure.
    slots_qs = NormalLessonSlot.objects.filter(
        teacher=teacher,
        day__in=days,
        start_time__in=[st for (st, _et) in slots],
    ).select_related("class_group", "subject_fk")

    # Build a grid: {day_code: [list of slot lists per time index]}
    normal_days = days
    normal_time_slots = slots
    normal_timetable_grid = {d: [[] for _ in slots] for d in normal_days}

    for slot in slots_qs:
        try:
            time_index = [st for (st, _et) in slots].index(slot.start_time)
        except ValueError:
            continue
        normal_timetable_grid[slot.day][time_index].append(slot)

    # Build colour grid from NormalLessonAttendance for the selected week.
    # If no week is selected, we still colour purely by presence (green/grey).
    normal_color_grid = {}

    # Precompute start_times list for index lookup
    start_times = [st for (st, _et) in slots]

    # Map logical lesson (day+start+end+subject) to a merged status based on
    # attendance for the selected week. Status priority:
    #   Attended > Not Attended > Pending/None.
    status_map = {}
    if selected_week:
        week_start = selected_week.start_date
        week_end = selected_week.end_date

        # Collect all slots for this teacher and then fetch their attendance
        slot_ids = list(slots_qs.values_list("id", flat=True))
        if slot_ids:
            atts = NormalLessonAttendance.objects.filter(
                slot_id__in=slot_ids,
                date__range=(week_start, week_end),
            ).select_related("slot", "slot__subject_fk")

            for att in atts:
                s = att.slot
                key = (
                    s.day,
                    s.start_time,
                    s.end_time,
                    s.subject_fk_id,
                )

                current = status_map.get(key)
                new_status = (att.status or "Pending").strip()

                # Apply priority: Attended > Not Attended > Pending
                def rank(val: str) -> int:
                    val_l = val.lower()
                    if val_l == "attended":
                        return 3
                    if val_l == "not attended":
                        return 2
                    if val_l == "pending":
                        return 1
                    return 0

                if current is None or rank(new_status) > rank(current):
                    status_map[key] = new_status

    # Now assign colours per cell
    for day_code in normal_days:
        row = []
        for idx, (st, et) in enumerate(slots):
            cell_slots = normal_timetable_grid[day_code][idx]
            if not cell_slots:
                row.append("grey")
                continue

            if not selected_week:
                # No week filter: any lesson present -> green
                row.append("green")
                continue

            # Determine merged status for this cell from status_map
            cell_status_rank = 0
            for s in cell_slots:
                key = (
                    s.day,
                    s.start_time,
                    s.end_time,
                    s.subject_fk_id,
                )
                st_val = status_map.get(key)
                if not st_val:
                    continue
                st_l = st_val.lower()
                if st_l == "attended":
                    cell_status_rank = max(cell_status_rank, 3)
                elif st_l == "not attended":
                    cell_status_rank = max(cell_status_rank, 2)
                elif st_l == "pending":
                    cell_status_rank = max(cell_status_rank, 1)

            if cell_status_rank == 3:
                row.append("green")
            elif cell_status_rank == 2:
                row.append("red")
            elif cell_status_rank == 1:
                row.append("grey")
            else:
                # No attendance record for this week yet
                row.append("grey")

        normal_color_grid[day_code] = row

    context = {
        "weeks": weeks,
        "selected_week": selected_week.id if selected_week else None,
        "normal_days": normal_days,
        "normal_time_slots": normal_time_slots,
        "normal_timetable_grid": normal_timetable_grid,
        "normal_color_grid": normal_color_grid,
    }

    return render(request, "lessons/teacher_normal_timetable.html", context)


@login_required
def teacher_remedial_timetable(request):
    """Display the logged-in teacher's remedial timetable as a grid.

    Uses Timetable rows (remedial timetable entries) and a fixed remedial
    time structure, similar in spirit to the normal timetable view.
    """

    teacher = get_object_or_404(Teacher, user=request.user)

    selected_week_id = request.GET.get("week")
    weeks = Week.objects.all()
    try:
        selected_week = Week.objects.get(id=selected_week_id) if selected_week_id else None
    except Week.DoesNotExist:
        selected_week = None

    days, slots = _fixed_remedial_structure()

    # Fetch remedial Timetable entries for this teacher matching the
    # remedial time slots and days.
    remedial_qs = (
        Timetable.objects
        .filter(teacher=teacher, day__in=days, start_time__in=[st for (st, _et) in slots])
        .select_related("subject_fk")
        .prefetch_related("class_groups")
    )

    days_set = set(days)

    # Build a grid indexed like: grid[day_code][time_index] -> list of Timetable rows
    remedial_days = days
    remedial_time_slots = slots
    remedial_grid = {d: [[] for _ in remedial_time_slots] for d in remedial_days}

    start_times = [st for (st, _et) in remedial_time_slots]

    for tt in remedial_qs:
        if tt.day not in days_set:
            continue
        try:
            time_index = start_times.index(tt.start_time)
        except ValueError:
            continue
        remedial_grid[tt.day][time_index].append(tt)

    # Colour grid based on LessonRecord status for the selected week.
    remedial_color_grid = {}

    # Precompute start_times list
    start_times = [st for (st, _et) in remedial_time_slots]

    # Build status map from LessonRecord when a week is selected.
    # Logical key: (teacher, day, start_time, end_time, subject).
    status_map = {}
    if selected_week:
        week_id = selected_week.id
        lessons = (
            LessonRecord.objects
            .filter(
                teacher=teacher,
                week_id=week_id,
                timetable__in=remedial_qs,
            )
            .select_related("timetable", "timetable__subject_fk")
        )

        for rec in lessons:
            tt = rec.timetable
            if not tt:
                continue
            key = (
                tt.teacher_id,
                tt.day,
                tt.start_time,
                tt.end_time,
                tt.subject_fk_id,
            )

            current = status_map.get(key)
            new_status = (rec.status or "Pending").strip()

            def rank(val: str) -> int:
                val_l = val.lower()
                if val_l == "attended":
                    return 3
                if val_l == "not attended":
                    return 2
                if val_l == "pending":
                    return 1
                return 0

            if current is None or rank(new_status) > rank(current):
                status_map[key] = new_status

    for day_code in remedial_days:
        row = []
        for idx in range(len(remedial_time_slots)):
            tts = remedial_grid[day_code][idx]
            if not tts:
                row.append("grey")
                continue

            if not selected_week:
                row.append("green")
                continue

            cell_status_rank = 0
            for tt in tts:
                key = (
                    tt.teacher_id,
                    tt.day,
                    tt.start_time,
                    tt.end_time,
                    tt.subject_fk_id,
                )
                st_val = status_map.get(key)
                if not st_val:
                    continue
                st_l = st_val.lower()
                if st_l == "attended":
                    cell_status_rank = max(cell_status_rank, 3)
                elif st_l == "not attended":
                    cell_status_rank = max(cell_status_rank, 2)
                elif st_l == "pending":
                    cell_status_rank = max(cell_status_rank, 1)

            if cell_status_rank == 3:
                row.append("green")
            elif cell_status_rank == 2:
                row.append("red")
            elif cell_status_rank == 1:
                row.append("grey")
            else:
                row.append("grey")

        remedial_color_grid[day_code] = row

    context = {
        "weeks": weeks,
        "selected_week": selected_week.id if selected_week else None,
        "days": remedial_days,
        "remedial_time_slots": remedial_time_slots,
        "remedial_grid": remedial_grid,
        "remedial_color_grid": remedial_color_grid,
    }

    return render(request, "lessons/teacher_remedial_timetable.html", context)


@staff_member_required
def remedial_timetable_builder(request):
    """Remedial Timetable Builder (Mon–Sat) using a fixed structure.

    Uses the Timetable model for remedial entries. Multiple rows with the
    same teacher/subject/time but different classes behave like joint
    classes; different teachers at the same time are parallels.
    """

    class_groups_all = ClassGroup.objects.all()
    days, slots = _fixed_remedial_structure()

    # Parse selected classes from GET/POST
    if request.method == "POST":
        selected_ids = request.POST.getlist("selected_classes")
    else:
        selected_ids = request.GET.getlist("classes")

    try:
        selected_class_ids = [int(cid) for cid in selected_ids if cid]
    except ValueError:
        selected_class_ids = []

    if selected_class_ids:
        class_groups = ClassGroup.objects.filter(id__in=selected_class_ids)
    else:
        class_groups = ClassGroup.objects.none()

    # Subject/teacher pairs for dropdown
    subjects = Subject.objects.all()
    teachers = Teacher.objects.all()
    pairs = []
    for subj in subjects:
        for teacher in teachers:
            pairs.append(
                {
                    "subject_id": subj.id,
                    "teacher_id": teacher.id,
                    "label": f"{subj.name} — {teacher}",
                    "key": f"{subj.id}-{teacher.id}",
                }
            )

    error_message = None

    if request.method == "POST" and selected_class_ids:
        action = request.POST.get("action")

        if action == "save":
            # ----- Pre-validate that any multi-class blocks are valid joint classes
            # and that a teacher never has more than one subject in the same
            # remedial time slot. -----
            from collections import defaultdict as _dd
            from .models import JointSubject as _JointSubject, JointClassGroupSet as _JointClassGroupSet

            block_classes: dict[tuple, set[int]] = _dd(set)
            block_subjects: dict[tuple, set[int]] = _dd(set)

            for cg in class_groups:
                for day in days:
                    for (st, et) in slots:
                        st_key = st.strftime("%H%M")
                        et_key = et.strftime("%H%M")

                        for idx in (1, 2, 3):
                            field_name = f"cell_{cg.id}_{day}_{st_key}_{et_key}_{idx}"
                            val = request.POST.get(field_name, "").strip()
                            if not val:
                                continue

                            try:
                                subj_id_str, teacher_id_str = val.split("-", 1)
                                subj_id = int(subj_id_str)
                                teacher_id = int(teacher_id_str)
                            except (ValueError, TypeError):
                                error_message = "Invalid subject/teacher selection received."
                                continue

                            k = (teacher_id, day, st, et, subj_id)
                            block_classes[k].add(cg.id)

                            tkey = (teacher_id, day, st, et)
                            block_subjects[tkey].add(subj_id)

            if not error_message:
                # First, ensure no teacher has two different subjects at the same remedial time slot
                for (_teacher_id, _day, _st, _et), subj_ids in block_subjects.items():
                    if len(subj_ids) > 1:
                        error_message = (
                            "A teacher cannot be assigned different subjects in the same "
                            "remedial time slot. Adjust the timetable so each teacher has only one "
                            "subject per slot."
                        )
                        break

            if not error_message:
                joint_subject_ids = set(
                    _JointSubject.objects.filter(active=True).values_list("subject_id", flat=True)
                )

                class_to_tag: dict[int, str] = {}
                for group_set in _JointClassGroupSet.objects.filter(active=True).prefetch_related("class_groups"):
                    ids = [c.id for c in group_set.class_groups.all()]
                    for cid in ids:
                        class_to_tag[cid] = group_set.name

                for (teacher_id, day, st, et, subj_id), class_ids in block_classes.items():
                    if len(class_ids) <= 1:
                        continue

                    if subj_id not in joint_subject_ids:
                        error_message = (
                            "Cannot assign this teacher to multiple classes at the same time "
                            "unless the subject is configured as a joint subject."
                        )
                        break

                    tags = {class_to_tag.get(cid) for cid in class_ids}
                    if len(tags) != 1 or None in tags:
                        error_message = (
                            "These classes are not configured as a single joint class group for this "
                            "subject and time. Please configure a JointClassGroupSet or select fewer "
                            "classes."
                        )
                        break

            if error_message:
                pass
            else:
                # Clear existing remedial rows for these classes at remedial slots
                for cg in class_groups:
                    Timetable.objects.filter(
                        class_groups=cg,
                        day__in=days,
                        start_time__in=[st for (st, _et) in slots],
                    ).delete()

                created_keys = set()

                for cg in class_groups:
                    for day in days:
                        for (st, et) in slots:
                            st_key = st.strftime("%H%M")
                            et_key = et.strftime("%H%M")

                            for idx in (1, 2, 3):
                                field_name = f"cell_{cg.id}_{day}_{st_key}_{et_key}_{idx}"
                                val = request.POST.get(field_name, "").strip()
                                if not val:
                                    continue

                                try:
                                    subj_id_str, teacher_id_str = val.split("-", 1)
                                    subj_id = int(subj_id_str)
                                    teacher_id = int(teacher_id_str)
                                except (ValueError, TypeError):
                                    error_message = "Invalid subject/teacher selection received."
                                    continue

                                key = (cg.id, day, st, et, subj_id, teacher_id)
                                if key in created_keys:
                                    continue
                                created_keys.add(key)

                                tt = Timetable.objects.create(
                                    subject_fk_id=subj_id,
                                    teacher_id=teacher_id,
                                    day=day,
                                    start_time=st,
                                    end_time=et,
                                )
                                tt.class_groups.add(cg)
        else:
            # For now we only support "save"; other actions are ignored.
            error_message = "Unknown action; remedial timetable was not saved."

    # Build current selection map from existing remedial Timetable rows
    current = {}
    if selected_class_ids:
        tts = (
            Timetable.objects.filter(
                class_groups__in=class_groups,
                day__in=days,
                start_time__in=[st for (st, _et) in slots],
            )
            .select_related("subject_fk", "teacher")
            .prefetch_related("class_groups")
        )

        for tt in tts:
            subj_id = tt.subject_fk_id if tt.subject_fk_id else None
            teacher_id = tt.teacher_id
            if not subj_id or not teacher_id:
                continue

            value = f"{subj_id}-{teacher_id}"

            for cg in tt.class_groups.all():
                if cg.id not in selected_class_ids:
                    continue
                st_key = tt.start_time.strftime("%H%M")
                et_key = tt.end_time.strftime("%H%M")
                base = f"{cg.id}_{tt.day}_{st_key}_{et_key}"

                placed = False
                for idx in (1, 2, 3):
                    key = f"{base}_{idx}"
                    if key not in current:
                        current[key] = value
                        placed = True
                        break
                if not placed:
                    continue

    # ----- Joint class configuration for auto-copy in the remedial builder -----
    from collections import defaultdict
    from .models import JointSubject, JointClassGroupSet

    joint_subject_ids = list(
        JointSubject.objects.filter(active=True).values_list("subject_id", flat=True)
    )

    joint_class_group_tags = {}
    joint_group_members = {}

    members_by_tag: dict[str, list[int]] = defaultdict(list)
    for group_set in JointClassGroupSet.objects.filter(active=True).prefetch_related("class_groups"):
        ids = [cg.id for cg in group_set.class_groups.all()]
        if len(ids) < 2:
            continue
        members_by_tag[group_set.name] = ids

    for tag, ids in members_by_tag.items():
        joint_group_members[tag] = ids
        for cid in ids:
            joint_class_group_tags[cid] = tag

    context = {
        "error_message": error_message,
        "class_groups_all": class_groups_all,
        "selected_class_ids": selected_class_ids,
        "days": days,
        "slots": slots,
        "class_groups": class_groups,
        "pairs": pairs,
        "current": current,
        "joint_subject_ids": joint_subject_ids,
        "joint_class_group_tags": joint_class_group_tags,
        "joint_group_members": joint_group_members,
    }
    return render(request, "lessons/remedial_timetable_builder.html", context)


@staff_member_required
def remedial_timetable_master(request):
    """Remedial Master Timetable view using the fixed remedial structure."""

    days, slots = _fixed_remedial_structure()
    class_groups = ClassGroup.objects.all()

    # Build grid keyed by "classId_day_HHMM_HHMM" similar to normal master
    tts = (
        Timetable.objects.filter(
            day__in=days,
            start_time__in=[st for (st, _et) in slots],
        )
        .select_related("subject_fk", "teacher")
        .prefetch_related("class_groups")
    )

    grid = {}
    for tt in tts:
        st_key = tt.start_time.strftime("%H%M")
        et_key = tt.end_time.strftime("%H%M")
        for cg in tt.class_groups.all():
            key = f"{cg.id}_{tt.day}_{st_key}_{et_key}"
            grid.setdefault(key, []).append(tt)

    context = {
        "days": days,
        "slots": slots,
        "class_groups": class_groups,
        "grid": grid,
    }
    return render(request, "lessons/remedial_timetable_master.html", context)


@staff_member_required
def generate_remedial_week_lessons(request):
    """Generate remedial LessonRecord rows from the remedial timetable.

    For the selected Week, create one LessonRecord per Timetable entry
    used for remedials. These are the same LessonRecords consumed by the
    remedial admin stats views. The operation is idempotent: if a
    LessonRecord already exists for a given (week, timetable) pair, it
    will not be duplicated.
    """

    weeks = Week.objects.all()
    selected_week = None
    created_att = None

    if request.method == "POST":
        week_id = request.POST.get("week")
        if week_id:
            try:
                selected_week = Week.objects.get(id=week_id)
            except Week.DoesNotExist:
                selected_week = None

        if selected_week is not None:
            timetables = Timetable.objects.all().select_related("teacher")
            created_count = 0

            for tt in timetables:
                defaults = {
                    "created_by": tt.teacher,
                    "teacher": tt.teacher,
                }
                obj, created = LessonRecord.objects.get_or_create(
                    timetable=tt,
                    week=selected_week,
                    defaults=defaults,
                )
                if created:
                    created_count += 1

            created_att = created_count
        else:
            created_att = 0

    context = {
        "weeks": weeks,
        "selected_week": selected_week,
        "created_att": created_att,
    }
    return render(request, "lessons/generate_remedial_week_lessons.html", context)
 # ---------- AJAX: load timetables (simple dropdown for admin/teacher) ----------

@login_required
def load_timetables(request):
    teacher_id = request.GET.get("teacher")
    timetables = Timetable.objects.filter(teacher_id=teacher_id) if teacher_id else []

    data = [
        {
            "id": t.id,
            "subject": t.subject_fk.name if t.subject_fk else "Unnamed",
            "day": t.get_day_display(),
            "start_time": t.start_time.strftime("%H:%M"),
            "end_time": t.end_time.strftime("%H:%M"),
        }
        for t in timetables
    ]
    return JsonResponse(data, safe=False)


@login_required
def student_payments(request):
    teacher = get_object_or_404(Teacher, user=request.user)

    # If teacher has no assigned class, deny access
    if not hasattr(teacher, "main_class") or teacher.main_class is None:
        return redirect('teacher_dashboard')

    students = Student.objects.filter(class_group=teacher.main_class)

    # Compute statistics
    total_students = students.count()
    total_fee_per_student = Decimal('1500.00')
    total_paid = sum(s.amount_paid for s in students)
    total_unpaid = total_students * total_fee_per_student - total_paid
    fully_paid = sum(1 for s in students if s.amount_paid >= total_fee_per_student)
    partial_paid = sum(1 for s in students if 0 < s.amount_paid < total_fee_per_student)

    # Record payments
    if request.method == "POST":
        for student in students:
            amount_str = request.POST.get(f"amount_{student.id}")
            if amount_str:
                try:
                    amount = Decimal(amount_str)
                    if amount > 0:
                        StudentPayment.objects.create(
                            student=student,
                            amount=amount,
                            recorded_by=teacher,
                            term="Term 1"
                        )
                        student.amount_paid = amount
                        student.save()
                except (InvalidOperation, ValueError):
                    continue
        return redirect(request.path)

    context = {
        "students": students,
        "class_group": teacher.main_class,
        "total_students": total_students,
        "total_paid": total_paid,
        "total_unpaid": total_unpaid,
        "fully_paid": fully_paid,
        "partial_paid": partial_paid,
        "total_fee_per_student": total_fee_per_student,
    }
    return render(request, "lessons/student_payments.html", context)

    context = {
        "class_groups": class_groups,
        "students": students,
        "selected_class_id": selected_class_id,
        # Statistics
        "total_students": total_students,
        "total_paid": total_paid,
        "total_unpaid": total_unpaid,
        "fully_paid": fully_paid,
        "partial_paid": partial_paid,
        "total_fee_per_student": total_fee_per_student,
    }
    return render(request, "lessons/student_payments.html", context)
@login_required
@csrf_exempt
def add_student_ajax(request):
    """AJAX endpoint for class teachers to add a student to their class.

    Always returns JSON; on validation errors or DB issues we return a
    clear error payload instead of raising an HTML 500 page, so the
    frontend `fetch(...).then(res => res.json())` call does not break
    with "Unexpected token '<'".
    """

    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)

    teacher = get_object_or_404(Teacher, user=request.user)

    first_name = (request.POST.get("first_name") or "").strip()
    last_name = (request.POST.get("last_name") or "").strip()
    admission_number = (request.POST.get("admission_number") or "").strip()
    class_group_id = request.POST.get("class_group")

    if not (first_name and last_name and admission_number and class_group_id):
        return JsonResponse({"error": "Missing required fields"}, status=400)

    try:
        class_group = ClassGroup.objects.get(id=class_group_id)
    except ClassGroup.DoesNotExist:
        return JsonResponse({"error": "Invalid class group"}, status=400)

    try:
        student = Student.objects.create(
            first_name=first_name,
            last_name=last_name,
            admission_number=admission_number,
            class_group=class_group,
        )
    except IntegrityError:
        # Likely duplicate admission number or similar constraint
        return JsonResponse({"error": "A student with this admission number already exists."}, status=400)
    except Exception as exc:  # Fallback safety
        return JsonResponse({"error": f"Failed to create student: {exc}"}, status=500)

    # Safely format balance if present, otherwise default to 0.00
    balance_val = getattr(student, "balance", 0) or 0
    try:
        balance_str = f"{balance_val:.2f}"
    except Exception:
        balance_str = "0.00"

    return JsonResponse(
        {
            "id": student.id,
            "name": f"{student.first_name} {student.last_name}",
            "balance": balance_str,
        }
    )


@login_required
@csrf_exempt
def edit_student_ajax(request, student_id):
    student = get_object_or_404(Student, id=student_id)
    if request.method == "POST":
        student.first_name = request.POST.get("first_name", student.first_name)
        student.last_name = request.POST.get("last_name", student.last_name)
        student.admission_number = request.POST.get("admission_number", student.admission_number)
        student.save()
        return JsonResponse({
            "id": student.id,
            "name": f"{student.first_name} {student.last_name}"
        })


@login_required
@csrf_exempt
def delete_student_ajax(request, student_id):
    student = get_object_or_404(Student, id=student_id)
    if request.method == "POST":
        student.delete()
        return JsonResponse({"success": True, "id": student_id})
        

@staff_member_required
def admin_payments(request):
    selected_class_id = request.GET.get("class")
    selected_class_obj = None

    # All classes
    class_groups = ClassGroup.objects.all()

    # Student queryset (filtered if a class is chosen)
    students = Student.objects.all()
    if selected_class_id:
        try:
            selected_class_obj = ClassGroup.objects.get(id=selected_class_id)
            students = students.filter(class_group=selected_class_obj)
        except ClassGroup.DoesNotExist:
            selected_class_obj = None  # fallback if invalid ID is passed

    # Global totals
    total_paid = students.aggregate(total=Sum("amount_paid"))["total"] or 0
    total_fees = students.aggregate(total=Sum("term_fee"))["total"] or 0
    total_unpaid = total_fees - total_paid

    # Count statuses
    total_students = students.count()
    fully_paid = students.filter(amount_paid__gte=F("term_fee")).count()
    unpaid = students.filter(amount_paid=0).count()
    partial = total_students - fully_paid - unpaid

    # Per-class stats (for summary table)
    class_stats = class_groups.annotate(
        total_students=Count("students"),
        total_paid=Sum("students__amount_paid"),
        total_fees=Sum("students__term_fee"),
    )

    context = {
        "class_groups": class_groups,
        "students": students,
        "selected_class_id": selected_class_id,
        "selected_class_obj": selected_class_obj,

        # global totals
        "total_students": total_students,
        "total_paid": total_paid,
        "total_fees": total_fees,
        "total_unpaid": total_unpaid,
        "fully_paid": fully_paid,
        "unpaid": unpaid,
        "partial": partial,

        # per-class summary
        "class_stats": class_stats,
    }
    return render(request, "lessons/admin_payments.html", context)
