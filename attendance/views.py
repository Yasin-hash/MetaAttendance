from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from django.utils import timezone
from django.http import HttpResponseRedirect, HttpResponseBadRequest
from django.urls import reverse
from django.contrib.auth.models import User
from django.db.models import Count, Q
from django.utils.translation import gettext as _
from django.conf import settings
from django.contrib import admin
from django.contrib.admin.filters import SimpleListFilter
from geopy.distance import geodesic
import requests
import ipaddress

from .models import Student, Teacher, Attendance, Faculty, Profile
from .forms import UserForm, ProfileForm
from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import json
from .models import Student, Attendance
from datetime import datetime, time
from geopy.distance import geodesic

COLLEGE_LOCATION = (52.5200, 13.4050)  # Replace with your college's coordinates
def attendance_by_hour(request):
    # Assuming you are querying attendance records
    attendances = Attendance.objects.all()  # Get all attendance records
    
    attendance_by_hour = {}
    for attendance in attendances:
        # Access the instance attribute correctly
        hour = timezone.localtime(attendance.time).hour  
        
        if hour not in attendance_by_hour:
            attendance_by_hour[hour] = 0  # Initialize the count
        attendance_by_hour[hour] += 1  # Increment the count for that hour
    
    # Add your logic for rendering the response
    return render(request, 'your_template.html', {'attendance_by_hour': attendance_by_hour})
