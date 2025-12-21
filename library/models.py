from django.db import models
from django.utils import timezone
from django.core.exceptions import ValidationError
from lessons.models import Student, Subject
from django.contrib.auth.models import User


class Book(models.Model):
    STATUS_CHOICES = [
        ("available", "Available"),
        ("assigned", "Assigned"),
        ("lost", "Lost"),
    ]

    title = models.CharField(max_length=255)
    # Use existing Subject model from lessons as the category/subject dropdown
    category = models.ForeignKey(Subject, on_delete=models.SET_NULL, null=True, blank=True)
    isbn = models.CharField(max_length=32, blank=True)
    book_number = models.CharField(max_length=50, blank=True, help_text="Internal book number/code")
    price = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="available")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.title} ({self.book_number})" if self.book_number else self.title


class BorrowRecord(models.Model):
    STATUS = [
        ("borrowed", "Borrowed"),
        ("returned", "Returned"),
        ("lost", "Lost"),
    ]

    book = models.ForeignKey(Book, on_delete=models.CASCADE, related_name="borrow_records")
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="borrowed_books")
    assigned_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    date_borrowed = models.DateField(default=timezone.localdate)
    expected_return_date = models.DateField(null=True, blank=True)
    date_returned = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS, default="borrowed")
    notes = models.TextField(blank=True)
    # When a lost-book penalty is cleared/paid, mark this True
    loss_cleared = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    def clean(self):
        # Prevent borrowing a book that is already assigned (unless it's being returned)
        if self.status == "borrowed" and self.book.status == "assigned":
            raise ValidationError("This book is already assigned to someone else.")

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
        # Update book status to reflect current borrowing state
        if self.status == "borrowed":
            if self.book.status != "assigned":
                self.book.status = "assigned"
                self.book.save(update_fields=["status"])
        elif self.status == "returned":
            # When marked returned, update book to available
            if self.book.status != "available":
                self.book.status = "available"
                self.book.save(update_fields=["status"])

    def __str__(self):
        return f"{self.book} -> {self.student} ({self.status})"
