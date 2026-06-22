import os

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'barberia.settings')

try:
    from celery import Celery
except ImportError:
    app = None
else:
    app = Celery('barberia')
    app.config_from_object('django.conf:settings', namespace='CELERY')
    app.autodiscover_tasks()
