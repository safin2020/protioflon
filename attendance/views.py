import csv
import calendar
import math
import os
import io as _io
from datetime import date, datetime, timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_POST

from accounts.decorators import role_required
from employees.models import Employee, OfficeSetting
from leave.models import LeaveRequest
from .models import Attendance, AttendanceAlert, DutyHour, MonthlyTarget, target_hours_for, monthly_target_for

from PIL import Image as PILImage
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.platypus import (SimpleDocTemplate, Table, TableStyle,
                                Paragraph, Spacer, Image as RLImage)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont


# ---------- helpers ----------
def _fh(h):
    if h is None or h == '':
        return '-'
    h = float(h)
    hh = int(h); mm = round((h - hh) * 60)
    if mm == 60: hh += 1; mm = 0
    if hh and mm: return f'{hh}h {mm}m'
    if hh: return f'{hh}h'
    if mm: return f'{mm}m'
    return '0m'


def _haversine(lat1, lon1, lat2, lon2):
    R = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1); dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _staff_emps(exclude_user=None):
    qs = Employee.objects.filter(status='active').exclude(duty_group='mojo').select_related('user__profile')
    out = []
    for e in qs:
        if e.user_id and e.user.profile.role == 'supervisor':
            if exclude_user and e.user_id == exclude_user.id:
                continue
        out.append(e)
    return out


def _locked(a, emp=None):
    if not a:
        return False
    if a.status in ('wfh', 'absent', 'off'):
        return True
    if a.status == 'present' and a.check_in and a.check_out:
        return True
    return False


# ---------- board ----------
@role_required('admin', 'supervisor')
def attendance_board(request):
    d = request.GET.get('date')
    day = datetime.strptime(d, '%Y-%m-%d').date() if d else date.today()
    exclude = request.user if request.user.profile.role == 'supervisor' else None
    emps = _staff_emps(exclude_user=exclude)
    att_map = {a.employee_id: a for a in Attendance.objects.filter(date=day)}
    now = datetime.now()

    rows = []
    for e in emps:
        target = target_hours_for(e, day)
        a = att_map.get(e.id)
        worked_str = rem_str = ot_str = '-'
        if a and a.check_in:
            start = datetime.combine(day, a.check_in)
            end_dt = datetime.combine(day, a.check_out) if a.check_out else now
            el = max(0, (end_dt - start).total_seconds() / 3600)
            worked_str = _fh(el)
            rem = max(0, target - el)
            rem_str = 'Done' if (a.check_out and rem <= 0) else _fh(rem)
            ot = max(0, el - target)
            ot_str = _fh(ot) if ot > 0 else '-'
        rows.append({'emp': e, 'att': a, 'locked': _locked(a, e),
                     'worked_str': worked_str, 'rem_str': rem_str, 'ot_str': ot_str,
                     'target_str': _fh(target)})

    atts = list(att_map.values())
    counts = {
        'present': sum(1 for a in atts if a.status == 'present'),
        'wfh': sum(1 for a in atts if a.status == 'wfh'),
        'absent': sum(1 for a in atts if a.status == 'absent'),
        'off': sum(1 for a in atts if a.status == 'off'),
        'live': sum(1 for a in atts if a.status == 'present' and a.check_in and not a.check_out),
        'leave': LeaveRequest.objects.filter(status='approved',
                   from_date__lte=day, to_date__gte=day).count(),
        'alerts': AttendanceAlert.objects.filter(created_at__date=day).count(),
    }
    return render(request, 'attendance/board.html',
                  {'rows': rows, 'day': day, 'counts': counts})


