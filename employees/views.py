import os
import io
import textwrap
import datetime

from django.contrib import messages
from django.contrib.auth.models import User
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import render, redirect, get_object_or_404

from accounts.models import Profile
from accounts.decorators import role_required
from .models import Employee, OfficeSetting
from .forms import EmployeeForm

from PIL import Image as PILImage
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.colors import HexColor, white
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont


PDF_FONT = 'Helvetica'
PDF_FONT_BOLD = 'Helvetica-Bold'


def _register_bengali_font():
    global PDF_FONT, PDF_FONT_BOLD
    for reg, bold in [('C:/Windows/Fonts/nirmala.ttf', 'C:/Windows/Fonts/nirmalab.ttf'),
                      ('C:/Windows/Fonts/vrinda.ttf', None)]:
        if os.path.exists(reg):
            try:
                pdfmetrics.registerFont(TTFont('Bengali', reg))
                PDF_FONT = 'Bengali'
                PDF_FONT_BOLD = 'Bengali'
                if bold and os.path.exists(bold):
                    pdfmetrics.registerFont(TTFont('BengaliBold', bold))
                    PDF_FONT_BOLD = 'BengaliBold'
                return
            except Exception:
                continue


_register_bengali_font()


def _ensure_login(emp):
    if emp.user:
        u = emp.user
        u.first_name = emp.name
        if emp.email:
            u.email = emp.email
        u.save()
        return None

    username = emp.emp_id.lower().replace('-', '').replace('_', '')

    base, i = username, 1
    while User.objects.filter(username__iexact=username).exists():
        username = f'{base}{i}'
        i += 1

    user = User.objects.create_user(
        username=username, email=emp.email or '',
        password='employee123', first_name=emp.name
    )
    prof, created = Profile.objects.get_or_create(user=user)
    if created:
        prof.role = 'employee'
        prof.save()
    emp.user = user
    emp.save()
    return username


@role_required('admin')
def employee_list(request):
    q = request.GET.get('q', '')
    employees = Employee.objects.all().order_by('emp_id')
    if q:
        employees = employees.filter(
            Q(name__icontains=q) | Q(emp_id__icontains=q) |
            Q(department__icontains=q) | Q(mobile__icontains=q))
    return render(request, 'employees/list.html', {'employees': employees, 'q': q})


@role_required('admin')
def employee_form(request, pk=None):
    emp = get_object_or_404(Employee, pk=pk) if pk else None
    if request.method == 'POST':
        form = EmployeeForm(request.POST, request.FILES, instance=emp)
        if form.is_valid():
            obj = form.save()
            new_user = _ensure_login(obj)
            if new_user:
                messages.success(request, f'{obj.name} saved. Login: {new_user} / employee123')
            else:
                messages.success(request, f'{obj.name} saved ({obj.emp_id}).')
            return redirect('employee_list')
        messages.error(request, 'Please fix the errors below.')
    else:
        form = EmployeeForm(instance=emp)
    return render(request, 'employees/form.html', {'form': form, 'emp': emp})


@role_required('admin')
def employee_delete(request, pk):
    emp = get_object_or_404(Employee, pk=pk)
    if request.method == 'POST':
        name = emp.name
        if emp.user:
            emp.user.delete()
        emp.delete()
        messages.success(request, f'{name} deleted.')
    return redirect('employee_list')


