from django.shortcuts import redirect
from django.conf import settings

class AcademicYearMiddleware:
    """Middleware to ensure academic year is selected before accessing protected views."""
    
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Paths that don't require academic year selection
        exempt_paths = [
            '/',
            '/accounts/login/',
            '/accounts/logout/',
            '/accounts/simple-password-reset/',
            '/lessons/select-year/',
            '/admin/',
            '/static/',
            '/media/',
        ]
        
        # Check if path is exempt
        path_is_exempt = any(request.path.startswith(exempt) for exempt in exempt_paths)
        
        if not path_is_exempt and request.user.is_authenticated:
            # Check if academic year is selected
            if not request.session.get('selected_academic_year_id'):
                # Store the intended URL to redirect after year selection
                request.session['next_after_year_selection'] = request.path
                return redirect('/lessons/select-year/?next=' + request.path)
        
        response = self.get_response(request)
        return response
