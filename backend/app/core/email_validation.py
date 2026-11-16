from typing import Annotated

from pydantic import AfterValidator, EmailStr
from pydantic_core import PydanticCustomError
from tld import get_tld


def _require_public_email_domain(email: str) -> str:
    domain = email.rsplit("@", 1)[1]
    suffix = get_tld(domain, fix_protocol=True, fail_silently=True, search_private=False)
    if suffix is None or domain == suffix:
        raise PydanticCustomError(
            "email_domain",
            "Email domain must have a recognized public suffix and a registrable name.",
        )
    return email


PublicEmail = Annotated[EmailStr, AfterValidator(_require_public_email_domain)]
