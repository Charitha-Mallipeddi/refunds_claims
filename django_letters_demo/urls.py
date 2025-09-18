from django.contrib import admin
from django.urls import path
from django.conf import settings
from django.conf.urls.static import static
from letters import views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', views.index, name='index'),
    path('letters/pdf', views.generate_pdf, name='generate_pdf'),
    path('letters/email', views.render_email, name='render_email'),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
