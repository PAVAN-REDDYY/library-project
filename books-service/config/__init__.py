import sys
from pathlib import Path

# Repo root on sys.path so `import common.jwt_auth` works no matter which
# entrypoint (manage.py, wsgi.py, celery.py) triggered settings loading first.
# Appended (not inserted at 0) so it never shadows this service's own
# top-level packages (e.g. `books`) with the same-named packages from the
# monolith at repo root that's being retired - this service's own directory
# must win that lookup.
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(_REPO_ROOT))

# Load the shared .env from the repo root - same file for all three services,
# since JWT_SECRET in particular must be identical across them. Safe to skip
# if python-dotenv isn't installed yet or .env doesn't exist (e.g. a fresh
# checkout before the developer has copied .env.example to .env).
try:
    from dotenv import load_dotenv
    load_dotenv(_REPO_ROOT / '.env')
except ImportError:
    pass

# Use PyMySQL as the MySQL driver. mysqlclient is the usual choice but it needs
# a C compiler and often won't install on Windows, whereas PyMySQL is pure
# Python. It registers itself under the "MySQLdb" name that Django looks for.
try:
    import pymysql

    # Django rejects anything below mysqlclient 1.4.3, and PyMySQL reports a
    # lower number, so bump the version it advertises before handing it over.
    pymysql.version_info = (1, 4, 6, 'final', 0)
    pymysql.install_as_MySQLdb()
except ImportError:
    pass