# ---------- stamp ----------
@require_POST
@role_required('admin', 'supervisor')
def stamp(request, emp_id, action):
    e = get_object_or_404(Employee, pk=emp_id)
    if e.duty_group == 'mojo':
        messages.error(request, f'{e.name} is Mojo — no attendance needed.')
        return redirect('attendance_board')
    day = date.today()
    a = Attendance.objects.filter(employee=e, date=day).first()
    if action == 'in':
        if a and a.check_in:
            messages.error(request, f'{e.name}: already checked in.')
        elif a and a.status != 'present':
            messages.error(request, f'{e.name}: locked.')
        else:
            if not a:
                a = Attendance(employee=e, date=day, status='present')
            a.check_in = datetime.now().time(); a.status = 'present'; a.save()
            messages.success(request, f'{e.name} → Check-In {a.check_in:%I:%M %p}')
    else:
        if not a or not a.check_in:
            messages.error(request, f'{e.name}: check-in first.')
        elif a.check_out:
            messages.error(request, f'{e.name}: already checked out.')
        else:
            a.check_out = datetime.now().time(); a.save()
            messages.success(request, f'{e.name} → Check-Out {a.check_out:%I:%M %p}')
    return redirect(request.META.get('HTTP_REFERER', 'attendance_board'))


@require_POST
@role_required('admin', 'supervisor')
def mark_status(request, emp_id):
    st = request.POST.get('status')
    if st not in ('wfh', 'absent', 'off'):
        messages.error(request, 'Invalid status.')
        return redirect('attendance_board')
    e = get_object_or_404(Employee, pk=emp_id)
    if e.duty_group == 'mojo':
        messages.error(request, f'{e.name} is Mojo — no attendance needed.')
        return redirect('attendance_board')
    day = date.today()
    if Attendance.objects.filter(employee=e, date=day).exists():
        messages.error(request, f'{e.name}: already finalized.')
    else:
        Attendance.objects.create(employee=e, date=day, status=st)
        messages.success(request, f'{e.name} marked {st}.')
    return redirect('attendance_board')


@require_POST
@role_required('admin', 'supervisor')
def mark_wfh_present(request, emp_id):
    e = get_object_or_404(Employee, pk=emp_id)
    if e.duty_group != 'wfh':
        messages.error(request, f'{e.name} is not WFH.')
        return redirect('attendance_board')
    day = date.today()
    if Attendance.objects.filter(employee=e, date=day).exists():
        messages.error(request, f'{e.name}: already marked.')
    else:
        Attendance.objects.create(employee=e, date=day, status='present', remarks='WFH')
        messages.success(request, f'{e.name} marked Present (WFH).')
    return redirect('attendance_board')


# ---------- alerts ----------
@role_required('admin', 'supervisor')
def alerts_list(request):
    d = request.GET.get('date')
    day = datetime.strptime(d, '%Y-%m-%d').date() if d else date.today()
    alerts = AttendanceAlert.objects.filter(created_at__date=day).select_related('employee')
    return render(request, 'attendance/alerts.html', {'alerts': alerts, 'day': day})


# ---------- employee self ----------
@login_required
def my_attendance(request):
    emp = getattr(request.user, 'employee', None)
    if not emp:
        messages.error(request, 'No employee profile linked.')
        return redirect('dashboard')
    if emp.duty_group == 'mojo':
        return render(request, 'attendance/mojo_page.html', {'emp': emp})
    day = date.today()
    a = Attendance.objects.filter(employee=emp, date=day).first()
    return render(request, 'attendance/self.html',
                  {'emp': emp, 'att': a, 'locked': _locked(a, emp),
                   'office': OfficeSetting.load()})


