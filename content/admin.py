from django.contrib import admin
from .models import LogOption, ContentLog


@admin.register(LogOption)
class LogOptionAdmin(admin.ModelAdmin):
    list_display = ('name', 'field_type')
    list_filter = ('field_type',)
    search_fields = ('name',)


@admin.register(ContentLog)
class ContentLogAdmin(admin.ModelAdmin):
    list_display = ('log_date', 'log_time', 'content_title', 'category',
                    'reporter', 'editor', 'panel', 'status')
    list_filter = ('log_date', 'category', 'status', 'panel', 'reporter')
    search_fields = ('content_title', 'remark')
    date_hierarchy = 'log_date'