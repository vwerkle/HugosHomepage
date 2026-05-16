"""
Run from the project root to send a test SMS and trigger the birthday check.

    venv\Scripts\python test_birthdays.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from blueprints.birthdays.scheduler import _send_sms, _check_birthdays

if __name__ == '__main__':
    _send_sms("Birthday tracker test - working!")
    print("Test SMS sent.")

    print("Running birthday check...")
    _check_birthdays()
    print("Done.")
