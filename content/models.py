from datetime import date
from django.db import models
from django.conf import settings


OPTION_TYPES = [
    ('category', 'Category'),
    ('assist', 'Assist (Mojo)'),
    ('item_type', 'Item Type'),
    ('cp', 'C-P (Camera Person)'),
    ('reporter', 'Reporter'),
    ('editor', 'Editor'),
    ('panel', 'Panel'),
    ('status', 'Status'),
]


class LogOption(models.Model):
    """সব dropdown option — admin panel থেকে add/edit হবে"""
    field_type = models.CharField(max_length=20, choices=OPTION_TYPES)
    name = models.CharField(max_length=100)

    class Meta:
        ordering = ['field_type', 'name']
        unique_together = ('field_type', 'name')

    def __str__(self):
        return self.name


class ContentLog(models.Model):
    content_title = models.TextField('Content Title', blank=True)
    category = models.ForeignKey(LogOption, blank=True, null=True, on_delete=models.SET_NULL,
                                 related_name='as_category',
                                 limit_choices_to={'field_type': 'category'})
    assist = models.ForeignKey(LogOption, blank=True, null=True, on_delete=models.SET_NULL,
                               related_name='as_assist',
                               limit_choices_to={'field_type': 'assist'})
    item_type = models.ForeignKey(LogOption, blank=True, null=True, on_delete=models.SET_NULL,
                                  related_name='as_item_type',
                                  limit_choices_to={'field_type': 'item_type'})
    cp = models.ForeignKey(LogOption, blank=True, null=True, on_delete=models.SET_NULL,
                           related_name='as_cp',
                           limit_choices_to={'field_type': 'cp'})
    reporter = models.ForeignKey(LogOption, blank=True, null=True, on_delete=models.SET_NULL,
                                 related_name='as_reporter',
                                 limit_choices_to={'field_type': 'reporter'})
    editor = models.ForeignKey(LogOption, blank=True, null=True, on_delete=models.SET_NULL,
                               related_name='as_editor',
                               limit_choices_to={'field_type': 'editor'})
    panel = models.ForeignKey(LogOption, blank=True, null=True, on_delete=models.SET_NULL,
                              related_name='as_panel',
                              limit_choices_to={'field_type': 'panel'})
    status = models.ForeignKey(LogOption, blank=True, null=True, on_delete=models.SET_NULL,
                               related_name='as_status',
                               limit_choices_to={'field_type': 'status'})
    log_date = models.DateField(blank=True, null=True)
    log_time = models.TimeField(auto_now_add=True)
    remark = models.TextField(blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                   null=True, blank=True)

    class Meta:
        ordering = ['log_date', 'log_time']

    def __str__(self):
        return f'{self.log_date} — {self.content_title[:40] or "(no title)"}'