from django.shortcuts import render, get_object_or_404, redirect
from .models import Book, BorrowRecord
from lessons.models import Student, Subject
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.urls import reverse
from .forms import (
    BorrowForm,
    BookForm,
    LibraryLoanForm,
    LibraryStudentForm,
    StudentAssignBooksForm,
)
from django.utils import timezone
from django.http import HttpResponse
from django.template.loader import render_to_string
from io import BytesIO
try:
    from xhtml2pdf import pisa
except Exception:
    pisa = None


def is_admin(user):
    return user.is_active and user.is_staff


@login_required
def book_list(request):
    books = Book.objects.all().select_related('category')
    return render(request, 'library/book_list.html', {'books': books})


@user_passes_test(is_admin)
def library_dashboard(request):
    """Simple library dashboard with small summary and main action buttons."""

    total_books = Book.objects.count()
    available_books = Book.objects.filter(status="available").count()
    assigned_books = Book.objects.filter(status="assigned").count()

    today = timezone.localdate()
    active_loans = BorrowRecord.objects.filter(status="borrowed")
    total_active_loans = active_loans.count()
    overdue_count = active_loans.filter(expected_return_date__lt=today).count()

    context = {
        "total_books": total_books,
        "available_books": available_books,
        "assigned_books": assigned_books,
        "total_active_loans": total_active_loans,
        "overdue_count": overdue_count,
    }
    return render(request, "library/dashboard.html", context)


@user_passes_test(is_admin)
def add_book(request):
    """Dedicated page for adding a new library book (custom UI, no admin)."""
    if request.method == "POST":
        form = BookForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect("library:dashboard")
    else:
        form = BookForm()

    return render(request, "library/add_book.html", {"form": form})


@user_passes_test(is_admin)
def delete_book(request, pk):
    """Confirm and delete a book from the catalogue."""
    book = get_object_or_404(Book, pk=pk)
    if request.method == 'POST':
        book.delete()
        return redirect('library:dashboard')
    return render(request, 'library/confirm_delete_book.html', {'book': book})


@user_passes_test(is_admin)
def manage_loans(request):
    """Central page to assign books to students and mark returns."""

    # Handle new loan creation
    if request.method == "POST" and request.POST.get("action") == "create_loan":
        loan_form = LibraryLoanForm(request.POST)
        if loan_form.is_valid():
            loan = loan_form.save(commit=False)
            loan.assigned_by = request.user
            loan.status = "borrowed"
            loan.save()
            return redirect("library:manage_loans")
    else:
        loan_form = LibraryLoanForm()

    # Handle mark-as-returned action
    if request.method == "POST" and request.POST.get("action") == "mark_returned":
        record_id = request.POST.get("record_id")
        if record_id:
            try:
                record = BorrowRecord.objects.get(id=record_id, status="borrowed")
                record.status = "returned"
                record.date_returned = timezone.localdate()
                record.save()
                return redirect("library:manage_loans")
            except BorrowRecord.DoesNotExist:
                pass

    # Handle mark-as-lost action
    if request.method == "POST" and request.POST.get("action") == "mark_lost":
        record_id = request.POST.get("record_id")
        if record_id:
            try:
                record = BorrowRecord.objects.get(id=record_id, status="borrowed")
                record.status = "lost"
                record.save()
                return redirect("library:manage_loans")
            except BorrowRecord.DoesNotExist:
                pass

    # Handle mark-as-cleared action
    if request.method == "POST" and request.POST.get("action") == "mark_cleared":
        record_id = request.POST.get("record_id")
        if record_id:
            try:
                record = BorrowRecord.objects.get(id=record_id, status="lost")
                record.delete()
                return redirect("library:manage_loans")
            except BorrowRecord.DoesNotExist:
                pass

    # Restrict book choices on the form to available books
    loan_form.fields["book"].queryset = Book.objects.filter(status="available").order_by("title")

    # Optional admission-number search that jumps to the student loans page
    adm = request.GET.get("adm") or ""
    if adm:
        target_student = Student.objects.filter(admission_number__iexact=adm).first()
        if target_student:
            return redirect("library:student_loans", student_id=target_student.id)

    # Active loans list (include borrowed and lost; hide only returned)
    active_loans = BorrowRecord.objects.select_related("book", "student", "student__class_group")
    active_loans = active_loans.filter(status__in=["borrowed", "lost"])
    active_loans = active_loans.order_by("-date_borrowed")

    # Student list for filter dropdown
    students = Student.objects.all().order_by("class_group__name", "admission_number")

    context = {
        "loan_form": loan_form,
        "active_loans": active_loans,
        "students": students,
    }
    return render(request, "library/manage_loans.html", context)


