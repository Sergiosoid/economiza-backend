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

## Autenticação

### Para Testes Locais

O backend aceita um token de teste para desenvolvimento:

**Header:** `Authorization: Bearer test`

Ou simplesmente: `Authorization: test`

O sistema aceita variações:
- `Authorization: Bearer test` (padrão)
- `Authorization: bearer test` (case-insensitive)
- `Authorization: test` (sem esquema Bearer)

### Usando o Swagger (OpenAPI)

1. Acesse `http://localhost:8000/docs`
2. Clique no botão **"Authorize"** (canto superior direito)
3. No campo de autenticação, digite: `Bearer test`
4. Clique em **"Authorize"**
5. Agora você pode testar todos os endpoints autenticados diretamente no Swagger

**Nota:** Em produção, o token "test" será rejeitado. A validação JWT real será implementada no futuro.

## Configuração do Provider de Notas Fiscais

O endpoint `/api/v1/receipts/scan` utiliza um provider externo para buscar dados de notas fiscais.

### Variáveis de Ambiente

Configure as seguintes variáveis no `.env`:

```env
PROVIDER_NAME=webmania  # webmania | oobj | serpro
PROVIDER_API_URL=https://api.webmania.com.br/2/nfce/consulta
PROVIDER_APP_KEY=<sua_app_key_aqui>
PROVIDER_APP_SECRET=<sua_app_secret_aqui>
PROVIDER_TIMEOUT=10
WHITELIST_DOMAINS=  # Domínios adicionais permitidos (separados por vírgula)
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
3. Vá em **Dashboard** → **API** → **Credenciais**
4. Gere suas credenciais de API (App Key e App Secret)
5. Copie as credenciais e cole no `.env`:
   ```env
   PROVIDER_NAME=webmania
   PROVIDER_API_URL=https://api.webmania.com.br/2/nfce/consulta
   PROVIDER_APP_KEY=sua-app-key-aqui
   PROVIDER_APP_SECRET=sua-app-secret-aqui
   PROVIDER_TIMEOUT=10
   ```

**Endpoint:** `GET /2/nfce/consulta/{chave}`  
**Headers:**
- `app_key: {PROVIDER_APP_KEY}`
- `app_secret: {PROVIDER_APP_SECRET}`

**Formato de Resposta:**
```json
{
  "retorno": {
    "chave": "35200112345678901234567890123456789012345678",
    "data_emissao": "2024-04-12T15:33:00-03:00",
    "emitente": {
      "razao_social": "SUPERMERCADO EXEMPLO LTDA",
      "cnpj": "12345678000100"
    },
    "produto": [
      {
        "descricao": "ARROZ TIPO 1 5KG",
        "quantidade": "1.000",
        "valor_unitario": "25.50",
        "valor_total": "25.50",
        "valor_imposto": "1.20"
      }
    ],
    "total": "125.30"
  }
}
```

**Como Testar com Chave Real:**

1. Obtenha uma chave de acesso real de uma NFC-e (44 dígitos)
2. Configure as credenciais no `.env`
3. Teste via API:
   ```bash
   curl -X POST http://localhost:8000/api/v1/receipts/scan \
     -H "Authorization: Bearer <token>" \
     -H "Content-Type: application/json" \
     -d '{"qr_text": "35200112345678901234567890123456789012345678"}'
   ```
4. Ou teste diretamente o provider:
   ```python
   from app.services.provider_client import ProviderClient
   client = ProviderClient()
   result = client.fetch_by_key("35200112345678901234567890123456789012345678")
   ```

#### Oobj

1. Acesse: https://oobj.com.br
2. Crie uma conta ou faça login
3. Vá em **Configurações** → **API** → **Credenciais**
4. Gere suas credenciais (App Key e App Secret)
5. Copie as credenciais e cole no `.env`:
   ```env
   PROVIDER_NAME=oobj
   PROVIDER_API_URL=https://api.oobj.com.br/2/nfce/consulta
   PROVIDER_APP_KEY=sua-app-key-aqui
   PROVIDER_APP_SECRET=sua-app-secret-aqui
   ```

**Endpoint:** `GET /2/nfce/consulta/{chave}`  
**Headers:**
- `app_key: {PROVIDER_APP_KEY}`
- `app_secret: {PROVIDER_APP_SECRET}`

**Formato de Resposta:** Mesmo formato do Webmania

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
  - `401/403` → `ProviderUnauthorized` (erro de autenticação)
  - `404` → `ProviderNotFound` (nota não encontrada)
  - `429` → `ProviderRateLimit` (rate limit excedido)
  - `5xx` → `ProviderError` (erro do servidor, com retries)
- **Timeout configurável**: Padrão 10 segundos
- **Validação de chave**: Verifica se chave tem 44 dígitos
- **Processamento de erros do provider**: Detecta campo "erro" nas respostas JSON

### Formato de Resposta do Provider

O sistema suporta dois formatos principais:

#### 1. Formato Webmania/Oobj (JSON)

```json
{
  "retorno": {
    "chave": "35200112345678901234567890123456789012345678",
    "data_emissao": "2024-04-12T15:33:00-03:00",
    "emitente": {
      "razao_social": "SUPERMERCADO EXEMPLO LTDA",
      "cnpj": "12345678000100"
    },
    "produto": [
      {
        "descricao": "ARROZ TIPO 1 5KG",
        "quantidade": "1.000",
        "valor_unitario": "25.50",
        "valor_total": "25.50",
        "valor_imposto": "1.20",
        "codigo_barras": "7891234567890"
      }
    ],
    "total": "125.30",
    "subtotal": "119.00",
    "total_impostos": "6.30"
  }
}
```

#### 2. Formato XML (NFe/NFC-e padrão)

O sistema também suporta XML convertido para dict:

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
- Header: `Authorization: Bearer test` (para testes locais)
- Também aceita: `Authorization: test` (sem Bearer)
- Case-insensitive: `Authorization: bearer test` funciona
- Em produção, tokens diferentes de "test" serão rejeitados até implementação JWT

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

### 🔧 DEV_REAL_MODE (Modo de Testes Realista)

O `DEV_REAL_MODE` é um modo especial de desenvolvimento que permite testar o sistema com dados fake mesmo quando um provider real está configurado. Isso é útil para:

- **Desenvolvimento local**: Testar funcionalidades sem fazer requisições reais aos providers
- **Testes automatizados**: Garantir que os testes não dependam de APIs externas
- **Debugging**: Isolar problemas sem depender de serviços externos
- **CI/CD**: Executar pipelines sem credenciais de produção

#### Como Funciona

Quando `DEV_REAL_MODE=true`:
- O sistema **ignora** o provider configurado (`PROVIDER_NAME`)
- Sempre retorna dados fake através do método `_get_fake_data()`
- Não faz requisições HTTP reais aos providers
- Valida chaves de acesso (44 dígitos) mas usa dados simulados

#### Ativação/Desativação

**Ativar DEV_REAL_MODE:**

Adicione ao arquivo `.env`:
```env
DEV_REAL_MODE=true
PROVIDER_NAME=fake  # ou qualquer outro provider
DEV_MODE=true
```

**Desativar DEV_REAL_MODE:**

```env
DEV_REAL_MODE=false
# ou simplesmente remova a variável
```

#### Comportamento

**Com `DEV_REAL_MODE=true`:**
- ✅ Retorna dados fake mesmo com `PROVIDER_NAME=webmania`
- ✅ Não faz requisições HTTP reais
- ✅ Valida formato de chave (44 dígitos)
- ✅ Usa chave padrão se chave inválida for fornecida
- ✅ Permite desenvolvimento sem credenciais reais

**Com `DEV_REAL_MODE=false` ou não definido:**
- ✅ Usa provider real se `PROVIDER_NAME` estiver configurado
- ✅ Faz requisições HTTP reais aos providers
- ✅ Requer credenciais válidas (`PROVIDER_APP_KEY`, `PROVIDER_APP_SECRET`)
- ✅ Retorna dados fake apenas se `PROVIDER_NAME=fake`

#### Limitações

- **Dados sempre fake**: Não retorna dados reais de notas fiscais
- **Não testa integração real**: Não valida se credenciais do provider estão corretas
- **Não testa rate limits**: Não verifica limites de requisições dos providers
- **Não testa erros reais**: Não simula erros específicos dos providers (404, 429, etc.)

#### Quando Usar

**Use `DEV_REAL_MODE=true` quando:**
- Desenvolvendo funcionalidades locais
- Executando testes automatizados
- Debugging sem depender de APIs externas
- Em ambientes CI/CD sem credenciais

**Use `DEV_REAL_MODE=false` quando:**
- Testando integração real com providers
- Validando credenciais de API
- Testando rate limits e erros
- Preparando para produção

#### Trocar para Provider Real

Para usar o provider real após desenvolvimento:

1. **Desative DEV_REAL_MODE:**
   ```env
   DEV_REAL_MODE=false
   ```

2. **Configure credenciais reais:**
   ```env
   PROVIDER_NAME=webmania
   PROVIDER_API_URL=https://api.webmania.com.br/2/nfce/consulta
   PROVIDER_APP_KEY=sua-app-key-real
   PROVIDER_APP_SECRET=sua-app-secret-real
   ```

3. **Reinicie o servidor:**
   ```bash
   uvicorn app.main:app --reload
   ```

4. **Teste com chave real:**
   ```bash
   curl -X POST http://localhost:8000/api/v1/receipts/scan \
     -H "Authorization: Bearer test" \
     -H "Content-Type: application/json" \
     -d '{"qr_text": "35200112345678901234567890123456789012345678"}'
   ```

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

## Integração com Stripe (Pagamentos)

O sistema suporta assinaturas PRO através do Stripe Checkout.

### Configuração

1. Crie uma conta no [Stripe](https://stripe.com)
2. Obtenha suas chaves de API (teste ou produção)
3. Crie um produto e preço no Stripe Dashboard
4. Configure o webhook no Stripe Dashboard

### Variáveis de Ambiente

Adicione ao `.env`:

```env
STRIPE_SECRET_KEY=sk_test_...
STRIPE_PUBLISHABLE_KEY=pk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...
STRIPE_PRICE_ID_PRO=price_...
FRONTEND_URL=http://localhost:3000
```

### Como Obter as Chaves

1. **Secret Key e Publishable Key:**
   - Acesse: https://dashboard.stripe.com/test/apikeys
   - Copie a "Secret key" e "Publishable key"
   - Use chaves de teste (`sk_test_` e `pk_test_`) para desenvolvimento

2. **Price ID:**
   - Crie um produto no Stripe Dashboard
   - Adicione um preço (recurring para assinatura)
   - Copie o Price ID (começa com `price_`)

3. **Webhook Secret:**
   - Acesse: https://dashboard.stripe.com/test/webhooks
   - Clique em "Add endpoint"
   - URL: `https://seu-dominio.com/api/v1/payments/webhook`
   - Selecione eventos: `checkout.session.completed`, `customer.subscription.updated`, `customer.subscription.deleted`
   - Copie o "Signing secret" (começa com `whsec_`)

