from django.contrib import admin
from django.db import models as db_models
from .models import (
    AcademicYear,
    Term,
    Subject,
    ClassGroup,
    Teacher,
    Timetable,
    Week,
    NormalLessonSlot,
    NormalLessonAttendance,
    LessonRecord,
    TeacherPushSubscription,
    SentClassNotification,
    SentRemedialNotification,
    PasswordResetToken,
    JointSubject,
    JointClassGroupSet,
    SubjectGroup,
    Student, 
    StudentPayment,
    StudentPreviousBalance
)
from . import views
from django.contrib.admin import AdminSite
from django import forms
from django.contrib.auth.models import User, Group
from django.contrib.auth.admin import UserAdmin, GroupAdmin
from django.urls import path
from django.shortcuts import render, redirect
from django.contrib import messages
from .models import Student, StudentPayment, Week, ClassGroup



class MyAdminSite(AdminSite):
    site_header = "Remedial System Admin"     # Top left banner
    site_title = "Remedial Admin Portal"      # Browser tab
    index_title = "Welcome to the Admin Dashboard"  # Dashboard title
    # Use the modern custom index template with cards/portals
    index_template = "admin/myadmin_index.html"
    
    def index(self, request, extra_context=None):
        return super().index(request, extra_context)

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "setup-guide/",
                self.admin_view(self.setup_guide),
                name="setup_guide",
            ),
            path(
                "setup-guide/add-year/",
                self.admin_view(self.add_year),
                name="setup_add_year",
            ),
            path(
                "setup-guide/add-term/",
                self.admin_view(self.add_term),
                name="setup_add_term",
            ),
            path(
                "setup-guide/skip-term/",
                self.admin_view(self.skip_term),
                name="setup_skip_term",
            ),
            path(
                "setup-guide/wrap-term/<int:term_id>/",
                self.admin_view(self.wrap_term),
                name="setup_wrap_term",
            ),
            path(
                "setup-guide/close-year/<int:year_id>/",
                self.admin_view(self.close_year),
                name="setup_close_year",
            ),
            path(
                "setup-guide/promote-students/",
                self.admin_view(self.promote_students),
                name="setup_promote_students",
            ),
            path(
                "remedial-stats/",
                self.admin_view(views.remedial_stats),
                name="remedial_stats",
            ),
            path(
                "remedial-stats/teacher/<int:teacher_id>/",
                self.admin_view(views.remedial_teacher_details),
                name="remedial_teacher_details",
            ),
            # Deputy normal-classes stats within the admin site
            path(
                "normal-stats/",
                self.admin_view(views.deputy_normal_stats),
                name="deputy_normal_stats",
            ),
            path(
                "normal-stats/teacher/<int:teacher_id>/",
                self.admin_view(views.normal_teacher_details),
                name="deputy_normal_teacher_details",
            ),
        ]
        return custom_urls + urls

    def setup_guide(self, request):
        """Setup guide dashboard showing first-time setup steps."""
        from .models import AcademicYear, Term, Week
        
        # Handle year selection from URL parameter
        select_year_id = request.GET.get('select_year')
        if select_year_id:
            try:
                selected_year = AcademicYear.objects.get(id=select_year_id)
                request.session['selected_academic_year_id'] = selected_year.id
            except AcademicYear.DoesNotExist:
                selected_year = AcademicYear.objects.first()
        else:
            # Get selected academic year from session
            selected_year_id = request.session.get('selected_academic_year_id')
            selected_year = None
            if selected_year_id:
                try:
                    selected_year = AcademicYear.objects.get(id=selected_year_id)
                except AcademicYear.DoesNotExist:
                    selected_year = AcademicYear.objects.first()
            else:
                selected_year = AcademicYear.objects.first()
        
        # Filter terms by selected academic year
        if selected_year:
            terms = Term.objects.filter(academic_year=selected_year)
            weeks = Week.objects.filter(academic_year=selected_year)
        else:
            terms = Term.objects.none()
            weeks = Week.objects.none()
        
        # Check setup status
        has_academic_year = AcademicYear.objects.exists()
        has_terms = terms.exists()
        has_weeks = weeks.exists()
        
        context = {
            'has_academic_year': has_academic_year,
            'has_terms': has_terms,
            'has_weeks': has_weeks,
            'academic_years': AcademicYear.objects.all(),
            'selected_academic_year': selected_year,
            'terms': terms,
            'weeks': weeks,
        }
        
        return render(request, "admin/lessons/setup_guide.html", context)

    def add_term(self, request):
        """Handle term addition from setup guide with auto-week generation."""
        if request.method == 'POST':
            from .models import Term, Week
            from datetime import timedelta, datetime
            name = request.POST.get('name')
            academic_year_id = request.POST.get('academic_year')
            start_date = request.POST.get('start_date')
            end_date = request.POST.get('end_date')
            
            try:
                academic_year = AcademicYear.objects.get(id=academic_year_id)
                term = Term.objects.create(
                    name=name,
                    academic_year=academic_year,
                    start_date=start_date,
                    end_date=end_date
                )
                
                # Auto-generate weeks (Mon-Sat, skip Sundays)
                current_date = datetime.strptime(start_date, '%Y-%m-%d').date()
                term_end = datetime.strptime(end_date, '%Y-%m-%d').date()
                week_number = 1
                
                while current_date <= term_end:
                    # Find Monday of this week
                    if current_date.weekday() != 0:  # Not Monday
                        current_date = current_date - timedelta(days=current_date.weekday())
                    
                    week_start = current_date
                    week_end = week_start + timedelta(days=5)  # Saturday
                    
                    # If week_end goes beyond term, cap it
                    if week_end > term_end:
                        week_end = term_end
                    
                    # Only create if week_start is within term
                    if week_start <= term_end:
                        Week.objects.create(
                            number=week_number,
                            academic_year=academic_year,
                            term=term,
                            start_date=week_start,
                            end_date=week_end
                        )
                        week_number += 1
                    
                    # Move to next Monday
                    current_date = week_end + timedelta(days=2)  # Skip Sunday, go to next Monday
                
                messages.success(request, f"Term '{name}' added with {week_number - 1} weeks (Mon-Sat)!")
            except Exception as e:
                messages.error(request, f"Error adding term: {str(e)}")
        
        return redirect('myadmin:setup_guide')

    def skip_term(self, request):
        """Handle skipping a term during setup."""
        if request.method == 'POST':
            from .models import Term
            name = request.POST.get('name')
            academic_year_id = request.POST.get('academic_year')
            start_date = request.POST.get('start_date')
            end_date = request.POST.get('end_date')
            
            try:
                academic_year = AcademicYear.objects.get(id=academic_year_id)
                term = Term.objects.create(
                    name=name,
                    academic_year=academic_year,
                    start_date=start_date,
                    end_date=end_date,
                    is_skipped=True  # Mark as skipped
                )
                messages.success(request, f"Term '{name}' skipped (no weeks generated).")
            except Exception as e:
                messages.error(request, f"Error skipping term: {str(e)}")
        
        return redirect('myadmin:setup_guide')

    def add_year(self, request):
        """Handle academic year addition from setup guide."""
        if request.method == 'POST':
            name = request.POST.get('name')
            start_date = request.POST.get('start_date')
            end_date = request.POST.get('end_date')
            
            try:
                year = AcademicYear.objects.create(
                    name=name,
                    start_date=start_date,
                    end_date=end_date
                )
                # Set the new year as selected
                request.session['selected_academic_year_id'] = year.id
                messages.success(request, f"Academic year '{name}' added successfully!")
            except Exception as e:
                messages.error(request, f"Error adding academic year: {str(e)}")
        
        return redirect('myadmin:setup_guide')

    def promote_students(self, request):
        """Promote students to their next class in the NEXT academic year."""
        from .models import Student, ClassGroup
        
        # Get the current active year
        current_year = AcademicYear.objects.filter(is_active=True).first()
        if not current_year:
            messages.error(request, "No active academic year found.")
            return redirect('myadmin:setup_guide')
        
        # Find or create the next academic year
        next_year = AcademicYear.objects.filter(is_active=False).order_by('-created_at').first()
        if not next_year:
            messages.error(request, "Please create the next academic year first before promoting students.")
            return redirect('myadmin:setup_guide')
        
        # Get all classes in the current year
        current_classes = ClassGroup.objects.filter(academic_year=current_year)
        
        # Promotion patterns
        promotion_map = {
            'Grade 10N': 'Grade 11N',
            'Grade 10S': 'Grade 11S',
            'Form 3 West': 'Form 4 West',
            'Form 3 S': 'Form 4 S',
            'Form 3': 'Form 4',
        }
        
        promoted_count = 0
        graduated_count = 0
        not_promoted_count = 0
        
        for current_class in current_classes:
            # Determine the next class name
            next_class_name = promotion_map.get(current_class.name)
            
            if not next_class_name:
                # No promotion rule for this class (e.g., Form 4 is dead end - they graduate)
                graduated_count += current_class.students.count()
                continue
            
            # Find or create the next class in the NEXT year
            next_class = ClassGroup.objects.filter(
                name=next_class_name,
                academic_year=next_year
            ).first()
            
            if not next_class:
                # Create the next class if it doesn't exist in the next year
                next_class = ClassGroup.objects.create(
                    name=next_class_name,
                    academic_year=next_year
                )
            
            # Move all students from current class to next class in next year
            students_moved = Student.objects.filter(class_group=current_class).update(class_group=next_class)
            promoted_count += students_moved
        
        messages.success(request, f"Promotion complete! {promoted_count} students promoted to next academic year ({next_year.name}). {graduated_count} students graduated (dead end classes).")
        return redirect('myadmin:setup_guide')

    def wrap_term(self, request, term_id):
        """Handle wrapping/completing a term."""
        try:
            from .models import Term
            term = Term.objects.get(id=term_id)
            term.is_wrapped = True
            term.save()
            messages.success(request, f"Term '{term.name}' has been wrapped successfully!")
        except Term.DoesNotExist:
            messages.error(request, "Term not found.")
        except Exception as e:
            messages.error(request, f"Error wrapping term: {str(e)}")
        
        return redirect('myadmin:setup_guide')

    def close_year(self, request, year_id):
        """Close an academic year and set up the next year with automatic promotion and balance carry-forward."""
        from .models import AcademicYear, Student, StudentPayment, StudentPreviousBalance, Term, Week, Teacher, ClassGroup
        from decimal import Decimal
        from django.db.models import Sum
        from datetime import timedelta, datetime
        
        try:
            year = AcademicYear.objects.get(id=year_id)
            
            # Mark the year as inactive
            year.is_active = False
            year.save()
            
            # Mark all terms in this year as wrapped if not already
            terms = Term.objects.filter(academic_year=year, is_wrapped=False)
            for term in terms:
                term.is_wrapped = True
                term.save()
            
            # Calculate and carry forward unpaid balances
            total_fee_per_student = Decimal('1500.00')
            terms_count = Term.objects.filter(academic_year=year).count()
            total_expected_fees = total_fee_per_student * terms_count if terms_count > 0 else Decimal('0')
            
            # Store unpaid balances for promotion
            student_unpaid_balances = {}
            for student in Student.objects.all():
                payments = StudentPayment.objects.filter(
                    student=student,
                    academic_year=year
                ).exclude(term="Previous Balance")
                total_paid = payments.aggregate(Sum('amount'))['amount__sum'] or Decimal('0')
                unpaid_balance = total_expected_fees - total_paid
                if unpaid_balance > 0:
                    student_unpaid_balances[student.id] = unpaid_balance
            
            # Check if POST request with next year setup data
            if request.method == 'POST':
                next_year_name = request.POST.get('next_year_name')
                next_year_start = request.POST.get('next_year_start')
                next_year_end = request.POST.get('next_year_end')
                
                if not next_year_name or not next_year_start or not next_year_end:
                    messages.error(request, "Please provide all next year details.")
                    return redirect('myadmin:setup_guide')
                
                # Create next academic year
                next_year = AcademicYear.objects.create(
                    name=next_year_name,
                    start_date=next_year_start,
                    end_date=next_year_end,
                    is_active=True
                )
                
                # Create terms for next year
                term_names = ['Term 1', 'Term 2', 'Term 3']
                for i, term_name in enumerate(term_names):
                    term_start = request.POST.get(f'term_{i+1}_start')
                    term_end = request.POST.get(f'term_{i+1}_end')
                    
                    if term_start and term_end:
                        term = Term.objects.create(
                            name=term_name,
                            academic_year=next_year,
                            start_date=term_start,
                            end_date=term_end
                        )
                        
                        # Auto-generate weeks for this term
                        current_date = datetime.strptime(term_start, '%Y-%m-%d').date()
                        term_end_date = datetime.strptime(term_end, '%Y-%m-%d').date()
                        week_number = 1
                        
                        while current_date <= term_end_date:
                            if current_date.weekday() != 0:  # Not Monday
                                current_date = current_date - timedelta(days=current_date.weekday())
                            
                            week_start = current_date
                            week_end = week_start + timedelta(days=5)  # Saturday
                            
                            if week_end > term_end_date:
                                week_end = term_end_date
                            
                            if week_start <= term_end_date:
                                Week.objects.create(
                                    number=week_number,
                                    academic_year=next_year,
                                    term=term,
                                    start_date=week_start,
                                    end_date=week_end
                                )
                                week_number += 1
                            
                            current_date = week_end + timedelta(days=2)
                
                # Promotion patterns
                promotion_map = {
                    'Grade 10N': 'Grade 11N',
                    'Grade 10S': 'Grade 11S',
                    'Form 3 West': 'Form 4 West',
                    'Form 3 S': 'Form 4 S',
                    'Form 3': 'Form 4',
                }
                
                # Promote students and teachers
                promoted_count = 0
                graduated_count = 0
                for current_class in ClassGroup.objects.filter(academic_year=year):
                    next_class_name = promotion_map.get(current_class.name)
                    
                    if not next_class_name:
                        graduated_count += current_class.students.count()
                        continue
                    
                    # Create next class in new year
                    next_class = ClassGroup.objects.create(
                        name=next_class_name,
                        academic_year=next_year,
                        class_teacher=current_class.class_teacher  # Move teacher too
                    )
                    
                    # Move students
                    students_moved = Student.objects.filter(class_group=current_class).update(class_group=next_class)
                    promoted_count += students_moved
                    
                    # Create previous balance records for promoted students
                    for student in next_class.students.all():
                        if student.id in student_unpaid_balances:
                            StudentPreviousBalance.objects.create(
                                student=student,
                                academic_year=next_year,
                                amount=student_unpaid_balances[student.id],
                                is_carried_forward=True,
                                notes=f"Carried forward from {year.name}"
                            )
                
                # Clear the selected academic year from session
                if 'selected_academic_year_id' in request.session:
                    del request.session['selected_academic_year_id']
                
                messages.success(request, f"Academic year '{year.name}' closed successfully! Next year '{next_year.name}' created with 3 terms. {promoted_count} students promoted. {graduated_count} students graduated. Unpaid balances carried forward.")
                return redirect('myadmin:setup_guide')
            
            # If GET request, show the setup form
            context = {
                'current_year': year,
                'student_unpaid_balances': student_unpaid_balances,
            }
            return render(request, "admin/lessons/close_year_setup.html", context)
            
        except AcademicYear.DoesNotExist:
            messages.error(request, "Academic year not found.")
        except Exception as e:
            messages.error(request, f"Error closing academic year: {str(e)}")
        
        return redirect('myadmin:setup_guide')


