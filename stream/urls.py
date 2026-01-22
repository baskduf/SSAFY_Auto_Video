from django.urls import path
from . import views

app_name = 'stream'

urlpatterns = [
    path('', views.index, name='index'),
    path('api/validate-url/', views.validate_url, name='validate_url'),
    path('api/video-info/', views.get_video_info, name='video_info'),
]
