# Copyright 2026 Avosdim
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html)


def job(*args, **kwargs):
    """Compatibility no-op for the removed queue_job @job decorator."""

    def decorator(func):
        return func

    if args and callable(args[0]) and not kwargs:
        return args[0]
    return decorator


def related_action(*args, **kwargs):
    """Compatibility no-op for the removed queue_job @related_action decorator."""

    def decorator(func):
        return func

    if args and callable(args[0]) and not kwargs:
        return args[0]
    return decorator


class NothingToDoJob(Exception):
    """Compatibility replacement for the removed queue_job NothingToDoJob."""
