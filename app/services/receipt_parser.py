"""
Parser para processar notas fiscais (NFC-e e NFe) em diferentes formatos
"""
import re
import logging
from datetime import datetime
from decimal import Decimal
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


def parse_note(raw: Dict[str, Any] | str) -> Dict[str, Any]:
    """
    Parseia uma nota fiscal (XML ou JSON) e extrai os dados principais.
    
    Args:
        raw: Dados brutos da nota (dict ou string XML)
        
    Returns:
        dict com os dados parseados:
        {
            "access_key": str,
            "emitted_at": datetime,
            "store_name": str,
            "store_cnpj": str,
            "subtotal": Decimal,
            "total_value": Decimal,
            "total_tax": Decimal,
            "items": List[Dict]
        }
    """
    # Se for string, tentar parsear como XML
    if isinstance(raw, str):
        try:
            import xmltodict
            raw = xmltodict.parse(raw)
        except:
            raise ValueError("Não foi possível parsear o formato da nota")
    
    # Normalizar estrutura (pode vir em diferentes formatos)
    note_data = _normalize_structure(raw)
    
    # Extrair dados principais
    access_key = _extract_access_key(note_data)
    emitted_at = _extract_emitted_at(note_data)
    store_name = _extract_store_name(note_data)
    store_cnpj = _extract_store_cnpj(note_data)
    subtotal, total_value, total_tax = _extract_totals(note_data)
    items = _extract_items(note_data)
    
    return {
        "access_key": access_key,
        "emitted_at": emitted_at,
        "store_name": store_name,
        "store_cnpj": store_cnpj,
        "subtotal": subtotal,
        "total_value": total_value,
        "total_tax": total_tax,
        "items": items,
    }


def _normalize_structure(data: Dict[str, Any]) -> Dict[str, Any]:
    """Normaliza a estrutura do XML/JSON para um formato comum"""
    # Tentar diferentes caminhos comuns
    if "nfeProc" in data:
        return data["nfeProc"]
    if "NFe" in data:
        return data["NFe"]
    if "nfe" in data:
        return data["nfe"]
    if "infNFe" in data:
        return data["infNFe"]
    return data


def _extract_access_key(data: Dict[str, Any]) -> str:
    """Extrai a chave de acesso da nota"""
    # Tentar diferentes caminhos
    paths = [
        ["@Id"],
        ["infNFe", "@Id"],
        ["ide", "chNFe"],
        ["chave"],
        ["access_key"],
    ]
    
    for path in paths:
        value = _get_nested_value(data, path)
        if value:
            # Remover prefixo "NFe" se existir
            if isinstance(value, str) and value.startswith("NFe"):
                value = value[3:]
            if len(value) == 44:
                return value
    
    raise ValueError("Chave de acesso não encontrada")


def _extract_emitted_at(data: Dict[str, Any]) -> datetime:
    """Extrai a data de emissão"""
    paths = [
        ["ide", "dhEmi"],
        ["ide", "dEmi"],
        ["emitted_at"],
        ["dataEmissao"],
    ]
    
    for path in paths:
        value = _get_nested_value(data, path)
        if value:
            try:
                # Tentar diferentes formatos de data
                if isinstance(value, str):
                    # Formato ISO com timezone
                    if "T" in value:
                        return datetime.fromisoformat(value.replace("Z", "+00:00"))
                    # Formato brasileiro
                    if "/" in value:
                        return datetime.strptime(value, "%d/%m/%Y")
                return datetime.fromisoformat(str(value))
            except:
                continue
    
    # Se não encontrar, usar data atual
    logger.warning("Data de emissão não encontrada, usando data atual")
    return datetime.now()


def _extract_store_name(data: Dict[str, Any]) -> str:
    """Extrai o nome da loja"""
    paths = [
        ["emit", "xNome"],
        ["emit", "xFant"],
        ["store_name"],
        ["nomeEmitente"],
    ]
    
    for path in paths:
        value = _get_nested_value(data, path)
        if value:
            return str(value)
    
    return "Loja não identificada"


