from hashlib import sha256


def digest(value):
    return sha256(value.encode()).hexdigest()
