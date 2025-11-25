"""
Parser para processar notas fiscais (NFC-e e NFe) em diferentes formatos
"""
import re
import logging
from datetime import datetime
from decimal import Decimal
from typing import Dict, Any, List

logger = logging.getLogger(__name__)


def parse_note(raw: Dict[str, Any]) -> Dict[str, Any]:
    """
    Parseia uma nota fiscal (XML ou JSON) e extrai os dados principais.
    Suporta formatos: Webmania/Oobj (retorno.produto), XML NFe/NFC-e, JSON fake.
    
    Args:
        raw: Dados brutos da nota (dict)
        
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
        
    Raises:
        ValueError: Se houver erro ao parsear ou validar os dados
    """
    # Verificar se é formato JSON fake (desenvolvimento)
    if "store" in raw and "total" in raw and "items" in raw:
        return _parse_fake_format(raw)
    
    # Verificar se é formato Webmania/Oobj (retorno.produto)
    if "retorno" in raw:
        return _parse_provider_format(raw)
    
    # Normalizar estrutura XML (pode vir em diferentes formatos)
    note_data = _normalize_structure(raw)
    
    # Extrair dados principais
    access_key = _extract_access_key(note_data)
    emitted_at = _extract_emitted_at(note_data)
    store_name = _extract_store_name(note_data)
    store_cnpj = _extract_store_cnpj(note_data)
    subtotal, total_value, total_tax = _extract_totals(note_data)
    items = _extract_items(note_data)
    
    # Validação
    if not access_key:
        raise ValueError("Chave de acesso não encontrada")
    if not emitted_at:
        raise ValueError("Data de emissão não encontrada")
    if not items:
        raise ValueError("Nenhum item encontrado na nota")
    
    return {
        "access_key": access_key,
        "emitted_at": emitted_at,
        "store_name": store_name or "Loja não identificada",
        "store_cnpj": store_cnpj,
        "subtotal": subtotal,
        "total_value": total_value,
        "total_tax": total_tax,
        "items": items,
    }


def _safe_decimal(value: Any) -> Decimal:
    """
    Converte valor para Decimal com segurança.
    """
    try:
        if value is None:
            return Decimal("0")
        if isinstance(value, Decimal):
            return value
        if isinstance(value, (int, float)):
            return Decimal(str(value))
        # Remover caracteres não numéricos exceto ponto e vírgula
        str_value = str(value).strip()
        str_value = str_value.replace(",", ".")
        # Remover tudo exceto números e ponto
        str_value = re.sub(r'[^\d.]', '', str_value)
        if not str_value:
            return Decimal("0")
        return Decimal(str_value)
    except Exception as e:
        logger.warning(f"Erro ao converter para Decimal: {value}, erro: {e}")
        return Decimal("0")


def _parse_provider_format(raw: Dict[str, Any]) -> Dict[str, Any]:
    """
    Parseia formato real do Webmania/Oobj:
    {
        "retorno": {
            "produto": [...],
            "emitente": {...},
            "chave": "...",
            "data_emissao": "..."
        }
    }
    """
    retorno = raw.get("retorno", {})
    
    if not retorno:
        raise ValueError("Formato de resposta do provider inválido: campo 'retorno' não encontrado")
    
    # Extrair chave de acesso
    access_key = retorno.get("chave") or retorno.get("chave_acesso") or ""
    if not access_key or len(str(access_key)) != 44:
        raise ValueError("Chave de acesso inválida ou não encontrada")
    
    # Extrair emitente
    emitente = retorno.get("emitente", {})
    store_name = emitente.get("razao_social") or emitente.get("nome") or "Loja não identificada"
    store_cnpj = emitente.get("cnpj") or emitente.get("CNPJ") or ""
    
    # Extrair data de emissão
    data_emissao_str = retorno.get("data_emissao") or retorno.get("dataEmissao") or retorno.get("dhEmi") or ""
    try:
        if data_emissao_str:
            if "T" in data_emissao_str:
                emitted_at = datetime.fromisoformat(data_emissao_str.replace("Z", "+00:00"))
            elif "/" in data_emissao_str:
                emitted_at = datetime.strptime(data_emissao_str, "%d/%m/%Y %H:%M:%S")
            else:
                emitted_at = datetime.fromisoformat(data_emissao_str)
        else:
            emitted_at = datetime.now()
    except Exception:
        emitted_at = datetime.now()
    
    # Extrair produtos
    produtos = retorno.get("produto", [])
    if not isinstance(produtos, list):
        produtos = [produtos] if produtos else []
    
    items = []
    subtotal = Decimal("0")
    total_tax = Decimal("0")
    
    for produto in produtos:
        try:
            descricao = str(produto.get("descricao") or produto.get("desc") or "Produto não identificado")
            
            # Converter valores para Decimal com segurança
            quantidade = _safe_decimal(produto.get("quantidade") or produto.get("qtd") or "1")
            valor_unitario = _safe_decimal(produto.get("valor_unitario") or produto.get("preco_unitario") or "0")
            valor_total = _safe_decimal(produto.get("valor_total") or produto.get("preco_total") or "0")
            valor_imposto = _safe_decimal(produto.get("valor_imposto") or produto.get("imposto") or "0")
            
            # Se valor_total não estiver presente, calcular
            if valor_total == 0 and quantidade > 0 and valor_unitario > 0:
                valor_total = quantidade * valor_unitario
            
            items.append({
                "description": descricao,
                "quantity": quantidade,
                "unit_price": valor_unitario,
                "total_price": valor_total,
                "tax_value": valor_imposto,
                "barcode": produto.get("codigo_barras") or produto.get("ean") or None
            })
            
            subtotal += valor_total
            total_tax += valor_imposto
            
        except Exception as e:
            logger.warning(f"Erro ao processar produto: {e}")
            continue
    
    if not items:
        raise ValueError("Nenhum produto encontrado na nota")
    
    # Calcular totais
    total_value = subtotal + total_tax
    
    # Se houver totais no retorno, usar eles
    if "total" in retorno:
        total_value = _safe_decimal(retorno.get("total") or retorno.get("valor_total") or total_value)
    
    return {
        "access_key": str(access_key),
        "emitted_at": emitted_at,
        "store_name": store_name,
        "store_cnpj": store_cnpj,
        "subtotal": subtotal,
        "total_value": total_value,
        "total_tax": total_tax,
        "items": items,
    }


