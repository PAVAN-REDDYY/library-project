#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
import sys
from pathlib import Path

# Repo root must be on sys.path so `import common.jwt_auth` resolves regardless
# of the current working directory this is invoked from. Appended (not
# inserted at 0) so it never shadows this service's own top-level packages
# (e.g. `users`) with the same-named packages from the monolith at repo root
# that's being retired - this service's own directory must win that lookup.
sys.path.append(str(Path(__file__).resolve().parent.parent))


def main():
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == '__main__':
    main()
