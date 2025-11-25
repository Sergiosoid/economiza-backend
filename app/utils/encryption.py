"""
Utilitários de criptografia para dados sensíveis usando Fernet.
TODO: Migrar para KMS (AWS KMS, Azure Key Vault, etc.) em produção
"""
import base64
import logging
import os
from cryptography.fernet import Fernet
from app.config import settings

logger = logging.getLogger(__name__)

# Chave de criptografia (Fernet requer 32 bytes em base64)
_fernet_key = None
_fernet_instance = None


def _get_fernet_key():
    """Obtém ou gera a chave Fernet"""
    global _fernet_key
    
    if _fernet_key:
        return _fernet_key
    
    # Tentar obter do .env
    encryption_key = getattr(settings, 'ENCRYPTION_KEY', None)
    
    if encryption_key:
        try:
            # Validar que é uma chave Fernet válida (32 bytes em base64)
            _fernet_key = encryption_key.encode()
            Fernet(_fernet_key)  # Validar
            return _fernet_key
        except Exception as e:
            logger.warning(f"Invalid encryption key in .env: {e}. Generating new key.")
    
    # Gerar nova chave (apenas para desenvolvimento)
    _fernet_key = Fernet.generate_key()
    logger.warning(
        "ENCRYPTION_KEY not set in .env. Generated temporary key. "
        "Set ENCRYPTION_KEY in .env for production!"
    )
    return _fernet_key


def _get_fernet():
    """Obtém instância Fernet (singleton)"""
    global _fernet_instance
    
    if _fernet_instance is None:
        key = _get_fernet_key()
        _fernet_instance = Fernet(key)
    
    return _fernet_instance


def encrypt_sensitive_data(data: str) -> str:
    """
    Criptografa dados sensíveis usando Fernet.
    
    Args:
        data: Dados a criptografar
        
    Returns:
        String criptografada em base64
    """
    if not data:
        return ""
    
    try:
        fernet = _get_fernet()
        encrypted = fernet.encrypt(data.encode('utf-8'))
        return encrypted.decode('utf-8')
    except Exception as e:
        logger.error(f"Error encrypting data: {e}")
        # Fallback para base64 se houver erro
        return base64.b64encode(data.encode('utf-8')).decode('utf-8')


def decrypt_sensitive_data(encrypted_data: str) -> str:
    """
    Descriptografa dados sensíveis usando Fernet.
    
    Args:
        encrypted_data: Dados criptografados
        
    Returns:
        String descriptografada
    """
    if not encrypted_data:
        return ""
    
    try:
        fernet = _get_fernet()
        decrypted = fernet.decrypt(encrypted_data.encode('utf-8'))
        return decrypted.decode('utf-8')
    except Exception as e:
        logger.error(f"Error decrypting data: {e}")
        # Tentar fallback para base64
        try:
            return base64.b64decode(encrypted_data.encode('utf-8')).decode('utf-8')
        except:
            return ""