@csrf_exempt
def update_location(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        latitude = data.get('latitude')
        longitude = data.get('longitude')
        
        if request.user.is_authenticated:
            student = Student.objects.get(user=request.user)
            student.latitude = latitude
            student.longitude = longitude
            student.save()
            
            # Calculate distance
            student_location = (latitude, longitude)
            distance = geodesic(student_location, COLLEGE_LOCATION).meters
            
            # Determine status
            now = datetime.now().time()
            if distance <= 150:
                if now <= time(10, 0):
                    status = 'present'
                else:
                    status = 'late'
            else:
                status = 'absent'
            
            # Create attendance record
            Attendance.objects.update_or_create(
                user=request.user,
                date=datetime.now().date(),
                defaults={'status': status}
            )
            
            return JsonResponse({'status': 'success', 'attendance_status': status})
    
    return JsonResponse({'status': 'error'}, status=400)

def attendance_view(request):
    if request.user.is_authenticated:
        student = Student.objects.get(user=request.user)
        attendance_records = Attendance.objects.filter(user=request.user).order_by('-date')
        return render(request, 'attendance.html', {'student': student, 'attendance_records': attendance_records})
    return JsonResponse({'status': 'error'}, status=401)


def all_teachers(request):
    teachers = Teacher.objects.all()  # Adjust based on your logic
    return render(request, 'attendance/all_teachers.html', {'teachers': teachers})

# Helper function to calculate distance using geodesic


# Attendance for a specific faculty
@login_required
def faculty_attendance(request, faculty_id):
    faculty = get_object_or_404(Faculty, id=faculty_id)
    students = Student.objects.filter(faculty=faculty)

    attendance_stats = {}
    for student in students:
        stats = {
            'present': Attendance.objects.filter(user=student.user, status='present').count(),
            'late': Attendance.objects.filter(user=student.user, status='late').count(),
            'absent': Attendance.objects.filter(user=student.user, status='absent').count(),
        }
        attendance_stats[student] = stats

    context = {
        'faculty': faculty,
        'attendance_stats': attendance_stats,
        'students': students,
    }
    return render(request, 'attendance/faculty_attendance.html', context)


# Leaderboard view
def leaderboard(request):
    student_leaderboard = Student.objects.annotate(
        absent_days=Count('user__attendance', filter=Q(user__attendance__status='absent'))
    ).order_by('-absent_days')

    faculty_filter = request.GET.get('faculty', None)
    student_filter = request.GET.get('student', None)

    if faculty_filter:
        student_leaderboard = student_leaderboard.filter(faculty__id=faculty_filter)

    if student_filter:
        student_leaderboard = student_leaderboard.filter(id=student_filter)

    faculties = Faculty.objects.all()
    students = Student.objects.all()

    context = {
        'student_leaderboard': student_leaderboard,
        'faculties': faculties,
        'students': students,
    }
    return render(request, 'attendance/leaderboard.html', context)

# Mark attendance view


# Home view for students and teachers
@login_required
def home(request):
    user = request.user

    if hasattr(user, 'student'):
        attendance_streak = user.student.get_attendance_streak()

        male_students = Student.objects.filter(profile__gender='male').annotate(
            present_days=Count('user__attendance', filter=Q(user__attendance__status='present'))
        ).order_by('-present_days')

        female_students = Student.objects.filter(profile__gender='female').annotate(
            present_days=Count('user__attendance', filter=Q(user__attendance__status='present'))
        ).order_by('-present_days')

        faculty_attendance = Faculty.objects.annotate(
            present_days=Count('students__user__attendance', filter=Q(students__user__attendance__status='present'))
        ).order_by('-present_days')

        context = {
            'attendance_streak': attendance_streak,
            'male_students': male_students,
            'female_students': female_students,
            'faculty_attendance': faculty_attendance,
        }
        return render(request, 'attendance/student_home.html', context)

    elif hasattr(user, 'teacher'):
        student_leaderboard = Student.objects.annotate(
            present_days=Count('user__attendance', filter=Q(user__attendance__status='present'))
        ).order_by('-present_days')

        faculty_attendance = Faculty.objects.annotate(
            present_days=Count('students__user__attendance', filter=Q(students__user__attendance__status='present'))
        ).order_by('-present_days')

        context = {
            'student_leaderboard': student_leaderboard,
            'faculty_attendance': faculty_attendance,
        }
        return render(request, 'attendance/teacher_home.html', context)

    elif user.is_staff:
        return redirect('admin_dashboard')

    else:
        return render(request, 'attendance/error.html', {'message': 'User type not recognized'})

# Admin dashboard view
@login_required
def admin_dashboard(request):
    if not request.user.is_staff:
        return redirect('home')

    total_students = Student.objects.count()
    total_teachers = Teacher.objects.count()
    total_faculties = Faculty.objects.count()

    teachers = Teacher.objects.all().annotate(
        total_days=Count('user__attendance', distinct=True),
        present_days=Count('user__attendance', filter=Q(user__attendance__status='present')),
        absent_days=Count('user__attendance', filter=Q(user__attendance__status='absent')),
    )

    faculty_attendance = Faculty.objects.annotate(
        present_days=Count('students__user__attendance', filter=Q(students__user__attendance__status='present'))
    ).order_by('-present_days')

    context = {
        'total_students': total_students,
        'total_teachers': total_teachers,
        'total_faculties': total_faculties,
        'teachers': teachers,
        'faculties': Faculty.objects.all(),
        'faculty_attendance': faculty_attendance,
    }
    return render(request, 'attendance/admin_dashboard.html', context)

# Profile management view
@login_required
def profile(request):
    user = request.user
    profile = getattr(user, 'profile', None)

    if request.method == 'POST':
        user_form = UserForm(request.POST, instance=user)
        profile_form = ProfileForm(request.POST, request.FILES, instance=profile)

        if user_form.is_valid() and profile_form.is_valid():
            user_form.save()
            profile_form.save()
            messages.success(request, 'Your profile was successfully updated!')
            return redirect('profile')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        user_form = UserForm(instance=user)
        profile_form = ProfileForm(instance=profile)

    context = {
        'user_form': user_form,
        'profile_form': profile_form
    }
    return render(request, 'attendance/profile.html', context)

# Login view
def login_view(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            return redirect('home')
        else:
            messages.error(request, 'Invalid username or password')
    return render(request, 'attendance/login.html')

# Add Student view
@login_required
def add_student(request):
    if not request.user.is_staff:
        return redirect('home')

    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        faculty_id = request.POST.get('faculty')

        if not username or not password or not faculty_id:
            messages.error(request, 'All fields are required.')
            return redirect('add_student')

        try:
            if User.objects.filter(username=username).exists():
                messages.error(request, 'Username already exists.')
                return redirect('add_student')

            user = User.objects.create_user(username=username, password=password)
            faculty = get_object_or_404(Faculty, id=faculty_id)
            Student.objects.create(user=user, faculty=faculty)
            messages.success(request, 'Student added successfully.')
            return redirect('admin_dashboard')
        except Exception as e:
            messages.error(request, f'Error adding student: {e}')
            return redirect('add_student')

    faculties = Faculty.objects.all()
    context = {'faculties': faculties}
    return render(request, 'attendance/add_student.html', context)

# Edit Student view
@login_required
def edit_student(request, student_id):
    if not request.user.is_staff:
        return redirect('home')

    student = get_object_or_404(Student, id=student_id)

    if request.method == 'POST':
        username = request.POST.get('username')
        faculty_id = request.POST.get('faculty')

        if not username or not faculty_id:
            messages.error(request, 'All fields are required.')
            return redirect('edit_student', student_id=student_id)

        try:
            user = student.user
            if user.username != username and User.objects.filter(username=username).exists():
                messages.error(request, 'Username already exists.')
                return redirect('edit_student', student_id=student_id)

            user.username = username
            user.save()

            faculty = get_object_or_404(Faculty, id=faculty_id)
            student.faculty = faculty
            student.save()

            messages.success(request, 'Student updated successfully.')
            return redirect('admin_dashboard')
        except Exception as e:
            messages.error(request, f'Error updating student: {e}')
            return redirect('edit_student', student_id=student_id)

    faculties = Faculty.objects.all()
    context = {
        'student': student,
        'faculties': faculties,
    }
    return render(request, 'attendance/edit_student.html', context)

# Delete Student view
@login_required
def delete_student(request, student_id):
    if not request.user.is_staff:
        return redirect('home')

    student = get_object_or_404(Student, id=student_id)

    if request.method == 'POST':
        try:
            user = student.user
            student.delete()
            user.delete()
            messages.success(request, 'Student deleted successfully.')
            return redirect('admin_dashboard')
        except Exception as e:
            messages.error(request, f'Error deleting student: {e}')
            return redirect('admin_dashboard')

    context = {'student': student}
    return render(request, 'attendance/delete_student.html', context)

# Add Teacher view
@login_required
def add_teacher(request):
    if not request.user.is_staff:
        return redirect('home')

    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        faculty_id = request.POST.get('faculty')  # Assuming teachers are assigned to a faculty

        if not username or not password:
            messages.error(request, 'Username and password are required.')
            return redirect('add_teacher')

        try:
            if User.objects.filter(username=username).exists():
                messages.error(request, 'Username already exists.')
                return redirect('add_teacher')

            user = User.objects.create_user(username=username, password=password)
            teacher = Teacher.objects.create(user=user)

            if faculty_id:
                faculty = get_object_or_404(Faculty, id=faculty_id)
                teacher.faculty = faculty
                teacher.save()

            messages.success(request, 'Teacher added successfully.')
            return redirect('admin_dashboard')
        except Exception as e:
            messages.error(request, f'Error adding teacher: {e}')
            return redirect('add_teacher')

    faculties = Faculty.objects.all()
    context = {'faculties': faculties}
    return render(request, 'attendance/add_teacher.html', context)

# Edit Teacher view
@login_required
def edit_teacher(request, teacher_id):
    if not request.user.is_staff:
        return redirect('home')

    teacher = get_object_or_404(Teacher, id=teacher_id)

    if request.method == 'POST':
        username = request.POST.get('username')
        faculty_id = request.POST.get('faculty')

        if not username:
            messages.error(request, 'Username is required.')
            return redirect('edit_teacher', teacher_id=teacher_id)

        try:
            user = teacher.user
            if user.username != username and User.objects.filter(username=username).exists():
                messages.error(request, 'Username already exists.')
                return redirect('edit_teacher', teacher_id=teacher_id)

            user.username = username
            user.save()

            if faculty_id:
                faculty = get_object_or_404(Faculty, id=faculty_id)
                teacher.faculty = faculty
                teacher.save()

            messages.success(request, 'Teacher updated successfully.')
            return redirect('admin_dashboard')
        except Exception as e:
            messages.error(request, f'Error updating teacher: {e}')
            return redirect('edit_teacher', teacher_id=teacher_id)

    faculties = Faculty.objects.all()
    context = {
        'teacher': teacher,
        'faculties': faculties,
    }
    return render(request, 'attendance/edit_teacher.html', context)

# Delete Teacher view
@login_required
def delete_teacher(request, teacher_id):
    if not request.user.is_staff:
        return redirect('home')

    teacher = get_object_or_404(Teacher, id=teacher_id)

    if request.method == 'POST':
        try:
            user = teacher.user
            teacher.delete()
            user.delete()
            messages.success(request, 'Teacher deleted successfully.')
            return redirect('admin_dashboard')
        except Exception as e:
            messages.error(request, f'Error deleting teacher: {e}')
            return redirect('admin_dashboard')

    context = {'teacher': teacher}
    return render(request, 'attendance/delete_teacher.html', context)

# Add Faculty view
@login_required
def add_faculty(request):
    if not request.user.is_staff:
        return redirect('home')

    if request.method == 'POST':
        name = request.POST.get('name')

        if not name:
            messages.error(request, 'Faculty name is required.')
            return redirect('add_faculty')

        try:
            if Faculty.objects.filter(name__iexact=name).exists():
                messages.error(request, 'Faculty with this name already exists.')
                return redirect('add_faculty')

            Faculty.objects.create(name=name)
            messages.success(request, 'Faculty added successfully.')
            return redirect('admin_dashboard')
        except Exception as e:
            messages.error(request, f'Error adding faculty: {e}')
            return redirect('add_faculty')

    return render(request, 'attendance/add_faculty.html')

# Edit Faculty view
@login_required
def edit_faculty(request, faculty_id):
    if not request.user.is_staff:
        return redirect('home')

    faculty = get_object_or_404(Faculty, id=faculty_id)

    if request.method == 'POST':
        name = request.POST.get('name')

        if not name:
            messages.error(request, 'Faculty name is required.')
            return redirect('edit_faculty', faculty_id=faculty_id)

        try:
            if Faculty.objects.filter(name__iexact=name).exclude(id=faculty_id).exists():
                messages.error(request, 'Another faculty with this name already exists.')
                return redirect('edit_faculty', faculty_id=faculty_id)

            faculty.name = name
            faculty.save()
            messages.success(request, 'Faculty updated successfully.')
            return redirect('admin_dashboard')
        except Exception as e:
            messages.error(request, f'Error updating faculty: {e}')
            return redirect('edit_faculty', faculty_id=faculty_id)

    context = {'faculty': faculty}
    return render(request, 'attendance/edit_faculty.html', context)

# Delete Faculty view
@login_required
def delete_faculty(request, faculty_id):
    if not request.user.is_staff:
        return redirect('home')

    faculty = get_object_or_404(Faculty, id=faculty_id)

    if request.method == 'POST':
        try:
            faculty.delete()
            messages.success(request, 'Faculty deleted successfully.')
            return redirect('admin_dashboard')
        except Exception as e:
            messages.error(request, f'Error deleting faculty: {e}')
            return redirect('admin_dashboard')

    context = {'faculty': faculty}
    return render(request, 'attendance/delete_faculty.html', context)

# Attendance by hour view


# Filter attendance view
@login_required
def filter_attendance(request):
    gender = request.GET.get('gender')
    faculty_id = request.GET.get('faculty')

    queryset = Attendance.objects.all()

    if gender:
        queryset = queryset.filter(user__student__profile__gender=gender)

    if faculty_id:
        queryset = queryset.filter(user__student__faculty_id=faculty_id)

    context = {
        'attendance_records': queryset,
        'faculties': Faculty.objects.all(),
        'selected_gender': gender,
        'selected_faculty': faculty_id,
    }

    return render(request, 'attendance/filter_attendance.html', context)

# Delete Attendance record view
@login_required
def delete_attendance(request, attendance_id):
    if not request.user.is_staff:
        messages.error(request, "You do not have permission to delete attendance records.")
        return redirect('home')

    attendance_record = get_object_or_404(Attendance, id=attendance_id)

    if request.method == 'POST':
        try:
            attendance_record.delete()
            messages.success(request, 'Attendance record deleted successfully.')
            return redirect('admin_dashboard')
        except Exception as e:
            messages.error(request, f"Error deleting attendance record: {e}")
            return redirect('admin_dashboard')

    context = {'attendance_record': attendance_record}
    return render(request, 'attendance/delete_attendance.html', context)

# Set language view
@login_required
def set_language_view(request):
    next_url = request.POST.get('next', request.GET.get('next', '/'))
    language = request.POST.get('language')

    if language:
        response = HttpResponseRedirect(next_url)
        response.set_cookie(
            key=settings.LANGUAGE_COOKIE_NAME,
            value=language,
            max_age=settings.LANGUAGE_COOKIE_AGE,
            path=settings.LANGUAGE_COOKIE_PATH,
            domain=settings.LANGUAGE_COOKIE_DOMAIN,
            secure=settings.LANGUAGE_COOKIE_SECURE,
            httponly=settings.LANGUAGE_COOKIE_HTTPONLY,
            samesite=settings.LANGUAGE_COOKIE_SAMESITE,
        )
        request.session[settings.LANGUAGE_SESSION_KEY] = language
        return response

    return HttpResponseBadRequest()
