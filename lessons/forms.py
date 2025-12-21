# lessons/forms.py
from django import forms
from .models import LessonRecord, Timetable, Teacher, Week

# lessons/forms.py
from django import forms
from .models import LessonRecord, Timetable, Teacher, Week

class LessonRecordForm(forms.ModelForm):
    # extra non-model field shown to admin: pick the 'teacher'
    teacher = forms.ModelChoiceField(
        queryset=Teacher.objects.all(),
        required=True,
        label="Teacher"
    )

    class Meta:
        model = LessonRecord
        # show teacher first, then week, then timetable (you said week first — adjust order here)
        fields = ['week', 'teacher', 'timetable', 'status', 'payment_status', 'amount']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Keep timetable empty until teacher (and optionally week) are selected
        self.fields['timetable'].queryset = Timetable.objects.none()

        # If the form was POSTed / has data (AJAX or normal submit)
        if 'teacher' in self.data:
            try:
                teacher_id = int(self.data.get('teacher'))
                week_id = self.data.get('week')  # may be '' or None
                qs = Timetable.objects.filter(teacher_id=teacher_id)

                # Optionally exclude timetables already used in that week
                if week_id:
                    used_ids = LessonRecord.objects.filter(
                        week_id=week_id,
                        timetable__in=qs
                    ).values_list('timetable_id', flat=True)
                    qs = qs.exclude(id__in=used_ids)

                self.fields['timetable'].queryset = qs
            except (ValueError, TypeError):
                pass

        # If editing an existing LessonRecord (populate teacher initial + timetable choices)
        elif self.instance and self.instance.pk:
            # If created_by exists use that; otherwise try to deduce teacher from the timetable
            teacher_obj = None
            if getattr(self.instance, 'created_by', None):
                teacher_obj = self.instance.created_by
            elif getattr(self.instance, 'timetable', None):
                teacher_obj = self.instance.timetable.teacher

            if teacher_obj:
                self.fields['teacher'].initial = teacher_obj
                self.fields['timetable'].queryset = Timetable.objects.filter(teacher=teacher_obj)


class TeacherLessonForm(forms.ModelForm):
    """
    Teacher-side form: teachers only choose week + timetable.
    """
    week = forms.ModelChoiceField(queryset=Week.objects.all(), required=True)

    class Meta:
        model = LessonRecord
        fields = ['week', 'timetable']

    def __init__(self, *args, **kwargs):
        teacher = kwargs.pop('teacher', None)
        super().__init__(*args, **kwargs)
        self.fields['timetable'].queryset = Timetable.objects.none()
        if teacher:
            self.fields['timetable'].queryset = Timetable.objects.filter(teacher=teacher)