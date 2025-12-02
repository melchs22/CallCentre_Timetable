from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse, JsonResponse
from django.contrib import messages
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.models import User
from django.utils.decorators import method_decorator
from django.views import View
from django.utils import timezone
from django.core.paginator import Paginator
from django.db.models import Q
from datetime import date, timedelta, datetime
import calendar
import json
from .models import *
from .forms import *
from .utils import TimetableGenerator, FoodPickupScheduler

# Authentication Views
def login_view(request):
    if request.user.is_authenticated:
        # Redirect based on user type
        try:
            if Employee.objects.filter(user=request.user).exists():
                return redirect('my_schedule')
            elif Manager.objects.filter(user=request.user).exists():
                return redirect('manager_dashboard')
        except:
            pass
        return redirect('dashboard')
        
    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            username = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password')
            user = authenticate(username=username, password=password)
            if user is not None:
                login(request, user)
                next_url = request.GET.get('next')
                if next_url:
                    return redirect(next_url)
                
                # Redirect based on user type
                try:
                    if Employee.objects.filter(user=user).exists():
                        return redirect('my_schedule')
                    elif Manager.objects.filter(user=user).exists():
                        return redirect('manager_dashboard')
                except:
                    pass
                return redirect('dashboard')
            else:
                messages.error(request, "Invalid username or password.")
        else:
            messages.error(request, "Invalid username or password.")
    else:
        form = AuthenticationForm()
    return render(request, 'timetable/login.html', {'form': form})

def logout_view(request):
    logout(request)
    return redirect('login')

@login_required
def dashboard_view(request):
    # Check if user is a manager
    try:
        manager = Manager.objects.get(user=request.user)
        return redirect('manager_dashboard')
    except Manager.DoesNotExist:
        pass
    
    # Check if user is an employee
    try:
        employee = Employee.objects.get(user=request.user)
    except Employee.DoesNotExist:
        messages.error(request, "No employee profile found. Please contact administrator.")
        return render(request, 'timetable/dashboard.html', {'employee': None})
    
    # Get current month schedules for the employee
    today = date.today()
    current_schedules = []
    if employee:
        current_schedules = DailySchedule.objects.filter(
            employee=employee,
            date__month=today.month,
            date__year=today.year
        ).order_by('date')[:5]
    
    # Get pending swap requests
    pending_swaps_received = ShiftSwapRequest.objects.filter(
        requested_to=employee, status='pending'
    ) if employee else []
    
    pending_swaps_sent = ShiftSwapRequest.objects.filter(
        requester=employee, status='pending'
    ) if employee else []
    
    # Get recent approved swaps
    recent_swaps = ShiftSwapRequest.objects.filter(
        Q(requester=employee) | Q(requested_to=employee),
        status='approved'
    ).order_by('-approved_at')[:5] if employee else []
    
    context = {
        'employee': employee,
        'current_schedules': current_schedules,
        'pending_swaps_received': pending_swaps_received,
        'pending_swaps_sent': pending_swaps_sent,
        'recent_swaps': recent_swaps,
        'today': today,
    }
    return render(request, 'timetable/dashboard.html', context)

@login_required
def manager_dashboard(request):
    """Dashboard specifically for managers"""
    try:
        manager = Manager.objects.get(user=request.user)
    except Manager.DoesNotExist:
        messages.error(request, "Manager profile not found.")
        return redirect('dashboard')
    
    today = date.today()
    
    # Get department filter
    department = request.GET.get('department', 'all')
    
    # Get employees based on department access
    if manager.department_access == 'all':
        employees = Employee.objects.filter(is_active=True)
    else:
        employees = Employee.objects.filter(
            is_active=True, 
            department=manager.department_access
        )
    
    # Get pending swap requests
    if manager.department_access == 'all':
        pending_swaps = ShiftSwapRequest.objects.filter(status='pending')
    else:
        pending_swaps = ShiftSwapRequest.objects.filter(
            status='pending',
            requester__department=manager.department_access
        )
    
    # Get current month timetables
    current_timetables = Timetable.objects.filter(
        month=today.month,
        year=today.year
    )
    
    # Get employee count by department
    if manager.department_access == 'all':
        inbound_count = Employee.objects.filter(department='inbound', is_active=True).count()
        outbound_count = Employee.objects.filter(department='outbound', is_active=True).count()
    else:
        inbound_count = Employee.objects.filter(
            department='inbound', 
            is_active=True
        ).count() if manager.department_access == 'inbound' else 0
        outbound_count = Employee.objects.filter(
            department='outbound', 
            is_active=True
        ).count() if manager.department_access == 'outbound' else 0
    
    context = {
        'manager': manager,
        'employees': employees,
        'pending_swaps': pending_swaps,
        'current_timetables': current_timetables,
        'today': today,
        'inbound_count': inbound_count,
        'outbound_count': outbound_count,
        'selected_department': department,
    }
    return render(request, 'timetable/manager_dashboard.html', context)

# Employee Views
@method_decorator(login_required, name='dispatch')
class EmployeeListView(View):
    def get(self, request):
        # Check permissions - allow managers with employee management permission
        if not (request.user.has_perm('timetable.view_employee') or 
                (hasattr(request.user, 'manager') and request.user.manager.can_manage_employees)):
            messages.error(request, "You don't have permission to view employees.")
            return redirect('dashboard')
            
        employees_list = Employee.objects.filter(is_active=True).order_by('name')
        
        # If user is a manager with department restrictions, filter employees
        try:
            manager = Manager.objects.get(user=request.user)
            if manager.department_access != 'all':
                employees_list = employees_list.filter(department=manager.department_access)
        except Manager.DoesNotExist:
            pass
        
        # Search functionality
        search_query = request.GET.get('search', '')
        if search_query:
            employees_list = employees_list.filter(
                Q(name__icontains=search_query) |
                Q(employee_id__icontains=search_query) |
                Q(department__icontains=search_query)
            )
        
        # Pagination
        paginator = Paginator(employees_list, 10)
        page_number = request.GET.get('page')
        employees = paginator.get_page(page_number)
        
        # Only show form if user has add permission or is manager with manage employees permission
        can_add_employee = (request.user.has_perm('timetable.add_employee') or 
                          (hasattr(request.user, 'manager') and request.user.manager.can_manage_employees))
        form = EmployeeForm() if can_add_employee else None
        
        return render(request, 'timetable/employee_list.html', {
            'employees': employees,
            'form': form,
            'search_query': search_query,
            'can_add_employee': can_add_employee,
        })

    def post(self, request):
        # Check permissions
        if not (request.user.has_perm('timetable.add_employee') or 
                (hasattr(request.user, 'manager') and request.user.manager.can_manage_employees)):
            messages.error(request, "You don't have permission to add employees.")
            return redirect('employee_list')
            
        form = EmployeeForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Employee added successfully!')
            return redirect('employee_list')
        
        employees_list = Employee.objects.filter(is_active=True).order_by('name')
        paginator = Paginator(employees_list, 10)
        page_number = request.GET.get('page')
        employees = paginator.get_page(page_number)
        
        return render(request, 'timetable/employee_list.html', {
            'employees': employees,
            'form': form
        })

# Timetable Views
@method_decorator(login_required, name='dispatch')
class TimetableListView(View):
    def get(self, request):
        timetable_list = Timetable.objects.all().order_by('-year', '-month')
        
        # Pagination
        paginator = Paginator(timetable_list, 5)
        page_number = request.GET.get('page')
        timetables = paginator.get_page(page_number)
        
        return render(request, 'timetable/timetable_list.html', {
            'timetables': timetables
        })

@method_decorator(login_required, name='dispatch')
class GenerateTimetableView(View):
    def get(self, request):
        # Check permissions - allow managers with timetable generation permission
        if not (request.user.has_perm('timetable.add_timetable') or 
                (hasattr(request.user, 'manager') and request.user.manager.can_generate_timetables)):
            messages.error(request, "You don't have permission to generate timetables.")
            return redirect('dashboard')
            
        form = TimetableGenerationForm()
        recent_timetables = Timetable.objects.all()[:5]
        return render(request, 'timetable/generate_timetable.html', {
            'form': form,
            'recent_timetables': recent_timetables
        })
    
    def post(self, request):
        # Check permissions
        if not (request.user.has_perm('timetable.add_timetable') or 
                (hasattr(request.user, 'manager') and request.user.manager.can_generate_timetables)):
            messages.error(request, "You don't have permission to generate timetables.")
            return redirect('dashboard')
            
        form = TimetableGenerationForm(request.POST)
        if form.is_valid():
            month = int(form.cleaned_data['month'])
            year = int(form.cleaned_data['year'])
            
            generator = TimetableGenerator(month, year)
            timetable = generator.generate_timetable()
            timetable.created_by = request.user
            timetable.save()
            
            # Generate food pickup schedules
            food_scheduler = FoodPickupScheduler(timetable)
            food_scheduler.generate_food_pickup_schedules()
            food_scheduler.assign_food_pickup_duties()
            
            messages.success(request, f'Timetable for {calendar.month_name[month]} {year} generated successfully!')
            return redirect('timetable_view', timetable_id=timetable.id)
        
        recent_timetables = Timetable.objects.all()[:5]
        return render(request, 'timetable/generate_timetable.html', {
            'form': form,
            'recent_timetables': recent_timetables
        })

