import json
import os
import io
import textwrap
import calendar
from datetime import datetime, date

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST

from accounts.decorators import role_required
from employees.models import Employee, OfficeSetting
from .models import LeaveRequest
from .forms import LeaveForm
from notifications.helpers import notify_admins, notify_employee

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from xml.sax.saxutils import escape


# ---------- My Leaves (Employee) ----------
@login_required
def my_leaves(request):
    emp = getattr(request.user, 'employee', None)
    if not emp:
        messages.error(request, 'No employee profile linked.')
        return redirect('dashboard')

    leaves = LeaveRequest.objects.filter(employee=emp).order_by('-created_at')

    if request.method == 'POST':
        form = LeaveForm(request.POST, request.FILES)
        leave_dates_json = request.POST.get('leave_dates_json', '[]')

        if form.is_valid():
            lv = form.save(commit=False)
            lv.employee = emp

            try:
                dates_list = json.loads(leave_dates_json)
                if dates_list:
                    lv.leave_dates = sorted(dates_list)
                    lv.from_date = min(dates_list)
                    lv.to_date = max(dates_list)
            except (json.JSONDecodeError, ValueError):
                pass

            lv.save()
            notify_admins(
                f'{emp.name} ({emp.emp_id}) নতুন leave apply করেছেন — {lv.days} দিন',
                link='/leave/manage/',
                type='leave_apply'
            )
            messages.success(request, f'✅ Leave application submitted ({lv.days} days).')
            return redirect('my_leaves')
        messages.error(request, 'Please correct the errors below.')
    else:
        form = LeaveForm()

    return render(request, 'leave/my_leaves.html', {'form': form, 'leaves': leaves, 'emp': emp})


# ---------- Manage Leaves (Admin/Supervisor) ----------
@role_required('admin', 'supervisor')
def manage_leaves(request):
    status = request.GET.get('status', 'pending')
    leaves = LeaveRequest.objects.all().order_by('-created_at')
    
    if status != 'all':
        leaves = leaves.filter(status=status)
        
    counts = {
        'pending': LeaveRequest.objects.filter(status='pending').count(),
        'approved': LeaveRequest.objects.filter(status='approved').count(),
        'rejected': LeaveRequest.objects.filter(status='rejected').count(),
    }
    
    return render(request, 'leave/manage.html', {
        'leaves': leaves, 
        'status': status, 
        'counts': counts
    })


# ---------- Approve Leave ----------
@require_POST
@role_required('admin', 'supervisor')
def leave_approve(request, pk):
    lv = get_object_or_404(LeaveRequest, pk=pk)
    if lv.status == 'pending':
        lv.status = 'approved'
        lv.save()
        notify_employee(
            lv.employee,
            f'আপনার leave ({lv.from_date:%d %b} – {lv.to_date:%d %b}) approved হয়েছে ✅',
            link='/leave/my/',
            type='leave_approve'
        )
        messages.success(request, f'✅ {lv.employee.name} এর leave approved.')
    
    # ✅ সবসময় redirect রিটার্ন করতে হবে
    return redirect('manage_leaves')


# ---------- Reject Leave ----------
@require_POST
@role_required('admin', 'supervisor')
def leave_reject(request, pk):
    lv = get_object_or_404(LeaveRequest, pk=pk)
    reason = request.POST.get('reason', '')
    
    if lv.status == 'pending':
        lv.status = 'rejected'
        lv.reject_reason = reason
        lv.save()
        notify_employee(
            lv.employee,
            f'আপনার leave ({lv.from_date:%d %b} – {lv.to_date:%d %b}) rejected হয়েছে ❌ কারণ: {reason[:50]}',
            link='/leave/my/',
            type='leave_reject'
        )
        messages.success(request, f'❌ {lv.employee.name} এর leave rejected.')
    
    # ✅ সবসময় redirect রিটার্ন করতে হবে
    return redirect('manage_leaves')