@user_passes_test(is_admin)
def student_loans(request, student_id: int):
    """Show current borrow/lost records for a student and allow assigning/managing loans."""

    student = get_object_or_404(Student, pk=student_id)

    # First handle per-record actions from the table (return, lost, cleared)
    if request.method == "POST" and request.POST.get("action") in {"mark_returned", "mark_lost", "mark_cleared"}:
        record_id = request.POST.get("record_id")
        action = request.POST.get("action")
        if record_id:
            try:
                rec = BorrowRecord.objects.get(id=record_id, student=student)
            except BorrowRecord.DoesNotExist:
                rec = None

            if rec:
                if action == "mark_returned":
                    rec.status = "returned"
                    rec.date_returned = timezone.localdate()
                    rec.save()
                elif action == "mark_lost":
                    rec.status = "lost"
                    rec.save()
                elif action == "mark_cleared" and rec.status == "lost":
                    # Make the book available again, then remove this lost record
                    if rec.book:
                        rec.book.status = "available"
                        rec.book.save(update_fields=["status"])
                    rec.delete()
        return redirect("library:student_loans", student_id=student.id)

    # Quick path: add a brand new book and assign it directly to this student
    if request.method == "POST" and request.POST.get("action") == "quick_add_assign":
        title = (request.POST.get("quick_title") or "").strip()
        book_number = (request.POST.get("quick_book_number") or "").strip()
        price_raw = (request.POST.get("quick_price") or "").strip()
        expected_date_str = (request.POST.get("quick_expected_return") or "").strip()
        category_id = (request.POST.get("quick_category") or "").strip()
        isbn = (request.POST.get("quick_isbn") or "").strip()

        errors = []
        if not title:
            errors.append("Title is required for the new book.")
        if not isbn:
            errors.append("ISBN is required for the new book.")
        if not book_number:
            errors.append("Book number / code is required for the new book.")
        if not price_raw:
            errors.append("Price is required for the new book.")
        if not expected_date_str:
            errors.append("Expected return date is required.")

        from decimal import Decimal, InvalidOperation
        from datetime import datetime

        price = None
        if price_raw:
            try:
                price = Decimal(price_raw)
            except InvalidOperation:
                errors.append("Price must be a valid number.")

        expected_return_date = None
        if expected_date_str:
            try:
                expected_return_date = datetime.strptime(expected_date_str, "%Y-%m-%d").date()
            except ValueError:
                errors.append("Expected return date must be a valid date.")

        category = None
        if category_id:
            try:
                category = Subject.objects.get(id=category_id)
            except Subject.DoesNotExist:
                # If lookup fails, leave category empty instead of blocking save
                category = None

        if errors:
            for e in errors:
                messages.error(request, e)
            return redirect("library:student_loans", student_id=student.id)

        # All required fields are valid; create book and immediate loan
        book = Book.objects.create(
            title=title,
            category=category,
            isbn=isbn,
            book_number=book_number,
            price=price,
            status="available",
        )

        BorrowRecord.objects.create(
            book=book,
            student=student,
            assigned_by=request.user,
            expected_return_date=expected_return_date,
            status="borrowed",
            notes="",
        )

        messages.success(request, "Book created and assigned to student.")
        return redirect("library:student_loans", student_id=student.id)

    # Handle assigning one or many books to this student
    if request.method == "POST" and request.POST.get("action") == "assign_books":
        assign_form = StudentAssignBooksForm(request.POST)
        # Limit choices to currently available books
        assign_form.fields["books"].queryset = Book.objects.filter(status="available").order_by("book_number", "title")
        if assign_form.is_valid():
            books = assign_form.cleaned_data["books"]
            expected_return_date = assign_form.cleaned_data.get("expected_return_date")

            for book in books:
                BorrowRecord.objects.create(
                    book=book,
                    student=student,
                    assigned_by=request.user,
                    expected_return_date=expected_return_date,
                    status="borrowed",
                    notes="",
                )
            return redirect("library:student_loans", student_id=student.id)
    else:
        assign_form = StudentAssignBooksForm()
        assign_form.fields["books"].queryset = Book.objects.filter(status="available").order_by("book_number", "title")

    records = (
        BorrowRecord.objects
        .filter(student=student, status__in=["borrowed", "lost"])
        .select_related("book")
        .order_by("-date_borrowed")
    )

    # Count and sum price of lost books for this student (only unpaid losses)
    lost_count = 0
    total_lost_amount = 0
    for r in records:
        if r.status == "lost" and not r.loss_cleared and r.book and r.book.price is not None:
            lost_count += 1
            total_lost_amount += r.book.price

    context = {
        "student": student,
        "records": records,
        "lost_count": lost_count,
        "total_lost_amount": total_lost_amount,
        "assign_form": assign_form,
        "categories": Subject.objects.all().order_by("name"),
    }
    return render(request, "library/student_loans.html", context)


@user_passes_test(is_admin)
def library_loans_pdf(request):
    """Generate PDF report for library loans (optionally filter by student)."""
    student_id = request.GET.get("student")
    student = None
    if student_id:
        try:
            student = Student.objects.get(id=student_id)
        except Student.DoesNotExist:
            student = None

    qs = BorrowRecord.objects.select_related("book", "student").all()
    if student:
        qs = qs.filter(student=student)

    records = qs.order_by("-date_borrowed")
    context = {"records": records, "student": student}
    html = render_to_string("library/library_loans_pdf.html", context)
    if pisa is None:
        return HttpResponse("PDF generation not available", status=500)
    result = BytesIO()
    status = pisa.CreatePDF(src=html, dest=result)
    if status.err:
        return HttpResponse("Error generating PDF", status=500)
    resp = HttpResponse(result.getvalue(), content_type="application/pdf")
    resp["Content-Disposition"] = 'attachment; filename="library_loans.pdf"'
    return resp


@login_required
def book_detail(request, pk):
    book = get_object_or_404(Book, pk=pk)
    return render(request, 'library/book_detail.html', {'book': book})


@user_passes_test(is_admin)
def library_add_student(request):
    """Allow library staff to add students for any class.

    Uses the shared Student model so students appear everywhere (payments, etc.).
    """

    if request.method == "POST":
        form = LibraryStudentForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('library:add_student')
    else:
        form = LibraryStudentForm()

    return render(request, 'library/add_student.html', {"form": form})


@user_passes_test(is_admin)
def borrow_book(request, pk):
    book = get_object_or_404(Book, pk=pk)
    if request.method == 'POST':
        form = BorrowForm(request.POST)
        if form.is_valid():
            br = form.save(commit=False)
            br.book = book
            br.assigned_by = request.user
            br.save()
            return redirect(reverse('library:book_detail', args=[book.id]))
    else:
        form = BorrowForm()
    return render(request, 'library/borrow_form.html', {'form': form, 'book': book})
