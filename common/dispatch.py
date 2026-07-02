"""
Celery's own task_always_eager setting only short-circuits *locally
registered* tasks (i.e. calling .delay()/.apply_async() on a task object this
process actually defined). Cross-service dispatch here always goes through
send_task() by name instead - deliberately, so no service ever needs to
import another service's task code - but send_task() does NOT check
task_always_eager, and unconditionally tries to publish to the broker. That
breaks running/testing a service standalone with no broker present, which is
the whole point of defaulting CELERY_TASK_ALWAYS_EAGER to True.

So: route every cross-service send_task call through this instead. In eager/
standalone mode there's no broker and also no other service listening, so the
notification is simply dropped - which is safe, since the same thing would be
true of a real deployment where the other service is down. Only send for
real once a real broker is configured (CELERY_TASK_ALWAYS_EAGER=0).
"""
from django.conf import settings


def send_task(app, name, args, queue):
    if getattr(settings, 'CELERY_TASK_ALWAYS_EAGER', False):
        return None
    return app.send_task(name, args=args, queue=queue)