@require_POST
@login_required
def self_stamp(request, action):
    emp = getattr(request.user, 'employee', None)
    if not emp:
        return redirect('dashboard')
    if emp.duty_group == 'mojo':
        messages.error(request, 'Mojo employee — attendance not required.')
        return redirect('my_attendance')
    day = date.today()
    a = Attendance.objects.filter(employee=emp, date=day).first()
    office = OfficeSetting.load()
    lat = request.POST.get('lat'); lng = request.POST.get('lng'); acc = request.POST.get('acc')
    latf = float(lat) if lat else None
    lngf = float(lng) if lng else None

    if action == 'wfh':
        if a:
            messages.error(request, 'Already marked today.')
        else:
            Attendance.objects.create(employee=emp, date=day, status='wfh', remarks='WFH')
            messages.success(request, '✅ Marked Present (Work From Home).')
        return redirect('my_attendance')

    if action == 'in':
        if a and a.status != 'present':
            messages.error(request, 'Today locked by admin.')
        elif a and a.check_in:
            messages.error(request, 'Already checked in.')
        else:
            if latf is None or lngf is None:
                AttendanceAlert.objects.create(employee=emp, kind='no_gps',
                                               note='GPS unavailable at check-in')
                messages.error(request, 'Location permission required. Attempt logged.')
                return redirect('my_attendance')
            distance = None
            if office.office_lat and office.office_lng:
                distance = _haversine(latf, lngf, float(office.office_lat), float(office.office_lng))
                radius = float(office.office_radius or 200)
                if distance > radius:
                    AttendanceAlert.objects.create(employee=emp, kind='out_of_range',
                        lat=latf, lng=lngf, distance_m=round(distance),
                        note=f'{round(distance)}m away (allowed {radius}m)')
                    messages.error(request, f'🚫 {round(distance)}m away from office. Denied & logged.')
                    return redirect('my_attendance')
            if not a:
                a = Attendance(employee=emp, date=day, status='present')
            a.check_in = datetime.now().time(); a.status = 'present'
            a.check_in_lat = latf; a.check_in_lng = lngf
            a.check_in_acc = float(acc) if acc else None
            a.check_in_distance = round(distance) if distance is not None else None
            a.save()
            dtxt = f' | {round(distance)}m from office' if distance is not None else ''
            messages.success(request, f'✅ Checked in at {a.check_in:%I:%M %p}{dtxt}')
    else:
        if not a or not a.check_in:
            messages.error(request, 'Check in first.')
        elif a.check_out:
            messages.error(request, 'Already checked out.')
        else:
            a.check_out = datetime.now().time(); a.save()
            messages.success(request, f'Checked out at {a.check_out:%I:%M %p}')
    return redirect('my_attendance')


# ---------- reports ----------
@role_required('admin', 'supervisor')
def attendance_reports(request):
    view_type = request.GET.get('type', 'daily')
    date_str = request.GET.get('date', '')
    month_str = request.GET.get('month', '')
    emp_id = request.GET.get('emp', '')
    
    if not emp_id or emp_id == 'None':
        emp_id = ''
    if not date_str or date_str == 'None':
        date_str = ''
    if not month_str or month_str == 'None':
        month_str = ''
    
    employees = Employee.objects.filter(status='active').exclude(duty_group='mojo').order_by('emp_id')

    if view_type == 'daily':
        if date_str:
            try:
                day = datetime.strptime(date_str, '%Y-%m-%d').date()
            except ValueError:
                day = date.today()
        else:
            day = date.today()
            
        atts = Attendance.objects.filter(date=day).select_related('employee')
        if emp_id:
            try:
                atts = atts.filter(employee_id=int(emp_id))
            except (ValueError, TypeError):
                pass
                
        att_map = {a.employee_id: a for a in atts}
        leave_map = {lv.employee_id: lv for lv in LeaveRequest.objects.filter(
            status='approved', from_date__lte=day, to_date__gte=day)}
        rows = []
        for e in employees:
            target = target_hours_for(e, day)
            a = att_map.get(e.id)
            worked_str = ot_str = rem_str = '-'
            if a and a.check_in:
                start = datetime.combine(day, a.check_in)
                end = datetime.combine(day, a.check_out) if a.check_out else datetime.now()
                el = max(0, (end - start).total_seconds() / 3600)
                worked_str = _fh(el)
                ot = max(0, el - target)
                ot_str = _fh(ot) if ot > 0 else '-'
                rem = max(0, target - el)
                rem_str = 'Done' if (a.check_out and rem <= 0) else _fh(rem)
            rows.append({'emp': e, 'att': a, 'leave': leave_map.get(e.id),
                         'worked_str': worked_str, 'ot_str': ot_str, 'rem_str': rem_str})
        counts = {
            'total': len(rows),
            'present': sum(1 for r in rows if r['att'] and r['att'].status == 'present'),
            'wfh': sum(1 for r in rows if r['att'] and r['att'].status == 'wfh'),
            'absent': sum(1 for r in rows if r['att'] and r['att'].status == 'absent'),
            'off': sum(1 for r in rows if r['att'] and r['att'].status == 'off'),
            'leave': LeaveRequest.objects.filter(status='approved',
                       from_date__lte=day, to_date__gte=day).count(),
        }
        return render(request, 'attendance/reports.html', {
            'view_type': 'daily', 'day': day, 'rows': rows, 'counts': counts,
            'employees': employees, 'emp_id': emp_id})

    # ===== MONTHLY VIEW =====
    if month_str:
        try:
            year, month = map(int, month_str.split('-'))
        except (ValueError, AttributeError):
            year, month = date.today().year, date.today().month
    else:
        year, month = date.today().year, date.today().month
        
    ms = date(year, month, 1)
    me = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    rows = []
    for e in employees:
        if emp_id:
            try:
                if str(e.id) != emp_id:
                    continue
            except (ValueError, TypeError):
                pass
                
        atts = Attendance.objects.filter(employee=e, date__gte=ms, date__lt=me)
        pa = atts.filter(status='present')
        
        # ✅ Monthly target (manual override support)
        total_target = monthly_target_for(e, year, month)
        total_worked = round(sum(a.worked_hours for a in pa), 1)
        # ✅ Monthly overtime: শুধু total_worked > total_target হলে
        total_ot = round(max(0, total_worked - total_target), 1)
        remaining = round(max(0, total_target - total_worked), 1)
        
        rows.append({'emp': e, 'stats': {
            'present': pa.count(),
            'wfh': atts.filter(status='wfh').count(),
            'absent': atts.filter(status='absent').count(),
            'off': atts.filter(status='off').count(),
            'leave': LeaveRequest.objects.filter(employee=e, status='approved',
                     from_date__lt=me, to_date__gte=ms).count(),
            'total_hours': total_worked,
            'total_ot': total_ot,
            'total_target': round(total_target, 1),
            'remaining': remaining,
            'total_days': (me - ms).days,
        }})
    return render(request, 'attendance/reports.html', {
        'view_type': 'monthly', 'year': year, 'month': month,
        'month_name': f'{calendar.month_name[month]} {year}',
        'rows': rows, 'employees': employees, 'emp_id': emp_id})


