from django import forms
from .models import BorrowRecord, Book
from lessons.models import Student


class BorrowForm(forms.ModelForm):
    class Meta:
        model = BorrowRecord
        fields = ['student', 'expected_return_date', 'notes', 'status']
        widgets = {
            'expected_return_date': forms.DateInput(attrs={'type': 'date'}),
        }


class BookForm(forms.ModelForm):
    class Meta:
        model = Book
        fields = [
            'title',
            'category',
            'isbn',
            'book_number',
            'price',
            'status',
        ]


class LibraryLoanForm(forms.ModelForm):
    class Meta:
        model = BorrowRecord
        fields = [
            'book',
            'student',
            'expected_return_date',
            'notes',
        ]
        widgets = {
            'expected_return_date': forms.DateInput(attrs={'type': 'date'}),
        }


class LibraryStudentForm(forms.ModelForm):
    class Meta:
        model = Student
        fields = [
            'first_name',
            'last_name',
            'admission_number',
            'class_group',
        ]

    def clean_admission_number(self):
        adm = self.cleaned_data.get('admission_number')
        if not adm:
            return adm

        qs = Student.objects.filter(admission_number__iexact=adm)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError("A student with this admission number already exists.")
        return adm


class StudentAssignBooksForm(forms.Form):
    books = forms.ModelMultipleChoiceField(
        queryset=Book.objects.none(),
        widget=forms.SelectMultiple(attrs={"size": 4}),
        required=True,
        label="Books to assign",
    )
    expected_return_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
        label="Expected return date",
    )
