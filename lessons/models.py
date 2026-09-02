from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone


# ----------------------------
# Academic Year model
# ----------------------------
class AcademicYear(models.Model):
    """Academic year (e.g., 2025-2026) for organizing all school data."""
    
    name = models.CharField(max_length=20, unique=True, help_text="e.g., 2025-2026")
    start_date = models.DateField()
    end_date = models.DateField()
    is_active = models.BooleanField(default=False, help_text="The currently active academic year")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-start_date']
        verbose_name = "Academic Year"
        verbose_name_plural = "Academic Years"

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        """Ensure only one academic year is active at a time."""
        if self.is_active:
            # Deactivate all other academic years
            AcademicYear.objects.filter(is_active=True).exclude(pk=self.pk).update(is_active=False)
        super().save(*args, **kwargs)


# ----------------------------
# Term model
# ----------------------------
class Term(models.Model):
    """Academic term (e.g., Term 1, Term 2, Term 3) within an academic year."""
    
    name = models.CharField(max_length=50, help_text="e.g., Term 1, Term 2, Term 3")
    academic_year = models.ForeignKey(
        AcademicYear,
        on_delete=models.CASCADE,
        related_name="terms",
        help_text="Academic year for this term"
    )
    start_date = models.DateField(help_text="Start date of this term")
    end_date = models.DateField(help_text="End date of this term")
    is_active = models.BooleanField(default=False, help_text="The currently active term")
    is_skipped = models.BooleanField(default=False, help_text="Mark if this term was skipped during setup")
    is_wrapped = models.BooleanField(default=False, help_text="Mark if this term has been wrapped/completed")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['start_date']
        verbose_name = "Term"
        verbose_name_plural = "Terms"
        unique_together = [['name', 'academic_year']]

    def __str__(self):
        return f"{self.name} ({self.academic_year.name})"

    def save(self, *args, **kwargs):
        """Ensure only one term is active at a time within the same academic year."""
        if self.is_active:
            Term.objects.filter(is_active=True, academic_year=self.academic_year).exclude(pk=self.pk).update(is_active=False)
        super().save(*args, **kwargs)


# ----------------------------
# Subject model
# ----------------------------
class Subject(models.Model):
    name = models.CharField(max_length=100)

    def __str__(self):
        return self.name


# ----------------------------
# ClassGroup model
# ----------------------------
class ClassGroup(models.Model):
    name = models.CharField(max_length=50)
    academic_year = models.ForeignKey(
        AcademicYear,
        on_delete=models.CASCADE,
        related_name="class_groups",
        null=True,
        blank=True,
        help_text="Academic year for this class group"
    )
    class_teacher = models.OneToOneField(
        "Teacher",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="main_class"
    )

    def __str__(self):
        year_str = f" ({self.academic_year.name})" if self.academic_year else ""
        return f"{self.name}{year_str}"

