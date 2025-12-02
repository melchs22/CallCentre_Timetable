from django.urls import path
from django.shortcuts import redirect
from . import views

def home_redirect(request):
    if request.user.is_authenticated:
        return redirect('my_schedule')
    else:
        return redirect('login')

urlpatterns = [
    path('', home_redirect, name='home'),
    
    # Authentication
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('dashboard/', views.dashboard_view, name='dashboard'),
    
    # Health check
    path('health-check/', views.health_check, name='health_check'),
    
    # Employee management
    path('employees/', views.EmployeeListView.as_view(), name='employee_list'),
    path('employees/<int:employee_id>/detail/', views.employee_detail, name='employee_detail'),
    
    # NEW: Dynamic Employee Timetable Management
    path('employees/<int:employee_id>/add-to-timetable/', views.AddEmployeeToTimetableView.as_view(), name='add_employee_to_timetable'),
    path('employees/add-to-timetables/', views.add_employees_to_timetables, name='add_employees_to_timetables'),
    
    # Timetable management
    path('timetables/', views.TimetableListView.as_view(), name='timetable_list'),
    path('generate-timetable/', views.GenerateTimetableView.as_view(), name='generate_timetable'),
    path('timetable/<int:timetable_id>/', views.TimetableView.as_view(), name='timetable_view'),
    path('timetable/<int:timetable_id>/adjust/', views.AdjustTimetableView.as_view(), name='adjust_timetable'),
    path('timetable/<int:timetable_id>/lunch/', views.LunchScheduleView.as_view(), name='lunch_schedule'),
    path('timetable/<int:timetable_id>/food-pickup/', views.FoodPickupView.as_view(), name='food_pickup'),
    
    # Department views
    path('department/<str:department>/', views.DepartmentScheduleView.as_view(), name='department_schedule'),
    
    # Personal views
    path('my-schedule/', views.MyScheduleView.as_view(), name='my_schedule'),
    path('my-swap-requests/', views.MySwapRequestsView.as_view(), name='my_swap_requests'),
    path('swap-request/<int:swap_id>/approve/', views.approve_swap_request, name='approve_swap_request'),
    path('swap-request/<int:swap_id>/reject/', views.reject_swap_request, name='reject_swap_request'),
    path('swap-request/<int:swap_id>/cancel/', views.cancel_swap_request, name='cancel_swap_request'),
    path('swap-request/<int:swap_id>/', views.swap_request_detail, name='swap_request_detail'),
    path('swap-history/', views.swap_history_view, name='swap_history'),
    
    # Admin views
    path('admin/shift-swaps/', views.AdminShiftSwapView.as_view(), name='admin_shift_swaps'),
    
    # Manager views
    path('manager/dashboard/', views.manager_dashboard, name='manager_dashboard'),
    path('manager/employees/', views.ManagerEmployeeView.as_view(), name='manager_employees'),
    path('manager/swap-approval/', views.manager_swap_approval, name='manager_swap_approval'),
    path('manager/swap-approval/<int:swap_id>/', views.manager_approve_swap_request, name='manager_approve_swap'),
    path('manager/timetables/', views.manager_timetable_list, name='manager_timetable_list'),
    path('manager/timetable/<int:timetable_id>/', views.manager_timetable_view, name='manager_timetable_view'),
    path('manager/calendar/', views.manager_calendar_view, name='manager_calendar'),
]