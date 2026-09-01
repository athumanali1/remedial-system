from lessons.models import AcademicYear

def academic_year_context(request):
    """Context processor to provide academic year data to all templates."""
    
    # Get all academic years
    years = AcademicYear.objects.all().order_by('-start_date')
    
    # Get selected year from session, default to active year
    selected_year_id = request.session.get('selected_academic_year_id')
    
    if selected_year_id:
        try:
            selected_year = AcademicYear.objects.get(id=selected_year_id)
        except AcademicYear.DoesNotExist:
            selected_year = None
    else:
        # Default to active year if none selected
        selected_year = AcademicYear.objects.filter(is_active=True).first()
    
    return {
        'academic_years': years,
        'selected_academic_year': selected_year,
    }