@method_decorator(login_required, name='dispatch')
class TimetableView(View):
    def get(self, request, timetable_id):
        timetable = get_object_or_404(Timetable, id=timetable_id)
        
        # Check if user has access to view this timetable
        try:
            employee = Employee.objects.get(user=request.user)
            # Employees can only view their own department's schedules
            daily_schedules = DailySchedule.objects.filter(
                timetable=timetable,
                employee__department=employee.department
            ).select_related('employee').order_by('date', 'start_time')
        except Employee.DoesNotExist:
            try:
                manager = Manager.objects.get(user=request.user)
                # Managers can view based on their department access
                if manager.department_access == 'all':
                    daily_schedules = DailySchedule.objects.filter(
                        timetable=timetable
                    ).select_related('employee').order_by('date', 'start_time')
                else:
                    daily_schedules = DailySchedule.objects.filter(
                        timetable=timetable,
                        employee__department=manager.department_access
                    ).select_related('employee').order_by('date', 'start_time')
            except Manager.DoesNotExist:
                messages.error(request, "You don't have permission to view timetables.")
                return redirect('dashboard')
        
        # Group by date
        schedules_by_date = {}
        for schedule in daily_schedules:
            date_str = schedule.date.isoformat()
            if date_str not in schedules_by_date:
                schedules_by_date[date_str] = []
            schedules_by_date[date_str].append(schedule)
        
        # Get all swap requests for this timetable period
        swap_requests = ShiftSwapRequest.objects.filter(
            requested_date__month=timetable.month,
            requested_date__year=timetable.year,
            status='approved'
        ).select_related('requester', 'requested_to', 'approved_by')
        
        context = {
            'timetable': timetable,
            'schedules_by_date': schedules_by_date,
            'swap_requests': swap_requests,
        }
        return render(request, 'timetable/timetable_view.html', context)

# Personal Views
@method_decorator(login_required, name='dispatch')
class MyScheduleView(View):
    def get(self, request):
        try:
            employee = Employee.objects.get(user=request.user)
        except Employee.DoesNotExist:
            messages.error(request, "Employee profile not found.")
            return redirect('dashboard')
        
        # Date filter
        month = request.GET.get('month', date.today().month)
        year = request.GET.get('year', date.today().year)
        
        schedules = DailySchedule.objects.filter(employee=employee)
        
        if month and year:
            schedules = schedules.filter(date__month=month, date__year=year)
        
        schedules = schedules.order_by('date')
        
        # Get approved swap requests for this employee in the selected period
        approved_swaps_received = ShiftSwapRequest.objects.filter(
            requested_to=employee,
            status='approved',
            requested_date__month=month,
            requested_date__year=year
        )
        
        approved_swaps_sent = ShiftSwapRequest.objects.filter(
            requester=employee,
            status='approved',
            requested_date__month=month,
            requested_date__year=year
        )
        
        # Create a mapping of dates to swap information
        swap_info = {}
        for swap in approved_swaps_received:
            swap_info[swap.requested_date] = {
                'type': 'received',
                'swap': swap,
                'other_employee': swap.requester,
                'action': 'accepted by you'
            }
        
        for swap in approved_swaps_sent:
            swap_info[swap.requested_date] = {
                'type': 'sent',
                'swap': swap,
                'other_employee': swap.requested_to,
                'action': f'accepted by {swap.requested_to.name}'
            }
        
        # Prepare calendar data with enhanced information including swap details
        calendar_data = []
        for schedule in schedules:
            swap_data = swap_info.get(schedule.date)
            
            if schedule.is_off:
                # Day off - show as red
                event_data = {
                    'title': 'DAY OFF',
                    'start': schedule.date.isoformat(),
                    'end': schedule.date.isoformat(),
                    'color': '#dc3545',  # Red
                    'textColor': 'white',
                    'display': 'block',
                    'extendedProps': {
                        'start_time': 'N/A',
                        'end_time': 'N/A',
                        'lunch_time': 'N/A',
                        'status': 'Day Off',
                        'shift_type': 'Off',
                        'is_off': True
                    }
                }
                if swap_data:
                    event_data['title'] = 'SWAPPED - DAY OFF'
                    event_data['color'] = '#6f42c1'  # Purple for swapped day off
                    event_data['extendedProps']['swap_info'] = {
                        'type': swap_data['type'],
                        'other_employee': swap_data['other_employee'].name,
                        'action': swap_data['action'],
                        'approved_by': swap_data['swap'].approved_by.get_full_name() if swap_data['swap'].approved_by else 'System',
                        'approved_at': swap_data['swap'].approved_at.strftime('%Y-%m-%d %H:%M') if swap_data['swap'].approved_at else 'N/A'
                    }
            else:
                # Working day - show shift details
                shift_type = self.get_shift_type(schedule.start_time)
                color = self.get_shift_color(schedule.start_time)
                
                event_data = {
                    'title': f'{shift_type} Shift\n{schedule.start_time.strftime("%H:%M")}-{schedule.end_time.strftime("%H:%M")}',
                    'start': schedule.date.isoformat(),
                    'end': schedule.date.isoformat(),
                    'color': color,
                    'textColor': 'white',
                    'display': 'block',
                    'extendedProps': {
                        'start_time': schedule.start_time.strftime('%H:%M'),
                        'end_time': schedule.end_time.strftime('%H:%M'),
                        'lunch_time': schedule.lunch_time.strftime('%H:%M'),
                        'status': 'Working',
                        'shift_type': f'{shift_type} Shift',
                        'is_off': False
                    }
                }
                
                if swap_data:
                    event_data['title'] = f'SWAPPED - {shift_type} Shift\n{schedule.start_time.strftime("%H:%M")}-{schedule.end_time.strftime("%H:%M")}'
                    event_data['color'] = '#20c997'  # Teal for swapped shift
                    event_data['extendedProps']['swap_info'] = {
                        'type': swap_data['type'],
                        'other_employee': swap_data['other_employee'].name,
                        'action': swap_data['action'],
                        'approved_by': swap_data['swap'].approved_by.get_full_name() if swap_data['swap'].approved_by else 'System',
                        'approved_at': swap_data['swap'].approved_at.strftime('%Y-%m-%d %H:%M') if swap_data['swap'].approved_at else 'N/A'
                    }
            
            calendar_data.append(event_data)
        
        # Pagination for table view
        paginator = Paginator(schedules, 15)
        page_number = request.GET.get('page')
        page_obj = paginator.get_page(page_number)
        
        # Get available months and years for filter
        available_months = schedules.dates('date', 'month')
        available_years = schedules.dates('date', 'year')
        
        # Get current month name for display
        current_month_name = calendar.month_name[int(month)]
        
        context = {
            'schedules': page_obj,
            'employee': employee,
            'available_months': available_months,
            'available_years': available_years,
            'selected_month': int(month),
            'selected_year': int(year),
            'current_month_name': current_month_name,
            'calendar_data': json.dumps(calendar_data),
            'swap_info': swap_info,
            'approved_swaps_received': approved_swaps_received,
            'approved_swaps_sent': approved_swaps_sent,
        }
        return render(request, 'timetable/my_schedule.html', context)
    
    def get_shift_type(self, start_time):
        """Determine shift type based on start time"""
        if start_time.hour == 8:
            return 'Early'
        elif start_time.hour == 9:
            return 'Morning'
        elif start_time.hour == 10:
            return 'Mid'
        elif start_time.hour == 11:
            return 'Late'
        else:
            return 'Custom'
    
    def get_shift_color(self, start_time):
        """Get color code based on shift type"""
        if start_time.hour == 8:
            return '#28a745'  # Green - Early shift
        elif start_time.hour == 9:
            return '#17a2b8'  # Blue - Morning shift
        elif start_time.hour == 10:
            return '#ffc107'  # Yellow - Mid shift
        elif start_time.hour == 11:
            return '#fd7e14'  # Orange - Late shift
        else:
            return '#6c757d'  # Gray - Custom shift