# ----------------------------
# Academic Year Admin
# ----------------------------
class AcademicYearAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'start_date', 'end_date', 'is_active', 'created_at', 'get_terms_count')
    list_filter = ('is_active',)
    search_fields = ('name',)
    ordering = ['-start_date']
    
    def get_terms_count(self, obj):
        return obj.terms.count()
    get_terms_count.short_description = 'Terms'


# ----------------------------
# Term Admin
# ----------------------------
class TermAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'academic_year', 'start_date', 'end_date', 'is_active', 'get_weeks_count')
    list_filter = ('academic_year', 'is_active')
    search_fields = ('name', 'academic_year__name')
    ordering = ['academic_year', 'start_date']
    actions = ['generate_weeks']
    
    def get_weeks_count(self, obj):
        return obj.weeks.count()
    get_weeks_count.short_description = 'Weeks'
    
    def generate_weeks(self, request, queryset):
        """Generate weeks for selected terms automatically."""
        from .models import Week
        from datetime import timedelta
        
        weeks_created = 0
        for term in queryset:
            current_date = term.start_date
            week_number = 1
            
            while current_date <= term.end_date:
                week_end = current_date + timedelta(days=6)
                if week_end > term.end_date:
                    week_end = term.end_date
                
                # Check if week already exists
                if not Week.objects.filter(term=term, start_date=current_date).exists():
                    Week.objects.create(
                        number=week_number,
                        academic_year=term.academic_year,
                        term=term,
                        start_date=current_date,
                        end_date=week_end
                    )
                    weeks_created += 1
                
                current_date = week_end + timedelta(days=1)
                week_number += 1
        
        self.message_user(request, f"Successfully created {weeks_created} weeks for {queryset.count()} term(s).")
    generate_weeks.short_description = "Generate weeks for selected terms"