### Endpoints

#### POST `/api/v1/payments/create-checkout-session`
Cria uma sessão de checkout do Stripe.

**Query Parameters:**
- `plan`: Plano a assinar (padrão: "pro")

**Response:**
```json
{
  "checkout_url": "https://checkout.stripe.com/...",
  "session_id": "cs_test_..."
}
```

#### POST `/api/v1/payments/webhook`
Webhook do Stripe para processar eventos de assinatura.

**Headers:**
- `stripe-signature`: Assinatura do Stripe

**Eventos processados:**
- `checkout.session.completed`: Marca usuário como PRO
- `customer.subscription.updated`: Atualiza status da assinatura
- `customer.subscription.deleted`: Remove status PRO

#### GET `/api/v1/payments/subscription-status`
Retorna o status da assinatura do usuário.

**Response:**
```json
{
  "is_pro": true,
  "subscription_id": "sub_...",
  "plan": "pro"
}
```

### Frontend (React Native)

Exemplo de integração:

```typescript
// Criar sessão de checkout
const response = await fetch(`${API_BASE}/api/v1/payments/create-checkout-session?plan=pro`, {
  method: 'POST',
  headers: {
    'Authorization': `Bearer ${token}`,
    'Content-Type': 'application/json'
  }
});

const { checkout_url } = await response.json();

// Abrir Stripe Checkout no navegador
import { Linking } from 'react-native';
await Linking.openURL(checkout_url);
```

