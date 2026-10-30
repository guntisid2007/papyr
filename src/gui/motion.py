"""Whether Papyr may animate. macOS users can ask for less motion in Accessibility settings."""
import subprocess
import sys
from functools import cache


@cache
def animations_enabled() -> bool:
    """Read once, best effort. Anything unexpected leaves animations on."""
    if sys.platform != "darwin":
        return True
    try:
        result = subprocess.run(["defaults", "read", "com.apple.universalaccess", "reduceMotion"],
                                capture_output=True, text=True, timeout=2)
    except (OSError, subprocess.SubprocessError):
        return True
    return result.stdout.strip() != "1"
