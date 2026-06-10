"""
CashSpace URL Configuration
"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

admin.site.site_header = "CashSpace Admin"
admin.site.site_title = "CashSpace"
admin.site.index_title = "Control Panel"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/auth/", include("apps.accounts.urls")),
    path("api/v1/payments/", include("apps.payments.urls")),
    path("api/v1/", include("apps.notifications.urls")),
    path("api/v1/", include("apps.merchants.urls")),
    
    # NEW: Gating app (URL-as-payable-asset)
    path("api/v1/gating/", include("apps.gating.urls")),
    
    # NEW: Creator app (simplified asset sales for individual creators)
    path("api/v1/creator/", include("apps.creator.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)