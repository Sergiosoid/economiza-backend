"""
Utilitários para extrair chave de acesso ou URL de QR codes
Com validação e sanitização de segurança
"""
import re
import logging
from typing import Optional, Tuple
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# Limites de segurança
MAX_QR_TEXT_LENGTH = 2000
MAX_URL_LENGTH = 500
MAX_ACCESS_KEY_LENGTH = 44

# Caracteres perigosos que podem indicar scripts ou payloads maliciosos
DANGEROUS_PATTERNS = [
    r'<script',
    r'javascript:',
    r'onerror=',
    r'onload=',
    r'data:text/html',
    r'vbscript:',
]


def sanitize_qr_text(qr_text: str) -> str:
    """
    Sanitiza o texto do QR code removendo caracteres perigosos.
    
    Args:
        qr_text: Texto do QR code
        
    Returns:
        Texto sanitizado
    """
    if not qr_text:
        return ""
    
    # Remover caracteres de controle (exceto \n, \r, \t)
    sanitized = re.sub(r'[\x00-\x08\x0B-\x0C\x0E-\x1F\x7F]', '', qr_text)
    
    # Normalizar espaços múltiplos
    sanitized = re.sub(r'\s+', ' ', sanitized)
    
    # Strip
    sanitized = sanitized.strip()
    
    return sanitized


def validate_qr_text(qr_text: str) -> None:
    """
    Valida o texto do QR code para segurança.
    
    Args:
        qr_text: Texto do QR code
        
    Raises:
        ValueError: Se o QR code for inválido ou perigoso
    """
    if not qr_text or not qr_text.strip():
        raise ValueError("QR code não pode ser vazio")
    
    # Verificar tamanho máximo
    if len(qr_text) > MAX_QR_TEXT_LENGTH:
        raise ValueError(f"QR code muito longo (máximo {MAX_QR_TEXT_LENGTH} caracteres)")
    
    # Verificar padrões perigosos
    qr_lower = qr_text.lower()
    for pattern in DANGEROUS_PATTERNS:
        if re.search(pattern, qr_lower, re.IGNORECASE):
            logger.warning(f"QR code bloqueado por padrão perigoso: {pattern}")
            raise ValueError("QR code contém conteúdo não permitido")
    
    # Verificar se contém apenas caracteres permitidos (básico)
    # Permitir letras, números, espaços, pontuação comum e caracteres de URL
    if not re.match(r'^[a-zA-Z0-9\s\-_./:?=&%#]+$', qr_text):
        # Se não passar, ainda pode ser válido se for uma URL ou chave numérica
        # Mas vamos ser mais permissivos aqui
        pass


def extract_key_or_url(qr_text: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Extrai chave de acesso ou URL do texto do QR code com validação de segurança.
    
    Args:
        qr_text: Texto do QR code
        
    Returns:
        Tupla (url, access_key) onde apenas um será não-None
        
    Raises:
        ValueError: Se não encontrar nem URL nem chave de acesso, ou se for inválido
    """
    # Sanitizar e validar
    sanitized = sanitize_qr_text(qr_text)
    validate_qr_text(sanitized)
    
    url = None
    access_key = None
    
    # Verificar se contém URL (http:// ou https://)
    url_pattern = r'https?://[^\s<>"\'{}|\\^`\[\]]+'
    url_match = re.search(url_pattern, sanitized)
    if url_match:
        url_candidate = url_match.group(0)
        
        # Validar URL
        try:
            parsed = urlparse(url_candidate)
            
            # Verificar tamanho
            if len(url_candidate) > MAX_URL_LENGTH:
                raise ValueError(f"URL muito longa (máximo {MAX_URL_LENGTH} caracteres)")
            
            # Verificar esquema
            if parsed.scheme not in ["http", "https"]:
                raise ValueError("URL deve usar http ou https")
            
            # Verificar host
            if not parsed.netloc:
                raise ValueError("URL inválida: sem host")
            
            url = url_candidate
            logger.debug(f"URL extraída do QR: {url[:50]}...")
            
        except Exception as e:
            logger.warning(f"URL inválida no QR: {e}")
            # Continuar para tentar extrair chave
    
    # Se não encontrou URL, buscar chave de acesso (exatamente 44 dígitos)
    if not url:
        key_pattern = r'^\d{44}$|(?<!\d)\d{44}(?!\d)'
        key_match = re.search(key_pattern, sanitized)
        if key_match:
            access_key_candidate = key_match.group(0)
            
            # Validar chave (deve ter exatamente 44 dígitos)
            if len(access_key_candidate) == MAX_ACCESS_KEY_LENGTH and access_key_candidate.isdigit():
                access_key = access_key_candidate
                logger.debug(f"Chave de acesso extraída do QR: {access_key[:10]}...")
            else:
                raise ValueError("Chave de acesso inválida (deve ter exatamente 44 dígitos)")
    
    if not url and not access_key:
        raise ValueError("QR code não contém URL válida nem chave de acesso (44 dígitos)")
    
    return url, access_key

