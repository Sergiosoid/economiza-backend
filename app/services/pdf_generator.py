"""
PDF Generator Service - Gera PDFs de relatórios de sincronização
"""
import logging
from io import BytesIO
from decimal import Decimal
from datetime import datetime
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from app.models.shopping_list_execution import ShoppingListExecution

logger = logging.getLogger(__name__)


def generate_sync_pdf(execution: ShoppingListExecution) -> bytes:
    """
    Gera PDF de uma execução de sincronização.
    
    Args:
        execution: ShoppingListExecution com dados da sincronização
        
    Returns:
        bytes do PDF gerado
    """
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=2*cm, leftMargin=2*cm, topMargin=2*cm, bottomMargin=2*cm)
    
    # Estilos
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=18,
        textColor=colors.HexColor('#1a1a1a'),
        spaceAfter=30,
        alignment=TA_CENTER
    )
    
    # Conteúdo
    story = []
    
    # Título
    story.append(Paragraph("Relatório de Compra — Economiza", title_style))
    story.append(Spacer(1, 0.5*cm))
    
    # Informações gerais
    info_data = [
        ['Data da Sincronização', execution.created_at.strftime('%d/%m/%Y %H:%M')],
        ['Lista de Compras', str(execution.shopping_list_id)],
        ['Nota Fiscal', str(execution.receipt_id)],
    ]
    
    info_table = Table(info_data, colWidths=[6*cm, 10*cm])
    info_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#f5f5f5')),
        ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
        ('TOPPADDING', (0, 0), (-1, -1), 12),
        ('GRID', (0, 0), (-1, -1), 1, colors.grey),
    ]))
    story.append(info_table)
    story.append(Spacer(1, 1*cm))
    
    # Resumo financeiro
    summary = execution.summary.get('summary', {}) if execution.summary else {}
    
    summary_data = [
        ['Resumo Financeiro', ''],
        ['Total Planejado', f"R$ {summary.get('planned_total', 0):.2f}" if summary.get('planned_total') else 'N/A'],
        ['Total Real', f"R$ {summary.get('real_total', 0):.2f}"],
        ['Diferença', f"R$ {summary.get('difference', 0):.2f}" if summary.get('difference') else 'N/A'],
        ['Diferença Percentual', f"{summary.get('difference_percent', 0):.2f}%" if summary.get('difference_percent') else 'N/A'],
    ]
    
    summary_table = Table(summary_data, colWidths=[8*cm, 8*cm])
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#4a90e2')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 11),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
        ('TOPPADDING', (0, 0), (-1, -1), 10),
        ('GRID', (0, 0), (-1, -1), 1, colors.grey),
    ]))
    story.append(summary_table)
    story.append(Spacer(1, 1*cm))
    
    # Itens
    items = execution.summary.get('items', []) if execution.summary else []
    
    if items:
        story.append(Paragraph("Itens Comparados", styles['Heading2']))
        story.append(Spacer(1, 0.3*cm))
        
        # Cabeçalho da tabela de itens
        items_header = [
            'Descrição',
            'Qtd Planejada',
            'Qtd Real',
            'Preço Unit.',
            'Total Real',
            'Status'
        ]
        
        items_data = [items_header]
        
        for item in items:
            status_text = item.get('status', 'N/A')
            # Traduzir status para português
            status_map = {
                'PLANNED_AND_MATCHED': 'OK',
                'PLANNED_NOT_PURCHASED': 'Não Comprado',
                'PURCHASED_NOT_PLANNED': 'Extra',
                'PRICE_HIGHER_THAN_EXPECTED': 'Preço Alto',
                'PRICE_LOWER_THAN_EXPECTED': 'Preço Baixo',
                'QUANTITY_DIFFERENT': 'Qtd Diferente'
            }
            status_text = status_map.get(status_text, status_text)
            
            items_data.append([
                item.get('description', 'N/A')[:40],  # Limitar tamanho
                f"{item.get('planned_quantity', 0):.2f}" if item.get('planned_quantity') else 'N/A',
                f"{item.get('real_quantity', 0):.2f}" if item.get('real_quantity') else 'N/A',
                f"R$ {item.get('real_unit_price', 0):.2f}" if item.get('real_unit_price') else 'N/A',
                f"R$ {item.get('real_total', 0):.2f}" if item.get('real_total') else 'N/A',
                status_text
            ])
        
        items_table = Table(items_data, colWidths=[5*cm, 2*cm, 2*cm, 2.5*cm, 2.5*cm, 2*cm])
        items_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#4a90e2')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('ALIGN', (1, 1), (4, -1), 'RIGHT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('FONTSIZE', (0, 1), (-1, -1), 9),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 1, colors.grey),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f9f9f9')]),
        ]))
        story.append(items_table)
    
    # Gerar PDF
    doc.build(story)
    buffer.seek(0)
    pdf_bytes = buffer.read()
    buffer.close()
    
    logger.info(f"PDF gerado para execução {execution.id}: {len(pdf_bytes)} bytes")
    
    return pdf_bytes

