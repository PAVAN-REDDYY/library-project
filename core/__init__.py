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
