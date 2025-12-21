from django.urls import path
from . import views

app_name = 'library'

urlpatterns = [
    path('dashboard/', views.library_dashboard, name='dashboard'),
    path('books/add/', views.add_book, name='add_book'),
    path('books/<int:pk>/delete/', views.delete_book, name='delete_book'),
    path('loans/manage/', views.manage_loans, name='manage_loans'),
    path('loans/pdf/', views.library_loans_pdf, name='library_loans_pdf'),
    path('students/<int:student_id>/loans/', views.student_loans, name='student_loans'),
    path('students/add/', views.library_add_student, name='add_student'),
    path('', views.book_list, name='book_list'),
    path('<int:pk>/', views.book_detail, name='book_detail'),
    path('borrow/<int:pk>/', views.borrow_book, name='borrow_book'),
]
