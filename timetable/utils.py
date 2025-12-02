from datetime import time, datetime, date, timedelta
import calendar
import random
from .models import *

class TimetableGenerator:
    def __init__(self, month, year):
        self.month = month
        self.year = year
        self.work_days = self.get_work_days()
        self.sundays = self.get_sundays()
        self.saturdays = self.get_saturdays()
        self.weeks = self.get_weeks_in_month()
    
    def get_work_days(self):
        """Get all working days (Monday to Saturday) for the month"""
        work_days = []
        cal = calendar.Calendar()
        for day in cal.itermonthdays(self.year, self.month):
            if day != 0:
                current_date = date(self.year, self.month, day)
                if current_date.weekday() < 6:  # 0-5 = Monday to Saturday
                    work_days.append(current_date)
        return work_days
    
    def get_sundays(self):
        """Get all Sundays for the month"""
        sundays = []
        cal = calendar.Calendar()
        for day in cal.itermonthdays(self.year, self.month):
            if day != 0:
                current_date = date(self.year, self.month, day)
                if current_date.weekday() == 6:  # 6 = Sunday
                    sundays.append(current_date)
        return sundays
    
    def get_saturdays(self):
        """Get all Saturdays for the month"""
        saturdays = []
        cal = calendar.Calendar()
        for day in cal.itermonthdays(self.year, self.month):
            if day != 0:
                current_date = date(self.year, self.month, day)
                if current_date.weekday() == 5:  # 5 = Saturday
                    saturdays.append(current_date)
        return saturdays
    
    def get_weeks_in_month(self):
        """Get all weeks in the month for weekly rotation"""
        weeks = []
        cal = calendar.Calendar()
        month_days = cal.monthdayscalendar(self.year, self.month)
        
        for week_index, week in enumerate(month_days):
            week_dates = []
            for day in week:
                if day != 0:
                    week_dates.append(date(self.year, self.month, day))
            if week_dates:  # Only add non-empty weeks
                weeks.append({
                    'week_index': week_index,
                    'dates': week_dates,
                    'start_date': min(week_dates),
                    'end_date': max(week_dates)
                })
        return weeks
    
    def get_week_number(self, work_date):
        """Get the week number within the month for a given date"""
        for week in self.weeks:
            if week['start_date'] <= work_date <= week['end_date']:
                return week['week_index']
        return 0
    
    def get_inbound_shift(self, employee, work_date):
        """Get Inbound department shift with weekly rotation"""
        try:
            inbound_employees = list(Employee.objects.filter(
                department='inbound', 
                is_active=True
            ).order_by('id'))
            
            if not inbound_employees:
                return None
            
            employee_index = inbound_employees.index(employee) if employee in inbound_employees else 0
            week_number = self.get_week_number(work_date)
            
            # For Monday to Friday - everyone works with weekly rotating distribution
            if work_date.weekday() < 5:  # Monday to Friday
                # MUST: First 2 employees always work at 8:00 AM (but rotate who these are weekly)
                rotated_employees = self.get_weekly_rotated_list(inbound_employees, week_number)
                rotated_index = rotated_employees.index(employee) if employee in rotated_employees else employee_index
                
                if rotated_index < 2:
                    return time(8, 0)
                
                # Distribute remaining employees among 9:00, 10:00, 11:00 AM shifts with weekly rotation
                remaining_employees = len(inbound_employees) - 2
                if remaining_employees <= 0:
                    return time(8, 0)
                
                # Calculate shifts for remaining employees with weekly variation
                shifts = [time(9, 0), time(10, 0), time(11, 0)]
                
                # Weekly rotation for shift assignment
                shift_rotation = (week_number + employee.id) % len(shifts)
                base_shift_index = (rotated_index - 2 + shift_rotation) % len(shifts)
                
                # If we have more employees than shifts, distribute evenly
                if remaining_employees > len(shifts):
                    employees_per_shift = remaining_employees // len(shifts)
                    extra_employees = remaining_employees % len(shifts)
                    
                    # Determine which shift this employee gets
                    cumulative_count = 0
                    for i, shift in enumerate(shifts):
                        count_for_shift = employees_per_shift + (1 if i < extra_employees else 0)
                        if rotated_index - 2 < cumulative_count + count_for_shift:
                            return shift
                        cumulative_count += count_for_shift
                
                return shifts[base_shift_index]
            
            # For Saturday - only inbound employees who are NOT working Sunday
            elif work_date.weekday() == 5:  # Saturday
                # Check if this employee is scheduled for Sunday this week
                sunday_workers = self.get_inbound_sunday_workers_for_week(work_date)
                if employee in sunday_workers:
                    return None  # Sunday workers don't work Saturday
                else:
                    # Saturday workers use weekly rotated distribution
                    rotated_employees = self.get_weekly_rotated_list(inbound_employees, week_number)
                    rotated_index = rotated_employees.index(employee) if employee in rotated_employees else employee_index
                    
                    if rotated_index < 2:
                        return time(8, 0)
                    
                    remaining_employees = len([e for e in inbound_employees if e not in sunday_workers]) - 2
                    if remaining_employees <= 0:
                        return time(8, 0)
                    
                    shifts = [time(9, 0), time(10, 0), time(11, 0)]
                    shift_rotation = (week_number + employee.id) % len(shifts)
                    base_shift_index = (rotated_index - 2 + shift_rotation) % len(shifts)
                    
                    if remaining_employees > len(shifts):
                        employees_per_shift = remaining_employees // len(shifts)
                        extra_employees = remaining_employees % len(shifts)
                        
                        cumulative_count = 0
                        for i, shift in enumerate(shifts):
                            count_for_shift = employees_per_shift + (1 if i < extra_employees else 0)
                            if rotated_index - 2 < cumulative_count + count_for_shift:
                                return shift
                            cumulative_count += count_for_shift
                    
                    return shifts[base_shift_index]
            
            else:  # Sunday
                return self.get_sunday_inbound_shift(employee, work_date)
                
        except Exception as e:
            print(f"Error in get_inbound_shift for {employee.name}: {e}")
            return time(8, 0)
    
    def get_weekly_rotated_list(self, employees, week_number):
        """Rotate employee list weekly to distribute early shifts fairly"""
        if not employees:
            return []
        
        # Rotate the list based on week number
        rotation_offset = week_number % len(employees)
        rotated_list = employees[rotation_offset:] + employees[:rotation_offset]
        return rotated_list
    
    def get_inbound_sunday_workers_for_week(self, date_in_week):
        """Get inbound employees working Sunday for the given week with weekly rotation"""
        try:
            inbound_employees = list(Employee.objects.filter(
                department='inbound', 
                is_active=True
            ).order_by('id'))
            
            if not inbound_employees:
                return []
            
            # Find the Sunday for this week
            sunday_date = None
            for sunday in self.sundays:
                # Check if this Sunday is in the same week as the given date
                week_start = date_in_week - timedelta(days=date_in_week.weekday())
                week_end = week_start + timedelta(days=6)
                if week_start <= sunday <= week_end:
                    sunday_date = sunday
                    break
            
            if not sunday_date:
                return []
            
            # Weekly rotation for Sunday workers
            week_number = self.get_week_number(sunday_date)
            rotated_employees = self.get_weekly_rotated_list(inbound_employees, week_number)
            
            employees_per_sunday = max(1, len(inbound_employees) // 2)  # About half work Sunday
            
            start_index = (week_number * employees_per_sunday) % len(rotated_employees)
            end_index = start_index + employees_per_sunday
            
            sunday_workers = []
            # Add employees for this Sunday
            for i in range(start_index, min(end_index, len(rotated_employees))):
                sunday_workers.append(rotated_employees[i])
            
            # Handle wrap-around
            if end_index > len(rotated_employees):
                wrap_count = end_index - len(rotated_employees)
                for i in range(wrap_count):
                    sunday_workers.append(rotated_employees[i])
            
            return sunday_workers
            
        except Exception as e:
            print(f"Error in get_inbound_sunday_workers_for_week: {e}")
            return []
    
    def get_sunday_inbound_shift(self, employee, work_date):
        """Get Sunday shift for inbound - rotating workers with weekly variation"""
        try:
            inbound_employees = list(Employee.objects.filter(
                department='inbound', 
                is_active=True
            ).order_by('id'))
            
            if not inbound_employees:
                return None
            
            week_number = self.get_week_number(work_date)
            
            # Check if this employee is scheduled for this Sunday
            sunday_workers = self.get_inbound_sunday_workers_for_week(work_date)
            if employee in sunday_workers:
                # Sunday workers use weekly rotated distribution
                rotated_employees = self.get_weekly_rotated_list(inbound_employees, week_number)
                rotated_index = rotated_employees.index(employee) if employee in rotated_employees else 0
                
                if rotated_index < 2:
                    return time(8, 0)
                
                remaining_sunday_workers = len(sunday_workers) - 2
                if remaining_sunday_workers <= 0:
                    return time(8, 0)
                
                shifts = [time(9, 0), time(10, 0), time(11, 0)]
                shift_rotation = (week_number + employee.id) % len(shifts)
                base_shift_index = (rotated_index - 2 + shift_rotation) % len(shifts)
                
                if remaining_sunday_workers > len(shifts):
                    employees_per_shift = remaining_sunday_workers // len(shifts)
                    extra_employees = remaining_sunday_workers % len(shifts)
                    
                    cumulative_count = 0
                    for i, shift in enumerate(shifts):
                        count_for_shift = employees_per_shift + (1 if i < extra_employees else 0)
                        if rotated_index - 2 < cumulative_count + count_for_shift:
                            return shift
                        cumulative_count += count_for_shift
                
                return shifts[base_shift_index]
            else:
                return None  # Not scheduled for Sunday
                
        except Exception as e:
            print(f"Error in get_sunday_inbound_shift for {employee.name}: {e}")
            return None
    
    def get_outbound_shift(self, employee, work_date):
        """Get Outbound department shift with weekly rotation between 8-5 / 9-6"""
        try:
            # Outbound only works Monday to Saturday
            if work_date.weekday() < 6:  # Monday to Saturday
                outbound_employees = list(Employee.objects.filter(
                    department='outbound', 
                    is_active=True
                ).order_by('id'))
                
                if not outbound_employees:
                    return None
                
                employee_index = outbound_employees.index(employee) if employee in outbound_employees else 0
                week_number = self.get_week_number(work_date)
                
                # Get total number of outbound employees
                total_outbound = len(outbound_employees)
                
                # Weekly rotation of the employee list
                rotated_employees = self.get_weekly_rotated_list(outbound_employees, week_number)
                rotated_index = rotated_employees.index(employee) if employee in rotated_employees else employee_index
                
                if total_outbound % 2 == 0:  # Even number of employees
                    # Balanced distribution: half at 8-5, half at 9-6 with weekly rotation
                    split_point = total_outbound // 2
                    if rotated_index < split_point:
                        return time(8, 0)  # 8AM-5PM
                    else:
                        return time(9, 0)  # 9AM-6PM
                else:  # Odd number of employees
                    # Weekly rotation for odd number distribution
                    # Even weeks: 8-5 gets extra, Odd weeks: 9-6 gets extra
                    if week_number % 2 == 0:
                        # This week: 8-5 gets the extra person
                        split_point = (total_outbound // 2) + 1
                    else:
                        # This week: 9-6 gets the extra person  
                        split_point = total_outbound // 2
                    
                    if rotated_index < split_point:
                        return time(8, 0)  # 8AM-5PM
                    else:
                        return time(9, 0)  # 9AM-6PM
            
            else:  # Sunday - Outbound doesn't work Sunday
                return None
                
        except Exception as e:
            print(f"Error in get_outbound_shift for {employee.name}: {e}")
            return time(8, 0)
    
    def calculate_end_time(self, start_time, department):
        """Calculate end time based on start time and department"""
        if start_time is None:
            return None
            
        start_dt = datetime.combine(date.today(), start_time)
        
        if department == 'outbound':
            # Outbound: 8AM-5PM (9 hours with lunch) or 9AM-6PM (9 hours with lunch)
            end_dt = start_dt + timedelta(hours=9)
        else:
            # Inbound: All shifts are 8AM-5PM (9 hours with lunch)
            end_dt = start_dt + timedelta(hours=9)
        
        return end_dt.time()
    
    def calculate_lunch_time(self, start_time):
        """Calculate lunch time (4 hours after start)"""
        if start_time is None:
            return None
            
        start_dt = datetime.combine(date.today(), start_time)
        lunch_dt = start_dt + timedelta(hours=4)
        return lunch_dt.time()
    
    def generate_timetable(self):
        """Generate complete timetable with weekly rotation logic"""
        print(f"Generating timetable for {self.month}/{self.year}")
        print(f"Month has {len(self.work_days)} work days, {len(self.sundays)} Sundays, and {len(self.weeks)} weeks")
        
        timetable, created = Timetable.objects.get_or_create(
            month=self.month,
            year=self.year,
            defaults={'is_active': True}
        )
        
        all_employees = list(Employee.objects.filter(is_active=True))
        inbound_employees = [e for e in all_employees if e.department == 'inbound']
        outbound_employees = [e for e in all_employees if e.department == 'outbound']
        
        print(f"Found {len(all_employees)} active employees")
        print(f"Inbound: {len(inbound_employees)}, Outbound: {len(outbound_employees)}")
        
        if not all_employees:
            print("No active employees found!")
            return timetable
        
        # Clear existing schedules
        DailySchedule.objects.filter(timetable=timetable).delete()
        print("Cleared existing schedules")
        
        schedules_created = []
        
        # Process all employees
        for employee in all_employees:
            print(f"Processing employee: {employee.name} ({employee.department})")
            
            # Combine all days for complete schedule
            all_days = sorted(self.work_days + self.sundays)
            
            for work_date in all_days:
                # Get department-specific shift
                if employee.department == 'inbound':
                    start_time = self.get_inbound_shift(employee, work_date)
                else:  # outbound
                    start_time = self.get_outbound_shift(employee, work_date)
                
                # If no shift assigned, mark as off
                if start_time is None:
                    schedule = DailySchedule(
                        timetable=timetable,
                        employee=employee,
                        date=work_date,
                        start_time=time(0, 0),
                        end_time=time(0, 0),
                        lunch_time=time(0, 0),
                        is_off=True
                    )
                    schedules_created.append(schedule)
                    continue
                
                end_time = self.calculate_end_time(start_time, employee.department)
                lunch_time = self.calculate_lunch_time(start_time)
                
                # Check if employee has time off
                time_off = TimeOff.objects.filter(
                    employee=employee,
                    start_date__lte=work_date,
                    end_date__gte=work_date
                ).exists()
                
                schedule = DailySchedule(
                    timetable=timetable,
                    employee=employee,
                    date=work_date,
                    start_time=start_time,
                    end_time=end_time,
                    lunch_time=lunch_time,
                    is_off=time_off
                )
                
                schedules_created.append(schedule)
        
        # Bulk create schedules
        print(f"Creating {len(schedules_created)} schedule entries...")
        try:
            DailySchedule.objects.bulk_create(schedules_created)
            print("Timetable generation completed successfully!")
        except Exception as e:
            print(f"Error during bulk create: {e}")
            # Fallback: create schedules one by one
            for schedule in schedules_created:
                try:
                    schedule.save()
                except Exception as e2:
                    print(f"Error saving schedule for {schedule.employee.name} on {schedule.date}: {e2}")
        
        self.print_department_schedules(inbound_employees, outbound_employees)
        return timetable

    def generate_employee_schedules(self, employee, start_date=None, end_date=None):
        """Generate schedules for a specific employee (for new employees added later)"""
        timetable = Timetable.objects.get(month=self.month, year=self.year)
        
        # Get all dates in the month
        _, num_days = calendar.monthrange(self.year, self.month)
        
        # Determine date range
        if start_date is None:
            start_date = date(self.year, self.month, 1)
        if end_date is None:
            end_date = date(self.year, self.month, num_days)
        
        # Adjust start_date based on employee's start date
        employee_start_date = employee.get_effective_start_date()
        if employee_start_date > start_date:
            start_date = employee_start_date
        
        # If employee starts after the month ends, no schedules needed
        if start_date > end_date:
            return []
        
        schedules = []
        current_date = start_date
        
        while current_date <= end_date:
            # Skip if schedule already exists
            existing_schedule = DailySchedule.objects.filter(
                timetable=timetable,
                employee=employee,
                date=current_date
            ).first()
            
            if existing_schedule:
                current_date += timedelta(days=1)
                continue
            
            # Get department-specific shift
            if employee.department == 'inbound':
                start_time = self.get_inbound_shift(employee, current_date)
            else:  # outbound
                start_time = self.get_outbound_shift(employee, current_date)
            
            # If no shift assigned, mark as off
            if start_time is None:
                schedule = DailySchedule(
                    timetable=timetable,
                    employee=employee,
                    date=current_date,
                    start_time=time(0, 0),
                    end_time=time(0, 0),
                    lunch_time=time(0, 0),
                    is_off=True,
                    is_auto_generated=True
                )
            else:
                end_time = self.calculate_end_time(start_time, employee.department)
                lunch_time = self.calculate_lunch_time(start_time)
                
                # Check if employee has time off
                time_off = TimeOff.objects.filter(
                    employee=employee,
                    start_date__lte=current_date,
                    end_date__gte=current_date
                ).exists()
                
                schedule = DailySchedule(
                    timetable=timetable,
                    employee=employee,
                    date=current_date,
                    start_time=start_time,
                    end_time=end_time,
                    lunch_time=lunch_time,
                    is_off=time_off,
                    is_auto_generated=True
                )
            
            schedules.append(schedule)
            current_date += timedelta(days=1)
        
        # Save all schedules
        if schedules:
            DailySchedule.objects.bulk_create(schedules)
            print(f"Generated {len(schedules)} schedules for new employee {employee.name}")
        
        return schedules
    
    def print_department_schedules(self, inbound_employees, outbound_employees):
        """Print sample schedules for both departments with weekly analysis"""
        print("\n" + "="*60)
        print("DEPARTMENT SCHEDULES SUMMARY (WITH WEEKLY ROTATION)")
        print("="*60)
        
        # Print weekly analysis
        print(f"\nWEEKLY ANALYSIS:")
        for week in self.weeks:
            print(f"Week {week['week_index'] + 1}: {week['start_date'].strftime('%b %d')} - {week['end_date'].strftime('%b %d')}")
        
        # Sample days (first 3 weeks)
        sample_days = sorted(self.work_days + self.sundays)[:21]
        
        print(f"\nINBOUND DEPARTMENT (Weekly Rotation - 2 at 8AM, rest distributed):")
        for employee in inbound_employees[:3]:  # Show first 3 employees as sample
            print(f"\n{employee.name}:")
            schedules = DailySchedule.objects.filter(
                timetable__month=self.month,
                timetable__year=self.year,
                employee=employee,
                date__in=sample_days
            ).order_by('date')
            
            current_week = None
            for schedule in schedules:
                week_number = self.get_week_number(schedule.date)
                if week_number != current_week:
                    current_week = week_number
                    print(f"  Week {week_number + 1}:")
                
                day_name = schedule.date.strftime('%a')
                if schedule.is_off:
                    if day_name == 'Sat':
                        status = "OFF (Working Sunday)"
                    elif day_name == 'Sun':
                        status = "OFF (Working Saturday)"
                    else:
                        status = "OFF"
                else:
                    status = f"{schedule.start_time.strftime('%H:%M')}-{schedule.end_time.strftime('%H:%M')}"
                print(f"    {schedule.date.strftime('%a %Y-%m-%d')}: {status}")
        
        print(f"\nOUTBOUND DEPARTMENT (Weekly Balanced 8-5 / 9-6):")
        for employee in outbound_employees[:3]:  # Show first 3 employees as sample
            print(f"\n{employee.name}:")
            schedules = DailySchedule.objects.filter(
                timetable__month=self.month,
                timetable__year=self.year,
                employee=employee,
                date__in=sample_days
            ).order_by('date')
            
            current_week = None
            for schedule in schedules:
                week_number = self.get_week_number(schedule.date)
                if week_number != current_week:
                    current_week = week_number
                    print(f"  Week {week_number + 1}:")
                
                day_name = schedule.date.strftime('%a')
                if schedule.is_off:
                    if day_name == 'Sun':
                        status = "OFF (No Sunday work)"
                    else:
                        status = "OFF"
                else:
                    status = f"{schedule.start_time.strftime('%H:%M')}-{schedule.end_time.strftime('%H:%M')}"
                print(f"    {schedule.date.strftime('%a %Y-%m-%d')}: {status}")
        
        # Print weekly shift distribution for outbound
        print(f"\nOUTBOUND WEEKLY SHIFT DISTRIBUTION ANALYSIS:")
        for week in self.weeks:
            week_days = [day for day in sample_days if week['start_date'] <= day <= week['end_date'] and day.weekday() < 6]
            if not week_days:
                continue
            
            # Take first weekday of the week for analysis
            analysis_day = week_days[0]
            
            eight_am_count = DailySchedule.objects.filter(
                timetable__month=self.month,
                timetable__year=self.year,
                date=analysis_day,
                employee__department='outbound',
                start_time=time(8, 0),
                is_off=False
            ).count()
            
            nine_am_count = DailySchedule.objects.filter(
                timetable__month=self.month,
                timetable__year=self.year,
                date=analysis_day,
                employee__department='outbound',
                start_time=time(9, 0),
                is_off=False
            ).count()
            
            total_outbound = len(outbound_employees)
            week_type = "EVEN" if total_outbound % 2 == 0 else "ODD"
            
            print(f"  Week {week['week_index'] + 1} ({week_type}): 8AM-5PM: {eight_am_count}, 9AM-6PM: {nine_am_count}")

class FoodPickupScheduler:
    def __init__(self, timetable):
        self.timetable = timetable
    
    def generate_food_pickup_schedules(self, max_people_per_day=2):
        """Generate food pickup schedules for the timetable"""
        work_days = set(
            DailySchedule.objects.filter(
                timetable=self.timetable
            ).values_list('date', flat=True)
        )
        
        food_schedules_created = []
        
        for work_date in work_days:
            food_schedule, created = FoodPickupSchedule.objects.get_or_create(
                timetable=self.timetable,
                date=work_date,
                defaults={'max_people': max_people_per_day}
            )
            
            if created:
                food_schedules_created.append(food_schedule)
        
        return food_schedules_created
    
    def assign_food_pickup_duties(self):
        """Assign employees to food pickup duties (mix of both departments)"""
        FoodPickupAssignment.objects.filter(
            food_pickup__timetable=self.timetable
        ).delete()
        
        work_days = FoodPickupSchedule.objects.filter(timetable=self.timetable)
        all_employees = list(Employee.objects.filter(is_active=True))
        
        if not all_employees or not work_days:
            return 0
        
        assignments = []
        
        for food_schedule in work_days:
            available_employees = all_employees.copy()
            random.shuffle(available_employees)
            
            for i in range(min(food_schedule.max_people, len(available_employees))):
                assignment = FoodPickupAssignment(
                    food_pickup=food_schedule,
                    employee=available_employees[i]
                )
                assignments.append(assignment)
        
        FoodPickupAssignment.objects.bulk_create(assignments)
        return len(assignments)

    def add_new_employee_to_food_pickup(self, employee):
        """Add new employee to food pickup rotation"""
        work_days = FoodPickupSchedule.objects.filter(timetable=self.timetable)
        
        if not work_days:
            return 0
        
        assignments = []
        
        for food_schedule in work_days:
            # Check if this food pickup needs more people
            current_assignments = FoodPickupAssignment.objects.filter(food_pickup=food_schedule).count()
            if current_assignments < food_schedule.max_people:
                # Check if employee is already assigned
                existing_assignment = FoodPickupAssignment.objects.filter(
                    food_pickup=food_schedule,
                    employee=employee
                ).exists()
                
                if not existing_assignment:
                    assignment = FoodPickupAssignment(
                        food_pickup=food_schedule,
                        employee=employee
                    )
                    assignments.append(assignment)
        
        if assignments:
            FoodPickupAssignment.objects.bulk_create(assignments)
            print(f"Added {employee.name} to {len(assignments)} food pickup assignments")
        
        return len(assignments)

def generate_monthly_timetable(month, year):
    """Convenience function to generate complete monthly timetable"""
    generator = TimetableGenerator(month, year)
    timetable = generator.generate_timetable()
    
    # Generate food pickup schedules
    food_scheduler = FoodPickupScheduler(timetable)
    food_scheduler.generate_food_pickup_schedules()
    food_scheduler.assign_food_pickup_duties()
    
    return timetable

def add_employee_to_existing_timetables(employee):
    """Add a new employee to all existing timetables from their start date"""
    employee_start_date = employee.get_effective_start_date()
    
    # Find all active timetables that include or are after the employee's start date
    relevant_timetables = Timetable.objects.filter(is_active=True)
    
    added_schedules = []
    
    for timetable in relevant_timetables:
        # Check if timetable month includes or is after employee start date
        month_start = date(timetable.year, timetable.month, 1)
        _, num_days = calendar.monthrange(timetable.year, timetable.month)
        month_end = date(timetable.year, timetable.month, num_days)
        
        # Skip if employee starts after this month
        if employee_start_date > month_end:
            continue
        
        # Generate schedules for this employee
        generator = TimetableGenerator(timetable.month, timetable.year)
        schedules = generator.generate_employee_schedules(
            employee, 
            start_date=max(employee_start_date, month_start),
            end_date=month_end
        )
        
        added_schedules.extend(schedules)
        
        # Add to food pickup duties
        food_scheduler = FoodPickupScheduler(timetable)
        food_scheduler.add_new_employee_to_food_pickup(employee)
    
    print(f"Added {len(added_schedules)} total schedules for new employee {employee.name}")
    return added_schedules