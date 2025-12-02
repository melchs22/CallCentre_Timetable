from django.contrib import admin
from django.contrib.auth.models import User
from django.contrib.auth.admin import UserAdmin
from django.utils.html import format_html
from .models import *

class ManagerInline(admin.StackedInline):
    model = Manager
    can_delete = False
    verbose_name_plural = 'Manager Profile'
    fk_name = 'user'
    fields = ['name', 'email', 'phone', 'department_access', 'can_approve_swaps', 'can_manage_employees', 'can_generate_timetables', 'is_active']
    extra = 0

class EmployeeInline(admin.StackedInline):
    model = Employee
    can_delete = False
    verbose_name_plural = 'Employee Profile'
    fk_name = 'user'
    extra = 0

class CustomUserAdmin(UserAdmin):
    inlines = [ManagerInline, EmployeeInline]
    list_display = ['username', 'email', 'first_name', 'last_name', 'user_type', 'is_staff', 'is_active', 'date_joined']
    list_filter = ['is_staff', 'is_active', 'manager', 'employee', 'date_joined']
    search_fields = ['username', 'email', 'first_name', 'last_name']
    actions = ['make_manager', 'make_employee', 'deactivate_users']
    
    def user_type(self, obj):
        if hasattr(obj, 'manager'):
            badge_color = 'primary'
            if obj.manager.department_access == 'inbound':
                badge_color = 'info'
            elif obj.manager.department_access == 'outbound':
                badge_color = 'success'
            return format_html(
                '<span class="badge bg-{}">Manager ({})</span>',
                badge_color,
                obj.manager.get_department_access_display()
            )
        elif hasattr(obj, 'employee'):
            badge_color = 'warning'
            if obj.employee.department == 'inbound':
                badge_color = 'info'
            elif obj.employee.department == 'outbound':
                badge_color = 'success'
            return format_html(
                '<span class="badge bg-{}">Employee ({})</span>',
                badge_color,
                obj.employee.get_department_display()
            )
        return format_html('<span class="badge bg-secondary">Admin</span>')
    user_type.short_description = 'User Type'

    def get_inline_instances(self, request, obj=None):
        if not obj:
            return []
        return super().get_inline_instances(request, obj)

    @admin.action(description='Convert selected users to managers')
    def make_manager(self, request, queryset):
        from .models import ManagerCreation
        count = 0
        for user in queryset:
            if not hasattr(user, 'manager') and not hasattr(user, 'employee'):
                try:
                    ManagerCreation.create_manager_from_user(user)
                    count += 1
                except Exception as e:
                    self.message_user(request, f"Error converting {user.username}: {str(e)}", level='error')
        self.message_user(request, f'Successfully converted {count} users to managers.')

    @admin.action(description='Convert selected users to employees')
    def make_employee(self, request, queryset):
        count = 0
        for user in queryset:
            if not hasattr(user, 'employee') and not hasattr(user, 'manager'):
                try:
                    # Create employee profile
                    employee = Employee.objects.create(
                        user=user,
                        name=user.get_full_name() or user.username,
                        email=user.email
                    )
                    count += 1
                except Exception as e:
                    self.message_user(request, f"Error converting {user.username}: {str(e)}", level='error')
        self.message_user(request, f'Successfully converted {count} users to employees.')

    @admin.action(description='Deactivate selected users')
    def deactivate_users(self, request, queryset):
        updated = queryset.update(is_active=False)
        # Also deactivate related profiles
        for user in queryset:
            if hasattr(user, 'manager'):
                user.manager.is_active = False
                user.manager.save()
            if hasattr(user, 'employee'):
                user.employee.is_active = False
                user.employee.save()
        self.message_user(request, f'{updated} users deactivated.')

@admin.register(Manager)
class ManagerAdmin(admin.ModelAdmin):
    list_display = ['name', 'user', 'department_access', 'permissions_display', 'is_active', 'created_at']
    list_filter = ['department_access', 'can_approve_swaps', 'can_manage_employees', 'can_generate_timetables', 'is_active', 'created_at']
    search_fields = ['name', 'user__username', 'email', 'phone']
    list_editable = ['is_active']
    actions = ['activate_managers', 'deactivate_managers', 'grant_all_permissions']
    readonly_fields = ['created_at']
    list_per_page = 20
    
    def permissions_display(self, obj):
        permissions = []
        if obj.can_approve_swaps:
            permissions.append('Swaps')
        if obj.can_manage_employees:
            permissions.append('Employees')
        if obj.can_generate_timetables:
            permissions.append('Timetables')
        return ', '.join(permissions) if permissions else 'None'
    permissions_display.short_description = 'Permissions'
    
    def activate_managers(self, request, queryset):
        updated = queryset.update(is_active=True)
        # Also activate related users
        for manager in queryset:
            manager.user.is_active = True
            manager.user.save()
        self.message_user(request, f'{updated} managers activated.')
    activate_managers.short_description = "Activate selected managers"
    
    def deactivate_managers(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f'{updated} managers deactivated.')
    deactivate_managers.short_description = "Deactivate selected managers"
    
    def grant_all_permissions(self, request, queryset):
        updated = queryset.update(
            can_approve_swaps=True,
            can_manage_employees=True,
            can_generate_timetables=True
        )
        self.message_user(request, f'Granted all permissions to {updated} managers.')
    grant_all_permissions.short_description = "Grant all permissions to selected managers"

