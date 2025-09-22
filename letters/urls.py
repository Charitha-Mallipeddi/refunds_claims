from django.urls import path
from . import views
app_name = "letters"
urlpatterns = [
    path("", views.index, name="index"),
    path("send-email/", views.send_email, name="send_email"),
    path("preview-email/", views.preview_email, name="preview_email"),
    path("download-letter-pdf/", views.download_letter_pdf, name="download_letter_pdf"),
    path("api/letters/generate", views.api_generate_letter, name="api_generate_letter"),
]
