from employees.models import Employee, OfficeSetting


def user_employee(request):
    """প্রতিটি template এ user_emp এবং office পাঠাবে"""
    context = {
        'user_emp': None,
        'office': OfficeSetting.load(),
        'role_key': 'employee',
        'role_label': 'Employee',
    }

    if request.user.is_authenticated:
        emp = getattr(request.user, 'employee', None)
        context['user_emp'] = emp

        if hasattr(request.user, 'profile'):
            role = request.user.profile.role
            context['role_key'] = role
            context['role_label'] = role.title()

    return context