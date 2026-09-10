import os
import a.b as c
from x.y import z, w


async def top(a, b=1):
    """Top docstring."""
    def nested():
        """Nested doc."""
        return 1

    class Inner:
        """Inner doc."""

        def method(self):
            return 2

    return nested()


class Foo(Base):
    """Class doc."""

    def bar(self):
        return 3
