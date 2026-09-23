from datetime import date, datetime
from decimal import Decimal


def safe(val):
    """Convert date/Decimal to string/float for JSON serialization."""
    if isinstance(val, (date, datetime)):
        return val.isoformat()
    if isinstance(val, Decimal):
        return float(val)
    return val