# ----------------------------
# Subject Admin
# ----------------------------
@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ('id', 'name')
    search_fields = ('name',)


# ----------------------------
# ClassGroup Admin
# ----------------------------

@admin.register(ClassGroup)
class ClassGroupAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "academic_year", "class_teacher")  # Show class teacher in the list
    list_filter = ("academic_year",)
    search_fields = ("name", "class_teacher__user__username", "class_teacher__user__first_name", "class_teacher__user__last_name")
    change_list_template = "admin/lessons/classgroup/change_list.html"

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "payments-dashboard/",
                self.admin_site.admin_view(self.payments_dashboard),
                name="admin_payments"
            ),
        ]
        return custom_urls + urls

    def payments_dashboard(self, request):
        # Get selected academic year from session or GET parameter
        selected_year_id = request.GET.get('academic_year') or request.session.get('selected_academic_year_id')
        selected_year = None
        if selected_year_id:
            try:
                selected_year = AcademicYear.objects.get(id=selected_year_id)
            except AcademicYear.DoesNotExist:
                selected_year = AcademicYear.objects.first()
        else:
            selected_year = AcademicYear.objects.first()
        
        # Get term filter from request
        selected_term_id = request.GET.get('term')
        selected_term = None
        if selected_term_id:
            try:
                selected_term = Term.objects.get(id=selected_term_id)
            except Term.DoesNotExist:
                selected_term = None
        
        # Get class filter from request
        selected_class_id = request.GET.get('class')
        selected_class_obj = None
        if selected_class_id:
            try:
                selected_class_obj = ClassGroup.objects.get(id=selected_class_id)
            except ClassGroup.DoesNotExist:
                selected_class_obj = None
        
        # Filter students by selected academic year, term, and class
        if selected_year:
            students = Student.objects.filter(class_group__academic_year=selected_year)
        else:
            students = Student.objects.none()
        
        if selected_term:
            students = students.filter(term=selected_term)
        
        if selected_class_obj:
            students = students.filter(class_group=selected_class_obj)
        
        # Filter payments by selected academic year and term
        if selected_year:
            payments = StudentPayment.objects.filter(academic_year=selected_year)
            if selected_term:
                payments = payments.filter(term=selected_term.name)
        else:
            payments = StudentPayment.objects.none()
        
        # Get all academic years and terms for filters
        academic_years = AcademicYear.objects.all()
        if selected_year:
            terms = Term.objects.filter(academic_year=selected_year)
        else:
            # Show all terms when no year is selected
            terms = Term.objects.all()
        
        # Get class groups for filter
        class_groups = ClassGroup.objects.all()
        if selected_year:
            class_groups = class_groups.filter(academic_year=selected_year)
        
        # Calculate summary statistics
        total_students = students.count()
        fully_paid = students.filter(amount_paid__gte=db_models.F('term_fee')).count()
        unpaid = students.filter(amount_paid=0).count()
        partial = total_students - fully_paid - unpaid
        total_fees = students.aggregate(total=db_models.Sum('term_fee'))['total'] or 0
        total_paid = students.aggregate(total=db_models.Sum('amount_paid'))['total'] or 0
        total_unpaid = total_fees - total_paid
        
        # Calculate per-class statistics
        class_stats = []
        for group in class_groups:
            class_students = students.filter(class_group=group)
            class_total_students = class_students.count()
            class_total_fees = class_students.aggregate(total=db_models.Sum('term_fee'))['total'] or 0
            class_total_paid = class_students.aggregate(total=db_models.Sum('amount_paid'))['total'] or 0
            class_stats.append({
                'name': group.name,
                'total_students': class_total_students,
                'total_fees': class_total_fees,
                'total_paid': class_total_paid,
            })

        return render(request, "lessons/admin_payments.html", {
            "students": students,
            "payments": payments,
            "selected_academic_year": selected_year,
            "selected_term": selected_term,
            "selected_class_id": selected_class_id,
            "selected_class_obj": selected_class_obj,
            "academic_years": academic_years,
            "terms": terms,
            "class_groups": class_groups,
            "total_students": total_students,
            "fully_paid": fully_paid,
            "unpaid": unpaid,
            "partial": partial,
            "total_fees": total_fees,
            "total_paid": total_paid,
            "total_unpaid": total_unpaid,
            "class_stats": class_stats,
        })


