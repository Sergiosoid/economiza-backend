"""
Utilitários para extrair chave de acesso ou URL de QR codes
"""
import re
from typing import Optional, Tuple


def extract_key_or_url(qr_text: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Extrai chave de acesso ou URL do texto do QR code.
    
    Args:
        qr_text: Texto do QR code
        
    Returns:
        Tupla (url, access_key) onde apenas um será não-None
        
    Raises:
        ValueError: Se não encontrar nem URL nem chave de acesso
    """
    url = None
    access_key = None
    
    # Verificar se contém URL (http:// ou https://)
    url_pattern = r'https?://[^\s]+'
    url_match = re.search(url_pattern, qr_text)
    if url_match:
        url = url_match.group(0)
    
    # Se não encontrou URL, buscar chave de acesso (44 dígitos)
    if not url:
        key_pattern = r'\d{44}'
        key_match = re.search(key_pattern, qr_text)
        if key_match:
            access_key = key_match.group(0)
    
    if not url and not access_key:
        raise ValueError("QR code não contém URL válida nem chave de acesso (44 dígitos)")
    
    return url, access_key

