# timetable/context_processors.py
def user_permissions(request):
    """Add user permissions to template context"""
    if request.user.is_authenticated:
        return {
            'can_add_employee': request.user.has_perm('timetable.add_employee'),
            'can_change_employee': request.user.has_perm('timetable.change_employee'),
            'can_delete_employee': request.user.has_perm('timetable.delete_employee'),
            'can_generate_timetable': request.user.has_perm('timetable.add_timetable'),
            'can_manage_all': request.user.has_perm('timetable.manage_all'),
            'is_staff': request.user.is_staff,
            'is_superuser': request.user.is_superuser,
        }
    return {}