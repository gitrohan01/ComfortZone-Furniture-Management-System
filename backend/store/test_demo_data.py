from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.contrib.auth.models import Group, Permission
from django.test import SimpleTestCase, TestCase

from store.management.commands.provision_staff_roles import ROLE_CODENAMES


class DemoDataCommandSafetyTests(SimpleTestCase):
    def test_seed_command_refuses_non_demo_settings(self):
        with self.assertRaisesMessage(CommandError, '--settings=config.demo_settings'):
            call_command('seed_demo_data', stdout=StringIO())


class StaffRoleProvisioningTests(TestCase):
    def test_staff_groups_have_exact_least_privilege_permissions(self):
        extra_permission = Permission.objects.filter(
            content_type__app_label='store',
        ).first()
        call_command('provision_staff_roles', stdout=StringIO())
        if extra_permission:
            Group.objects.get(name='Reports-only Staff').permissions.add(extra_permission)
        call_command('provision_staff_roles', stdout=StringIO())

        for role, expected_codenames in ROLE_CODENAMES.items():
            with self.subTest(role=role):
                group = Group.objects.get(name=role)
                actual = set(group.permissions.values_list(
                    'content_type__app_label', 'codename',
                ))
                expected = {('store', codename) for codename in expected_codenames}
                self.assertEqual(actual, expected)

    def test_administrator_group_receives_store_and_account_permissions(self):
        call_command('provision_staff_roles', stdout=StringIO())
        group = Group.objects.get(name='Administrator')
        expected = set(Permission.objects.filter(
            content_type__app_label='store',
        ).values_list('content_type__app_label', 'codename'))
        expected.update(Permission.objects.filter(
            content_type__app_label='auth',
            content_type__model__in=('user', 'group'),
        ).values_list('content_type__app_label', 'codename'))
        actual = set(group.permissions.values_list(
            'content_type__app_label', 'codename',
        ))
        self.assertEqual(actual, expected)