# ----------------------------
# Teacher Admin
# ----------------------------
@admin.register(Teacher)
class TeacherAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'get_subjects', 'is_class_teacher')  # show is_class_teacher
    list_editable = ('is_class_teacher',)  # allow inline editing in list view
    filter_horizontal = ('subjects', 'class_groups')
    search_fields = ('user__first_name', 'user__last_name', 'subjects__name', 'class_groups__name')

    def get_subjects(self, obj):
        return ", ".join([s.name for s in obj.subjects.all()])
    get_subjects.short_description = 'Subjects'

# ----------------------------
# Timetable Admin
# ----------------------------
@admin.register(Timetable)
class TimetableAdmin(admin.ModelAdmin):
    list_display = ('id', 'subject_fk', 'teacher', 'day', 'start_time', 'end_time', 'academic_year', 'term')
    filter_horizontal = ('class_groups',)
    list_filter = ('day', 'teacher', 'academic_year', 'term')
    search_fields = ('subject_fk__name', 'teacher__user__first_name', 'teacher__user__last_name', 'class_groups__name')

    def get_classes(self, obj):
        return ", ".join([c.name for c in obj.class_groups.all()])
    get_classes.short_description = 'Classes'


# ----------------------------
# Week Admin
# ----------------------------
@admin.register(Week)
class WeekAdmin(admin.ModelAdmin):
    list_display = ('id', 'number', 'academic_year', 'term', 'start_date', 'end_date', 'created_at')
    list_filter = ('academic_year', 'term')
    search_fields = ('number', 'academic_year__name', 'term__name')
    list_editable = ('number', 'start_date', 'end_date')