# ----------------------------
# Teacher model
# ----------------------------
class Teacher(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    subjects = models.ManyToManyField(Subject, blank=True)
    class_groups = models.ManyToManyField(ClassGroup, blank=True)
    profile_picture = models.ImageField(upload_to='profile_pics/', blank=True, null=True)
    
    # New field to indicate if a teacher is a class teacher
    is_class_teacher = models.BooleanField(default=False)

    def __str__(self):
        return self.user.get_full_name() or self.user.username

# ----------------------------
# Timetable model
# ----------------------------
class Timetable(models.Model):
    DAYS = [
        ('Mon', 'Monday'),
        ('Tue', 'Tuesday'),
        ('Wed', 'Wednesday'),
        ('Thu', 'Thursday'),
        ('Fri', 'Friday'),
    ]

    subject_fk = models.ForeignKey(Subject, on_delete=models.CASCADE, null=True, blank=True)
    teacher = models.ForeignKey(Teacher, on_delete=models.CASCADE)
    class_groups = models.ManyToManyField(ClassGroup)
    day = models.CharField(max_length=3, choices=DAYS)
    start_time = models.TimeField()
    end_time = models.TimeField()
    academic_year = models.ForeignKey(
        AcademicYear,
        on_delete=models.CASCADE,
        related_name="timetables",
        null=True,
        blank=True,
        help_text="Academic year for this timetable"
    )
    term = models.ForeignKey(
        Term,
        on_delete=models.CASCADE,
        related_name="timetables",
        null=True,
        blank=True,
        help_text="Term for this timetable"
    )

    def __str__(self):
        if self.subject_fk:
            return f"{self.subject_fk.name} - {self.get_day_display()} {self.start_time.strftime('%H:%M')}"
        return f"Unnamed - {self.get_day_display()} {self.start_time.strftime('%H:%M')}"

    def clean(self):
        """Prevent a teacher from having *different* subjects in the
        same time slot.

        We still allow joint classes, where the same teacher teaches the
        same subject to multiple classes at once, possibly using more
        than one Timetable row. What we block is a situation where the
        teacher is assigned to two different subjects at the exact same
        day/start/end time.
        """

        from django.core.exceptions import ValidationError

        if not (self.teacher and self.day and self.start_time and self.end_time):
            return

        clash_qs = (
            Timetable.objects
            .filter(
                teacher=self.teacher,
                day=self.day,
                start_time=self.start_time,
                end_time=self.end_time,
            )
            .exclude(pk=self.pk)
        )

        # Allow same subject in the same slot (joint classes),
        # but block if there is at least one clash with a
        # *different* subject.
        if clash_qs.exclude(subject_fk=self.subject_fk).exists():
            raise ValidationError(
                {
                    "teacher": (
                        "This teacher is already assigned a different subject in this time "
                        "slot. A teacher can only teach one subject at a time; use the same "
                        "subject to create joint classes across multiple groups."
                    )
                }
            )

# ----------------------------
# Week model
# ----------------------------
class Week(models.Model):
    number = models.PositiveIntegerField(help_text="Week number (e.g., 1, 2, 3...)")  # Week 1, Week 2...
    academic_year = models.ForeignKey(
        AcademicYear,
        on_delete=models.CASCADE,
        related_name="weeks",
        null=True,
        blank=True,
        help_text="Academic year for this week"
    )
    term = models.ForeignKey(
        Term,
        on_delete=models.CASCADE,
        related_name="weeks",
        null=True,
        blank=True,
        help_text="Term for this week"
    )
    start_date = models.DateField(help_text="Start date of this week")
    end_date = models.DateField(help_text="End date of this week")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        year_str = f" {self.academic_year.name}" if self.academic_year else ""
        return f"Week {self.number}{year_str} ({self.start_date} - {self.end_date})"


# ----------------------------
# Normal lessons (Jago-style slot + attendance models)
# ----------------------------

class NormalLessonSlot(models.Model):
    DAYS = [
        ("Mon", "Monday"),
        ("Tue", "Tuesday"),
        ("Wed", "Wednesday"),
        ("Thu", "Thursday"),
        ("Fri", "Friday"),
    ]

    day = models.CharField(max_length=3, choices=DAYS)
    start_time = models.TimeField()
    end_time = models.TimeField()
    class_group = models.ForeignKey(
        ClassGroup,
        on_delete=models.CASCADE,
        related_name="normal_slots",
    )
    subject_fk = models.ForeignKey(Subject, on_delete=models.CASCADE)
    teacher = models.ForeignKey(Teacher, on_delete=models.CASCADE)
    academic_year = models.ForeignKey(
        AcademicYear,
        on_delete=models.CASCADE,
        related_name="normal_slots",
        null=True,
        blank=True,
        help_text="Academic year for this lesson slot"
    )
    term = models.ForeignKey(
        Term,
        on_delete=models.CASCADE,
        related_name="normal_slots",
        null=True,
        blank=True,
        help_text="Term for this lesson slot"
    )

    def __str__(self):
        return f"{self.class_group} {self.get_day_display()} {self.start_time.strftime('%H:%M')} - {self.end_time.strftime('%H:%M')}"

    class Meta:
        verbose_name = "Lesson slot"
        verbose_name_plural = "Lesson slots"


class NormalLessonAttendance(models.Model):
    STATUS_CHOICES = [
        ("Pending", "Pending"),
        ("Attended", "Attended"),
        ("Not Attended", "Not Attended"),
    ]

    slot = models.ForeignKey(
        NormalLessonSlot,
        on_delete=models.CASCADE,
        related_name="attendances",
    )
    date = models.DateField(default=timezone.now)
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="Pending",
    )
    marked_at = models.DateTimeField(auto_now_add=True)
    marked_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )

    def __str__(self):
        return f"{self.slot} on {self.date} ({self.status})"

    class Meta:
        verbose_name = "Lesson attendance"
        verbose_name_plural = "Lesson attendances"


