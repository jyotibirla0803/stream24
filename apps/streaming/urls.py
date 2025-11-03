from django.urls import path
from . import views

urlpatterns = [
    # YouTube OAuth
    path('connect/', views.connect_youtube, name='connect_youtube'),
    path('oauth2callback/', views.oauth_callback, name='oauth_callback'),
    
    # Streams
    path('streams/', views.stream_list, name='stream_list'),
    path('streams/create/', views.stream_create, name='stream_create'),
    path('streams/<uuid:stream_id>/', views.stream_detail, name='stream_detail'),
    path('streams/<uuid:stream_id>/start/', views.stream_start, name='stream_start'),
    path('streams/<uuid:stream_id>/stop/', views.stream_stop, name='stream_stop'),
    path('streams/<uuid:stream_id>/delete/', views.stream_delete, name='stream_delete'),
    path('streams/<uuid:stream_id>/status/', views.stream_status_api, name='stream_status_api'),
    
    # Media
    path('media/', views.media_list_view, name='media_list'),
    path('media/upload/', views.media_upload_view, name='media_upload'),
    path('media/delete/<int:media_id>/', views.media_delete_view, name='media_delete'),
    path('media/reorder/', views.media_reorder_view, name='media_reorder'),

]