@role_required('admin', 'supervisor')
def employee_biodata(request, pk):
    emp = get_object_or_404(Employee, pk=pk)
    office = OfficeSetting.load()

    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="Biodata_{emp.emp_id}.pdf"'
    c = canvas.Canvas(response, pagesize=A4)
    W, H = A4

    INDIGO = HexColor('#6366f1')
    DARK = HexColor('#1e293b')
    MUTED = HexColor('#64748b')
    LINE = HexColor('#e2e8f0')
    BG_LIGHT = HexColor('#eef2ff')
    F, FB = PDF_FONT, PDF_FONT_BOLD

    logo_reader = None
    if office.logo:
        try:
            img = PILImage.open(office.logo.path).convert('RGBA')
            bg = PILImage.new('RGBA', img.size, (255, 255, 255, 255))
            bg.alpha_composite(img)
            buf = io.BytesIO()
            bg.convert('RGB').save(buf, format='PNG')
            buf.seek(0)
            logo_reader = ImageReader(buf)
        except Exception:
            logo_reader = None

    if logo_reader:
        c.setFillColor(white); c.setStrokeColor(LINE); c.setLineWidth(0.8)
        c.roundRect(36, H - 72, 48, 48, 8, fill=1, stroke=1)
        c.drawImage(logo_reader, 40, H - 68, 40, 40,
                    preserveAspectRatio=True, anchor='c')
        lx = 98
    else:
        lx = 36

    c.setFillColor(DARK); c.setFont(FB, 17)
    c.drawString(lx, H - 44, office.title)
    c.setFillColor(MUTED); c.setFont(F, 7.5)
    c.drawString(lx, H - 60, 'E M P L O Y E E   B I O D A T A')

    chip_w = c.stringWidth(emp.emp_id, FB, 9.5) + 22
    c.setFillColor(BG_LIGHT)
    c.roundRect(W - 36 - chip_w, H - 50, chip_w, 18, 9, fill=1, stroke=0)
    c.setFillColor(HexColor('#4338ca')); c.setFont(FB, 9.5)
    c.drawCentredString(W - 36 - chip_w / 2, H - 45, emp.emp_id)
    c.setFillColor(MUTED); c.setFont(F, 8)
    c.drawRightString(W - 36, H - 64, datetime.date.today().strftime('%d %b, %Y'))

    c.setFillColor(INDIGO); c.rect(0, H - 90, W, 3, fill=1, stroke=0)
    c.setFillColor(LINE); c.rect(0, H - 92, W, 0.8, fill=1, stroke=0)

    y0 = H - 120
    px, py, pw, ph = 36, y0 - 106, 86, 106
    c.setFillColor(BG_LIGHT); c.roundRect(px, py, pw, ph, 6, fill=1, stroke=0)
    if emp.photo:
        try:
            c.drawImage(ImageReader(emp.photo.path), px + 3, py + 3, pw - 6, ph - 6,
                        preserveAspectRatio=True, anchor='c', mask='auto')
        except Exception:
            pass
    c.setStrokeColor(INDIGO); c.setLineWidth(1)
    c.roundRect(px, py, pw, ph, 6, fill=0, stroke=1)

    tx = 140
    c.setFillColor(DARK); c.setFont(FB, 16); c.drawString(tx, y0 - 16, emp.name)
    c.setFillColor(INDIGO); c.setFont(FB, 10); c.drawString(tx, y0 - 32, emp.designation)
    c.setFillColor(MUTED); c.setFont(F, 9); c.drawString(tx, y0 - 46, emp.department)

    chip_y = y0 - 66
    def chip(x, text, bg, fg):
        c.setFillColor(HexColor(bg))
        w = c.stringWidth(text, F, 7.5) + 14
        c.roundRect(x, chip_y, w, 16, 8, fill=1, stroke=0)
        c.setFillColor(HexColor(fg)); c.setFont(F, 7.5)
        c.drawString(x + 7, chip_y + 5, text)
        return x + w + 6

    nx = chip(tx, emp.get_duty_group_display(), '#eef2ff', '#4338ca')
    nx = chip(nx, emp.get_status_display(),
              '#d1fae5' if emp.status == 'active' else '#fee2e2',
              '#047857' if emp.status == 'active' else '#b91c1c')
    chip(nx, f'Joined {emp.joining_date.strftime("%d %b, %Y")}', '#fef3c7', '#92400e')

    def section(title, sy):
        c.setFillColor(INDIGO); c.rect(36, sy - 1, 3, 10, fill=1, stroke=0)
        c.setFillColor(DARK); c.setFont(FB, 10); c.drawString(46, sy, title)
        c.setStrokeColor(LINE); c.setLineWidth(0.6); c.line(36, sy - 8, W - 36, sy - 8)
        return sy - 22

    def field(label, value, x, sy):
        c.setFillColor(MUTED); c.setFont(F, 6.8); c.drawString(x, sy, label.upper())
        c.setFillColor(DARK); c.setFont(F, 9); c.drawString(x, sy - 12, value or '-')

    col1, col2 = 36, 306
    sy = y0 - 132

    sy = section('Employment Information', sy)
    field('Employee ID', emp.emp_id, col1, sy)
    field('Joining Date', emp.joining_date.strftime('%d %b, %Y'), col2, sy)
    sy -= 26
    field('Department', emp.department, col1, sy)
    field('Designation', emp.designation, col2, sy)
    sy -= 26
    field('Duty Group', emp.get_duty_group_display(), col1, sy)
    field('Monthly Salary', f'BDT {emp.salary:,.0f}', col2, sy)
    sy -= 32

    sy = section('Contact Information', sy)
    field('Mobile', emp.mobile, col1, sy)
    field('Email', emp.email, col2, sy)
    sy -= 26

    def emergency_line(name, mobile):
        if name and mobile:
            return f'{name} — {mobile}'
        if name:
            return name
        if mobile:
            return mobile
        return '-'
    field('Emergency 1', emergency_line(emp.emergency1_name, emp.emergency1_mobile), col1, sy)
    field('Emergency 2', emergency_line(emp.emergency2_name, emp.emergency2_mobile), col2, sy)
    sy -= 26
    c.setFillColor(MUTED); c.setFont(F, 6.8); c.drawString(col1, sy, 'ADDRESS')
    c.setFillColor(DARK); c.setFont(F, 9)
    yy = sy - 12
    for ln in textwrap.wrap(emp.address or '-', 95)[:2]:
        c.drawString(col1, yy, ln)
        yy -= 12
    sy = yy - 10

    sy = section('Documents & Status', sy)
    field('Employee NID', emp.nid, col1, sy)
    field('Status', emp.get_status_display(), col2, sy)
    sy -= 26
    field("Father's NID", emp.father_nid, col1, sy)
    field("Mother's NID", emp.mother_nid, col2, sy)

    c.setStrokeColor(LINE); c.setLineWidth(0.6); c.line(36, 74, W - 36, 74)
    c.setFillColor(MUTED); c.setFont(F, 7)
    c.drawString(36, 62, f'Computer-generated biodata | {office.title} | '
                         f'Generated on {datetime.date.today().strftime("%d %b, %Y")}')
    c.setStrokeColor(MUTED); c.setLineWidth(0.7); c.line(W - 160, 92, W - 36, 92)
    c.setFont(F, 8); c.drawCentredString(W - 98, 81, 'Authorized Signature')

    c.showPage()
    c.save()
    return response