# ---------- CSV ----------
@role_required('admin', 'supervisor')
def download_csv(request):
    view_type = request.GET.get('type', 'daily')
    date_str = request.GET.get('date', '')
    month_str = request.GET.get('month', '')
    response = HttpResponse(content_type='text/csv')
    w = csv.writer(response)

    if view_type == 'daily':
        if date_str:
            try:
                day = datetime.strptime(date_str, '%Y-%m-%d').date()
            except ValueError:
                day = date.today()
        else:
            day = date.today()
        response['Content-Disposition'] = f'attachment; filename="attendance_{day}.csv"'
        w.writerow(['Emp ID', 'Name', 'Designation', 'Status', 'Check In',
                    'Check Out', 'Hours', 'Overtime', 'Distance'])
        am = {a.employee_id: a for a in Attendance.objects.filter(date=day)}
        for e in Employee.objects.filter(status='active').exclude(duty_group='mojo').order_by('emp_id'):
            a = am.get(e.id)
            if a and a.check_in:
                w.writerow([e.emp_id, e.name, e.designation, a.get_status_display(),
                            a.check_in.strftime('%I:%M %p') if a.check_in else '',
                            a.check_out.strftime('%I:%M %p') if a.check_out else '',
                            a.worked_hours, a.overtime_hours,
                            f'{a.check_in_distance}m' if a.check_in_distance else ''])
            else:
                w.writerow([e.emp_id, e.name, e.designation, 'No Record', '', '', '', '', ''])
    else:
        if month_str:
            try:
                y, m = map(int, month_str.split('-'))
            except (ValueError, AttributeError):
                y, m = date.today().year, date.today().month
        else:
            y, m = date.today().year, date.today().month
        ms = date(y, m, 1); me = date(y + 1, 1, 1) if m == 12 else date(y, m + 1, 1)
        response['Content-Disposition'] = f'attachment; filename="attendance_{y}_{m:02d}.csv"'
        w.writerow(['Emp ID', 'Name', 'Present', 'WFH', 'Absent', 'Off', 'Leave',
                    'Total Hours', 'Target Hours', 'Remaining', 'Overtime', 'Days'])
        for e in Employee.objects.filter(status='active').exclude(duty_group='mojo').order_by('emp_id'):
            atts = Attendance.objects.filter(employee=e, date__gte=ms, date__lt=me)
            pa = atts.filter(status='present')
            total_target = monthly_target_for(e, y, m)
            total_worked = round(sum(a.worked_hours for a in pa), 1)
            # ✅ Monthly overtime: শুধু total_worked > total_target হলে
            total_ot = round(max(0, total_worked - total_target), 1)
            remaining = round(max(0, total_target - total_worked), 1)
            w.writerow([e.emp_id, e.name, pa.count(), atts.filter(status='wfh').count(),
                        atts.filter(status='absent').count(), atts.filter(status='off').count(),
                        LeaveRequest.objects.filter(employee=e, status='approved',
                            from_date__lt=me, to_date__gte=ms).count(),
                        total_worked, round(total_target, 1), remaining,
                        total_ot, (me - ms).days])
    return response