@method_decorator(login_required, name='dispatch')
class DepartmentScheduleView(View):
    def get(self, request, department):
        # Check permissions - allow managers and users with manage_all permission
        try:
            manager = Manager.objects.get(user=request.user)
            if not manager.has_department_access(department):
                messages.error(request, "You don't have permission to view this department.")
                return redirect('dashboard')
        except Manager.DoesNotExist:
            if not request.user.has_perm('timetable.manage_all'):
                messages.error(request, "You don't have permission to view department schedules.")
                return redirect('dashboard')
        
        if department not in ['inbound', 'outbound']:
            messages.error(request, "Invalid department specified.")
            return redirect('dashboard')
        
        # Date filter
        month = request.GET.get('month', date.today().month)
        year = request.GET.get('year', date.today().year)
        
        employees = Employee.objects.filter(department=department, is_active=True)
        schedules = DailySchedule.objects.filter(
            employee__department=department,
            date__month=month,
            date__year=year
        ).select_related('employee').order_by('date', 'start_time')
        
        # Get swap requests for this period
        swap_requests = ShiftSwapRequest.objects.filter(
            requested_date__month=month,
            requested_date__year=year,
            status='approved'
        ).select_related('requester', 'requested_to', 'approved_by')
        
        # Create swap mapping for easy lookup
        swap_mapping = {}
        for swap in swap_requests:
            swap_mapping[swap.requested_date] = swap
        
        # Group by date and employee
        schedules_by_date = {}
        for schedule in schedules:
            date_str = schedule.date.isoformat()
            if date_str not in schedules_by_date:
                schedules_by_date[date_str] = []
            
            # Add swap info to schedule if available
            schedule.swap_info = swap_mapping.get(schedule.date)
            schedules_by_date[date_str].append(schedule)
        
        context = {
            'department': department,
            'department_display': department.title(),
            'employees': employees,
            'schedules_by_date': schedules_by_date,
            'selected_month': int(month),
            'selected_year': int(year),
            'swap_requests': swap_requests,
        }
        return render(request, 'timetable/department_schedule.html', context)

@method_decorator(login_required, name='dispatch')
class FoodPickupView(View):
    def get(self, request, timetable_id):
        timetable = get_object_or_404(Timetable, id=timetable_id)
        food_pickups = FoodPickupSchedule.objects.filter(
            timetable=timetable
        ).prefetch_related('foodpickupassignment_set__employee').order_by('date')
        
        return render(request, 'timetable/food_pickup.html', {
            'timetable': timetable,
            'food_pickups': food_pickups
        })

@method_decorator(login_required, name='dispatch')
class MySwapRequestsView(View):
    def get(self, request):
        try:
            employee = Employee.objects.get(user=request.user)
        except Employee.DoesNotExist:
            messages.error(request, "Employee profile not found.")
            return redirect('dashboard')
        
        # Get swap requests where user is involved
        swap_requests = ShiftSwapRequest.objects.filter(
            Q(requester=employee) | Q(requested_to=employee)
        ).order_by('-created_at')
        
        # Calculate counts for statistics
        pending_count = swap_requests.filter(status='pending').count()
        approved_count = swap_requests.filter(status='approved').count()
        rejected_count = swap_requests.filter(status='rejected').count()
        cancelled_count = swap_requests.filter(status='cancelled').count()
        
        # Pagination
        paginator = Paginator(swap_requests, 10)
        page_number = request.GET.get('page')
        page_obj = paginator.get_page(page_number)
        
        form = ShiftSwapRequestForm()
        # Filter employees to exclude current user
        form.fields['requested_to'].queryset = Employee.objects.exclude(id=employee.id)
        
        context = {
            'swap_requests': page_obj,
            'form': form,
            'employee': employee,
            'pending_count': pending_count,
            'approved_count': approved_count,
            'rejected_count': rejected_count,
            'cancelled_count': cancelled_count,
        }
        return render(request, 'timetable/my_swap_requests.html', context)
    
    def post(self, request):
        try:
            employee = Employee.objects.get(user=request.user)
        except Employee.DoesNotExist:
            messages.error(request, "Employee profile not found.")
            return redirect('dashboard')
            
        form = ShiftSwapRequestForm(request.POST)
        if form.is_valid():
            swap_request = form.save(commit=False)
            swap_request.requester = employee
            
            # Find the original schedule for validation
            original_schedule = DailySchedule.objects.filter(
                employee=employee,
                date=swap_request.requested_date
            ).first()
            
            if not original_schedule:
                messages.error(request, "No schedule found for the selected date.")
                return redirect('my_swap_requests')
            
            # Check if target employee has a schedule on that date
            target_schedule = DailySchedule.objects.filter(
                employee=swap_request.requested_to,
                date=swap_request.requested_date
            ).first()
            
            if not target_schedule:
                messages.error(request, "The requested employee has no schedule on the selected date.")
                return redirect('my_swap_requests')
                
            swap_request.original_schedule = original_schedule
            swap_request.save()
            
            messages.success(request, 'Shift swap request submitted!')
            return redirect('my_swap_requests')
        
        # If form is invalid, reload the page with errors
        swap_requests = ShiftSwapRequest.objects.filter(
            Q(requester=employee) | Q(requested_to=employee)
        ).order_by('-created_at')
        
        pending_count = swap_requests.filter(status='pending').count()
        approved_count = swap_requests.filter(status='approved').count()
        rejected_count = swap_requests.filter(status='rejected').count()
        cancelled_count = swap_requests.filter(status='cancelled').count()
        
        paginator = Paginator(swap_requests, 10)
        page_number = request.GET.get('page')
        page_obj = paginator.get_page(page_number)
        
        context = {
            'swap_requests': page_obj,
            'form': form,
            'employee': employee,
            'pending_count': pending_count,
            'approved_count': approved_count,
            'rejected_count': rejected_count,
            'cancelled_count': cancelled_count,
        }
        return render(request, 'timetable/my_swap_requests.html', context)

@login_required
def approve_swap_request(request, swap_id):
    swap_request = get_object_or_404(ShiftSwapRequest, id=swap_id)
    
    try:
        current_employee = Employee.objects.get(user=request.user)
    except Employee.DoesNotExist:
        # Check if user is a manager with approval permissions
        try:
            manager = Manager.objects.get(user=request.user)
            if manager.can_approve_swaps:
                return manager_approve_swap_request(request, swap_id)
            else:
                messages.error(request, "You don't have permission to approve swap requests.")
                return redirect('dashboard')
        except Manager.DoesNotExist:
            messages.error(request, "Employee or manager profile not found.")
            return redirect('dashboard')
    
    # Check if current user is the requested employee
    if swap_request.requested_to != current_employee:
        messages.error(request, "You can only approve requests sent to you.")
        return redirect('my_swap_requests')
    
    # Check if request is already processed
    if swap_request.status != 'pending':
        messages.warning(request, f"This request has already been {swap_request.status}.")
        return redirect('my_swap_requests')
    
    if request.method == 'GET':
        # Get the target schedule (current user's schedule on the requested date)
        target_schedule = DailySchedule.objects.filter(
            employee=current_employee,
            date=swap_request.requested_date
        ).first()
        
        context = {
            'swap_request': swap_request,
            'target_schedule': target_schedule,
        }
        return render(request, 'timetable/approve_swap_request.html', context)
    
    elif request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'approve':
            # Get both schedules
            target_schedule = DailySchedule.objects.filter(
                employee=swap_request.requested_to,
                date=swap_request.requested_date
            ).first()
            
            original_schedule = swap_request.original_schedule
            
            # Perform the swap if both schedules exist
            if target_schedule and original_schedule:
                # Store original data for history
                original_employee = original_schedule.employee
                target_employee = target_schedule.employee
                original_schedule_data = {
                    'start_time': str(original_schedule.start_time),
                    'end_time': str(original_schedule.end_time),
                    'lunch_time': str(original_schedule.lunch_time),
                    'is_off': original_schedule.is_off,
                }
                target_schedule_data = {
                    'start_time': str(target_schedule.start_time),
                    'end_time': str(target_schedule.end_time),
                    'lunch_time': str(target_schedule.lunch_time),
                    'is_off': target_schedule.is_off,
                }
                
                # Instead of swapping employees directly (which violates unique constraint),
                # we need to swap the schedule details while keeping the original employee assignments
                # Store original values
                original_start = original_schedule.start_time
                original_end = original_schedule.end_time
                original_lunch = original_schedule.lunch_time
                original_is_off = original_schedule.is_off
                
                target_start = target_schedule.start_time
                target_end = target_schedule.end_time
                target_lunch = target_schedule.lunch_time
                target_is_off = target_schedule.is_off
                
                # Swap the schedule details
                original_schedule.start_time = target_start
                original_schedule.end_time = target_end
                original_schedule.lunch_time = target_lunch
                original_schedule.is_off = target_is_off
                
                target_schedule.start_time = original_start
                target_schedule.end_time = original_end
                target_schedule.lunch_time = original_lunch
                target_schedule.is_off = original_is_off
                
                # Save both schedules
                original_schedule.save()
                target_schedule.save()
                
                # Update swap request with approval info
                swap_request.status = 'approved'
                swap_request.employee_approved = True
                swap_request.employee_approved_at = timezone.now()
                swap_request.approved_by = request.user
                swap_request.approved_at = timezone.now()
                swap_request.save()
                
                # Create swap history record
                SwapHistory.objects.create(
                    swap_request=swap_request,
                    original_employee=original_employee,
                    target_employee=target_employee,
                    swap_date=swap_request.requested_date,
                    original_schedule_data=original_schedule_data,
                    target_schedule_data=target_schedule_data,
                    approved_by=request.user
                )
                
                messages.success(request, 'Shift swap approved and schedules updated successfully!')
            else:
                messages.warning(request, 'Shift swap approved, but one or both schedules were not found.')
            
        elif action == 'reject':
            # Reject the swap request
            swap_request.status = 'rejected'
            swap_request.save()
            messages.success(request, 'Shift swap request rejected.')
        
        return redirect('my_swap_requests')

