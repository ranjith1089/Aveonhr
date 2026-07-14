"""Authentication backend that accepts either username or email address.

Users kept forgetting which username they chose at signup - their email is
the identifier they actually remember, so the login form accepts both.
"""
from django.contrib.auth.backends import ModelBackend
from django.contrib.auth.models import User


class EmailOrUsernameBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        if not username or not password:
            return None
        user = User.objects.filter(username__iexact=username).first()
        if user is None and "@" in username:
            # Emails are unique at signup; guard against legacy duplicates.
            matches = User.objects.filter(email__iexact=username)
            user = matches.first() if matches.count() == 1 else None
        if user and user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
