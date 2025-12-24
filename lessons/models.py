from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone




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
    class_teacher = models.OneToOneField(
        "Teacher",
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="main_class"
    )

    def __str__(self):
        return self.name

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
    number = models.PositiveIntegerField()  # Week 1, Week 2...
    start_date = models.DateField()
    end_date = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Week {self.number} ({self.start_date} - {self.end_date})"


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
    
    # Payment info
    term_fee = models.DecimalField(max_digits=8, decimal_places=2, default=1500)  # Default per term
    amount_paid = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    
    # Optional: to track debt
    @property
    def balance(self):
        return self.term_fee - self.amount_paid

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.admission_number})"

class StudentPayment(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='payments')
    amount = models.DecimalField(max_digits=8, decimal_places=2)
    date_paid = models.DateField(auto_now_add=True)  # Defaults to today
    term = models.CharField(max_length=20)  # Optional: "Term 1", "Term 2", etc.
    recorded_by = models.ForeignKey(Teacher, on_delete=models.SET_NULL, null=True, blank=True)  # Who collected the payment

    def __str__(self):
        return f"{self.student} - Paid {self.amount} on {self.date_paid}"
    
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
