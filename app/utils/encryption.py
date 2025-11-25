"""
Utilitários de criptografia para dados sensíveis
"""
import base64
import logging

logger = logging.getLogger(__name__)


def encrypt_sensitive_data(data: str) -> str:
    """
    Criptografa dados sensíveis usando base64 (temporário).
    TODO: Implementar criptografia real usando KMS (AWS KMS, Azure Key Vault, etc.)
    """
    if not data:
        return ""
    encoded = base64.b64encode(data.encode('utf-8')).decode('utf-8')
    return encoded


def decrypt_sensitive_data(encrypted_data: str) -> str:
    """
    Descriptografa dados sensíveis.
    TODO: Implementar descriptografia real usando KMS
    """
    if not encrypted_data:
        return ""
    try:
        decoded = base64.b64decode(encrypted_data.encode('utf-8')).decode('utf-8')
        return decoded
    except Exception as e:
        logger.error(f"Error decrypting data: {e}")
        return ""