@login_required
def manager_approve_swap_request(request, swap_id):
    """Handle swap request approval by manager"""
    try:
        manager = Manager.objects.get(user=request.user)
    except Manager.DoesNotExist:
        messages.error(request, "Manager profile not found.")
        return redirect('dashboard')
    
    swap_request = get_object_or_404(ShiftSwapRequest, id=swap_id)
    
    # Check if manager has permission to approve swaps
    if not manager.can_approve_swaps:
        messages.error(request, "You don't have permission to approve swap requests.")
        return redirect('manager_dashboard')
    
    # Check if manager has department access
    has_department_access = manager.has_department_access(swap_request.requester.department)
    if not has_department_access:
        messages.error(request, "You don't have permission to approve swaps for this department.")
        return redirect('manager_dashboard')
    
    # Check if request is already processed
    if swap_request.status not in ['pending', 'employee_approved']:
        messages.warning(request, f"This request has already been {swap_request.status}.")
        return redirect('manager_swap_approval')
    
    if request.method == 'GET':
        # Get both schedules
        original_schedule = swap_request.original_schedule
        target_schedule = DailySchedule.objects.filter(
            employee=swap_request.requested_to,
            date=swap_request.requested_date
        ).first()
        
        context = {
            'swap_request': swap_request,
            'original_schedule': original_schedule,
            'target_schedule': target_schedule,
            'manager': manager,
            'has_department_access': has_department_access,
        }
        return render(request, 'timetable/manager_approve_swap.html', context)
    
    elif request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'approve':
            # Get both schedules
            target_schedule = DailySchedule.objects.filter(
                employee=swap_request.requested_to,
                date=swap_request.requested_date
            ).first()
            
            original_schedule = swap_request.original_schedule
            
            # Perform the swap if both schedules exist
            if target_schedule and original_schedule:
                # Store original data for history
                original_employee = original_schedule.employee
                target_employee = target_schedule.employee
                original_schedule_data = {
                    'start_time': str(original_schedule.start_time),
                    'end_time': str(original_schedule.end_time),
                    'lunch_time': str(original_schedule.lunch_time),
                    'is_off': original_schedule.is_off,
                }
                target_schedule_data = {
                    'start_time': str(target_schedule.start_time),
                    'end_time': str(target_schedule.end_time),
                    'lunch_time': str(target_schedule.lunch_time),
                    'is_off': target_schedule.is_off,
                }
                
                # Instead of swapping employees directly (which violates unique constraint),
                # we need to swap the schedule details while keeping the original employee assignments
                # Store original values
                original_start = original_schedule.start_time
                original_end = original_schedule.end_time
                original_lunch = original_schedule.lunch_time
                original_is_off = original_schedule.is_off
                
                target_start = target_schedule.start_time
                target_end = target_schedule.end_time
                target_lunch = target_schedule.lunch_time
                target_is_off = target_schedule.is_off
                
                # Swap the schedule details
                original_schedule.start_time = target_start
                original_schedule.end_time = target_end
                original_schedule.lunch_time = target_lunch
                original_schedule.is_off = target_is_off
                
                target_schedule.start_time = original_start
                target_schedule.end_time = original_end
                target_schedule.lunch_time = original_lunch
                target_schedule.is_off = original_is_off
                
                # Save both schedules
                original_schedule.save()
                target_schedule.save()
                
                # Update swap request with manager approval info
                swap_request.status = 'approved'
                swap_request.manager_approved = True
                swap_request.manager_approved_by = request.user
                swap_request.manager_approved_at = timezone.now()
                swap_request.approved_by = request.user
                swap_request.approved_at = timezone.now()
                swap_request.save()
                
                # Create swap history record
                SwapHistory.objects.create(
                    swap_request=swap_request,
                    original_employee=original_employee,
                    target_employee=target_employee,
                    swap_date=swap_request.requested_date,
                    original_schedule_data=original_schedule_data,
                    target_schedule_data=target_schedule_data,
                    approved_by=request.user
                )
                
                messages.success(request, 'Shift swap approved by manager and schedules updated successfully!')
            else:
                messages.warning(request, 'Shift swap approved, but one or both schedules were not found.')
        
        elif action == 'reject':
            rejection_reason = request.POST.get('rejection_reason', '')
            swap_request.status = 'rejected'
            swap_request.manager_approved_by = request.user
            swap_request.manager_approved_at = timezone.now()
            
            if rejection_reason:
                swap_request.rejection_reason = rejection_reason
                
            swap_request.save()
            messages.success(request, 'Shift swap request rejected by manager.')
        
        return redirect('manager_swap_approval')

@login_required
def manager_swap_approval(request):
    """View for managers to see all pending swap requests"""
    try:
        manager = Manager.objects.get(user=request.user)
    except Manager.DoesNotExist:
        messages.error(request, "Manager profile not found.")
        return redirect('dashboard')
    
    if not manager.can_approve_swaps:
        messages.error(request, "You don't have permission to approve swap requests.")
        return redirect('manager_dashboard')
    
    # Get swap requests based on department access
    if manager.department_access == 'all':
        swap_requests = ShiftSwapRequest.objects.filter(
            Q(status='pending') | Q(status='employee_approved')
        )
    else:
        swap_requests = ShiftSwapRequest.objects.filter(
            Q(status='pending') | Q(status='employee_approved'),
            requester__department=manager.department_access
        )
    
    swap_requests = swap_requests.order_by('-created_at')
    
    # Pagination
    paginator = Paginator(swap_requests, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'swap_requests': page_obj,
        'manager': manager,
    }
    return render(request, 'timetable/manager_swap_approval.html', context)

@login_required
def reject_swap_request(request, swap_id):
    swap_request = get_object_or_404(ShiftSwapRequest, id=swap_id)
    
    try:
        current_employee = Employee.objects.get(user=request.user)
    except Employee.DoesNotExist:
        messages.error(request, "Employee profile not found.")
        return redirect('dashboard')
    
    if swap_request.requested_to != current_employee:
        messages.error(request, "You can only reject requests sent to you.")
        return redirect('my_swap_requests')
    
    # Check if request is already processed
    if swap_request.status != 'pending':
        messages.warning(request, f"This request has already been {swap_request.status}.")
        return redirect('my_swap_requests')
    
    if request.method == 'GET':
        context = {
            'swap_request': swap_request,
        }
        return render(request, 'timetable/reject_swap_request.html', context)
    
    elif request.method == 'POST':
        rejection_reason = request.POST.get('rejection_reason', '')
        swap_request.status = 'rejected'
        
        # Store rejection reason if provided
        if rejection_reason:
            swap_request.rejection_reason = rejection_reason
            
        swap_request.save()
        messages.success(request, 'Shift swap request rejected.')
        return redirect('my_swap_requests')

