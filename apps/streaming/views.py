from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from django.conf import settings
from datetime import datetime, timedelta
import os
from .models import Stream, MediaFile, StreamLog
from apps.accounts.models import YouTubeAccount
from apps.payments.models import Subscription
from .stream_manager import StreamManager
import json
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt

# NEW: Helper function to get user's total storage used
def get_user_storage_usage(user):
    """Calculate total storage used by user in bytes"""
    total_size = 0
    media_files = MediaFile.objects.filter(user=user)
    for media in media_files:
        if media.file:
            try:
                total_size += media.file.size
            except:
                pass
    return total_size

# NEW: Helper function to check if user has storage available
def has_storage_available(user, file_size):
    """Check if user has storage available for new file"""
    subscription = Subscription.objects.filter(
        user=user,
        is_active=True,
        status='active'
    ).first()

    if not subscription:
        return False, 0, 0

    current_usage = get_user_storage_usage(user)
    available_storage = subscription.storage_limit - current_usage

    if file_size > available_storage:
        return False, current_usage, subscription.storage_limit

    return True, current_usage, subscription.storage_limit

# NEW: Convert bytes to readable format
def format_bytes(bytes_size):
    """Convert bytes to human readable format"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes_size < 1024:
            return f"{bytes_size:.2f} {unit}"
        bytes_size /= 1024
    return f"{bytes_size:.2f} TB"

@login_required
@require_POST
def media_reorder_view(request):
    try:
        data = json.loads(request.body)
        order = data.get('order', [])
        for item in order:
            media_id = item['id']
            sequence = item['sequence']
            MediaFile.objects.filter(id=media_id, user=request.user).update(sequence=sequence)
        return JsonResponse({'status': 'success'})
    except Exception as e:
        print("Error reordering media:", e)
        return JsonResponse({'status': 'error'}, status=400)

@login_required
def connect_youtube(request):
    """Initiate YouTube OAuth flow"""
    flow = Flow.from_client_config(
        {
            "web": {
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [settings.GOOGLE_REDIRECT_URI],
            }
        },
        scopes=settings.GOOGLE_SCOPES,
        redirect_uri=settings.GOOGLE_REDIRECT_URI
    )

    authorization_url, state = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true',
        prompt='consent'
    )

    request.session['oauth_state'] = state
    return redirect(authorization_url)

@login_required
def oauth_callback(request):
    """Handle YouTube OAuth callback"""
    try:
        state = request.session.get('oauth_state')
        flow = Flow.from_client_config(
            {
                "web": {
                    "client_id": settings.GOOGLE_CLIENT_ID,
                    "client_secret": settings.GOOGLE_CLIENT_SECRET,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "redirect_uris": [settings.GOOGLE_REDIRECT_URI],
                }
            },
            scopes=settings.GOOGLE_SCOPES,
            state=state,
            redirect_uri=settings.GOOGLE_REDIRECT_URI
        )

        flow.fetch_token(authorization_response=request.build_absolute_uri())
        credentials = flow.credentials

        # Get channel info
        youtube = build('youtube', 'v3', credentials=credentials)
        channel_response = youtube.channels().list(
            part='snippet,contentDetails',
            mine=True
        ).execute()

        if channel_response['items']:
            channel = channel_response['items'][0]
            channel_id = channel['id']
            channel_title = channel['snippet']['title']

            # Save or update YouTube account
            youtube_account, created = YouTubeAccount.objects.update_or_create(
                user=request.user,
                channel_id=channel_id,
                defaults={
                    'channel_title': channel_title,
                    'access_token': credentials.token,
                    'refresh_token': credentials.refresh_token,
                    'token_expiry': credentials.expiry,
                    'is_active': True
                }
            )
            messages.success(request, f'Successfully connected YouTube channel: {channel_title}')
        else:
            messages.error(request, 'No YouTube channel found for this account')
    except Exception as e:
        messages.error(request, f'Failed to connect YouTube: {str(e)}')

    return redirect('dashboard')

@login_required
def stream_list(request):
    """List all user streams"""
    streams = Stream.objects.filter(user=request.user).order_by('-created_at')
    return render(request, 'streaming/stream_list.html', {'streams': streams})

@login_required
def stream_create(request):
    """Create a new stream"""
    # Check subscription
    subscription = Subscription.objects.filter(
        user=request.user,
        is_active=True
    ).first()

    if not subscription:
        messages.error(request, 'You need an active subscription to create streams')
        return redirect('subscribe')

    # STRONG LIMIT CHECK
    forbidden_statuses = ['running','stopped', 'starting', 'scheduled']
    active_streams = Stream.objects.filter(
        user=request.user,
        status__in=forbidden_statuses
    ).count()

    if active_streams >= subscription.max_streams:
        messages.error(request, f'You have reached your stream limit ({subscription.max_streams} streams). '
                      f'This includes all running, starting, and scheduled streams.')
        return redirect('stream_list')

    # Check YouTube connection
    youtube_accounts = YouTubeAccount.objects.filter(user=request.user, is_active=True)
    if not youtube_accounts.exists():
        messages.error(request, 'Please connect your YouTube account first')
        return redirect('connect_youtube')

    if request.method == 'POST':
        title = request.POST.get('title')
        description = request.POST.get('description', '')
        youtube_account_id = request.POST.get('youtube_account')
        media_file_ids = request.POST.getlist('media_files')
        loop_enabled = request.POST.get('loop_enabled') == 'on'
        thumbnail = request.FILES.get('thumbnail')

        try:
            youtube_account = YouTubeAccount.objects.get(id=youtube_account_id, user=request.user)

            # Create stream with thumbnail
            stream = Stream.objects.create(
                user=request.user,
                youtube_account=youtube_account,
                title=title,
                description=description,
                loop_enabled=loop_enabled,
                thumbnail=thumbnail
            )

            # Add media files
            if media_file_ids:
                media_files = MediaFile.objects.filter(id__in=media_file_ids, user=request.user)
                stream.media_files.set(media_files)

            messages.success(request, 'Stream created successfully!')
            return redirect('stream_detail', stream_id=stream.id)

        except Exception as e:
            messages.error(request, f'Failed to create stream: {str(e)}')

    media_files = MediaFile.objects.filter(user=request.user)

    # NEW: Get storage info for context
    current_usage = get_user_storage_usage(request.user)
    available_storage = subscription.storage_limit - current_usage

    context = {
        'youtube_accounts': youtube_accounts,
        'media_files': media_files,
        'storage_usage': format_bytes(current_usage),
        'storage_limit': format_bytes(subscription.storage_limit),
        'storage_available': format_bytes(available_storage),
    }
    return render(request, 'streaming/stream_create.html', context)

@login_required
def stream_detail(request, stream_id):
    """View stream details"""
    stream = get_object_or_404(Stream, id=stream_id, user=request.user)
    logs = stream.logs.all()[:50]
    context = {
        'stream': stream,
        'logs': logs,
    }
    return render(request, 'streaming/stream_detail.html', context)

@login_required
def stream_start(request, stream_id):
    """Start a stream"""
    stream = get_object_or_404(Stream, id=stream_id, user=request.user)

    if stream.status == 'running':
        messages.warning(request, 'Stream is already running')
        return redirect('stream_detail', stream_id=stream.id)

    try:
        stream.status = 'starting'
        stream.save()

        manager = StreamManager(stream)

        # Create YouTube broadcast
        broadcast_id = manager.create_broadcast()
        if not broadcast_id:
            raise Exception("Failed to create YouTube broadcast")

        # Upload thumbnail to YouTube if exists
        if stream.thumbnail:
            try:
                upload_thumbnail_to_youtube(stream, broadcast_id)
                StreamLog.objects.create(
                    stream=stream,
                    level='INFO',
                    message='Thumbnail uploaded to YouTube successfully'
                )
            except Exception as thumb_error:
                StreamLog.objects.create(
                    stream=stream,
                    level='WARNING',
                    message=f'Failed to upload thumbnail: {str(thumb_error)}'
                )

        # Start FFmpeg streaming
        process_id = manager.start_ffmpeg_stream()
        if not process_id:
            raise Exception("Failed to start streaming process")

        StreamLog.objects.create(
            stream=stream,
            level='INFO',
            message='Stream started successfully'
        )
        messages.success(request, 'Stream started successfully!')

    except Exception as e:
        stream.status = 'error'
        stream.error_message = str(e)
        stream.save()
        StreamLog.objects.create(
            stream=stream,
            level='ERROR',
            message=f'Failed to start stream: {str(e)}'
        )
        messages.error(request, f'Failed to start stream: {str(e)}')

    return redirect('stream_detail', stream_id=stream.id)

def upload_thumbnail_to_youtube(stream, video_id):
    """Upload thumbnail to YouTube using the Thumbnails.set API endpoint"""
    youtube_account = stream.youtube_account

    # Build credentials
    credentials = Credentials(
        token=youtube_account.access_token,
        refresh_token=youtube_account.refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=settings.GOOGLE_CLIENT_ID,
        client_secret=settings.GOOGLE_CLIENT_SECRET,
        scopes=settings.GOOGLE_SCOPES
    )

    # Build YouTube service
    youtube = build('youtube', 'v3', credentials=credentials)

    # Upload thumbnail
    thumbnail_path = stream.thumbnail.path
    media = MediaFileUpload(thumbnail_path, mimetype='image/jpeg', resumable=True)

    response = youtube.thumbnails().set(
        videoId=video_id,
        media_body=media
    ).execute()

    return response

@login_required
def stream_stop(request, stream_id):
    """Stop a stream"""
    stream = get_object_or_404(Stream, id=stream_id, user=request.user)

    try:
        stream.status = 'stopping'
        stream.save()

        manager = StreamManager(stream)
        manager.stop_stream()

        StreamLog.objects.create(
            stream=stream,
            level='INFO',
            message='Stream stopped successfully'
        )
        messages.success(request, 'Stream stopped successfully!')

    except Exception as e:
        messages.error(request, f'Failed to stop stream: {str(e)}')

    return redirect('stream_detail', stream_id=stream.id)

@login_required
def stream_delete(request, stream_id):
    """Delete a stream"""
    stream = get_object_or_404(Stream, id=stream_id, user=request.user)

    if stream.status in ['running', 'starting']:
        messages.error(request, 'Cannot delete a running stream. Please stop it first.')
        return redirect('stream_detail', stream_id=stream.id)

    manager = StreamManager(stream)
    manager.stop_stream()

    stream.delete()
    messages.success(request, 'Stream deleted successfully!')
    return redirect('stream_list')

@login_required
def media_upload_view(request):
    """Upload media files with storage limit check"""
    # Get subscription
    subscription = Subscription.objects.filter(
        user=request.user,
        is_active=True,
        status='active'
    ).first()

    if not subscription:
        messages.error(request, 'You need an active subscription to upload media')
        return redirect('subscribe')

    if request.method == 'POST':
        title = request.POST.get('title')
        media_type = request.POST.get('media_type')
        file = request.FILES.get('file')
        thumbnail = request.FILES.get('thumbnail')

        try:
            # NEW: Check storage before upload
            file_size = file.size
            has_storage, current_usage, storage_limit = has_storage_available(request.user, file_size)

            if not has_storage:
                messages.error(
                    request,
                    f'Not enough storage! You have used {format_bytes(current_usage)} out of '
                    f'{format_bytes(storage_limit)} ({subscription.plan_type.title()} plan). '
                    f'Please delete some files or upgrade your plan.'
                )
                return redirect('media_upload')

            # Create media file
            media_file = MediaFile.objects.create(
                user=request.user,
                title=title,
                file=file,
                thumbnail=thumbnail,
                media_type=media_type,
                file_size=file.size
            )

            # Get updated storage info
            new_usage = get_user_storage_usage(request.user)
            new_available = subscription.storage_limit - new_usage

            messages.success(
                request, 
                f'Media file uploaded successfully! '
                f'Storage: {format_bytes(new_usage)} / {format_bytes(subscription.storage_limit)} used. '
                f'({format_bytes(new_available)} available)'
            )
            return redirect('media_list')

        except Exception as e:
            messages.error(request, f'Failed to upload media: {str(e)}')

    # NEW: Get storage info for context
    current_usage = get_user_storage_usage(request.user)
    available_storage = subscription.storage_limit - current_usage

    context = {
        'storage_usage': format_bytes(current_usage),
        'storage_limit': format_bytes(subscription.storage_limit),
        'storage_available': format_bytes(available_storage),
        'storage_percentage': (current_usage / subscription.storage_limit) * 100,
    }

    return render(request, 'streaming/media_upload.html', context)

@login_required
def media_list_view(request):
    """List media files with storage info"""
    media_files = MediaFile.objects.filter(user=request.user)

    # Get subscription
    subscription = Subscription.objects.filter(
        user=request.user,
        is_active=True,
        status='active'
    ).first()

    # Get storage info
    current_usage = get_user_storage_usage(request.user)
    available_storage = 0
    if subscription:
        available_storage = subscription.storage_limit - current_usage

    context = {
        'media_files': media_files,
        'storage_usage': format_bytes(current_usage),
        'storage_limit': format_bytes(subscription.storage_limit) if subscription else 'N/A',
        'storage_available': format_bytes(available_storage),
    }

    return render(request, 'streaming/media_list.html', context)

@login_required
def media_delete_view(request, media_id):
    """Delete media file and free up storage"""
    media = get_object_or_404(MediaFile, id=media_id, user=request.user)

    if request.method == "POST":
        freed_size = media.file.size if media.file else 0

        media.file.delete(save=False)
        if media.thumbnail:
            media.thumbnail.delete(save=False)
        media.delete()

        # Get updated storage info
        subscription = Subscription.objects.filter(
            user=request.user,
            is_active=True,
            status='active'
        ).first()

        if subscription:
            current_usage = get_user_storage_usage(request.user)
            messages.success(
                request, 
                f'Media file deleted successfully. '
                f'Freed {format_bytes(freed_size)} storage. '
                f'Current usage: {format_bytes(current_usage)} / {format_bytes(subscription.storage_limit)}'
            )
        else:
            messages.success(request, "Media file deleted successfully.")

        return redirect('media_list')

    return redirect('media_list')

@login_required
def stream_status_api(request, stream_id):
    """API endpoint to check stream status"""
    stream = get_object_or_404(Stream, id=stream_id, user=request.user)
    data = {
        'status': stream.status,
        'started_at': stream.started_at.isoformat() if stream.started_at else None,
        'error_message': stream.error_message,
    }
    return JsonResponse(data)
