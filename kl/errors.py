"""The errors the service raises; the API turns each into an RFC 9457 problem."""


class Problem(Exception):
    status = 400
    title = "Bad request"

    def __init__(self, detail: str, problems=None, **extra):
        super().__init__(detail)
        self.detail = detail
        self.problems = list(problems or [])
        self.extra = extra

    def body(self) -> dict:
        return {"type": f"https://kl.dev/problems/{self.__class__.__name__.lower()}", "title": self.title,
                "status": self.status, "detail": self.detail, **({"problems": self.problems} if self.problems else {}),
                **self.extra}


class Unauthorized(Problem):
    status, title = 401, "Not signed in"


class Forbidden(Problem):
    status, title = 403, "Not allowed"


class NotFound(Problem):
    status, title = 404, "Not found"


class Conflict(Problem):
    status, title = 409, "Conflict"


class Gone(Problem):
    status, title = 410, "Gone"


class Invalid(Problem):
    status, title = 422, "Cannot be done"


class TooMany(Problem):
    status, title = 429, "Over a limit"


class TooLarge(Problem):
    status, title = 413, "Too large"