"""Joint timetable configuration models.

These models allow configuring which subjects run in joint classes and
which class groups move together, without changing code.
"""


class JointSubject(models.Model):
    subject = models.OneToOneField(Subject, on_delete=models.CASCADE)
    active = models.BooleanField(default=True)

    def __str__(self) -> str:  # pragma: no cover - simple representation
        status = "active" if self.active else "inactive"
        return f"JointSubject({self.subject.name} - {status})"


class JointClassGroupSet(models.Model):
    name = models.CharField(max_length=100, unique=True)
    class_groups = models.ManyToManyField(ClassGroup, blank=True)
    active = models.BooleanField(default=True)

    def __str__(self) -> str:  # pragma: no cover - simple representation
        return f"JointClassGroupSet({self.name})"


class SubjectGroup(models.Model):
    """Group of subjects that run together in the same time slot (e.g., technical electives)."""
    name = models.CharField(max_length=100, help_text="e.g., Technical Subjects")
    subjects = models.ManyToManyField(Subject, help_text="Subjects that run together")
    joint_class_group = models.ForeignKey(
        JointClassGroupSet,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="Optional: restrict to specific joint class group"
    )
    academic_year = models.ForeignKey(
        AcademicYear,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        help_text="Optional: restrict to specific academic year"
    )
    active = models.BooleanField(default=True)

    def __str__(self) -> str:  # pragma: no cover - simple representation
        status = "active" if self.active else "inactive"
        return f"SubjectGroup({self.name} - {status})"


# ----------------------------
# LessonRecord model (remedial/normal unified records)
# ----------------------------

class LessonRecord(models.Model):
    timetable = models.ForeignKey(Timetable, on_delete=models.CASCADE)
    week = models.ForeignKey(Week, on_delete=models.CASCADE)
    created_by = models.ForeignKey(Teacher, on_delete=models.CASCADE, related_name="created_lessons")

    teacher = models.ForeignKey(
        Teacher,
        on_delete=models.CASCADE,
        related_name="lesson_records",
        null=True,
        blank=True,
    )

    status = models.CharField(
        max_length=20,
        choices=[
            ("Pending", "Pending"),
            ("Attended", "Attended"),
            ("Not Attended", "Not Attended"),
        ],
        default="Pending"
    )

    # Add these back
    payment_status = models.CharField(
        max_length=20,
        choices=[
            ("Unpaid", "Unpaid"),
            ("Paid", "Paid"),
        ],
        default="Unpaid"
    )

    amount = models.DecimalField(max_digits=8, decimal_places=2, default=0)

    def __str__(self):
        return f"{self.teacher} - {self.timetable} ({self.week})"


    status = models.CharField(
        max_length=20,
        choices=[
            ("Pending", "Pending"),
            ("Attended", "Attended"),
            ("Not Attended", "Not Attended"),
        ],
        default="Pending"
    )

    payment_status = models.CharField(
        max_length=20,
        choices=[
            ("Unpaid", "Unpaid"),
            ("Paid", "Paid"),
        ],
        default="Unpaid"
    )

    amount = models.DecimalField(max_digits=10, decimal_places=2, default=400)

    def save(self, *args, **kwargs):
        if self.amount is None:  # only replace if it's not set
            self.amount = 400
        super().save(*args, **kwargs)
        
