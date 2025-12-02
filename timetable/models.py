from django.db import models
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.utils import timezone
from datetime import date, timedelta
import calendar

class Employee(models.Model):
    DEPARTMENT_CHOICES = [
        ('inbound', 'Inbound'),
        ('outbound', 'Outbound'),
    ]
    
    user = models.OneToOneField(User, on_delete=models.CASCADE, null=True, blank=True)
    name = models.CharField(max_length=100)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=15, blank=True)
    employee_id = models.CharField(max_length=20, unique=True, blank=True, null=True)
    department = models.CharField(max_length=20, choices=DEPARTMENT_CHOICES, default='inbound')
    position = models.CharField(max_length=100, blank=True)
    start_date = models.DateField(default=date.today)  # Employee's start date
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        permissions = [
            ("manage_all", "Can manage all timetable operations"),
            ("view_personal_schedule", "Can view personal schedule"),
            ("request_shift_swap", "Can request shift swaps"),
        ]
        ordering = ['name']  
    
    def __str__(self):
        return f"{self.name} ({self.employee_id}) - {self.get_department_display()}"
    
    def save(self, *args, **kwargs):
        if not self.employee_id:
            last_employee = Employee.objects.order_by('-id').first()
            if last_employee and last_employee.employee_id:
                try:
                    last_id = int(last_employee.employee_id[3:])
                    self.employee_id = f"EMP{last_id + 1:04d}"
                except:
                    self.employee_id = f"EMP0001"
            else:
                self.employee_id = f"EMP0001"
        super().save(*args, **kwargs)
    
    def get_effective_start_date(self):
        """Get the effective start date for scheduling purposes"""
        return self.start_date

class Manager(models.Model):
    """Manager role for users who can view everything but are not employees"""
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=15, blank=True)
    department_access = models.CharField(
        max_length=20, 
        choices=[('all', 'All Departments'), ('inbound', 'Inbound Only'), ('outbound', 'Outbound Only')],
        default='all'
    )
    can_approve_swaps = models.BooleanField(default=True)
    can_manage_employees = models.BooleanField(default=True)
    can_generate_timetables = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['name']
        verbose_name = "Manager"
        verbose_name_plural = "Managers"
    
    def __str__(self):
        return f"Manager: {self.name} ({self.get_department_access_display()})"
    
    def has_department_access(self, department):
        """Check if manager has access to view specific department"""
        if self.department_access == 'all':
            return True
        return self.department_access == department
    
    def save(self, *args, **kwargs):
        """Automatically set manager permissions on the user"""
        if not self.name and self.user:
            self.name = self.user.get_full_name() or self.user.username
        if not self.email and self.user:
            self.email = self.user.email
        
        super().save(*args, **kwargs)
        
        # Ensure user has staff status to access admin
        if self.user and not self.user.is_staff:
            self.user.is_staff = True
            self.user.save()

class WorkRule(models.Model):
    name = models.CharField(max_length=100)
    max_start_time = models.TimeField(default='11:00')
    min_end_time = models.TimeField(default='17:00')
    max_end_time = models.TimeField(default='20:00')
    work_hours = models.IntegerField(default=8)
    lunch_duration = models.IntegerField(default=60)
    
    def __str__(self):
        return self.name

class EmployeeRule(models.Model):
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE)
    work_rule = models.ForeignKey(WorkRule, on_delete=models.CASCADE)
    preferred_start_time = models.TimeField(null=True, blank=True)
    
    class Meta:
        unique_together = ['employee', 'work_rule']

class Timetable(models.Model):
    MONTH_CHOICES = [(i, i) for i in range(1, 13)]
    YEAR_CHOICES = [(i, i) for i in range(2020, 2031)]
    
    month = models.IntegerField(choices=MONTH_CHOICES)
    year = models.IntegerField(choices=YEAR_CHOICES)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)
    last_updated = models.DateTimeField(auto_now=True)  # Track when timetable was last updated
    
    class Meta:
        unique_together = ['month', 'year']
        ordering = ['-year', '-month']
    
    def __str__(self):
        return f"{calendar.month_name[self.month]} {self.year}"
    
    def get_month_dates(self):
        """Get all dates in the timetable month"""
        _, num_days = calendar.monthrange(self.year, self.month)
        dates = []
        for day in range(1, num_days + 1):
            dates.append(date(self.year, self.month, day))
        return dates
    
    def add_new_employee_schedules(self, employee):
        """Add schedules for a new employee starting from their start date"""
        from .utils import TimetableGenerator
        
        # Only add schedules if employee start date is within this timetable period
        month_start = date(self.year, self.month, 1)
        _, num_days = calendar.monthrange(self.year, self.month)
        month_end = date(self.year, self.month, num_days)
        
        employee_start_date = employee.get_effective_start_date()
        
        # If employee starts after this month, no schedules needed
        if employee_start_date > month_end:
            return []
        
        # If employee starts before this month, start from 1st of month
        start_date = max(employee_start_date, month_start)
        
        # Generate schedules for the employee from their start date
        generator = TimetableGenerator(self.month, self.year)
        new_schedules = generator.generate_employee_schedules(employee, start_date, month_end)
        
        return new_schedules

