"""
Root package for the automation framework.

Creating this file marks the ``enterprise_automation_framework_final``
directory as a Python package and enables relative imports between
subpackages such as ``utils``, ``web``, ``mobile``, ``api`` and
``llm_integration``.  Without this file Python would treat the
directory as a namespace package and ``..`` relative imports would
fail when executing modules outside of the package context.
"""

__all__ = []