# Admin Views
@method_decorator(login_required, name='dispatch')
class AdminShiftSwapView(View):
    def get(self, request):
        # Check if user is manager with appropriate permissions or has manage_all permission
        try:
            manager = Manager.objects.get(user=request.user)
            if not manager.can_approve_swaps:
                messages.error(request, "You don't have permission to view all swap requests.")
                return redirect('dashboard')
            
            # Filter based on department access
            if manager.department_access == 'all':
                swap_requests = ShiftSwapRequest.objects.all()
            else:
                swap_requests = ShiftSwapRequest.objects.filter(
                    requester__department=manager.department_access
                )
        except Manager.DoesNotExist:
            if not request.user.has_perm('timetable.manage_all'):
                messages.error(request, "You don't have permission to view all swap requests.")
                return redirect('dashboard')
            swap_requests = ShiftSwapRequest.objects.all()
        
        swap_requests = swap_requests.order_by('-created_at')
        
        # Search functionality
        search_query = request.GET.get('search', '')
        if search_query:
            swap_requests = swap_requests.filter(
                Q(requester__name__icontains=search_query) |
                Q(requested_to__name__icontains=search_query) |
                Q(status__icontains=search_query)
            )
        
        # Status filter
        status_filter = request.GET.get('status', '')
        if status_filter:
            swap_requests = swap_requests.filter(status=status_filter)
        
        # Pagination
        paginator = Paginator(swap_requests, 15)
        page_number = request.GET.get('page')
        page_obj = paginator.get_page(page_number)
        
        context = {
            'swap_requests': page_obj,
            'search_query': search_query,
            'status_filter': status_filter,
            'status_choices': ShiftSwapRequest.STATUS_CHOICES,
        }
        return render(request, 'timetable/admin_shift_swap.html', context)

# Missing Views that were referenced in URLs
@method_decorator(login_required, name='dispatch')
class AdjustTimetableView(View):
    def get(self, request, timetable_id):
        if not request.user.has_perm('timetable.manage_all'):
            messages.error(request, "You don't have permission to adjust timetables.")
            return redirect('dashboard')
            
        timetable = get_object_or_404(Timetable, id=timetable_id)
        time_off_form = TimeOffForm()
        
        # Get time off requests for this month
        time_off_requests = TimeOff.objects.filter(
            start_date__month=timetable.month,
            start_date__year=timetable.year
        )
        
        # Get affected schedules
        affected_schedules = DailySchedule.objects.filter(
            timetable=timetable,
            is_off=True
        ).select_related('employee')
        
        # Get swap history for this timetable period
        swap_history = SwapHistory.objects.filter(
            swap_date__month=timetable.month,
            swap_date__year=timetable.year
        ).select_related('swap_request', 'original_employee', 'target_employee', 'approved_by')
        
        return render(request, 'timetable/adjust_timetable.html', {
            'timetable': timetable,
            'time_off_form': time_off_form,
            'time_off_requests': time_off_requests,
            'affected_schedules': affected_schedules,
            'swap_history': swap_history,
        })
    
    def post(self, request, timetable_id):
        if not request.user.has_perm('timetable.manage_all'):
            messages.error(request, "You don't have permission to adjust timetables.")
            return redirect('dashboard')
            
        timetable = get_object_or_404(Timetable, id=timetable_id)
        time_off_form = TimeOffForm(request.POST)
        
        if time_off_form.is_valid():
            time_off = time_off_form.save(commit=False)
            time_off.save()
            
            # Update affected schedules
            affected_schedules = DailySchedule.objects.filter(
                timetable=timetable,
                employee=time_off.employee,
                date__gte=time_off.start_date,
                date__lte=time_off.end_date
            )
            
            affected_schedules.update(is_off=True)
            
            messages.success(request, f'Time off approved for {time_off.employee.name}')
            return redirect('adjust_timetable', timetable_id=timetable_id)
        
        # Get time off requests for this month
        time_off_requests = TimeOff.objects.filter(
            start_date__month=timetable.month,
            start_date__year=timetable.year
        )
        
        # Get affected schedules
        affected_schedules = DailySchedule.objects.filter(
            timetable=timetable,
            is_off=True
        ).select_related('employee')
        
        # Get swap history for this timetable period
        swap_history = SwapHistory.objects.filter(
            swap_date__month=timetable.month,
            swap_date__year=timetable.year
        ).select_related('swap_request', 'original_employee', 'target_employee', 'approved_by')
        
        return render(request, 'timetable/adjust_timetable.html', {
            'timetable': timetable,
            'time_off_form': time_off_form,
            'time_off_requests': time_off_requests,
            'affected_schedules': affected_schedules,
            'swap_history': swap_history,
        })

@method_decorator(login_required, name='dispatch')
class LunchScheduleView(View):
    def get(self, request, timetable_id):
        timetable = get_object_or_404(Timetable, id=timetable_id)
        # Since we replaced LunchSchedule with FoodPickupSchedule, redirect to food pickup
        return redirect('food_pickup', timetable_id=timetable_id)

# Health check
def health_check(request):
    return HttpResponse("System is running correctly.")

# Additional utility views
@login_required
def cancel_swap_request(request, swap_id):
    """Allow users to cancel their own pending swap requests"""
    swap_request = get_object_or_404(ShiftSwapRequest, id=swap_id)
    
    try:
        current_employee = Employee.objects.get(user=request.user)
    except Employee.DoesNotExist:
        messages.error(request, "Employee profile not found.")
        return redirect('dashboard')
    
    # Check if current user is the requester
    if swap_request.requester != current_employee:
        messages.error(request, "You can only cancel your own swap requests.")
        return redirect('my_swap_requests')
    
    # Check if request is still pending
    if swap_request.status != 'pending':
        messages.warning(request, f"Cannot cancel a request that has already been {swap_request.status}.")
        return redirect('my_swap_requests')
    
    if request.method == 'POST':
        swap_request.status = 'cancelled'
        swap_request.save()
        messages.success(request, 'Shift swap request cancelled.')
    
    return redirect('my_swap_requests')

@login_required
def swap_request_detail(request, swap_id):
    """View details of a specific swap request"""
    swap_request = get_object_or_404(ShiftSwapRequest, id=swap_id)
    
    try:
        current_employee = Employee.objects.get(user=request.user)
    except Employee.DoesNotExist:
        # Check if user is a manager
        try:
            manager = Manager.objects.get(user=request.user)
            current_employee = None
        except Manager.DoesNotExist:
            messages.error(request, "Employee or manager profile not found.")
            return redirect('dashboard')
    
    # Check if current user is involved in the swap request or is a manager
    if current_employee and (swap_request.requester != current_employee and swap_request.requested_to != current_employee):
        if not request.user.has_perm('timetable.manage_all'):
            messages.error(request, "You don't have permission to view this swap request.")
            return redirect('my_swap_requests')
    
    # Get schedules for both employees on the requested date
    requester_schedule = DailySchedule.objects.filter(
        employee=swap_request.requester,
        date=swap_request.requested_date
    ).first()
    
    requested_to_schedule = DailySchedule.objects.filter(
        employee=swap_request.requested_to,
        date=swap_request.requested_date
    ).first()
    
    # Get swap history if approved
    swap_history = None
    if swap_request.status == 'approved':
        swap_history = SwapHistory.objects.filter(swap_request=swap_request).first()
    
    context = {
        'swap_request': swap_request,
        'requester_schedule': requester_schedule,
        'requested_to_schedule': requested_to_schedule,
        'current_employee': current_employee,
        'swap_history': swap_history,
        'can_approve': current_employee and swap_request.requested_to == current_employee and swap_request.status == 'pending',
        'can_cancel': current_employee and swap_request.requester == current_employee and swap_request.status == 'pending',
        'is_manager': hasattr(request.user, 'manager'),
    }
    
    return render(request, 'timetable/swap_request_detail.html', context)

@login_required
def swap_history_view(request):
    """View complete swap history for the current user"""
    try:
        employee = Employee.objects.get(user=request.user)
    except Employee.DoesNotExist:
        messages.error(request, "Employee profile not found.")
        return redirect('dashboard')
    
    # Get swap history where user was involved
    swap_history = SwapHistory.objects.filter(
        Q(original_employee=employee) | Q(target_employee=employee)
    ).order_by('-swap_date')
    
    # Pagination
    paginator = Paginator(swap_history, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'swap_history': page_obj,
        'employee': employee,
    }
    return render(request, 'timetable/swap_history.html', context)

