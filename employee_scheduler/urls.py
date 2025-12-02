from django.contrib import admin
from django.urls import path, include
from django.shortcuts import redirect

def redirect_to_admin(request):
    return redirect('/admin/')

urlpatterns = [
    path('', redirect_to_admin, name='home'),
    path('admin/', admin.site.urls),
    path('', include('timetable.urls')),  
]