def _extract_store_cnpj(data: Dict[str, Any]) -> Optional[str]:
    """Extrai o CNPJ da loja"""
    paths = [
        ["emit", "CNPJ"],
        ["emit", "cnpj"],
        ["store_cnpj"],
        ["cnpjEmitente"],
    ]
    
    for path in paths:
        value = _get_nested_value(data, path)
        if value:
            return str(value)
    
    return None


def _extract_totals(data: Dict[str, Any]) -> tuple[Decimal, Decimal, Decimal]:
    """Extrai totais (subtotal, total, impostos)"""
    paths_total = [
        ["total", "ICMSTot", "vNF"],
        ["total", "ICMSTot", "vProd"],
        ["total", "vNF"],
        ["total_value"],
        ["valorTotal"],
    ]
    
    paths_subtotal = [
        ["total", "ICMSTot", "vProd"],
        ["total", "vProd"],
        ["subtotal"],
        ["valorProdutos"],
    ]
    
    paths_tax = [
        ["total", "ICMSTot", "vTotTrib"],
        ["total", "ICMSTot", "vIPI"],
        ["total", "vTotTrib"],
        ["total_tax"],
        ["valorImpostos"],
    ]
    
    total_value = Decimal("0")
    subtotal = Decimal("0")
    total_tax = Decimal("0")
    
    for path in paths_total:
        value = _get_nested_value(data, path)
        if value:
            total_value = Decimal(str(value))
            break
    
    for path in paths_subtotal:
        value = _get_nested_value(data, path)
        if value:
            subtotal = Decimal(str(value))
            break
    
    for path in paths_tax:
        value = _get_nested_value(data, path)
        if value:
            total_tax = Decimal(str(value))
            break
    
    # Se subtotal não foi encontrado, usar total_value
    if subtotal == 0:
        subtotal = total_value
    
    return subtotal, total_value, total_tax


def _extract_items(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Extrai os itens da nota"""
    items = []
    
    # Tentar diferentes caminhos para os itens
    det_paths = [
        ["det"],
        ["dets", "det"],
        ["items"],
        ["produtos"],
    ]
    
    det_list = None
    for path in det_paths:
        det_list = _get_nested_value(data, path)
        if det_list:
            break
    
    if not det_list:
        logger.warning("Nenhum item encontrado na nota")
        return items
    
    # Normalizar para lista
    if not isinstance(det_list, list):
        det_list = [det_list]
    
    for det in det_list:
        try:
            # Extrair dados do produto
            prod = det.get("prod", {}) if isinstance(det, dict) else {}
            
            description = (
                prod.get("xProd") or
                prod.get("descricao") or
                det.get("description") or
                "Produto não identificado"
            )
            
            quantity = Decimal(str(prod.get("qCom", prod.get("quantidade", "1"))))
            unit_price = Decimal(str(prod.get("vUnCom", prod.get("precoUnitario", "0"))))
            total_price = Decimal(str(prod.get("vProd", prod.get("valorTotal", "0"))))
            
            # Calcular impostos
            tax_value = Decimal("0")
            if isinstance(det, dict):
                imp = det.get("imposto", {})
                if imp:
                    # IPI
                    ipi = imp.get("IPI", {})
                    if ipi:
                        ipi_tot = ipi.get("IPITrib", {}) or ipi.get("IPINT", {})
                        if ipi_tot:
                            tax_value += Decimal(str(ipi_tot.get("vIPI", "0")))
                    
                    # ICMS
                    icms = imp.get("ICMS", {})
                    if isinstance(icms, dict):
                        icms_val = icms.get("vICMS", "0")
                        if icms_val:
                            tax_value += Decimal(str(icms_val))
            
            barcode = (
                prod.get("cEAN") or
                prod.get("cBarra") or
                prod.get("barcode") or
                None
            )
            
            items.append({
                "description": str(description),
                "quantity": quantity,
                "unit_price": unit_price,
                "total_price": total_price,
                "tax_value": tax_value,
                "barcode": str(barcode) if barcode else None,
            })
        except Exception as e:
            logger.warning(f"Erro ao processar item: {e}")
            continue
    
    return items


def _get_nested_value(data: Dict[str, Any], path: List[str]) -> Any:
    """Obtém valor aninhado de um dict usando caminho"""
    current = data
    for key in path:
        if isinstance(current, dict):
            current = current.get(key)
        else:
            return None
        if current is None:
            return None
    return current