# Manager-specific views
@method_decorator(login_required, name='dispatch')
class ManagerEmployeeView(View):
    """View for managers to see employees in their department"""
    def get(self, request):
        try:
            manager = Manager.objects.get(user=request.user)
        except Manager.DoesNotExist:
            messages.error(request, "Manager profile not found.")
            return redirect('dashboard')
        
        employees = Employee.objects.filter(is_active=True)
        
        # Filter by department if manager has restricted access
        if manager.department_access != 'all':
            employees = employees.filter(department=manager.department_access)
        
        # Search functionality
        search_query = request.GET.get('search', '')
        if search_query:
            employees = employees.filter(
                Q(name__icontains=search_query) |
                Q(employee_id__icontains=search_query) |
                Q(position__icontains=search_query)
            )
        
        employees = employees.order_by('name')
        
        # Pagination
        paginator = Paginator(employees, 10)
        page_number = request.GET.get('page')
        page_obj = paginator.get_page(page_number)
        
        context = {
            'employees': page_obj,
            'manager': manager,
            'search_query': search_query,
        }
        return render(request, 'timetable/manager_employees.html', context)

@login_required
def manager_timetable_view(request, timetable_id):
    """Enhanced timetable view for managers with department filtering"""
    timetable = get_object_or_404(Timetable, id=timetable_id)
    
    try:
        manager = Manager.objects.get(user=request.user)
    except Manager.DoesNotExist:
        messages.error(request, "Manager profile not found.")
        return redirect('dashboard')
    
    # Department filter
    department = request.GET.get('department', manager.department_access if manager.department_access != 'all' else 'inbound')
    
    # Get schedules based on department
    if manager.department_access == 'all':
        daily_schedules = DailySchedule.objects.filter(
            timetable=timetable,
            employee__department=department
        )
    else:
        daily_schedules = DailySchedule.objects.filter(
            timetable=timetable,
            employee__department=manager.department_access
        )
        department = manager.department_access
    
    daily_schedules = daily_schedules.select_related('employee').order_by('date', 'start_time')
    
    # Group by date
    schedules_by_date = {}
    for schedule in daily_schedules:
        date_str = schedule.date.isoformat()
        if date_str not in schedules_by_date:
            schedules_by_date[date_str] = []
        schedules_by_date[date_str].append(schedule)
    
    context = {
        'timetable': timetable,
        'schedules_by_date': schedules_by_date,
        'manager': manager,
        'selected_department': department,
        'show_department_filter': manager.department_access == 'all',
    }
    return render(request, 'timetable/manager_timetable_view.html', context)
@login_required
def manager_calendar_view(request):
    """Calendar view for managers to view schedules"""
    try:
        manager = Manager.objects.get(user=request.user)
    except Manager.DoesNotExist:
        messages.error(request, "Manager profile not found.")
        return redirect('dashboard')
    
    # Date filter
    month = request.GET.get('month', date.today().month)
    year = request.GET.get('year', date.today().year)
    
    # Department filter
    department = request.GET.get('department', manager.department_access if manager.department_access != 'all' else 'inbound')
    
    # Get schedules based on department access
    if manager.department_access == 'all':
        schedules = DailySchedule.objects.filter(
            date__month=month,
            date__year=year,
            employee__department=department
        )
    else:
        schedules = DailySchedule.objects.filter(
            date__month=month,
            date__year=year,
            employee__department=manager.department_access
        )
        department = manager.department_access
    
    schedules = schedules.select_related('employee').order_by('date', 'start_time')
    
    # Get swap requests for this period
    swap_requests = ShiftSwapRequest.objects.filter(
        requested_date__month=month,
        requested_date__year=year,
        status='approved'
    ).select_related('requester', 'requested_to')
    
    # Create swap mapping for easy lookup
    swap_mapping = {}
    for swap in swap_requests:
        swap_mapping[swap.requested_date] = swap
    
    # Prepare calendar data
    calendar_data = []
    for schedule in schedules:
        swap_data = swap_mapping.get(schedule.date)
        
        if schedule.is_off:
            # Day off
            event_data = {
                'title': f'{schedule.employee.name} - DAY OFF',
                'start': schedule.date.isoformat(),
                'end': schedule.date.isoformat(),
                'color': '#dc3545',  # Red
                'textColor': 'white',
                'display': 'block',
                'extendedProps': {
                    'employee': schedule.employee.name,
                    'employee_id': schedule.employee.employee_id,
                    'department': schedule.employee.department,
                    'start_time': 'N/A',
                    'end_time': 'N/A',
                    'lunch_time': 'N/A',
                    'status': 'Day Off',
                    'shift_type': 'Off',
                    'is_off': True
                }
            }
            if swap_data:
                event_data['title'] = f'{schedule.employee.name} - SWAPPED DAY OFF'
                event_data['color'] = '#6f42c1'  # Purple
                event_data['extendedProps']['swap_info'] = {
                    'type': 'swapped',
                    'other_employee': swap_data.requester.name if swap_data.requester != schedule.employee else swap_data.requested_to.name,
                    'approved_by': swap_data.approved_by.get_full_name() if swap_data.approved_by else 'System'
                }
        else:
            # Working day
            shift_type = get_shift_type(schedule.start_time)
            color = get_shift_color(schedule.start_time)
            
            event_data = {
                'title': f'{schedule.employee.name} - {shift_type}',
                'start': schedule.date.isoformat(),
                'end': schedule.date.isoformat(),
                'color': color,
                'textColor': 'white',
                'display': 'block',
                'extendedProps': {
                    'employee': schedule.employee.name,
                    'employee_id': schedule.employee.employee_id,
                    'department': schedule.employee.department,
                    'start_time': schedule.start_time.strftime('%H:%M'),
                    'end_time': schedule.end_time.strftime('%H:%M'),
                    'lunch_time': schedule.lunch_time.strftime('%H:%M'),
                    'status': 'Working',
                    'shift_type': f'{shift_type} Shift',
                    'is_off': False
                }
            }
            
            if swap_data:
                event_data['title'] = f'{schedule.employee.name} - SWAPPED {shift_type}'
                event_data['color'] = '#20c997'  # Teal
                event_data['extendedProps']['swap_info'] = {
                    'type': 'swapped',
                    'other_employee': swap_data.requester.name if swap_data.requester != schedule.employee else swap_data.requested_to.name,
                    'approved_by': swap_data.approved_by.get_full_name() if swap_data.approved_by else 'System'
                }
        
        calendar_data.append(event_data)
    
    # Get available months and years for filter
    available_months = schedules.dates('date', 'month')
    available_years = schedules.dates('date', 'year')
    
    # Get current month name for display
    current_month_name = calendar.month_name[int(month)]
    
    context = {
        'manager': manager,
        'calendar_data': json.dumps(calendar_data),
        'selected_month': int(month),
        'selected_year': int(year),
        'selected_department': department,
        'available_months': available_months,
        'available_years': available_years,
        'current_month_name': current_month_name,
        'show_department_filter': manager.department_access == 'all',
    }
    return render(request, 'timetable/manager_calendar.html', context)

# Add these helper functions if they don't exist
def get_shift_type(start_time):
    """Determine shift type based on start time"""
    if start_time.hour == 8:
        return 'Early'
    elif start_time.hour == 9:
        return 'Morning'
    elif start_time.hour == 10:
        return 'Mid'
    elif start_time.hour == 11:
        return 'Late'
    else:
        return 'Custom'

def get_shift_color(start_time):
    """Get color code based on shift type"""
    if start_time.hour == 8:
        return '#28a745'  # Green - Early shift
    elif start_time.hour == 9:
        return '#17a2b8'  # Blue - Morning shift
    elif start_time.hour == 10:
        return '#ffc107'  # Yellow - Mid shift
    elif start_time.hour == 11:
        return '#fd7e14'  # Orange - Late shift
    else:
        return '#6c757d'  # Gray - Custom shift
@login_required
def manager_timetable_list(request):
    """Manager view for listing all timetables"""
    try:
        manager = Manager.objects.get(user=request.user)
    except Manager.DoesNotExist:
        messages.error(request, "Manager profile not found.")
        return redirect('dashboard')
    
    # Get all timetables
    timetables = Timetable.objects.all().order_by('-year', '-month')
    
    # Get current month for highlighting
    today = date.today()
    
    context = {
        'manager': manager,
        'timetables': timetables,
        'today': today,
    }
    return render(request, 'timetable/manager_timetable_list.html', context)