### Modo de Teste

Use cartões de teste do Stripe:
- Cartão de sucesso: `4242 4242 4242 4242`
- Data de validade: qualquer data futura
- CVC: qualquer 3 dígitos
- CEP: qualquer CEP válido

## Docker

### Desenvolvimento com Docker Compose

1. **Inicie os serviços:**
```bash
docker-compose up -d
```

2. **Execute as migrações:**
```bash
docker-compose exec backend alembic upgrade head
```

3. **Acesse a API:**
- API: http://localhost:8000
- Docs: http://localhost:8000/docs
- PostgreSQL: localhost:5432
- Redis: localhost:6379

4. **Parar os serviços:**
```bash
docker-compose down
```

5. **Ver logs:**
```bash
docker-compose logs -f backend
```

### Build da imagem Docker

```bash
docker build -t economiza-backend .
docker run -p 8000:8000 --env-file .env economiza-backend
```

## Deploy

### Opções de Deploy

O Economiza pode ser deployado em várias plataformas:

- **Render** (recomendado para começar)
- **Railway** (alternativa simples)
- **AWS/GCP/Azure** (para produção em escala)

### Deploy no Render

#### Pré-requisitos

1. Conta no [Render](https://render.com)
2. Repositório no GitHub
3. Banco de dados PostgreSQL (pode ser criado no Render)

### Passo a Passo

1. **Criar Web Service:**
   - Acesse: https://dashboard.render.com
   - Clique em "New" → "Web Service"
   - Conecte seu repositório GitHub
   - Configure:
     - **Name:** `economiza-backend`
     - **Environment:** `Docker`
     - **Region:** Escolha a região mais próxima
     - **Branch:** `main`
     - **Root Directory:** `economiza-backend` (se o backend estiver em subdiretório)

2. **Configurar Variáveis de Ambiente:**
   - Vá em "Environment" no dashboard do serviço
   - Adicione todas as variáveis do `.env.example`:
     ```
     DATABASE_URL=postgresql://user:password@host:5432/dbname
     REDIS_URL=redis://host:6379/0
     CELERY_BROKER_URL=redis://host:6379/0
     CELERY_RESULT_BACKEND=redis://host:6379/0
     STRIPE_SECRET_KEY=sk_live_...
     STRIPE_PUBLISHABLE_KEY=pk_live_...
     STRIPE_WEBHOOK_SECRET=whsec_...
     STRIPE_PRICE_ID_PRO=price_...
     FRONTEND_URL=https://seu-frontend.com
     ENCRYPTION_KEY=...
     PROVIDER_NAME=webmania
     PROVIDER_API_URL=...
     PROVIDER_API_KEY=...
     ```

3. **Criar PostgreSQL Database:**
   - Clique em "New" → "PostgreSQL"
   - Configure nome e região
   - Copie a `DATABASE_URL` interna (Render fornece automaticamente)
   - Use essa URL nas variáveis de ambiente do Web Service

4. **Criar Redis Instance (opcional, se não usar Redis do Render):**
   - Clique em "New" → "Redis"
   - Configure nome e região
   - Copie a URL e use nas variáveis de ambiente

5. **Configurar Build Command:**
   - No Web Service, vá em "Settings" → "Build Command"
   - Deixe vazio (Docker build automático) ou:
     ```bash
     docker build -t economiza-backend .
     ```

6. **Configurar Start Command:**
   - No Web Service, vá em "Settings" → "Start Command"
   - Use:
     ```bash
     sh -c "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port $PORT"
     ```
   - **Nota:** Render define `$PORT` automaticamente

7. **Deploy:**
   - Render fará deploy automático a cada push em `main`
   - Ou clique em "Manual Deploy" → "Deploy latest commit"

### Configurar Celery Worker (Opcional)

1. **Criar Background Worker:**
   - Clique em "New" → "Background Worker"
   - Conecte o mesmo repositório
   - Configure:
     - **Name:** `economiza-celery`
     - **Environment:** `Docker`
     - **Root Directory:** `economiza-backend`

2. **Start Command:**
   ```bash
   celery -A celery_worker worker --loglevel=info
   ```

3. **Variáveis de Ambiente:**
   - Use as mesmas do Web Service

### Health Checks

Render verifica automaticamente o endpoint `/health`:
- Certifique-se de que está funcionando
- Configure timeout adequado (padrão: 30s)

### Custom Domain

1. Vá em "Settings" → "Custom Domains"
2. Adicione seu domínio
3. Configure DNS conforme instruções do Render

### Monitoramento

- **Logs:** Acesse "Logs" no dashboard
- **Metrics:** Render fornece métricas básicas
- **Alerts:** Configure alertas para downtime

### Deploy no Railway

#### Pré-requisitos

1. Conta no [Railway](https://railway.app)
2. Repositório no GitHub
3. Cartão de crédito (para serviços pagos)

#### Passo a Passo

1. **Criar Projeto:**
   - Acesse: https://railway.app
   - Clique em "New Project"
   - Selecione "Deploy from GitHub repo"
   - Conecte seu repositório

2. **Adicionar PostgreSQL:**
   - No projeto, clique em "+ New"
   - Selecione "Database" → "PostgreSQL"
   - Railway cria automaticamente e fornece `DATABASE_URL`

3. **Adicionar Redis:**
   - Clique em "+ New"
   - Selecione "Database" → "Redis"
   - Railway cria automaticamente e fornece `REDIS_URL`

4. **Configurar Serviço:**
   - Railway detecta automaticamente o Dockerfile
   - Configure variáveis de ambiente:
     - Use as variáveis do PostgreSQL e Redis criados
     - Adicione todas as outras do `.env.example`

5. **Deploy:**
   - Railway faz deploy automático a cada push em `main`
   - Acesse a URL fornecida pelo Railway

#### Variáveis de Ambiente no Railway

Railway fornece automaticamente:
- `DATABASE_URL` (do PostgreSQL)
- `REDIS_URL` (do Redis)

Você precisa adicionar manualmente:
- `STRIPE_SECRET_KEY`
- `STRIPE_PUBLISHABLE_KEY`
- `STRIPE_WEBHOOK_SECRET`
- `STRIPE_PRICE_ID_PRO`
- `ENCRYPTION_KEY`
- `PROVIDER_APP_KEY`
- `PROVIDER_APP_SECRET`
- `FRONTEND_URL`
- Outras variáveis do `.env.example`

## Testes

Execute os testes com:
```bash
pytest tests/
```

Para executar apenas os testes de scan:
```bash
pytest tests/test_scan.py -v
```

Para executar os testes de pagamento:
```bash
pytest tests/test_payments.py -v
```

### Testes com Docker

```bash
docker-compose exec backend pytest tests/ -v
```

## Analytics

O sistema fornece endpoints de analytics para análise de gastos e comparação de preços.

### Endpoints

#### GET `/api/v1/analytics/monthly-summary`

Retorna resumo mensal de gastos do usuário.

**Query Parameters:**
- `year`: Ano (ex: 2024)
- `month`: Mês (1-12)
- `use_cache`: Usar cache se disponível (padrão: true)

**Response:**
```json
{
  "total_mes": 1250.50,
  "total_por_categoria": {
    "Alimentos": 850.30,
    "Bebidas": 200.20,
    "Limpeza": 200.00
  },
  "top_10_itens": [
    {
      "description": "ARROZ TIPO 1 5KG",
      "total_quantity": 4.0,
      "total_spent": 102.00,
      "purchase_count": 2
    },
    {
      "description": "FEIJAO PRETO 1KG",
      "total_quantity": 6.0,
      "total_spent": 51.00,
      "purchase_count": 3
    }
  ],
  "variacao_vs_mes_anterior": 15.5,
  "month": "2024-04"
}
```

**Exemplo de uso:**
```bash
GET /api/v1/analytics/monthly-summary?year=2024&month=4
Authorization: Bearer <token>
```

#### GET `/api/v1/analytics/top-items`

Retorna os itens mais comprados pelo usuário.

**Query Parameters:**
- `limit`: Número máximo de itens (padrão: 20, máximo: 100)

**Response:**
```json
{
  "items": [
    {
      "description": "ARROZ TIPO 1 5KG",
      "total_quantity": 12.0,
      "total_spent": 306.00,
      "avg_price": 25.50,
      "purchase_count": 5
    },
    {
      "description": "FEIJAO PRETO 1KG",
      "total_quantity": 10.0,
      "total_spent": 85.00,
      "avg_price": 8.50,
      "purchase_count": 4
    }
  ],
  "count": 2
}
```

**Exemplo de uso:**
```bash
GET /api/v1/analytics/top-items?limit=20
Authorization: Bearer <token>
```

#### GET `/api/v1/analytics/compare-store`

Compara preços de um produto em diferentes supermercados.

**Query Parameters:**
- `product_id`: ID do produto (UUID)

**Response:**
```json
{
  "product_id": "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11",
  "product_name": "arroz tipo branco",
  "preco_medio_por_supermercado": [
    {
      "store_name": "SUPERMERCADO A",
      "avg_price": 24.50,
      "min_price": 23.00,
      "max_price": 26.00,
      "purchase_count": 5
    },
    {
      "store_name": "SUPERMERCADO B",
      "avg_price": 25.80,
      "min_price": 24.50,
      "max_price": 27.00,
      "purchase_count": 3
    }
  ],
  "menor_preco_encontrado": 23.00,
  "loja_menor_preco": "SUPERMERCADO A",
  "total_comparacoes": 2
}
```

**Exemplo de uso:**
```bash
GET /api/v1/analytics/compare-store?product_id=a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11
Authorization: Bearer <token>
```

### Cache

Os resultados de `monthly-summary` são cacheados automaticamente por mês para melhor performance. O cache é armazenado na tabela `analytics_cache` e é atualizado quando novos dados são processados.

### Otimizações

- **Queries otimizadas**: Usa GROUP BY e agregações SQL nativas
- **Índices**: Aproveita índices em `user_id`, `emitted_at`, `product_id`
- **Cache**: Resultados mensais são cacheados para evitar recálculos
- **Lazy loading**: Relacionamentos são carregados apenas quando necessário

## CI/CD (GitHub Actions)

O projeto inclui workflow do GitHub Actions que executa:

1. **Testes:** Executa pytest em cada push/PR
2. **Lint:** Verifica código com flake8
3. **Build:** Constrói imagem Docker e publica no GitHub Container Registry

### Workflow

O workflow está em `.github/workflows/ci.yml` e executa:
- Testes com PostgreSQL e Redis como serviços
- Lint com flake8
- Build e push da imagem Docker (apenas em push para main)

### Verificar Status

- Acesse: `https://github.com/seu-usuario/economiza-backend/actions`
- Veja o status de cada commit

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