# ---------- PDF ----------
@role_required('admin', 'supervisor')
def download_pdf(request):
    font_name = 'Helvetica'
    for reg in ('C:/Windows/Fonts/nirmala.ttf', 'C:/Windows/Fonts/vrinda.ttf'):
        if os.path.exists(reg):
            try:
                pdfmetrics.registerFont(TTFont('BengaliRep', reg))
                font_name = 'BengaliRep'
                break
            except Exception:
                continue

    view_type = request.GET.get('type', 'daily')
    date_str = request.GET.get('date', '')
    month_str = request.GET.get('month', '')
    office = OfficeSetting.load()

    response = HttpResponse(content_type='application/pdf')
    doc = SimpleDocTemplate(response, pagesize=landscape(A4),
                            topMargin=0.4 * inch, bottomMargin=0.4 * inch,
                            leftMargin=0.5 * inch, rightMargin=0.5 * inch)
    styles = getSampleStyleSheet()
    story = []
    FULL_W = 10.7 * inch

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
            max_s = 62.0
            scale = min(max_s / w, max_s / h)
            logo_flow = RLImage(buf, width=w * scale, height=h * scale)
        except Exception:
            logo_flow = ''

    c_title = ParagraphStyle('CT', parent=styles['Normal'], fontSize=17, leading=22,
                             alignment=1, textColor=colors.HexColor('#111827'))
    c_sub = ParagraphStyle('CS', parent=styles['Normal'], fontSize=9.5, leading=14,
                           alignment=1, textColor=colors.HexColor('#6b7280'))

    if logo_flow:
        lt = Table([[logo_flow]], colWidths=[FULL_W])
        lt.setStyle(TableStyle([('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                                ('BOTTOMPADDING', (0, 0), (-1, -1), 8)]))
        story.append(lt)
    story.append(Paragraph(f'<b>{office.title}</b>', c_title))
    story.append(Paragraph('Employee Management System — Attendance Report', c_sub))
    story.append(Paragraph(f'Generated: {datetime.now():%d %b, %Y}', c_sub))
    story.append(Spacer(1, 8))
    story.append(Table([['']], colWidths=[FULL_W], rowHeights=[3],
                       style=TableStyle([('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#6366f1'))])))
    story.append(Spacer(1, 16))

    tbl_style = TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#6366f1')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, -1), font_name),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#d1d5db')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8fafc')]),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ])

    cell = ParagraphStyle('CELL', parent=styles['Normal'], fontName=font_name,
                          fontSize=9, leading=12)
    c_head = ParagraphStyle('CH', parent=styles['Normal'], fontSize=12.5, leading=16,
                            alignment=1, textColor=colors.HexColor('#111827'))

    if view_type == 'daily':
        if date_str:
            try:
                day = datetime.strptime(date_str, '%Y-%m-%d').date()
            except ValueError:
                day = date.today()
        else:
            day = date.today()
        response['Content-Disposition'] = f'attachment; filename="attendance_{day}.pdf"'
        story.append(Paragraph(f'<b>Daily Attendance — {day:%d %B, %Y}</b>', c_head))
        story.append(Spacer(1, 10))
        data = [['Emp ID', 'Name', 'Status', 'Check In', 'Check Out', 'Working Hours', 'Overtime']]
        am = {a.employee_id: a for a in Attendance.objects.filter(date=day)}
        for e in Employee.objects.filter(status='active').exclude(duty_group='mojo').order_by('emp_id'):
            a = am.get(e.id)
            if a and a.check_in:
                data.append([e.emp_id, e.name, a.get_status_display(),
                             a.check_in.strftime('%I:%M %p'),
                             a.check_out.strftime('%I:%M %p') if a.check_out else '-',
                             _fh(a.worked_hours),
                             _fh(a.overtime_hours) if a.overtime_hours > 0 else '-'])
            elif a:
                data.append([e.emp_id, e.name, a.get_status_display(), '-', '-', '-', '-'])
            else:
                lv = LeaveRequest.objects.filter(status='approved', employee=e,
                       from_date__lte=day, to_date__gte=day).exists()
                data.append([e.emp_id, e.name, 'On Leave' if lv else 'No Record', '-', '-', '-', '-'])
        t = Table(data, colWidths=[0.9*inch, 2.2*inch, 1.4*inch, 1.2*inch, 1.2*inch, 1.4*inch, 1.1*inch])
    else:
        if month_str:
            try:
                y, m = map(int, month_str.split('-'))
            except (ValueError, AttributeError):
                y, m = date.today().year, date.today().month
        else:
            y, m = date.today().year, date.today().month
        ms = date(y, m, 1); me = date(y + 1, 1, 1) if m == 12 else date(y, m + 1, 1)
        response['Content-Disposition'] = f'attachment; filename="attendance_{y}_{m:02d}.pdf"'
        story.append(Paragraph(f'<b>Monthly Attendance — {calendar.month_name[m]} {y}</b>', c_head))
        story.append(Spacer(1, 10))
        data = [['Emp ID', 'Name', 'Present', 'WFH', 'Absent', 'Off', 'Leave',
                 'Hours', 'Target', 'OT', 'Remaining']]
        for e in Employee.objects.filter(status='active').exclude(duty_group='mojo').order_by('emp_id'):
            atts = Attendance.objects.filter(employee=e, date__gte=ms, date__lt=me)
            pa = atts.filter(status='present')
            total_target = monthly_target_for(e, y, m)
            total_worked = round(sum(a.worked_hours for a in pa), 1)
            # ✅ Monthly overtime: শুধু total_worked > total_target হলে
            total_ot = round(max(0, total_worked - total_target), 1)
            remaining = round(max(0, total_target - total_worked), 1)
            
            if remaining > 0:
                remaining_display = f'{remaining}h'
            else:
                remaining_display = 'Done'
            
            data.append([
                e.emp_id, 
                e.name, 
                str(pa.count()),
                str(atts.filter(status='wfh').count()),
                str(atts.filter(status='absent').count()),
                str(atts.filter(status='off').count()),
                str(LeaveRequest.objects.filter(employee=e, status='approved',
                    from_date__lt=me, to_date__gte=ms).count()),
                f'{total_worked}h', 
                f'{round(total_target, 1)}h',
                f'+{total_ot}h' if total_ot > 0 else '-',
                remaining_display
            ])
        t = Table(data, colWidths=[0.8*inch, 1.6*inch, 0.7*inch, 0.6*inch, 0.7*inch,
                                   0.6*inch, 0.6*inch, 1.0*inch, 1.0*inch, 0.8*inch, 0.9*inch])

    t.hAlign = 'CENTER'
    t.setStyle(tbl_style)
    story.append(t)

    story.append(Spacer(1, 14))
    story.append(Paragraph(
        f'<font size=8 color="#9ca3af">Computer-generated report | {office.title}</font>',
        ParagraphStyle('F', parent=styles['Normal'], alignment=1)))

    doc.build(story)
    return response


# ---------- manual duty hours ----------
@role_required('admin', 'supervisor')
def duty_hours(request):
    d = request.GET.get('date')
    day = datetime.strptime(d, '%Y-%m-%d').date() if d else date.today()

    if request.method == 'POST':
        pd = request.POST.get('date')
        if pd:
            day = datetime.strptime(pd, '%Y-%m-%d').date()
        count = 0
        for e in Employee.objects.filter(status='active').exclude(duty_group='mojo'):
            val = request.POST.get(f'hours_{e.id}', '').strip()
            ov = DutyHour.objects.filter(employee=e, date=day).first()
            if val:
                try:
                    h = float(val)
                    if ov:
                        ov.hours = h
                        ov.remark = request.POST.get(f'remark_{e.id}', '').strip()
                        ov.set_by = request.user
                        ov.save()
                    else:
                        DutyHour.objects.create(
                            employee=e, date=day, hours=h,
                            remark=request.POST.get(f'remark_{e.id}', '').strip(),
                            set_by=request.user)
                    count += 1
                except ValueError:
                    pass
            else:
                if ov:
                    ov.delete()
                    count += 1
        messages.success(request, f'✅ {day:%d %b, %Y} এর duty hours save হয়েছে ({count} জন updated).')
        return redirect(f'/attendance/duty-hours/?date={day:%Y-%m-%d}')

    emps = Employee.objects.filter(status='active').exclude(duty_group='mojo').order_by('emp_id')
    overrides = {o.employee_id: o for o in DutyHour.objects.filter(date=day)}
    rows = []
    for e in emps:
        ov = overrides.get(e.id)
        rows.append({'emp': e, 'override': ov,
                     'hours': ov.hours if ov else e.target_hours,
                     'custom': bool(ov)})
    return render(request, 'attendance/duty_hours.html', {'rows': rows, 'day': day})


# ---------- monthly targets ----------
@role_required('admin', 'supervisor')
def monthly_targets(request):
    """প্রতি employee এর মাসিক target hours সেট করা"""
    year = int(request.GET.get('year', date.today().year))
    month = int(request.GET.get('month', date.today().month))
    
    if request.GET.get('prev'):
        if month == 1:
            year -= 1; month = 12
        else:
            month -= 1
    elif request.GET.get('next'):
        if month == 12:
            year += 1; month = 1
        else:
            month += 1
    
    if request.method == 'POST':
        count = 0
        for e in Employee.objects.filter(status='active').exclude(duty_group='mojo'):
            val = request.POST.get(f'hours_{e.id}', '').strip()
            mt = MonthlyTarget.objects.filter(employee=e, year=year, month=month).first()
            if val:
                try:
                    h = float(val)
                    if mt:
                        mt.hours = h
                        mt.remark = request.POST.get(f'remark_{e.id}', '').strip()
                        mt.set_by = request.user
                        mt.save()
                    else:
                        MonthlyTarget.objects.create(
                            employee=e, year=year, month=month, hours=h,
                            remark=request.POST.get(f'remark_{e.id}', '').strip(),
                            set_by=request.user)
                    count += 1
                except ValueError:
                    pass
            else:
                if mt:
                    mt.delete()
                    count += 1
        messages.success(request, f'✅ {calendar.month_name[month]} {year} এর monthly targets save হয়েছে ({count} জন updated).')
        return redirect(f'/attendance/monthly-targets/?year={year}&month={month}')

    emps = Employee.objects.filter(status='active').exclude(duty_group='mojo').order_by('emp_id')
    overrides = {mt.employee_id: mt for mt in MonthlyTarget.objects.filter(year=year, month=month)}
    rows = []
    for e in emps:
        mt = overrides.get(e.id)
        auto_target = monthly_target_for(e, year, month)
        rows.append({
            'emp': e, 
            'override': mt,
            'hours': mt.hours if mt else auto_target,
            'auto_target': round(auto_target, 1),
            'custom': bool(mt)
        })
    
    return render(request, 'attendance/monthly_targets.html', {
        'rows': rows, 'year': year, 'month': month,
        'month_name': f'{calendar.month_name[month]} {year}'
    })