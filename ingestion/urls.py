from django.urls import path

from . import views

urlpatterns = [
    path("", views.dashboard_view, name="dashboard"),
    path("upload/", views.upload_view, name="upload"),
    path("submissions/", views.submission_list_view, name="submission_list"),
    path("submissions/<int:pk>/", views.submission_detail_view, name="submission_detail"),
    path("submissions/<int:pk>/status/", views.submission_status_view, name="submission_status"),
    path("submissions/<int:pk>/delete/", views.submission_delete_view, name="submission_delete"),
    path("reports/system-hourly/", views.report_system_hourly_view, name="report_system_hourly"),
    path("reports/plant-generation/", views.report_plant_generation_view, name="report_plant_generation"),
    path("export/system-hourly.csv", views.export_system_hourly_csv, name="export_system_hourly_csv"),
    path("export/plant-generation.xlsx", views.export_plant_generation_xlsx, name="export_plant_generation_xlsx"),
]
