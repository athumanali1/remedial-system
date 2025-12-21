from django.contrib import admin
from .models import Book, BorrowRecord

# Also register models on the project's custom admin site used at /admin/
try:
    from lessons import admin as lessons_admin
    custom_admin_site = getattr(lessons_admin, 'admin_site', None)
except Exception:
    custom_admin_site = None


@admin.register(Book)
class BookAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "book_number", "category", "status", "price")
    search_fields = ("title", "book_number", "isbn")
    list_filter = ("status", "category")


@admin.register(BorrowRecord)
class BorrowRecordAdmin(admin.ModelAdmin):
    list_display = ("id", "book", "student", "status", "date_borrowed", "expected_return_date", "date_returned", "assigned_by")
    list_filter = ("status", "date_borrowed")
    search_fields = ("book__title", "student__admission_number", "student__first_name", "student__last_name")


# If the project uses a custom AdminSite (registered as `admin_site` in
# `lessons.admin`), also register our models there so they appear at
# the configured `/admin/` URL. Fall back silently if not available.
if custom_admin_site is not None:
    try:
        custom_admin_site.register(Book, BookAdmin)
        custom_admin_site.register(BorrowRecord, BorrowRecordAdmin)
    except Exception:
        pass


# --- Dedicated Library AdminSite for librarian group members ---
from django.contrib.admin import AdminSite


class LibraryAdminSite(AdminSite):
    site_header = "Library Admin"
    site_title = "Library Admin Portal"
    index_title = "Library Dashboard"

    def has_permission(self, request):
        user = request.user
        if not (user and user.is_active and user.is_staff):
            return False
        try:
            return user.groups.filter(name__iexact='library').exists()
        except Exception:
            return False


library_admin_site = LibraryAdminSite(name='library_admin')
try:
    library_admin_site.register(Book, BookAdmin)
    library_admin_site.register(BorrowRecord, BorrowRecordAdmin)
except Exception:
    pass
