from datetime import datetime, timedelta


def generate_dates(date_str: str) -> list[datetime]:
    """Generates a list of datetime objects from the input."""
    dates = date_str.split("/")
    if len(dates) > 2:
        raise ValueError(f"Unsupported date format: {date_str}. Only input one date or two dates seperated by '/'.")

    dt_start, precision = get_date_from_str(dates[0])

    if len(dates) == 1:
        # Determine end time based on precision if no end was given
        if precision == 1:
            dt_end = dt_start.replace(year=dt_start.year + 1)
        elif precision == 2:
            month = dt_start.month + 1 if dt_start.month < 12 else 1
            year = dt_start.year if dt_start.month < 12 else dt_start.year + 1
            dt_end = dt_start.replace(year=year, month=month, day=1)
        elif precision == 3:
            dt_end = dt_start + timedelta(days=1)
        else:
            dt_end = dt_start + timedelta(hours=1)
    else:
        dt_end, _ = get_date_from_str(dates[1])
        if dt_end < dt_start:
            raise ValueError(f"Unsupported date format: {date_str}. End date before start date.")

    # Generate list of hour segments
    hours = []
    current = dt_start
    final_date = datetime(2022, 12, 31, 23, 00)
    while current < dt_end and current <= final_date:
        if datetime(2022, 3, 27, 2, 0) <= current < datetime(2022, 3, 27, 3, 0):
            current += timedelta(hours=1)
            continue
        hours.append(current)
        current += timedelta(hours=1)

    return hours


def get_date_from_str(date_str: str) -> tuple[datetime, int]:
    # Supported formats:
    formats = {
        1: "%Y",
        2: "%Y-%m",
        3: "%Y-%m-%d",
        4: "%Y-%m-%dT%H"
    }

    parts = date_str.replace("T", "-").replace(":", "-").split("-")
    precision = len(parts)

    if precision not in formats:
        raise ValueError(f"Unsupported date format: {date_str}")

    dt = datetime.strptime(date_str, formats[precision])
    dt.replace(minute=0)  # Floor down to exact hour
    return dt, precision
