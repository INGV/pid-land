



class Utils:

    # ---------------------------
    # Utils
    # ---------------------------
    def is_date_only(self, s):
        return s is not None and "T" not in s

    # ---------------------------
    # Time Handler
    # ---------------------------
    def _normalize_time(self, t, is_end=False):
        """
        Accept:
        - YYYY-MM-DD
        - YYYY-MM-DDTHH:MM
        - YYYY-MM-DDTHH:MM:SS

        Return a coherent datetime
        """

        if "T" not in t:
            # only date
            if is_end:
                return datetime.fromisoformat(t + "T23:59:59")
            else:
                return datetime.fromisoformat(t + "T00:00:00")

        return datetime.fromisoformat(t)

        # ---------------------------
        # time-only
        # ---------------------------

    def _parse_time_only(self, t_str, base_day):
        # t_str tipo "10:00:00"
        h, m, s = map(float, t_str.split(":"))
        return base_day + h * 3600 + m * 60 + s