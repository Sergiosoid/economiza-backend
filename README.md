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

O endpoint `/api/v1/receipts/scan` utiliza um provider externo para buscar dados de notas fiscais.

### Variáveis de Ambiente

Configure as seguintes variáveis no `.env`:

```env
PROVIDER_NAME=webmania  # webmania | oobj | serpro
PROVIDER_API_URL=https://api.webmania.com.br/nfe
PROVIDER_API_KEY=<sua_key_aqui>
PROVIDER_TIMEOUT=8
```

### Providers Suportados

O sistema suporta os seguintes providers:
- **Webmania**: API para consulta de NFe/NFC-e
- **Oobj**: Solução de consulta de notas fiscais
- **Serpro**: API pública da Receita Federal

### Como Obter API Key

#### Webmania

1. Acesse: https://webmania.com.br
2. Crie uma conta ou faça login
3. Vá em **Dashboard** → **API** → **Chaves de API**
4. Gere uma nova chave de API
5. Copie a chave e cole no `.env`:
   ```env
   PROVIDER_NAME=webmania
   PROVIDER_API_URL=https://api.webmania.com.br/nfe
   PROVIDER_API_KEY=sua-chave-aqui
   ```

**Endpoint:** `GET /nfe/{chave}`  
**Header:** `Authorization: Bearer {API_KEY}`

#### Oobj

1. Acesse: https://oobj.com.br
2. Crie uma conta ou faça login
3. Vá em **Configurações** → **API** → **Tokens**
4. Gere um novo token de API
5. Copie o token e cole no `.env`:
   ```env
   PROVIDER_NAME=oobj
   PROVIDER_API_URL=https://api.oobj.com.br
   PROVIDER_API_KEY=seu-token-aqui
   ```

**Endpoint:** `POST /consulta`  
**Header:** `Authorization-Token: {TOKEN}`  
**Body:** `{"chave": "44_digitos"}`

#### Serpro

1. Acesse: https://www.gov.br/serpro
2. Crie uma conta no portal de desenvolvedores
3. Solicite acesso à API de consulta de NFe
4. Após aprovação, gere suas credenciais
5. Configure no `.env`:
   ```env
   PROVIDER_NAME=serpro
   PROVIDER_API_URL=https://api.serpro.gov.br/nfe
   PROVIDER_API_KEY=suas-credenciais-aqui
   ```

**Endpoint:** `GET /nfe/{chave}`  
**Header:** `Authorization: Bearer {CREDENTIALS}`

### Validação de URL (Anti-SSRF)

O sistema valida URLs para prevenir ataques SSRF. Apenas os seguintes hosts são permitidos:

- `*.fazenda.gov.br` (qualquer subdomínio)
- `nfe.fazenda.gov.br`
- `nfce.fazenda.gov.br`
- `www.fazenda.gov.br`

URLs de outros hosts serão bloqueadas automaticamente.

### Retries e Tratamento de Erros

O sistema implementa:

- **Retries exponenciais**: Até 3 tentativas com backoff exponencial (1s, 2s, 4s)
- **Tratamento de erros específicos**:
  - `404` → `ProviderNotFound` (nota não encontrada)
  - `429` → `ProviderRateLimit` (rate limit excedido)
  - `5xx` → `ProviderError` (erro do servidor, com retries)
- **Timeout configurável**: Padrão 8 segundos

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

Endpoint completo para escanear QR code de nota fiscal, consultar provider, parsear e salvar no banco.

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

**Exemplo de chamada com curl:**
```bash
curl -X POST "http://localhost:8000/api/v1/receipts/scan" \
  -H "Authorization: Bearer test-token" \
  -H "Content-Type: application/json" \
  -d '{
    "qr_text": "35200112345678901234567890123456789012345678"
  }'
```

**Responses:**

**200 OK - Receipt salvo com sucesso:**
```json
{
  "receipt_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "saved"
}
```

**400 Bad Request - QR code inválido:**
```json
{
  "detail": "invalid qr code"
}
```

**409 Conflict - Receipt já existe:**
```json
{
  "detail": "receipt already exists",
  "receipt_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

**500 Internal Server Error - Erro do provider:**
```json
{
  "detail": "provider error"
}
```

### Fluxo Completo

1. **Recebe qr_text** do app
2. **Extrai chave de acesso ou URL** usando regex
3. **Consulta provider externo** (ou retorna stub fake se não configurado)
4. **Parseia a nota** extraindo itens, loja, impostos, total
5. **Salva no banco**:
   - Cria/atualiza `receipts`
   - Cria/atualiza `products` (normalizados)
   - Cria `receipt_items`
6. **Retorna receipt_id** para o app

### Modo de Desenvolvimento (Sem Provider)

**Sem provider configurado** (deixe `PROVIDER_API_KEY` vazio), o sistema retorna dados fake para desenvolvimento:
- Loja: "SUPERMERCADO EXEMPLO"
- CNPJ: "12345678000100"
- Itens de exemplo (Arroz, Feijão, Açúcar)

Isso permite desenvolvimento e testes sem necessidade de credenciais reais.

### Modo de Produção (Com Provider)

**Com provider configurado**, o sistema:
- Faz requisição HTTP para o endpoint correto do provider
- Usa headers de autenticação específicos de cada provider
- Converte XML para dict automaticamente se necessário
- Faz retry (até 3x) com backoff exponencial em caso de erro
- Trata erros específicos (404, 429, 5xx) adequadamente

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
