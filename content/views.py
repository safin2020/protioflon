import csv
import calendar
import os
import io as _io
import json
from datetime import date, datetime, timedelta
from collections import Counter

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.db.models import Q

from employees.models import OfficeSetting
from .models import ContentLog, LogOption
from .forms import ContentLogForm

from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.platypus import (SimpleDocTemplate, Table, TableStyle,
                                Paragraph, Spacer, Image as RLImage)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from PIL import Image as PILImage
from xml.sax.saxutils import escape


# ---------- helpers ----------
def _n(obj, fallback='-'):
    return obj.name if obj else fallback


def _get_filters(request):
    return {
        'mode': request.GET.get('mode', 'daily'),
        'date': request.GET.get('date', ''),
        'month': request.GET.get('month', ''),
        'category': request.GET.get('category', ''),
        'item_type': request.GET.get('item_type', ''),
        'reporter': request.GET.get('reporter', ''),
        'editor': request.GET.get('editor', ''),
        'panel': request.GET.get('panel', ''),
        'status': request.GET.get('status', ''),
    }


def _filtered_logs(fl):
    logs = ContentLog.objects.select_related(
        'category', 'assist', 'item_type', 'cp',
        'reporter', 'editor', 'panel', 'status')

    if fl['mode'] == 'monthly' and fl['month']:
        y, m = map(int, fl['month'].split('-'))
        logs = logs.filter(log_date__year=y, log_date__month=m)
        period = f'{calendar.month_name[m]} {y}'
    else:
        day = datetime.strptime(fl['date'], '%Y-%m-%d').date() if fl['date'] else date.today()
        logs = logs.filter(log_date=day)
        period = day.strftime('%d %B, %Y')

    for key, field in [('category', 'category_id'), ('item_type', 'item_type_id'),
                       ('reporter', 'reporter_id'), ('editor', 'editor_id'),
                       ('panel', 'panel_id'), ('status', 'status_id')]:
        if fl[key]:
            logs = logs.filter(**{field: fl[key]})

    return logs.order_by('log_time'), period


def _options_grouped():
    opts = {}
    for o in LogOption.objects.all():
        opts.setdefault(o.field_type, []).append(o)
    return opts


# ---------- list ----------
@login_required
def log_list(request):
    fl = _get_filters(request)
    logs, period = _filtered_logs(fl)
    rows = [{'sl': i, 'log': lg} for i, lg in enumerate(logs, 1)]
    return render(request, 'content/log.html', {
        'rows': rows, 'fl': fl, 'period': period,
        'opts': _options_grouped(),
    })


# ---------- add ----------
@login_required
def log_add(request):
    if request.method == 'POST':
        form = ContentLogForm(request.POST)
        if form.is_valid():
            obj = form.save(commit=False)
            if not obj.log_date:
                obj.log_date = date.today()
            obj.created_by = request.user
            obj.save()
            messages.success(request, '✅ Content log added.')
            return redirect('content_log')
        messages.error(request, 'Please fix the errors below.')
    else:
        form = ContentLogForm(initial={'log_date': date.today()})
    return render(request, 'content/log_form.html', {'form': form, 'editing': None})


# ---------- edit ----------
@login_required
def log_edit(request, pk):
    obj = get_object_or_404(ContentLog, pk=pk)
    if request.method == 'POST':
        form = ContentLogForm(request.POST, instance=obj)
        if form.is_valid():
            obj2 = form.save(commit=False)
            if not obj2.log_date:
                obj2.log_date = date.today()
            obj2.save()
            messages.success(request, '✅ Content log updated.')
            return redirect('content_log')
        messages.error(request, 'Please fix the errors below.')
    else:
        form = ContentLogForm(instance=obj)
    return render(request, 'content/log_form.html', {'form': form, 'editing': obj})