# Add this new view for managing employee addition to timetables
@method_decorator(login_required, name='dispatch')
class AddEmployeeToTimetableView(View):
    def get(self, request, employee_id):
        """View to manually add an employee to existing timetables"""
        try:
            manager = Manager.objects.get(user=request.user)
        except Manager.DoesNotExist:
            messages.error(request, "Manager profile not found.")
            return redirect('dashboard')
        
        if not manager.can_manage_employees:
            messages.error(request, "You don't have permission to manage employees.")
            return redirect('dashboard')
        
        employee = get_object_or_404(Employee, id=employee_id)
        
        # Get all timetables that could include this employee
        relevant_timetables = Timetable.objects.filter(is_active=True).order_by('-year', '-month')
        
        # Count total existing schedules for this employee
        existing_schedules = DailySchedule.objects.filter(employee=employee).count()
        
        # For each timetable, count how many schedules this employee already has
        timetables_with_counts = []
        for timetable in relevant_timetables:
            schedule_count = DailySchedule.objects.filter(
                timetable=timetable, 
                employee=employee
            ).count()
            
            timetables_with_counts.append({
                'timetable': timetable,
                'schedule_count': schedule_count
            })
        
        context = {
            'employee': employee,
            'timetables_with_counts': timetables_with_counts,
            'existing_schedules': existing_schedules,
            'manager': manager,
        }
        return render(request, 'timetable/add_employee_to_timetable.html', context)
    
    def post(self, request, employee_id):
        try:
            manager = Manager.objects.get(user=request.user)
        except Manager.DoesNotExist:
            messages.error(request, "Manager profile not found.")
            return redirect('dashboard')
        
        if not manager.can_manage_employees:
            messages.error(request, "You don't have permission to manage employees.")
            return redirect('dashboard')
        
        employee = get_object_or_404(Employee, id=employee_id)
        
        # Get selected timetables
        timetable_ids = request.POST.getlist('timetables')
        include_food_pickup = request.POST.get('include_food_pickup') == 'on'
        overwrite_existing = request.POST.get('overwrite_existing') == 'on'
        
        if not timetable_ids:
            messages.error(request, "Please select at least one timetable.")
            return redirect('add_employee_to_timetable', employee_id=employee_id)
        
        added_schedules = 0
        
        for timetable_id in timetable_ids:
            timetable = get_object_or_404(Timetable, id=timetable_id)
            
            # Delete existing schedules if overwrite is enabled
            if overwrite_existing:
                DailySchedule.objects.filter(
                    timetable=timetable, 
                    employee=employee
                ).delete()
            
            # Generate schedules for this employee
            generator = TimetableGenerator(timetable.month, timetable.year)
            schedules = generator.generate_employee_schedules(employee)
            
            added_schedules += len(schedules)
            
            # Add to food pickup duties
            if include_food_pickup:
                food_scheduler = FoodPickupScheduler(timetable)
                food_scheduler.add_new_employee_to_food_pickup(employee)
        
        messages.success(request, f'Successfully added {employee.name} to {len(timetable_ids)} timetables with {added_schedules} schedules.')
        return redirect('employee_list')

# Update the EmployeeListView to include the new functionality
@method_decorator(login_required, name='dispatch')
class EmployeeListView(View):
    def get(self, request):
        # Check permissions - allow managers with employee management permission
        if not (request.user.has_perm('timetable.view_employee') or 
                (hasattr(request.user, 'manager') and request.user.manager.can_manage_employees)):
            messages.error(request, "You don't have permission to view employees.")
            return redirect('dashboard')
            
        employees_list = Employee.objects.filter(is_active=True).order_by('name')
        
        # If user is a manager with department restrictions, filter employees
        try:
            manager = Manager.objects.get(user=request.user)
            if manager.department_access != 'all':
                employees_list = employees_list.filter(department=manager.department_access)
        except Manager.DoesNotExist:
            pass
        
        # Search functionality
        search_query = request.GET.get('search', '')
        if search_query:
            employees_list = employees_list.filter(
                Q(name__icontains=search_query) |
                Q(employee_id__icontains=search_query) |
                Q(department__icontains=search_query)
            )
        
        # Pagination
        paginator = Paginator(employees_list, 10)
        page_number = request.GET.get('page')
        employees = paginator.get_page(page_number)
        
        # Only show form if user has add permission or is manager with manage employees permission
        can_add_employee = (request.user.has_perm('timetable.add_employee') or 
                          (hasattr(request.user, 'manager') and request.user.manager.can_manage_employees))
        form = EmployeeForm() if can_add_employee else None
        
        return render(request, 'timetable/employee_list.html', {
            'employees': employees,
            'form': form,
            'search_query': search_query,
            'can_add_employee': can_add_employee,
        })

    def post(self, request):
        # Check permissions
        if not (request.user.has_perm('timetable.add_employee') or 
                (hasattr(request.user, 'manager') and request.user.manager.can_manage_employees)):
            messages.error(request, "You don't have permission to add employees.")
            return redirect('employee_list')
            
        form = EmployeeForm(request.POST)
        if form.is_valid():
            employee = form.save()
            
            # Automatically add employee to existing timetables from their start date
            from .utils import add_employee_to_existing_timetables
            added_schedules = add_employee_to_existing_timetables(employee)
            
            messages.success(request, f'Employee added successfully! Generated {added_schedules} schedules across existing timetables.')
            return redirect('employee_list')
        
        employees_list = Employee.objects.filter(is_active=True).order_by('name')
        paginator = Paginator(employees_list, 10)
        page_number = request.GET.get('page')
        employees = paginator.get_page(page_number)
        
        return render(request, 'timetable/employee_list.html', {
            'employees': employees,
            'form': form
        })

# Add this to the GenerateTimetableView to handle existing employees better
@method_decorator(login_required, name='dispatch')
class GenerateTimetableView(View):
    def get(self, request):
        # Check permissions - allow managers with timetable generation permission
        if not (request.user.has_perm('timetable.add_timetable') or 
                (hasattr(request.user, 'manager') and request.user.manager.can_generate_timetables)):
            messages.error(request, "You don't have permission to generate timetables.")
            return redirect('dashboard')
            
        form = TimetableGenerationForm()
        recent_timetables = Timetable.objects.all()[:5]
        
        # Get employees without schedules in recent timetables
        recent_months = recent_timetables.values_list('month', 'year')
        employees_without_schedules = Employee.objects.filter(
            is_active=True
        ).exclude(
            dailyschedule__timetable__month__in=[m for m, y in recent_months],
            dailyschedule__timetable__year__in=[y for m, y in recent_months]
        )[:10]
        
        return render(request, 'timetable/generate_timetable.html', {
            'form': form,
            'recent_timetables': recent_timetables,
            'employees_without_schedules': employees_without_schedules
        })
    
    def post(self, request):
        # Check permissions
        if not (request.user.has_perm('timetable.add_timetable') or 
                (hasattr(request.user, 'manager') and request.user.manager.can_generate_timetables)):
            messages.error(request, "You don't have permission to generate timetables.")
            return redirect('dashboard')
            
        form = TimetableGenerationForm(request.POST)
        if form.is_valid():
            month = int(form.cleaned_data['month'])
            year = int(form.cleaned_data['year'])
            
            generator = TimetableGenerator(month, year)
            timetable = generator.generate_timetable()
            timetable.created_by = request.user
            timetable.save()
            
            # Generate food pickup schedules
            food_scheduler = FoodPickupScheduler(timetable)
            food_scheduler.generate_food_pickup_schedules()
            food_scheduler.assign_food_pickup_duties()
            
            # Check for any employees that might have been missed
            all_employees = Employee.objects.filter(is_active=True)
            scheduled_employees = set(DailySchedule.objects.filter(
                timetable=timetable
            ).values_list('employee_id', flat=True))
            
            missing_employees = [emp for emp in all_employees if emp.id not in scheduled_employees]
            
            if missing_employees:
                for employee in missing_employees:
                    generator.generate_employee_schedules(employee)
                messages.warning(request, f'Added {len(missing_employees)} missing employees to the timetable.')
            
            messages.success(request, f'Timetable for {calendar.month_name[month]} {year} generated successfully!')
            return redirect('timetable_view', timetable_id=timetable.id)
        
        recent_timetables = Timetable.objects.all()[:5]
        return render(request, 'timetable/generate_timetable.html', {
            'form': form,
            'recent_timetables': recent_timetables
        })