@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ['name', 'employee_id', 'department', 'position', 'email', 'phone', 'is_active', 'user_link']
    list_filter = ['department', 'is_active', 'position', 'created_at']
    search_fields = ['name', 'employee_id', 'email', 'phone']
    list_editable = ['is_active']
    actions = ['activate_employees', 'deactivate_employees']
    readonly_fields = ['created_at', 'employee_id']
    list_per_page = 20
    
    def user_link(self, obj):
        if obj.user:
            return format_html(
                '<a href="/admin/auth/user/{}/change/">{}</a>',
                obj.user.id,
                obj.user.username
            )
        return "No user"
    user_link.short_description = 'User Account'
    
    def activate_employees(self, request, queryset):
        updated = queryset.update(is_active=True)
        # Also activate related users
        for employee in queryset:
            if employee.user:
                employee.user.is_active = True
                employee.user.save()
        self.message_user(request, f'{updated} employees activated.')
    activate_employees.short_description = "Activate selected employees"
    
    def deactivate_employees(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f'{updated} employees deactivated.')
    deactivate_employees.short_description = "Deactivate selected employees"

@admin.register(WorkRule)
class WorkRuleAdmin(admin.ModelAdmin):
    list_display = ['name', 'max_start_time', 'min_end_time', 'max_end_time', 'work_hours', 'lunch_duration']
    list_filter = ['work_hours']
    search_fields = ['name']

@admin.register(EmployeeRule)
class EmployeeRuleAdmin(admin.ModelAdmin):
    list_display = ['employee', 'work_rule', 'preferred_start_time']
    list_filter = ['work_rule']
    autocomplete_fields = ['employee', 'work_rule']
    search_fields = ['employee__name']

@admin.register(Timetable)
class TimetableAdmin(admin.ModelAdmin):
    list_display = ['month_year', 'year', 'created_by', 'created_at', 'is_active', 'schedules_count']
    list_filter = ['month', 'year', 'is_active', 'created_at']
    search_fields = ['month', 'year', 'created_by__username']
    readonly_fields = ['created_at']
    list_per_page = 10
    
    def month_year(self, obj):
        import calendar
        return f"{calendar.month_name[obj.month]} {obj.year}"
    month_year.short_description = 'Period'
    
    def schedules_count(self, obj):
        return obj.daily_schedules.count()
    schedules_count.short_description = 'Schedules'

@admin.register(DailySchedule)
class DailyScheduleAdmin(admin.ModelAdmin):
    list_display = ['employee', 'date', 'start_time', 'end_time', 'lunch_time', 'is_off', 'timetable', 'department']
    list_filter = ['date', 'is_off', 'timetable', 'employee__department']
    search_fields = ['employee__name', 'employee__employee_id']
    autocomplete_fields = ['employee', 'replacement', 'timetable']
    list_per_page = 20
    
    def department(self, obj):
        return obj.employee.get_department_display()
    department.short_description = 'Department'

@admin.register(TimeOff)
class TimeOffAdmin(admin.ModelAdmin):
    list_display = ['employee', 'start_date', 'end_date', 'status', 'approved_by', 'created_at']
    list_filter = ['start_date', 'end_date', 'status', 'created_at']
    search_fields = ['employee__name', 'reason']
    autocomplete_fields = ['employee', 'approved_by']
    list_per_page = 15

@admin.register(ShiftSwapRequest)
class ShiftSwapRequestAdmin(admin.ModelAdmin):
    list_display = ['requester', 'requested_to', 'requested_date', 'status', 'employee_approved', 'manager_approved', 'created_at']
    list_filter = ['status', 'requested_date', 'created_at', 'employee_approved', 'manager_approved']
    search_fields = ['requester__name', 'requested_to__name', 'reason']
    autocomplete_fields = ['requester', 'requested_to', 'original_schedule', 'approved_by', 'manager_approved_by']
    readonly_fields = ['created_at', 'employee_approved_at', 'manager_approved_at', 'approved_at']
    list_per_page = 15
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'requester', 'requested_to', 'approved_by', 'manager_approved_by'
        )

@admin.register(SwapHistory)
class SwapHistoryAdmin(admin.ModelAdmin):
    list_display = ['original_employee', 'target_employee', 'swap_date', 'approved_by', 'created_at']
    list_filter = ['swap_date', 'created_at']
    search_fields = ['original_employee__name', 'target_employee__name']
    autocomplete_fields = ['swap_request', 'original_employee', 'target_employee', 'approved_by']
    readonly_fields = ['created_at']
    list_per_page = 15

@admin.register(FoodPickupSchedule)
class FoodPickupScheduleAdmin(admin.ModelAdmin):
    list_display = ['date', 'timetable', 'max_people', 'get_assigned_count']
    list_filter = ['date', 'timetable']
    search_fields = ['date', 'timetable__month', 'timetable__year']
    autocomplete_fields = ['timetable']
    list_per_page = 15
    
    def get_assigned_count(self, obj):
        return obj.foodpickupassignment_set.count()
    get_assigned_count.short_description = 'Assigned'

@admin.register(FoodPickupAssignment)
class FoodPickupAssignmentAdmin(admin.ModelAdmin):
    list_display = ['food_pickup', 'employee', 'department', 'assigned_at']
    list_filter = ['food_pickup__date', 'employee__department']
    search_fields = ['employee__name', 'food_pickup__date']
    autocomplete_fields = ['food_pickup', 'employee']
    readonly_fields = ['assigned_at']
    list_per_page = 20
    
    def department(self, obj):
        return obj.employee.get_department_display()
    department.short_description = 'Department'

# Re-register UserAdmin with custom configuration
admin.site.unregister(User)
admin.site.register(User, CustomUserAdmin)

# Custom admin site header and title
admin.site.site_header = "Timetable System Administration"
admin.site.site_title = "Timetable System Admin"
admin.site.index_title = "Welcome to Timetable System Administration"