# ---------- CSV ----------
@login_required
def log_csv(request):
    fl = _get_filters(request)
    logs, period = _filtered_logs(fl)

    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="content_log_{datetime.now():%Y%m%d_%H%M}.csv"'
    response.write('\ufeff')
    w = csv.writer(response)
    w.writerow(['SL.', 'Content Title', 'Category', 'Assist (Mojo)', 'Item Type',
                'C-P', 'Reporter Name', 'Editors', 'Panel', 'Status',
                'Date', 'Time', 'Remark'])
    for i, lg in enumerate(logs, 1):
        w.writerow([
            i, lg.content_title, _n(lg.category), _n(lg.assist),
            _n(lg.item_type), _n(lg.cp), _n(lg.reporter), _n(lg.editor),
            _n(lg.panel), _n(lg.status),
            lg.log_date.strftime('%d %b, %Y') if lg.log_date else '',
            lg.log_time.strftime('%I:%M %p'),
            lg.remark,
        ])
    return response


# ---------- PDF ----------
@login_required
def log_pdf(request):
    font_name = 'Helvetica'
    for reg in ('C:/Windows/Fonts/nirmala.ttf', 'C:/Windows/Fonts/vrinda.ttf'):
        if os.path.exists(reg):
            try:
                pdfmetrics.registerFont(TTFont('BengaliCL', reg))
                font_name = 'BengaliCL'
                break
            except Exception:
                continue

    fl = _get_filters(request)
    logs, period = _filtered_logs(fl)
    office = OfficeSetting.load()

    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="content_log_{datetime.now():%Y%m%d_%H%M}.pdf"'
    doc = SimpleDocTemplate(response, pagesize=landscape(A4),
                            topMargin=0.4 * inch, bottomMargin=0.4 * inch,
                            leftMargin=0.4 * inch, rightMargin=0.4 * inch)
    styles = getSampleStyleSheet()
    story = []
    FULL_W = 10.9 * inch

    logo_flow = ''
    if office.logo:
        try:
            img = PILImage.open(office.logo.path).convert('RGBA')
            bg = PILImage.new('RGBA', img.size, (255, 255, 255, 255))
            bg.alpha_composite(img)
            buf = _io.BytesIO()
            bg.convert('RGB').save(buf, format='PNG')
            buf.seek(0)
            w, h = img.size
            scale = min(56.0 / w, 56.0 / h)
            logo_flow = RLImage(buf, width=w * scale, height=h * scale)
        except Exception:
            logo_flow = ''

    c_title = ParagraphStyle('CT', parent=styles['Normal'], fontSize=16, leading=20,
                             alignment=1, textColor=colors.HexColor('#111827'))
    c_sub = ParagraphStyle('CS', parent=styles['Normal'], fontSize=9.5, leading=13,
                           alignment=1, textColor=colors.HexColor('#6b7280'))

    if logo_flow:
        lt = Table([[logo_flow]], colWidths=[FULL_W])
        lt.setStyle(TableStyle([('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                                ('BOTTOMPADDING', (0, 0), (-1, -1), 6)]))
        story.append(lt)
    story.append(Paragraph(f'<b>{office.title} — Log Sheet</b>', c_title))
    story.append(Paragraph(f'Period: {period}', c_sub))
    story.append(Spacer(1, 6))
    story.append(Table([['']], colWidths=[FULL_W], rowHeights=[3],
                       style=TableStyle([('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#c62828'))])))
    story.append(Spacer(1, 12))

    cell = ParagraphStyle('CELL', parent=styles['Normal'], fontName=font_name,
                          fontSize=7.5, leading=10)

    data = [['SL.', 'Content Title', 'Category', 'Assist', 'Item Type', 'C-P',
             'Reporter', 'Editors', 'Panel', 'Status', 'Date & Time', 'Remark']]
    for i, lg in enumerate(logs, 1):
        data.append([
            str(i),
            Paragraph(escape(lg.content_title or '-'), cell),
            _n(lg.category, '-'),
            _n(lg.assist, '-'),
            _n(lg.item_type, '-'),
            _n(lg.cp, '-'),
            _n(lg.reporter, '-'),
            _n(lg.editor, '-'),
            _n(lg.panel, '-'),
            _n(lg.status, '-'),
            f'{lg.log_date:%d %b, %y}\n{lg.log_time:%I:%M %p}' if lg.log_date else f'-\n{lg.log_time:%I:%M %p}',
            Paragraph(escape(lg.remark or '-'), cell),
        ])

    if len(data) == 1:
        data.append(['', 'No logs found for this period.', '', '', '', '',
                     '', '', '', '', '', ''])

    t = Table(data, colWidths=[0.35*inch, 2.1*inch, 0.8*inch, 0.7*inch, 0.7*inch,
                               0.7*inch, 1.0*inch, 0.9*inch, 0.7*inch, 0.8*inch,
                               1.0*inch, 0.95*inch],
              repeatRows=1)
    t.hAlign = 'CENTER'
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#c62828')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, -1), font_name),
        ('FONTSIZE', (0, 0), (-1, 0), 8),
        ('FONTSIZE', (0, 1), (-1, -1), 7.5),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#d1d5db')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#fff8e1')]),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
    ]))
    story.append(t)

    story.append(Spacer(1, 12))
    story.append(Paragraph(
        f'<font size=8 color="#9ca3af">Computer-generated log sheet | {office.title} | '
        f'Total: {len(data) - 1} entry(ies) | Generated: {datetime.now():%d %b, %Y %I:%M %p}</font>',
        ParagraphStyle('F', parent=styles['Normal'], alignment=1)))

    doc.build(story)
    return response


