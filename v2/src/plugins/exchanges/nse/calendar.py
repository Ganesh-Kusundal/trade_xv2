"""NSE trading calendar — weekends + Indian market holidays."""

from __future__ import annotations

from datetime import date

# NSE holidays for 2024 and 2025
NSE_HOLIDAYS: set[date] = {
    # 2024
    date(2024, 1, 26),   # Republic Day
    date(2024, 3, 25),   # Holi
    date(2024, 3, 29),   # Good Friday
    date(2024, 4, 11),   # Id-ul-Fitr
    date(2024, 4, 14),   # Dr. Ambedkar Jayanti
    date(2024, 4, 17),   # Ram Navami
    date(2024, 4, 21),   # Shri Mahavir Jayanti
    date(2024, 5, 1),    # Maharashtra Day
    date(2024, 5, 23),   # Buddha Purnima
    date(2024, 6, 17),   # Id-ul-Adha (Bakri Eid)
    date(2024, 7, 17),   # Muharram
    date(2024, 8, 15),   # Independence Day
    date(2024, 8, 26),   # Janmashtami
    date(2024, 9, 7),    # Ganesh Chaturthi
    date(2024, 10, 2),   # Mahatma Gandhi Jayanti
    date(2024, 10, 12),  # Dussehra
    date(2024, 11, 1),   # Diwali Laxmi Pujan
    date(2024, 11, 15),  # Guru Nanak Jayanti
    date(2024, 12, 25),  # Christmas
    # 2025
    date(2025, 1, 26),   # Republic Day
    date(2025, 2, 26),   # Maha Shivaratri
    date(2025, 3, 14),   # Holi
    date(2025, 3, 31),   # Id-ul-Fitr
    date(2025, 4, 10),   # Shri Mahavir Jayanti
    date(2025, 4, 14),   # Dr. Ambedkar Jayanti
    date(2025, 4, 18),   # Good Friday
    date(2025, 5, 1),    # Maharashtra Day
    date(2025, 5, 14),   # Buddha Purnima
    date(2025, 6, 7),    # Id-ul-Adha (Bakri Eid)
    date(2025, 7, 6),    # Muharram
    date(2025, 8, 15),   # Independence Day
    date(2025, 8, 27),   # Janmashtami
    date(2025, 9, 27),   # Dussehra
    date(2025, 10, 2),   # Mahatma Gandhi Jayanti
    date(2025, 10, 21),  # Diwali Laxmi Pujan
    date(2025, 11, 5),   # Guru Nanak Jayanti
    date(2025, 12, 25),  # Christmas
}


class NSETradingCalendar:
    """NSE calendar: weekends + Indian market holidays."""

    def __init__(self, holidays: set[date] | None = None) -> None:
        self._holidays = holidays if holidays is not None else NSE_HOLIDAYS

    def is_trading_day(self, day: date) -> bool:
        if day.weekday() >= 5:  # Saturday=5, Sunday=6
            return False
        return day not in self._holidays