# ----------------------------
# NormalLessonSlot / NormalLessonAttendance Admin
# ----------------------------

@admin.register(NormalLessonSlot)
class NormalLessonSlotAdmin(admin.ModelAdmin):
    list_display = ("id", "class_group", "teacher", "subject_fk", "day", "start_time", "end_time", "academic_year", "term")
    list_filter = ("day", "class_group", "teacher", "academic_year", "term")
    search_fields = ("class_group__name", "teacher__user__first_name", "teacher__user__last_name", "subject_fk__name")


@admin.register(NormalLessonAttendance)
class NormalLessonAttendanceAdmin(admin.ModelAdmin):
    list_display = ("id", "slot", "date", "status", "marked_by", "marked_at")
    list_filter = ("status", "date")
    search_fields = ("slot__class_group__name", "slot__teacher__user__first_name", "slot__teacher__user__last_name")


# ----------------------------
# Joint timetable config Admin
# ----------------------------


@admin.register(JointSubject)
class JointSubjectAdmin(admin.ModelAdmin):
    list_display = ("subject", "active")
    list_filter = ("active",)
    search_fields = ("subject__name",)


@admin.register(JointClassGroupSet)
class JointClassGroupSetAdmin(admin.ModelAdmin):
    list_display = ("name", "active")
    list_filter = ("active",)
    filter_horizontal = ("class_groups",)