# ---------- CONTENT REPORT (চার্ট সহ) ----------
# ---------- CONTENT REPORT (চার্ট সহ + ফিল্টার) ----------
@login_required
def content_report(request):
    """সবাই দেখতে পারবে — চার্ট সহ রিপোর্ট + ৭টি ফিল্টার"""
    
    # ========== FILTERS ==========
    from_date_str = request.GET.get('from_date', '')
    to_date_str = request.GET.get('to_date', '')
    reporter_id = request.GET.get('reporter', '')
    editor_id = request.GET.get('editor', '')
    category_id = request.GET.get('category', '')
    panel_id = request.GET.get('panel', '')
    item_type_id = request.GET.get('item_type', '')
    status_id = request.GET.get('status', '')
    
    # Base queryset
    logs = ContentLog.objects.select_related(
        'category', 'item_type', 'reporter', 'editor', 'panel', 'status')
    
    # Apply filters
    if from_date_str:
        try:
            from_date = datetime.strptime(from_date_str, '%Y-%m-%d').date()
            logs = logs.filter(log_date__gte=from_date)
        except ValueError:
            from_date = None
    else:
        from_date = date.today() - timedelta(days=30)
    
    if to_date_str:
        try:
            to_date = datetime.strptime(to_date_str, '%Y-%m-%d').date()
            logs = logs.filter(log_date__lte=to_date)
        except ValueError:
            to_date = date.today()
    else:
        to_date = date.today()
    
    if reporter_id:
        logs = logs.filter(reporter_id=reporter_id)
    if editor_id:
        logs = logs.filter(editor_id=editor_id)
    if category_id:
        logs = logs.filter(category_id=category_id)
    if panel_id:
        logs = logs.filter(panel_id=panel_id)
    if item_type_id:
        logs = logs.filter(item_type_id=item_type_id)
    if status_id:
        logs = logs.filter(status_id=status_id)
    
    # ========== CALCULATIONS ==========
    total = logs.count()
    
    category_data = Counter(lg.category.name for lg in logs if lg.category)
    reporter_data = Counter(lg.reporter.name for lg in logs if lg.reporter)
    editor_data = Counter(lg.editor.name for lg in logs if lg.editor)
    panel_data = Counter(lg.panel.name for lg in logs if lg.panel)
    item_type_data = Counter(lg.item_type.name for lg in logs if lg.item_type)
    status_data = Counter(lg.status.name for lg in logs if lg.status)
    
    # Daily trend
    daily_trend = {}
    current = from_date
    while current <= to_date:
        daily_trend[current.strftime('%d %b')] = logs.filter(log_date=current).count()
        current += timedelta(days=1)
    
    top_reporters = reporter_data.most_common(10)
    top_editors = editor_data.most_common(10)
    
    mojo_count = logs.filter(
        Q(category__name__icontains='Mojo') | 
        Q(item_type__name__icontains='Mojo')
    ).count()
    
    # Helper: JSON for Chart.js
    def to_chart(data, colors=None):
        if not colors:
            colors = ['#6366f1', '#8b5cf6', '#ec4899', '#f43f5e', '#f97316', 
                      '#eab308', '#22c55e', '#14b8a6', '#06b6d4', '#3b82f6']
        labels = list(data.keys())
        values = list(data.values())
        return {
            'labels': json.dumps(labels),
            'values': json.dumps(values),
            'colors': json.dumps(colors[:len(labels)])
        }
    
    # Get all options for dropdowns
    all_reporters = LogOption.objects.filter(field_type='reporter').order_by('name')
    all_editors = LogOption.objects.filter(field_type='editor').order_by('name')
    all_categories = LogOption.objects.filter(field_type='category').order_by('name')
    all_panels = LogOption.objects.filter(field_type='panel').order_by('name')
    all_item_types = LogOption.objects.filter(field_type='item_type').order_by('name')
    all_statuses = LogOption.objects.filter(field_type='status').order_by('name')
    
    return render(request, 'content/report.html', {
        'total': total,
        'mojo_count': mojo_count,
        'status_type_count': len(status_data),
        'reporter_count': len(reporter_data),
        'editor_count': len(editor_data),
        'from_date': from_date,
        'to_date': to_date,
        'from_date_str': from_date_str,
        'to_date_str': to_date_str,
        'reporter_id': reporter_id,
        'editor_id': editor_id,
        'category_id': category_id,
        'panel_id': panel_id,
        'item_type_id': item_type_id,
        'status_id': status_id,
        'all_reporters': all_reporters,
        'all_editors': all_editors,
        'all_categories': all_categories,
        'all_panels': all_panels,
        'all_item_types': all_item_types,
        'all_statuses': all_statuses,
        'category_chart': to_chart(category_data),
        'reporter_chart': to_chart(reporter_data),
        'editor_chart': to_chart(editor_data, ['#10b981', '#059669', '#047857', '#065f46', '#064e3b',
                                                '#34d399', '#6ee7b7', '#a7f3d0', '#d1fae5', '#ecfdf5']),
        'panel_chart': to_chart(panel_data, ['#f59e0b', '#d97706', '#b45309', '#92400e', '#78350f']),
        'item_type_chart': to_chart(item_type_data, ['#8b5cf6', '#7c3aed', '#6d28d9', '#5b21b6', '#4c1d95']),
        'status_chart': to_chart(status_data, ['#10b981', '#f59e0b', '#ef4444', '#6b7280']),
        'daily_trend': daily_trend,
        'daily_labels': json.dumps(list(daily_trend.keys())),
        'daily_values': json.dumps(list(daily_trend.values())),
        'top_reporters': top_reporters,
        'top_editors': top_editors,
        'has_filters': any([from_date_str, to_date_str, reporter_id, editor_id, 
                           category_id, panel_id, item_type_id, status_id]),
    })