# Add this view function for employee detail
@login_required
def employee_detail(request, employee_id):
    """View employee details and schedule history"""
    employee = get_object_or_404(Employee, id=employee_id)
    
    # Check permissions
    try:
        current_employee = Employee.objects.get(user=request.user)
        if current_employee != employee and not request.user.has_perm('timetable.view_employee'):
            messages.error(request, "You don't have permission to view this employee's details.")
            return redirect('dashboard')
    except Employee.DoesNotExist:
        # Check if user is a manager with access
        try:
            manager = Manager.objects.get(user=request.user)
            if not manager.has_department_access(employee.department):
                messages.error(request, "You don't have permission to view this employee's details.")
                return redirect('dashboard')
        except Manager.DoesNotExist:
            if not request.user.has_perm('timetable.view_employee'):
                messages.error(request, "You don't have permission to view employee details.")
                return redirect('dashboard')
    
    # Get employee schedules with pagination
    schedules = DailySchedule.objects.filter(employee=employee).order_by('-date')
    
    # Calculate statistics
    total_schedules = schedules.count()
    active_timetables = Timetable.objects.filter(
        daily_schedules__employee=employee,
        is_active=True
    ).distinct().count()
    
    auto_generated_schedules = schedules.filter(is_auto_generated=True).count()
    manual_schedules = total_schedules - auto_generated_schedules
    
    # Pagination
    paginator = Paginator(schedules, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Recent activity (simplified - you can enhance this)
    recent_activity = []
    
    context = {
        'employee': employee,
        'schedules': page_obj,
        'total_schedules': total_schedules,
        'active_timetables': active_timetables,
        'auto_generated_schedules': auto_generated_schedules,
        'manual_schedules': manual_schedules,
        'recent_activity': recent_activity,
    }
    return render(request, 'timetable/employee_detail.html', context)

# Add this view function for bulk employee addition to timetables
@login_required
def add_employees_to_timetables(request):
    """Bulk add multiple employees to existing timetables"""
    try:
        manager = Manager.objects.get(user=request.user)
    except Manager.DoesNotExist:
        messages.error(request, "Manager profile not found.")
        return redirect('dashboard')
    
    if not manager.can_manage_employees:
        messages.error(request, "You don't have permission to manage employees.")
        return redirect('dashboard')
    
    # Get employees based on department access
    if manager.department_access == 'all':
        employees = Employee.objects.filter(is_active=True)
    else:
        employees = Employee.objects.filter(
            is_active=True, 
            department=manager.department_access
        )
    
    # Get all active timetables
    timetables = Timetable.objects.filter(is_active=True).order_by('-year', '-month')
    
    # Calculate potential schedules
    potential_schedules = employees.count() * timetables.count() * 20  # approx 20 working days per month
    
    if request.method == 'POST':
        employee_ids = request.POST.getlist('employees')
        timetable_ids = request.POST.getlist('timetables')
        include_food_pickup = request.POST.get('include_food_pickup') == 'on'
        skip_existing = request.POST.get('skip_existing') == 'on'
        
        if not employee_ids or not timetable_ids:
            messages.error(request, "Please select at least one employee and one timetable.")
            return redirect('add_employees_to_timetables')
        
        selected_employees = Employee.objects.filter(id__in=employee_ids)
        selected_timetables = Timetable.objects.filter(id__in=timetable_ids)
        
        total_schedules_added = 0
        
        for employee in selected_employees:
            for timetable in selected_timetables:
                # Generate schedules for this employee
                generator = TimetableGenerator(timetable.month, timetable.year)
                schedules = generator.generate_employee_schedules(employee)
                total_schedules_added += len(schedules)
                
                # Add to food pickup if requested
                if include_food_pickup:
                    food_scheduler = FoodPickupScheduler(timetable)
                    food_scheduler.add_new_employee_to_food_pickup(employee)
        
        messages.success(request, f'Successfully added {total_schedules_added} schedules for {selected_employees.count()} employees across {selected_timetables.count()} timetables.')
        return redirect('employee_list')
    
    context = {
        'manager': manager,
        'employees': employees,
        'timetables': timetables,
        'potential_schedules': potential_schedules,
    }
    return render(request, 'timetable/add_employees_to_timetables.html', context)

# Update the manager_dashboard view to include new employee data
@login_required
def manager_dashboard(request):
    """Dashboard specifically for managers"""
    try:
        manager = Manager.objects.get(user=request.user)
    except Manager.DoesNotExist:
        messages.error(request, "Manager profile not found.")
        return redirect('dashboard')
    
    today = date.today()
    
    # Get department filter
    department = request.GET.get('department', 'all')
    
    # Get employees based on department access
    if manager.department_access == 'all':
        employees = Employee.objects.filter(is_active=True)
    else:
        employees = Employee.objects.filter(
            is_active=True, 
            department=manager.department_access
        )
    
    # Get new employees (last 30 days)
    thirty_days_ago = today - timedelta(days=30)
    new_employees = employees.filter(start_date__gte=thirty_days_ago)
    
    # Get employees without schedules in current month
    current_month_schedules = DailySchedule.objects.filter(
        date__month=today.month,
        date__year=today.year
    ).values_list('employee_id', flat=True)
    
    unscheduled_employees = employees.exclude(id__in=current_month_schedules)
    
    # Get pending swap requests
    if manager.department_access == 'all':
        pending_swaps = ShiftSwapRequest.objects.filter(status='pending')
    else:
        pending_swaps = ShiftSwapRequest.objects.filter(
            status='pending',
            requester__department=manager.department_access
        )
    
    # Get current month timetables
    current_timetables = Timetable.objects.filter(
        month=today.month,
        year=today.year
    )
    
    # Get employee count by department
    if manager.department_access == 'all':
        inbound_count = Employee.objects.filter(department='inbound', is_active=True).count()
        outbound_count = Employee.objects.filter(department='outbound', is_active=True).count()
    else:
        inbound_count = Employee.objects.filter(
            department='inbound', 
            is_active=True
        ).count() if manager.department_access == 'inbound' else 0
        outbound_count = Employee.objects.filter(
            department='outbound', 
            is_active=True
        ).count() if manager.department_access == 'outbound' else 0
    
    context = {
        'manager': manager,
        'employees': employees,
        'new_employees': new_employees,
        'unscheduled_employees': unscheduled_employees.count(),
        'new_employees_without_schedules': unscheduled_employees.filter(start_date__gte=thirty_days_ago),
        'pending_swaps': pending_swaps,
        'current_timetables': current_timetables,
        'today': today,
        'inbound_count': inbound_count,
        'outbound_count': outbound_count,
        'selected_department': department,
    }
    return render(request, 'timetable/manager_dashboard.html', context)

# Update the TimetableView to include statistics
@method_decorator(login_required, name='dispatch')
class TimetableView(View):
    def get(self, request, timetable_id):
        timetable = get_object_or_404(Timetable, id=timetable_id)
        
        # Check if user has access to view this timetable
        try:
            employee = Employee.objects.get(user=request.user)
            # Employees can only view their own department's schedules
            daily_schedules = DailySchedule.objects.filter(
                timetable=timetable,
                employee__department=employee.department
            ).select_related('employee').order_by('date', 'start_time')
        except Employee.DoesNotExist:
            try:
                manager = Manager.objects.get(user=request.user)
                # Managers can view based on their department access
                if manager.department_access == 'all':
                    daily_schedules = DailySchedule.objects.filter(
                        timetable=timetable
                    ).select_related('employee').order_by('date', 'start_time')
                else:
                    daily_schedules = DailySchedule.objects.filter(
                        timetable=timetable,
                        employee__department=manager.department_access
                    ).select_related('employee').order_by('date', 'start_time')
            except Manager.DoesNotExist:
                messages.error(request, "You don't have permission to view timetables.")
                return redirect('dashboard')
        
        # Calculate statistics
        total_schedules = daily_schedules.count()
        working_schedules = daily_schedules.filter(is_off=False).count()
        auto_generated_schedules = daily_schedules.filter(is_auto_generated=True).count()
        
        # Group by date
        schedules_by_date = {}
        for schedule in daily_schedules:
            date_str = schedule.date.isoformat()
            if date_str not in schedules_by_date:
                schedules_by_date[date_str] = []
            schedules_by_date[date_str].append(schedule)
        
        # Get all swap requests for this timetable period
        swap_requests = ShiftSwapRequest.objects.filter(
            requested_date__month=timetable.month,
            requested_date__year=timetable.year,
            status='approved'
        ).select_related('requester', 'requested_to', 'approved_by')
        
        context = {
            'timetable': timetable,
            'schedules_by_date': schedules_by_date,
            'swap_requests': swap_requests,
            'total_schedules': total_schedules,
            'working_schedules': working_schedules,
            'auto_generated_schedules': auto_generated_schedules,
            'swapped_schedules': swap_requests.count(),
        }
        return render(request, 'timetable/timetable_view.html', context)