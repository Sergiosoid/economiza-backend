# economiza-backend
Backend do Economiza (FastAPI + PostgreSQL)

## Configuração

1. Instale as dependências:
```bash
pip install -r requirements.txt
```

2. Configure as variáveis de ambiente:
```bash
cp .env.example .env
# Edite o arquivo .env com suas configurações
```

3. Configure o banco de dados PostgreSQL e atualize a `DATABASE_URL` no arquivo `.env`

4. Execute as migrações:
```bash
alembic upgrade head
```

5. Inicie o servidor:
```bash
uvicorn app.main:app --reload
```

A API estará disponível em `http://localhost:8000`

Documentação interativa: `http://localhost:8000/docs`

## Configuração do Provider de Notas Fiscais

O endpoint `/api/v1/receipts/scan` utiliza um provider externo para buscar dados de notas fiscais. Configure as seguintes variáveis no `.env`:

- `PROVIDER_API_URL`: URL base da API do provider (ex: `https://api.webmania.com.br/v1`)
- `PROVIDER_API_KEY`: Chave de API do provider
- `PROVIDER_TIMEOUT`: Timeout em segundos (padrão: 5)

### Providers Suportados

O sistema foi projetado para funcionar com providers como:
- **Webmania**: API para consulta de NFe/NFC-e
- **Serpro**: API pública da Receita Federal
- **Oobj**: Solução de consulta de notas fiscais

### Exemplo de Resposta Esperada do Provider

O provider deve retornar dados em formato XML ou JSON. Exemplo de estrutura esperada:

**XML (convertido para dict):**
```xml
<nfeProc>
  <NFe>
    <infNFe Id="NFe35200112345678901234567890123456789012345678">
      <ide>
        <dhEmi>2024-01-15T10:30:00-03:00</dhEmi>
      </ide>
      <emit>
        <xNome>Nome da Loja</xNome>
        <CNPJ>12345678000190</CNPJ>
      </emit>
      <total>
        <ICMSTot>
          <vProd>100.00</vProd>
          <vNF>120.00</vNF>
          <vTotTrib>20.00</vTotTrib>
        </ICMSTot>
      </total>
      <det>
        <prod>
          <xProd>Produto Exemplo</xProd>
          <qCom>1.000</qCom>
          <vUnCom>100.00</vUnCom>
          <vProd>100.00</vProd>
        </prod>
      </det>
    </infNFe>
  </NFe>
</nfeProc>
```

**JSON:**
```json
{
  "access_key": "35200112345678901234567890123456789012345678",
  "emitted_at": "2024-01-15T10:30:00-03:00",
  "store_name": "Nome da Loja",
  "store_cnpj": "12345678000190",
  "total_value": 120.00,
  "subtotal": 100.00,
  "total_tax": 20.00,
  "items": [...]
}
```

## Endpoint de Scan de Receipts

### POST `/api/v1/receipts/scan`

Endpoint para escanear QR code de nota fiscal e salvar no banco.

**Autenticação:**
- Header: `Authorization: Bearer <token>`
- Por enquanto, aceita qualquer token (stub para testes)
- TODO: Implementar autenticação JWT real

**Request:**
```json
{
  "qr_text": "35200112345678901234567890123456789012345678"
}
```

**Responses:**
- `200 OK`: Receipt salvo com sucesso
- `400 Bad Request`: Erro de validação (QR inválido, etc)
- `409 Conflict`: Receipt já existe (idempotência)
- `500 Internal Error`: Erro ao processar

## Criptografia de Dados Sensíveis

Os campos `raw_qr_text` e `xml_raw` são criptografados antes de serem salvos no banco de dados.

**Atual:** Usa base64 (temporário para desenvolvimento)

**TODO:** Implementar criptografia real usando KMS (AWS KMS, Azure Key Vault, etc.)

## Testes

Execute os testes com:
```bash
pytest tests/
```

Para executar apenas os testes de scan:
```bash
pytest tests/test_scan.py -v
```

## Estrutura do Projeto

```
app/
├── config.py              # Configurações e variáveis de ambiente
├── database.py            # Configuração SQLAlchemy
├── dependencies.py        # Dependências FastAPI (auth, etc)
├── main.py               # Aplicação FastAPI principal
├── models/               # Modelos SQLAlchemy
├── routers/              # Routers FastAPI
├── schemas/              # Schemas Pydantic
├── services/             # Lógica de negócio
│   ├── provider_client.py    # Cliente para providers externos
│   ├── receipt_parser.py      # Parser de notas fiscais
│   └── receipt_service.py     # Service para gerenciar receipts
└── utils/                # Utilitários (criptografia, etc)
```