@login_required
def content_report_pdf(request):
    """Content Report PDF Download"""
    font_name = 'Helvetica'
    for reg in ('C:/Windows/Fonts/nirmala.ttf', 'C:/Windows/Fonts/vrinda.ttf'):
        if os.path.exists(reg):
            try:
                pdfmetrics.registerFont(TTFont('BengaliRep', reg))
                font_name = 'BengaliRep'
                break
            except Exception:
                continue

    # Same filters as content_report
    from_date_str = request.GET.get('from_date', '')
    to_date_str = request.GET.get('to_date', '')
    reporter_id = request.GET.get('reporter', '')
    editor_id = request.GET.get('editor', '')
    category_id = request.GET.get('category', '')
    panel_id = request.GET.get('panel', '')
    item_type_id = request.GET.get('item_type', '')
    status_id = request.GET.get('status', '')

    logs = ContentLog.objects.select_related(
        'category', 'item_type', 'reporter', 'editor', 'panel', 'status')

    if from_date_str:
        try:
            from_date = datetime.strptime(from_date_str, '%Y-%m-%d').date()
            logs = logs.filter(log_date__gte=from_date)
        except ValueError:
            from_date = date.today() - timedelta(days=30)
    else:
        from_date = date.today() - timedelta(days=30)

    if to_date_str:
        try:
            to_date = datetime.strptime(to_date_str, '%Y-%m-%d').date()
            logs = logs.filter(log_date__lte=to_date)
        except ValueError:
            to_date = date.today()
    else:
        to_date = date.today()

    if reporter_id: logs = logs.filter(reporter_id=reporter_id)
    if editor_id: logs = logs.filter(editor_id=editor_id)
    if category_id: logs = logs.filter(category_id=category_id)
    if panel_id: logs = logs.filter(panel_id=panel_id)
    if item_type_id: logs = logs.filter(item_type_id=item_type_id)
    if status_id: logs = logs.filter(status_id=status_id)

    total = logs.count()
    category_data = Counter(lg.category.name for lg in logs if lg.category)
    reporter_data = Counter(lg.reporter.name for lg in logs if lg.reporter)
    editor_data = Counter(lg.editor.name for lg in logs if lg.editor)
    panel_data = Counter(lg.panel.name for lg in logs if lg.panel)
    item_type_data = Counter(lg.item_type.name for lg in logs if lg.item_type)
    status_data = Counter(lg.status.name for lg in logs if lg.status)
    
    mojo_count = logs.filter(
        Q(category__name__icontains='Mojo') | 
        Q(item_type__name__icontains='Mojo')
    ).count()

    office = OfficeSetting.load()

    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="content_report_{from_date}_{to_date}.pdf"'
    
    doc = SimpleDocTemplate(response, pagesize=landscape(A4),
                            topMargin=0.5 * inch, bottomMargin=0.5 * inch,
                            leftMargin=0.5 * inch, rightMargin=0.5 * inch)
    styles = getSampleStyleSheet()
    story = []
    FULL_W = 10.7 * inch

    # Logo
    logo_flow = ''
    if office.logo:
        try:
            img = PILImage.open(office.logo.path).convert('RGBA')
            bg = PILImage.new('RGBA', img.size, (255, 255, 255, 255))
            bg.alpha_composite(img)
            buf = _io.BytesIO()
            bg.convert('RGB').save(buf, format='PNG')
            buf.seek(0)
            w, h = img.size
            scale = min(60.0 / w, 60.0 / h)
            logo_flow = RLImage(buf, width=w * scale, height=h * scale)
        except Exception:
            logo_flow = ''

    c_title = ParagraphStyle('CT', parent=styles['Normal'], fontSize=18, leading=24,
                             alignment=1, textColor=colors.HexColor('#111827'), fontName=font_name)
    c_sub = ParagraphStyle('CS', parent=styles['Normal'], fontSize=10, leading=14,
                           alignment=1, textColor=colors.HexColor('#6b7280'), fontName=font_name)
    c_head = ParagraphStyle('CH', parent=styles['Normal'], fontSize=12, leading=16,
                            fontName=font_name, textColor=colors.HexColor('#111827'))
    cell = ParagraphStyle('CELL', parent=styles['Normal'], fontName=font_name,
                          fontSize=9, leading=12)
    cell_bold = ParagraphStyle('CB', parent=cell, fontName=font_name,
                               fontSize=9, leading=12, textColor=colors.HexColor('#ffffff'))

    if logo_flow:
        lt = Table([[logo_flow]], colWidths=[FULL_W])
        lt.setStyle(TableStyle([('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                                ('BOTTOMPADDING', (0, 0), (-1, -1), 8)]))
        story.append(lt)
    
    story.append(Paragraph(f'<b>{office.title}</b>', c_title))
    story.append(Paragraph('Content Report', c_sub))
    story.append(Paragraph(f'Period: {from_date:%d %b, %Y} — {to_date:%d %b, %Y}', c_sub))
    story.append(Paragraph(f'Generated: {datetime.now():%d %b, %Y %I:%M %p}', c_sub))
    story.append(Spacer(1, 6))
    story.append(Table([['']], colWidths=[FULL_W], rowHeights=[3],
                       style=TableStyle([('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#c62828'))])))
    story.append(Spacer(1, 14))

    # ===== Stats Cards =====
    stats_data = [['Total Content', 'Mojo Items', 'Active Reporters', 'Categories']]
    stats_vals = [[str(total), str(mojo_count), str(len(reporter_data)), str(len(category_data))]]
    
    stats_table = Table(stats_data + stats_vals, colWidths=[2.5*inch]*4)
    stats_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#6366f1')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, -1), font_name),
        ('FONTSIZE', (0, 0), (-1, 0), 9),
        ('FONTSIZE', (0, 1), (-1, -1), 14),
        ('FONTNAME', (0, 1), (-1, -1), font_name),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#d1d5db')),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#f8fafc')),
    ]))
    story.append(stats_table)
    story.append(Spacer(1, 14))

    # ===== Category Distribution =====
    story.append(Paragraph('<b>📊 Category Distribution</b>', c_head))
    story.append(Spacer(1, 6))
    if category_data:
        cat_data = [['Category', 'Count', 'Percentage']]
        for name, count in category_data.most_common():
            pct = f'{(count/total*100):.1f}%' if total > 0 else '0%'
            cat_data.append([name, str(count), pct])
        cat_table = Table(cat_data, colWidths=[3*inch, 1.5*inch, 1.5*inch])
        cat_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#6366f1')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, -1), font_name),
            ('FONTSIZE', (0, 0), (-1, 0), 9),
            ('FONTSIZE', (0, 1), (-1, -1), 8.5),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#d1d5db')),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8fafc')]),
            ('TOPPADDING', (0, 0), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ]))
        story.append(cat_table)
    else:
        story.append(Paragraph('No data', cell))
    story.append(Spacer(1, 14))

    # ===== Top Reporters =====
    story.append(Paragraph('<b>🏆 Top Reporters</b>', c_head))
    story.append(Spacer(1, 6))
    if reporter_data:
        rep_data = [['Rank', 'Reporter', 'Count']]
        for i, (name, count) in enumerate(reporter_data.most_common(10), 1):
            rep_data.append([str(i), name, str(count)])
        rep_table = Table(rep_data, colWidths=[0.8*inch, 3.5*inch, 1.5*inch])
        rep_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#10b981')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, -1), font_name),
            ('FONTSIZE', (0, 0), (-1, 0), 9),
            ('FONTSIZE', (0, 1), (-1, -1), 8.5),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#d1d5db')),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8fafc')]),
            ('TOPPADDING', (0, 0), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            ('ALIGN', (0, 0), (0, -1), 'CENTER'),
            ('ALIGN', (2, 0), (2, -1), 'CENTER'),
        ]))
        story.append(rep_table)
    else:
        story.append(Paragraph('No data', cell))
    story.append(Spacer(1, 14))

    # ===== Top Editors =====
    story.append(Paragraph('<b>️ Top Editors</b>', c_head))
    story.append(Spacer(1, 6))
    if editor_data:
        ed_data = [['Rank', 'Editor', 'Count']]
        for i, (name, count) in enumerate(editor_data.most_common(10), 1):
            ed_data.append([str(i), name, str(count)])
        ed_table = Table(ed_data, colWidths=[0.8*inch, 3.5*inch, 1.5*inch])
        ed_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#8b5cf6')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, -1), font_name),
            ('FONTSIZE', (0, 0), (-1, 0), 9),
            ('FONTSIZE', (0, 1), (-1, -1), 8.5),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#d1d5db')),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8fafc')]),
            ('TOPPADDING', (0, 0), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            ('ALIGN', (0, 0), (0, -1), 'CENTER'),
            ('ALIGN', (2, 0), (2, -1), 'CENTER'),
        ]))
        story.append(ed_table)
    else:
        story.append(Paragraph('No data', cell))
    story.append(Spacer(1, 14))

    # ===== Status Distribution =====
    story.append(Paragraph('<b>✅ Status Distribution</b>', c_head))
    story.append(Spacer(1, 6))
    if status_data:
        st_data = [['Status', 'Count', 'Percentage']]
        for name, count in status_data.most_common():
            pct = f'{(count/total*100):.1f}%' if total > 0 else '0%'
            st_data.append([name, str(count), pct])
        st_table = Table(st_data, colWidths=[3*inch, 1.5*inch, 1.5*inch])
        st_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f59e0b')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, -1), font_name),
            ('FONTSIZE', (0, 0), (-1, 0), 9),
            ('FONTSIZE', (0, 1), (-1, -1), 8.5),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#d1d5db')),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8fafc')]),
            ('TOPPADDING', (0, 0), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ]))
        story.append(st_table)
    else:
        story.append(Paragraph('No data', cell))
    story.append(Spacer(1, 14))

    # ===== Panel & Item Type (side by side) =====
    panel_data_list = [['Panel', 'Count']]
    for name, count in panel_data.most_common():
        panel_data_list.append([name, str(count)])
    
    item_data_list = [['Item Type', 'Count']]
    for name, count in item_type_data.most_common():
        item_data_list.append([name, str(count)])

    if panel_data or item_type_data:
        story.append(Paragraph('<b>📺 Panel & Item Type Distribution</b>', c_head))
        story.append(Spacer(1, 6))
        
        combined = []
        max_rows = max(len(panel_data_list), len(item_data_list))
        for i in range(max_rows):
            row = []
            if i < len(panel_data_list):
                row.extend(panel_data_list[i])
            else:
                row.extend(['', ''])
            if i < len(item_data_list):
                row.extend(item_data_list[i])
            else:
                row.extend(['', ''])
            combined.append(row)
        
        if combined:
            combined.insert(0, ['Panel', 'Count', 'Item Type', 'Count'])
            pt_table = Table(combined, colWidths=[2.5*inch, 1*inch, 2.5*inch, 1*inch])
            pt_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#ec4899')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('FONTNAME', (0, 0), (-1, -1), font_name),
                ('FONTSIZE', (0, 0), (-1, 0), 9),
                ('FONTSIZE', (0, 1), (-1, -1), 8.5),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#d1d5db')),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8fafc')]),
                ('TOPPADDING', (0, 0), (-1, -1), 5),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
                ('ALIGN', (1, 0), (1, -1), 'CENTER'),
                ('ALIGN', (3, 0), (3, -1), 'CENTER'),
            ]))
            story.append(pt_table)
    story.append(Spacer(1, 14))

    # ===== Daily Trend =====
    story.append(Paragraph('<b>📈 Daily Trend</b>', c_head))
    story.append(Spacer(1, 6))
    
    daily_trend = {}
    current = from_date
    while current <= to_date:
        daily_trend[current.strftime('%d %b')] = logs.filter(log_date=current).count()
        current += timedelta(days=1)
    
    if daily_trend:
        trend_data = [['Date', 'Content Count']]
        for d, count in daily_trend.items():
            trend_data.append([d, str(count)])
        trend_table = Table(trend_data, colWidths=[2*inch, 2*inch])
        trend_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#06b6d4')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, -1), font_name),
            ('FONTSIZE', (0, 0), (-1, 0), 9),
            ('FONTSIZE', (0, 1), (-1, -1), 8.5),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#d1d5db')),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8fafc')]),
            ('TOPPADDING', (0, 0), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            ('ALIGN', (1, 0), (1, -1), 'CENTER'),
        ]))
        story.append(trend_table)
    else:
        story.append(Paragraph('No data', cell))

    # Footer
    story.append(Spacer(1, 14))
    story.append(Table([['']], colWidths=[FULL_W], rowHeights=[2],
                       style=TableStyle([('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#c62828'))])))
    story.append(Spacer(1, 8))
    story.append(Paragraph(
        f'<font size=8 color="#9ca3af">Computer-generated content report | {office.title} | '
        f'Total: {total} entries</font>',
        ParagraphStyle('F', parent=styles['Normal'], alignment=1, fontName=font_name)))

    doc.build(story)
    return response