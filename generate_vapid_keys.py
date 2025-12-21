from base64 import urlsafe_b64encode

from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization


def b64url_nopad(data: bytes) -> str:
    """Return URL-safe base64 without padding (=), as required by VAPID/webpush."""

    return urlsafe_b64encode(data).rstrip(b"=").decode("utf-8")


def main() -> None:
    # Generate a new EC P-256 key pair suitable for VAPID
    private_key = ec.generate_private_key(ec.SECP256R1())
    public_key = private_key.public_key()

    # Export in the format expected by web push (unpadded base64url)
    raw_private = private_key.private_numbers().private_value.to_bytes(32, "big")
    raw_public = public_key.public_bytes(
        encoding=serialization.Encoding.X962,
        format=serialization.PublicFormat.UncompressedPoint,
    )

    print("PUBLIC KEY:\n" + b64url_nopad(raw_public))
    print("\nPRIVATE KEY:\n" + b64url_nopad(raw_private))


if __name__ == "__main__":
    main()
    