# ---------- Leave Application PDF ----------
@role_required('admin', 'supervisor', 'employee')
def leave_application_pdf(request, pk):
    lv = get_object_or_404(LeaveRequest, pk=pk)
    emp = getattr(request.user, 'employee', None)
    is_owner = emp is not None and emp.id == lv.employee_id
    
    if request.user.profile.role not in ['admin', 'supervisor'] and not is_owner:
        messages.error(request, 'Access denied.')
        return redirect('dashboard')

    font_name = 'Helvetica'
    for reg in ('C:/Windows/Fonts/nirmala.ttf', 'C:/Windows/Fonts/vrinda.ttf'):
        if os.path.exists(reg):
            try:
                pdfmetrics.registerFont(TTFont('BengaliLeave', reg))
                font_name = 'BengaliLeave'
                break
            except Exception:
                continue

    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="Leave_Application_{lv.id}.pdf"'
    
    doc = SimpleDocTemplate(response, pagesize=A4,
                            topMargin=0.8 * inch, bottomMargin=0.8 * inch,
                            leftMargin=0.8 * inch, rightMargin=0.8 * inch)
    styles = getSampleStyleSheet()
    story = []

    c_title = ParagraphStyle('CT', parent=styles['Normal'], fontSize=18, leading=24,
                             alignment=1, textColor=colors.HexColor('#111827'), fontName=font_name)
    c_sub = ParagraphStyle('CS', parent=styles['Normal'], fontSize=11, leading=16,
                           alignment=1, textColor=colors.HexColor('#6b7280'), fontName=font_name)
    cell = ParagraphStyle('CELL', parent=styles['Normal'], fontSize=11, leading=15, fontName=font_name)

    story.append(Paragraph('Leave Application', c_title))
    story.append(Spacer(1, 10))
    story.append(Paragraph(f'Generated on: {date.today():%d %B, %Y}', c_sub))
    story.append(Spacer(1, 20))

    if lv.leave_dates:
        dates_text = ', '.join([datetime.strptime(d, '%Y-%m-%d').strftime('%d %b, %Y') for d in lv.date_list])
    else:
        dates_text = f"{lv.from_date:%d %b, %Y} to {lv.to_date:%d %b, %Y}"

    data = [
        [Paragraph('<b>Employee Name</b>', cell), Paragraph(lv.employee.name, cell)],
        [Paragraph('<b>Employee ID</b>', cell), Paragraph(lv.employee.emp_id, cell)],
        [Paragraph('<b>Designation</b>', cell), Paragraph(lv.employee.designation, cell)],
        [Paragraph('<b>Department</b>', cell), Paragraph(lv.employee.department, cell)],
        [Paragraph('<b>Leave Dates</b>', cell), Paragraph(dates_text, cell)],
        [Paragraph('<b>Total Days</b>', cell), Paragraph(str(lv.days), cell)],
        [Paragraph('<b>Reason</b>', cell), Paragraph(escape(lv.reason or 'No reason provided'), cell)],
        [Paragraph('<b>Status</b>', cell), Paragraph(lv.get_status_display(), cell)],
    ]
    
    if lv.status == 'rejected' and lv.reject_reason:
        data.append([Paragraph('<b>Reject Reason</b>', cell), Paragraph(escape(lv.reject_reason), cell)])

    t = Table(data, colWidths=[2.5*inch, 4.5*inch])
    t.setStyle(TableStyle([
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e5e7eb')),
        ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#f8fafc')),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
    ]))
    story.append(t)

    story.append(Spacer(1, 30))
    story.append(Paragraph(
        f'<font size=9 color="#9ca3af">Computer-generated document | Authorized Signature: _________________</font>',
        ParagraphStyle('F', parent=styles['Normal'], alignment=1, fontName=font_name)))

    doc.build(story)
    return response


# ---------- Download CSV ----------
@role_required('admin', 'supervisor')
def leave_download_csv(request):
    status = request.GET.get('status', 'all')
    leaves = LeaveRequest.objects.all().order_by('-created_at')
    if status != 'all':
        leaves = leaves.filter(status=status)

    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="leave_requests_{date.today()}.csv"'
    response.write('\ufeff')
    w = csv.writer(response)
    w.writerow(['Emp ID', 'Name', 'Department', 'From Date', 'To Date', 'Days', 'Reason', 'Status', 'Reject Reason'])
    
    for lv in leaves:
        dates_str = ', '.join(lv.date_list) if lv.leave_dates else f"{lv.from_date} to {lv.to_date}"
        w.writerow([
            lv.employee.emp_id, lv.employee.name, lv.employee.department,
            dates_str, lv.days, lv.reason, lv.get_status_display(), lv.reject_reason
        ])
    return response


# ---------- Download PDF ----------
@role_required('admin', 'supervisor')
def leave_download_pdf(request):
    status = request.GET.get('status', 'all')
    leaves = LeaveRequest.objects.all().order_by('-created_at')
    if status != 'all':
        leaves = leaves.filter(status=status)

    font_name = 'Helvetica'
    for reg in ('C:/Windows/Fonts/nirmala.ttf', 'C:/Windows/Fonts/vrinda.ttf'):
        if os.path.exists(reg):
            try:
                pdfmetrics.registerFont(TTFont('BengaliLeaveList', reg))
                font_name = 'BengaliLeaveList'
                break
            except Exception:
                continue

    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="leave_requests_{date.today()}.pdf"'
    
    doc = SimpleDocTemplate(response, pagesize=A4,
                            topMargin=0.6 * inch, bottomMargin=0.6 * inch,
                            leftMargin=0.5 * inch, rightMargin=0.5 * inch)
    styles = getSampleStyleSheet()
    story = []

    c_title = ParagraphStyle('CT', parent=styles['Normal'], fontSize=16, leading=20,
                             alignment=1, textColor=colors.HexColor('#111827'), fontName=font_name)
    
    story.append(Paragraph(f'Leave Requests Report ({status.title()})', c_title))
    story.append(Spacer(1, 15))

    data = [['Emp ID', 'Name', 'Dates', 'Days', 'Reason', 'Status']]
    for lv in leaves:
        dates_str = ', '.join(lv.date_list) if lv.leave_dates else f"{lv.from_date:%d %b} - {lv.to_date:%d %b}"
        data.append([
            lv.employee.emp_id,
            lv.employee.name,
            dates_str,
            str(lv.days),
            (lv.reason or '-')[:40],
            lv.get_status_display()
        ])

    t = Table(data, colWidths=[0.8*inch, 1.5*inch, 1.5*inch, 0.5*inch, 2.5*inch, 0.8*inch])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#6366f1')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#d1d5db')),
        ('FONTNAME', (0, 0), (-1, -1), font_name),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
    ]))
    story.append(t)
    doc.build(story)
    return response