def _parse_fake_format(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Parseia formato JSON fake usado em desenvolvimento"""
    store = raw.get("store", {})
    items = raw.get("items", [])
    
    # Converter items para formato padrão
    parsed_items = []
    for item in items:
        parsed_items.append({
            "description": str(item.get("description", "")),
            "quantity": Decimal(str(item.get("quantity", 1))),
            "unit_price": Decimal(str(item.get("unit_price", 0))),
            "total_price": Decimal(str(item.get("total_price", 0))),
            "tax_value": Decimal(str(item.get("tax_value", 0))),
        })
    
    # Parsear data
    emitted_at_str = raw.get("emitted_at", "")
    try:
        emitted_at = datetime.fromisoformat(emitted_at_str.replace("Z", "+00:00"))
    except:
        emitted_at = datetime.now()
    
    return {
        "access_key": str(raw.get("access_key", "")),
        "emitted_at": emitted_at,
        "store_name": store.get("name", "Loja não identificada"),
        "store_cnpj": store.get("cnpj"),
        "subtotal": Decimal(str(raw.get("subtotal", 0))),
        "total_value": Decimal(str(raw.get("total", 0))),
        "total_tax": Decimal(str(raw.get("tax", 0))),
        "items": parsed_items,
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
            if isinstance(value, str) and value.startswith("NFe"):
                value = value[3:]
            if len(str(value)) == 44:
                return str(value)
    
    return ""


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
                if isinstance(value, str):
                    if "T" in value:
                        return datetime.fromisoformat(value.replace("Z", "+00:00"))
                    if "/" in value:
                        return datetime.strptime(value, "%d/%m/%Y")
                return datetime.fromisoformat(str(value))
            except:
                continue
    
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
    
    return ""


def _extract_store_cnpj(data: Dict[str, Any]) -> str:
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
    
    if subtotal == 0:
        subtotal = total_value
    
    return subtotal, total_value, total_tax


def _extract_items(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Extrai os itens da nota"""
    items = []
    
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
        return items
    
    if not isinstance(det_list, list):
        det_list = [det_list]
    
    for det in det_list:
        try:
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
            
            tax_value = Decimal("0")
            if isinstance(det, dict):
                imp = det.get("imposto", {})
                if imp:
                    ipi = imp.get("IPI", {})
                    if ipi:
                        ipi_tot = ipi.get("IPITrib", {}) or ipi.get("IPINT", {})
                        if ipi_tot:
                            tax_value += Decimal(str(ipi_tot.get("vIPI", "0")))
                    
                    icms = imp.get("ICMS", {})
                    if isinstance(icms, dict):
                        icms_val = icms.get("vICMS", "0")
                        if icms_val:
                            tax_value += Decimal(str(icms_val))
            
            items.append({
                "description": str(description),
                "quantity": quantity,
                "unit_price": unit_price,
                "total_price": total_price,
                "tax_value": tax_value,
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