class DailySchedule(models.Model):
    timetable = models.ForeignKey(Timetable, on_delete=models.CASCADE, related_name='daily_schedules')
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE)
    date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField()
    lunch_time = models.TimeField()
    is_off = models.BooleanField(default=False)
    replacement = models.ForeignKey(Employee, on_delete=models.SET_NULL, null=True, blank=True, related_name='replacements')
    is_auto_generated = models.BooleanField(default=False)  # Track if schedule was auto-generated for new employee
    
    class Meta:
        unique_together = ['timetable', 'employee', 'date']
        ordering = ['date', 'start_time']
    
    def clean(self):
        if self.start_time and self.end_time:
            from datetime import datetime
            start_dt = datetime.combine(self.date, self.start_time)
            end_dt = datetime.combine(self.date, self.end_time)
            
            if end_dt <= start_dt:
                raise ValidationError("End time must be after start time")

class TimeOff(models.Model):
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE)
    start_date = models.DateField()
    end_date = models.DateField()
    reason = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=[('pending', 'Pending'), ('approved', 'Approved'), ('rejected', 'Rejected')], default='pending')
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_time_off')
    created_at = models.DateTimeField(auto_now_add=True)
    
    def clean(self):
        if self.end_date < self.start_date:
            raise ValidationError("End date cannot be before start date")

class ShiftSwapRequest(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('manager_approved', 'Manager Approved'),
        ('cancelled', 'Cancelled'),
    ]
    
    requester = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='swap_requests_made')
    requested_to = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='swap_requests_received')
    original_schedule = models.ForeignKey(DailySchedule, on_delete=models.CASCADE, related_name='original_swap_requests')
    requested_date = models.DateField()
    reason = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
    
    # Approval tracking
    employee_approved = models.BooleanField(default=False)
    employee_approved_at = models.DateTimeField(null=True, blank=True)
    
    manager_approved = models.BooleanField(default=False)
    manager_approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_swaps')
    manager_approved_at = models.DateTimeField(null=True, blank=True)
    
    # Final approval
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='final_approved_swaps')
    approved_at = models.DateTimeField(null=True, blank=True)
    
    rejection_reason = models.TextField(blank=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Swap: {self.requester.name} -> {self.requested_to.name} on {self.requested_date}"
    
    def clean(self):
        if self.requested_date < date.today():
            raise ValidationError("Cannot request swap for past dates")
    
    def can_employee_approve(self, employee):
        """Check if employee can approve this swap request"""
        return self.requested_to == employee and self.status == 'pending'
    
    def can_manager_approve(self, user):
        """Check if manager can approve this swap request"""
        try:
            manager = Manager.objects.get(user=user)
            return (manager.is_active and manager.can_approve_swaps and 
                    self.status in ['pending', 'employee_approved'])
        except Manager.DoesNotExist:
            return False

class SwapHistory(models.Model):
    """Track completed shift swaps"""
    swap_request = models.ForeignKey(ShiftSwapRequest, on_delete=models.CASCADE)
    original_employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='original_swaps')
    target_employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='target_swaps')
    swap_date = models.DateField()
    original_schedule_data = models.JSONField()  # Store original schedule details
    target_schedule_data = models.JSONField()    # Store target schedule details
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-swap_date', '-created_at']
    
    def __str__(self):
        return f"Swap History: {self.original_employee.name} <-> {self.target_employee.name} on {self.swap_date}"

class FoodPickupSchedule(models.Model):
    timetable = models.ForeignKey(Timetable, on_delete=models.CASCADE, related_name='food_pickups')
    date = models.DateField()
    max_people = models.IntegerField(default=2)
    assigned_employees = models.ManyToManyField(Employee, through='FoodPickupAssignment', related_name='food_pickup_assignments')
    
    class Meta:
        unique_together = ['timetable', 'date']
        ordering = ['date']
    
    def __str__(self):
        return f"Food Pickup - {self.date}"

class FoodPickupAssignment(models.Model):
    food_pickup = models.ForeignKey(FoodPickupSchedule, on_delete=models.CASCADE)
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE)
    assigned_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ['food_pickup', 'employee']

# Signals to handle automatic schedule generation for new employees
from django.db.models.signals import post_save
from django.dispatch import receiver

@receiver(post_save, sender=Employee)
def add_employee_to_existing_timetables(sender, instance, created, **kwargs):
    """Automatically add new employees to existing timetables from their start date"""
    if created and instance.is_active:
        # Get all active timetables from the employee's start date
        employee_start_date = instance.get_effective_start_date()
        
        # Find timetables that include or are after the employee's start date
        relevant_timetables = Timetable.objects.filter(
            is_active=True
        ).extra(
            where=[
                """
                (year > %s OR (year = %s AND month >= %s))
                """,
            ],
            params=[employee_start_date.year, employee_start_date.year, employee_start_date.month]
        )
        
        for timetable in relevant_timetables:
            # Add schedules for this employee to the timetable
            timetable.add_new_employee_schedules(instance)

@receiver(post_save, sender=Manager)
def set_user_staff_status(sender, instance, created, **kwargs):
    """Ensure manager users have staff status"""
    if instance.user and not instance.user.is_staff:
        instance.user.is_staff = True
        instance.user.save()