@admin.register(SubjectGroup)
class SubjectGroupAdmin(admin.ModelAdmin):
    list_display = ("name", "active", "academic_year", "joint_class_group")
    list_filter = ("active", "academic_year", "joint_class_group")
    filter_horizontal = ("subjects",)
    search_fields = ("name",)


# ----------------------------
# Custom filter for class in LessonRecord
# ----------------------------
class ClassGroupFilter(admin.SimpleListFilter):
    title = 'Class'
    parameter_name = 'class_group'

    def lookups(self, request, model_admin):
        classes = ClassGroup.objects.all()
        return [(c.id, c.name) for c in classes]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(timetable__class_groups__id=self.value())
        return queryset


# ----------------------------
# LessonRecord form
# ----------------------------
class LessonRecordForm(forms.ModelForm):
    class Meta:
        model = LessonRecord
        fields = ['created_by', 'timetable', 'week', 'status', 'payment_status', 'amount']
        labels = {
            'created_by': 'Teacher',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['timetable'].queryset = Timetable.objects.none()

        # Get selected academic year from request if available
        request = kwargs.get('request')
        selected_year_id = None
        if request:
            selected_year_id = request.session.get('selected_academic_year_id')
            if selected_year_id:
                # Filter timetables by selected academic year
                self.fields['timetable'].queryset = Timetable.objects.filter(academic_year_id=selected_year_id)
        
        # If editing an existing record, show its timetable regardless of year status
        if self.instance.pk and self.instance.timetable:
            self.fields['timetable'].queryset = Timetable.objects.filter(id=self.instance.timetable.id)
        
        if 'created_by' in self.data:
            try:
                teacher_id = int(self.data.get('created_by'))
                if request and selected_year_id:
                    self.fields['timetable'].queryset = Timetable.objects.filter(
                        teacher_id=teacher_id,
                        academic_year_id=selected_year_id
                    )
                else:
                    self.fields['timetable'].queryset = Timetable.objects.filter(teacher_id=teacher_id)
            except (ValueError, TypeError):
                pass
        elif self.instance.pk and self.instance.timetable:
            if request and selected_year_id:
                self.fields['timetable'].queryset = Timetable.objects.filter(
                    teacher=self.instance.timetable.teacher,
                    academic_year_id=selected_year_id
                )
            else:
                self.fields['timetable'].queryset = Timetable.objects.filter(
                    teacher=self.instance.timetable.teacher
                )
        
        # Filter weeks by selected academic year, but show existing week if editing
        if request and selected_year_id:
            self.fields['week'].queryset = Week.objects.filter(academic_year_id=selected_year_id).order_by('number')
        elif self.instance.pk and self.instance.week:
            # Show the existing week if editing a record from a closed year
            self.fields['week'].queryset = Week.objects.filter(id=self.instance.week.id)


# ----------------------------
# LessonRecord admin
# ----------------------------
@admin.register(LessonRecord)
class LessonRecordAdmin(admin.ModelAdmin):
    form = LessonRecordForm
    list_display = ('id', 'get_teacher', 'timetable', 'week', 'status', 'payment_status', 'amount', 'get_year_status')
    list_filter = ('week', 'week__academic_year', 'week__term', 'timetable__teacher', 'status', 'payment_status', 'week__academic_year__is_active')

    class Media:
        js = ('lessons/js/lessonrecord.js',)

    def get_form(self, request, obj=None, **kwargs):
        kwargs['request'] = request  # Pass request to form for academic year filtering
        form = super().get_form(request, obj, **kwargs)
        # pass current user id into the created_by widget
        form.base_fields['created_by'].widget.attrs['data-current-user'] = request.user.id
        return form

    def save_model(self, request, obj, form, change):
        teacher_from_form = form.cleaned_data.get('created_by')
        if teacher_from_form:
            obj.created_by = teacher_from_form
        elif obj.timetable and not obj.created_by:
            obj.created_by = obj.timetable.teacher
        super().save_model(request, obj, form, change)

    def get_teacher(self, obj):
        if obj.created_by:
            return obj.created_by.user.get_full_name()
        elif obj.timetable and obj.timetable.teacher:
            return obj.timetable.teacher.user.get_full_name()
        return ''
    get_teacher.short_description = "Teacher"

    def get_year_status(self, obj):
        if obj.week and obj.week.academic_year:
            if obj.week.academic_year.is_active:
                return "Active"
            else:
                return "Closed"
        return "N/A"
    get_year_status.short_description = "Year Status"


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ('id', 'first_name', 'last_name', 'admission_number', 'class_group', 'term_fee', 'amount_paid', 'balance', 'get_year_status')
    list_filter = ('class_group', 'class_group__academic_year', 'class_group__academic_year__is_active')
    search_fields = ('first_name', 'last_name', 'admission_number')

    def get_year_status(self, obj):
        if obj.class_group and obj.class_group.academic_year:
            if obj.class_group.academic_year.is_active:
                return "Active"
            else:
                return "Closed"
        return "N/A"
    get_year_status.short_description = "Year Status"


@admin.register(StudentPayment)
class StudentPaymentAdmin(admin.ModelAdmin):
    list_display = ('id', 'student', 'amount', 'date_paid', 'term', 'academic_year', 'get_year_status')
    list_filter = ('date_paid', 'academic_year', 'academic_year__is_active', 'term')
    search_fields = ('student__first_name', 'student__last_name', 'student__admission_number')

    def get_year_status(self, obj):
        if obj.academic_year:
            if obj.academic_year.is_active:
                return "Active"
            else:
                return "Closed"
        return "N/A"
    get_year_status.short_description = "Year Status"


@admin.register(StudentPreviousBalance)
class StudentPreviousBalanceAdmin(admin.ModelAdmin):
    list_display = ('id', 'student', 'academic_year', 'amount', 'is_carried_forward', 'created_at')
    list_filter = ('academic_year', 'is_carried_forward', 'created_at')
    search_fields = ('student__first_name', 'student__last_name', 'student__admission_number')
    readonly_fields = ('created_at',)


@admin.register(PasswordResetToken)
class PasswordResetTokenAdmin(admin.ModelAdmin):
    list_display = ("user", "code", "is_used", "created_at", "expires_at")
    search_fields = ("user__username", "user__first_name", "user__last_name", "code")
    list_filter = ("is_used", "created_at")


# ----------------------------
# Custom Admin Site
# ----------------------------
admin_site = MyAdminSite(name='myadmin')
admin_site.register(AcademicYear, AcademicYearAdmin)
admin_site.register(Term, TermAdmin)
admin_site.register(Subject, SubjectAdmin)
admin_site.register(ClassGroup, ClassGroupAdmin)
admin_site.register(Teacher, TeacherAdmin)
admin_site.register(Timetable, TimetableAdmin)
admin_site.register(Week, WeekAdmin)
admin_site.register(NormalLessonSlot, NormalLessonSlotAdmin)
admin_site.register(NormalLessonAttendance, NormalLessonAttendanceAdmin)
admin_site.register(LessonRecord, LessonRecordAdmin)
admin_site.register(JointSubject, JointSubjectAdmin)
admin_site.register(JointClassGroupSet, JointClassGroupSetAdmin)
admin_site.register(SubjectGroup, SubjectGroupAdmin)
admin_site.register(User, UserAdmin)
admin_site.register(Group, GroupAdmin)
admin_site.register(PasswordResetToken, PasswordResetTokenAdmin)
