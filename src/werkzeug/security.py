import hashlib
import hmac
import os
import posixpath
import secrets
import typing as t

if t.TYPE_CHECKING:
    pass

SALT_CHARS = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
DEFAULT_PBKDF2_ITERATIONS = 260000

_os_alt_seps: t.List[str] = list(
    sep for sep in [os.path.sep, os.path.altsep] if sep is not None and sep != "/"
)


def safe_str_cmp(a: str, b: str) -> bool:
    """This function compares strings in somewhat constant time. This
    requires that the length of at least one string is known in advance.

    Returns `True` if the two strings are equal, or `False` if they are not.
    """

    if isinstance(a, str):
        a = a.encode("utf-8")  # type: ignore

    if isinstance(b, str):
        b = b.encode("utf-8")  # type: ignore

    return hmac.compare_digest(a, b)


def gen_salt(length: int) -> str:
    """Generate a random string of SALT_CHARS with specified ``length``."""
    if length <= 0:
        raise ValueError("Salt length must be positive")

    return "".join(secrets.choice(SALT_CHARS) for _ in range(length))


def _hash_internal(method: str, salt: str, password: str) -> t.Tuple[str, str]:
    """Internal password hash helper.  Supports plaintext without salt,
    unsalted and salted passwords.  In case salted passwords are used
    hmac is used.
    """
    if method == "plain":
        return password, method

    salt = salt.encode("utf-8")
    password = password.encode("utf-8")

    if method.startswith("pbkdf2:"):
        if not salt:
            raise ValueError("Salt is required for PBKDF2")

        args = method[7:].split(":")

        if len(args) not in (1, 2):
            raise ValueError("Invalid number of arguments for PBKDF2")

        method = args.pop(0)
        iterations = int(args[0] or 0) if args else DEFAULT_PBKDF2_ITERATIONS
        return (
            hashlib.pbkdf2_hmac(method, password, salt, iterations).hex(),
            f"pbkdf2:{method}:{iterations}",
        )

    if salt:
        return hmac.new(salt, password, method).hexdigest(), method

    return hashlib.new(method, password).hexdigest(), method


def generate_password_hash(
    password: str, method: str = "pbkdf2:sha256", salt_length: int = 16
) -> str:
    """Hash a password with the given method and salt with a string of
    the given length. The format of the string returned includes the method
    that was used so that :func:`check_password_hash` can check the hash.

    The format for the hashed string looks like this::

        method$salt$hash

    This method can **not** generate unsalted passwords but it is possible
    to set param method='plain' in order to enforce plaintext passwords.
    If a salt is used, hmac is used internally to salt the password.

    If PBKDF2 is wanted it can be enabled by setting the method to
    ``pbkdf2:method:iterations`` where iterations is optional::

        pbkdf2:sha256:80000$salt$hash
        pbkdf2:sha256$salt$hash

    :param password: the password to hash.
    :param method: the hash method to use (one that hashlib supports). Can
                   optionally be in the format ``pbkdf2:method:iterations``
                   to enable PBKDF2.
    :param salt_length: the length of the salt in letters.
    """
    salt = gen_salt(salt_length) if method != "plain" else ""
    h, actual_method = _hash_internal(method, salt, password)
    return f"{actual_method}${salt}${h}"


def check_password_hash(pwhash: str, password: str) -> bool:
    """Check a password against a given salted and hashed password value.
    In order to support unsalted legacy passwords this method supports
    plain text passwords, md5 and sha1 hashes (both salted and unsalted).

    Returns `True` if the password matched, `False` otherwise.

    :param pwhash: a hashed string like returned by
                   :func:`generate_password_hash`.
    :param password: the plaintext password to compare against the hash.
    """
    if pwhash.count("$") < 2:
        return False

    method, salt, hashval = pwhash.split("$", 2)
    return hmac.compare_digest(_hash_internal(method, salt, password)[0], hashval)


def safe_join(directory: str, *pathnames: str) -> t.Optional[str]:
    """Safely join zero or more untrusted path components to a base
    directory to avoid escaping the base directory.

    :param directory: The trusted base directory.
    :param pathnames: The untrusted path components relative to the
        base directory.
    :return: A safe path, otherwise ``None``.
    """
    if not directory:
        # Ensure we end up with ./path if directory="" is given,
        # otherwise the first untrusted part could become trusted.
        directory = "."

    parts = [directory]

    for filename in pathnames:
        if filename != "":
            filename = posixpath.normpath(filename)

        if (
            any(sep in filename for sep in _os_alt_seps)
            or os.path.isabs(filename)
            or filename == ".."
            or filename.startswith("../")
        ):
            return None

        parts.append(filename)

    return posixpath.join(*parts)