class Student(models.Model):
    first_name = models.CharField(max_length=50)
    last_name = models.CharField(max_length=50)
    admission_number = models.CharField(max_length=20, unique=True)
    class_group = models.ForeignKey(ClassGroup, on_delete=models.CASCADE, related_name='students')
    term = models.ForeignKey(Term, on_delete=models.SET_NULL, null=True, blank=True, related_name='students', help_text="Current term for this student")
    
    # Payment info
    term_fee = models.DecimalField(max_digits=8, decimal_places=2, default=1500)  # Default per term
    amount_paid = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    
    # Optional: to track debt
    @property
    def balance(self):
        return self.term_fee - self.amount_paid

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.admission_number})"


class StudentPreviousBalance(models.Model):
    """Track previous year unpaid balances carried forward to current year."""
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='previous_balances')
    academic_year = models.ForeignKey(AcademicYear, on_delete=models.CASCADE, related_name='previous_balances')
    amount = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    is_carried_forward = models.BooleanField(default=False, help_text="Whether this balance was automatically carried forward from previous year")
    notes = models.TextField(blank=True, help_text="Notes about this previous balance")
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.student} - {self.academic_year}: {self.amount}"

class StudentPayment(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='payments')
    amount = models.DecimalField(max_digits=8, decimal_places=2)
    date_paid = models.DateField(auto_now_add=True)  # Defaults to today
    term = models.CharField(max_length=20)  # Optional: "Term 1", "Term 2", etc.
    academic_year = models.ForeignKey(
        AcademicYear,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="student_payments",
        help_text="Academic year when payment was made"
    )
    recorded_by = models.ForeignKey(Teacher, on_delete=models.SET_NULL, null=True, blank=True)  # Who collected the payment

    def __str__(self):
        year_str = f" [{self.academic_year.name}]" if self.academic_year else ""
        return f"{self.student} - Paid {self.amount} on {self.date_paid}{year_str}"
    
    class Meta:
        ordering = ['-date_paid']  # Latest payments first


class TeacherPushSubscription(models.Model):
    """Web push subscription for a teacher's browser/device."""

    teacher = models.ForeignKey(
        Teacher,
        on_delete=models.CASCADE,
        related_name="push_subscriptions",
    )
    endpoint = models.URLField(unique=True)
    p256dh = models.CharField(max_length=200)
    auth = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Subscription for {self.teacher} ({self.endpoint[:40]}...)"


class SentClassNotification(models.Model):
    """Record that a normal-class lesson notification was sent."""

    slot = models.ForeignKey(
        NormalLessonSlot,
        on_delete=models.CASCADE,
        related_name="sent_notifications",
    )
    date = models.DateField()
    start_time = models.TimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = (("slot", "date", "start_time"),)

    def __str__(self):
        return f"Notif for {self.slot} on {self.date} at {self.start_time}"


class SentRemedialNotification(models.Model):
    """Record that a remedial lesson notification was sent."""

    timetable = models.ForeignKey(
        Timetable,
        on_delete=models.CASCADE,
        related_name="sent_remedial_notifications",
    )
    date = models.DateField()
    start_time = models.TimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = (("timetable", "date", "start_time"),)

    def __str__(self):
        return f"Remedial notif for {self.timetable} on {self.date} at {self.start_time}"


class PasswordResetToken(models.Model):
    """One-time password reset tokens for users (linked from the admin dashboard)."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="password_reset_tokens")
    code = models.CharField(max_length=32, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    is_used = models.BooleanField(default=False)

    def __str__(self):
        return f"Token for {self.user.username} ({'used' if self.is_used else 'active'})"
