"""
Cryptographic utilities for tests.

Provides signature generation functions and re-exports common crypto utilities.
"""

import json
import base64
import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import hashes

# Re-export from common for convenience
from common.jwt_utils import generate_ecdsa_key_pair, serialize_private_key, serialize_public_key
from common.security_utils import generate_client_key_id


def generate_push_signature(private_key, distributor_package: str, push_endpoint: str, timestamp: int) -> str:
    """
    Generate ECDSA signature for push registration.

    Message format: [distributor_package, push_endpoint, timestamp]
    """
    message_data = [distributor_package, push_endpoint, timestamp]
    message = json.dumps(message_data, separators=(',', ':'), ensure_ascii=False, sort_keys=True)

    signature_bytes = private_key.sign(
        message.encode('utf-8'),
        ec.ECDSA(hashes.SHA256())
    )

    return base64.b64encode(signature_bytes).decode('ascii')
